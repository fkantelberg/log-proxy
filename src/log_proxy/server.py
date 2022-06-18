import asyncio
import json
import logging
import os
import ssl
from asyncio import StreamReader, StreamWriter
from asyncio.exceptions import IncompleteReadError
from typing import List

from . import forwarders, utils

_logger = logging.getLogger()


RequiredFields = ("level", "pid", "message", "created_at", "created_by")


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
        forwarder: forwarders.Forwarder,
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
        self.forwarder = forwarder

    def add_token(self, token: str, **kwargs) -> None:
        """Add a token and store additional information about the client"""
        if self.token_file:
            raise LogTokenFileError("Token file is used")

        self.tokens[token] = kwargs

    def delete_token(self, token: str) -> dict:
        """Delete a token from the storage. It's not possible if a token_file is used"""
        if self.token_file:
            raise LogTokenFileError("Token file is used")

        return self.tokens.pop(token, None)

    def _update_tokens(self) -> None:
        """Update the token store if the file changed"""
        if not self.token_file:
            return

        stat = os.stat(self.token_file)
        if self.token_mtime != stat.st_mtime:
            with open(self.token_file) as fp:
                self.tokens = json.load(fp)

    def auth_client(self, auth: dict) -> dict:
        """Evaluate the auth message and return the fitting client"""
        if not isinstance(auth, dict):
            return None

        token = auth.get("token")
        if not token:
            return None

        self._update_tokens()
        client = self.tokens.get(token)
        if client is None:
            return None

        client["name"] = client.get("name", token)
        return client

    async def _read_message(self, reader: StreamReader) -> dict:
        """Read a message from the reader and evaluate it"""
        try:
            (length,) = await utils.receive_struct(reader, ">L")
            if length <= 0:
                return None

            message = json.loads(await reader.readexactly(length))
            return message
        except (json.JSONDecodeError, IncompleteReadError):
            return None

    def _validate_message(self, message: dict, required: List[str]) -> dict:
        """Validate a message against a list of required keys"""
        if not isinstance(message, dict):
            return None

        return message if set(message).issuperset(required) else None

    async def _process_message(self, message: dict, client_name: str = None) -> None:
        """Forward the log to the next server or database"""
        if not message.get("host") and client_name:
            message["host"] = client_name

        _logger.debug(f"Forwarding: {message}")
        await self.forwarder.put(message)

    async def _stop(self, reader: StreamReader, writer: StreamWriter) -> None:
        """Stop the reader and writer"""
        reader.feed_eof()
        writer.close()
        await writer.wait_closed()

    async def _accept(self, reader: StreamReader, writer: StreamWriter) -> None:
        """Accept new clients and wait for logs to process them"""
        if self.use_auth:
            message = await self._read_message(reader)
            message = self._validate_message(message, ["token"])
            client = self.auth_client(message)

            if not client:
                await self._stop(reader, writer)
                return

            name = client["name"]
            _logger.info(f"Client '{name}' connected")
        else:
            client = {}
            name = None

        while True:
            message = await self._read_message(reader)
            data = self._validate_message(message, RequiredFields)
            if not isinstance(data, dict):
                break

            await self._process_message(data, name)

        await self._stop(reader, writer)

    async def run(self) -> None:
        """Start the server and listen for logs"""
        if self.forwarder:
            _logger.info(f"Starting forwarder to {self.forwarder}")
            asyncio.create_task(self.forwarder.process())

        _logger.info(f"Starting log server on {self.host}:{self.port}")
        self.sock = await asyncio.start_server(
            self._accept,
            self.host,
            self.port,
            ssl=self.ssl_context,
        )

        async with self.sock:
            await self.sock.serve_forever()

    def start(self) -> None:
        """Start the log server as asyncio task"""
        asyncio.run(self.run())

    async def stop(self) -> None:
        """Stop the LogServer and close the socket"""
        self.sock.close()
        await self.sock.wait_closed()
