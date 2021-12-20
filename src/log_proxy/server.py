import asyncio
import json
import logging
import struct

_logger = logging.getLogger()


class LogServer:
    """Logging server which can accept logs from the JSONSocketHandler. Received
    logs are passed to the standard python log. This allows to pass the logs further
    with other logging handlers."""

    def __init__(self, host, port, ssl_context=None, token=None):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.token = token
        self.loggers = {}

    async def _read_log_data(self, reader):
        """Read a log entry from a JSONSocketHandler"""
        size = struct.calcsize(">L")

        try:
            datalen = struct.unpack(">L", await reader.readexactly(size))[0]
            if datalen <= 0:
                return False

            return json.loads(await reader.readexactly(datalen))
        except Exception:
            return False

    async def _read_token(self, reader):
        """Read a log entry from a JSONSocketHandler"""
        size = struct.calcsize(">L")

        try:
            datalen = struct.unpack(">L", await reader.readexactly(size))[0]
            if datalen <= 0:
                return False

            data = json.loads(await reader.readexactly(datalen))

            return data["token"] == self.token
        except Exception:
            return False

    def _log_record(self, data):
        """Send the data to the log"""
        record = logging.makeLogRecord(data)
        _logger.handle(record)

    async def _accept(self, reader, writer):
        """Accept new clients and wait for logs to process them"""

        running = not self.token or await self._read_token(reader)
        while running:
            data = await self._read_log_data(reader)
            if not isinstance(data, dict):
                break

            self._log_record(data)

        reader.feed_eof()
        writer.close()
        await writer.wait_closed()

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
