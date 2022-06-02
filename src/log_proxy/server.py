import asyncio
import json
import logging
import os
import ssl
from asyncio.exceptions import IncompleteReadError

from . import utils

_logger = logging.getLogger()


class LogTokenFileError(Exception):
    pass


class LogServer:
    """Logging server which can accept logs from the JSONSocketHandler. Received
    logs are passed to the standard python log. This allows to pass the logs further
    with other logging handlers."""

    def __init__(
        self,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext = None,
        token_file: str = None,
        use_auth: bool = True,
    ):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.use_auth = use_auth
        self.tokens = {}
        self.token_file = token_file
        self.token_mtime = None
        self.loggers = {}

    def add_token(self, token: str, **kwargs):
        """Add a token and store additional information about the client"""
        if self.token_file:
            raise LogTokenFileError("Token file is used")

        self.tokens[token] = kwargs

    def delete_token(self, token):
        if self.token_file:
            raise LogTokenFileError("Token file is used")

        return self.tokens.pop(token, None)

    def _update_tokens(self):
        """Update the token store if the file changed"""
        if not self.token_file:
            return

        stat = os.stat(self.token_file)
        if self.token_mtime != stat.st_mtime:
            with open(self.token_file) as fp:
                self.tokens = json.load(fp)

    def auth_client(self, auth):
        if not isinstance(auth, dict):
            return None

        token = auth.get("token")
        if not token:
            return None

        return token

    async def _read_json(self, reader):
        try:
            (length,) = await utils.receive_struct(reader, ">L")
            if length <= 0:
                return None

            return json.loads(await reader.readexactly(length))
        except (json.JSONDecodeError, IncompleteReadError):
            return None

    def _log_record(self, data, client_name=None):
        """Forward the log to the default logging stream"""

        if client_name:
            data["name"] = f"{client_name} > {data['name']}"

        record = logging.makeLogRecord(data)
        _logger.handle(record)

    async def _stop(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        reader.feed_eof()
        writer.close()
        await writer.wait_closed()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Accept new clients and wait for logs to process them"""

        if self.use_auth:
            token = self.auth_client(await self._read_json(reader))

            self._update_tokens()
            client = self.tokens.get(token)
            if not client:
                await self._stop(reader, writer)
                return

            name = client.get("name", token)
            if name:
                _logger.info(f"Client '{name}' connected")
        else:
            client = {}
            name = None

        while True:
            data = await self._read_json(reader)
            if not isinstance(data, dict):
                break

            self._log_record(data, name)

        await self._stop(reader, writer)

    async def run(self):
        """Start the server and listen for logs"""
        _logger.info(f"Starting log server on {self.host}:{self.port}")
        self.sock = await asyncio.start_server(
            self._accept,
            self.host,
            self.port,
            ssl=self.ssl_context,
        )

        async with self.sock:
            await self.sock.serve_forever()

    def start(self):
        """Start the log server as asyncio task"""
        asyncio.run(self.run())

    async def stop(self):
        """Stop the LogServer and close the socket"""
        self.sock.close()
        await self.sock.wait_closed()
