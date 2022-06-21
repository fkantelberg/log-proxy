import asyncio
import json
import ssl
import struct

from .base import Forwarder


class SocketForwarder(Forwarder):
    """Forwards messages to a log server"""

    def __init__(
        self,
        host,
        port,
        *,
        ssl_context: ssl.SSLContext = None,
        token: str = None,
        max_size: int = 0,
    ):
        super().__init__(max_size)

        self.host, self.port = host, port
        self.ssl_context = ssl_context
        self.token = token
        self.reader = self.writer = None

    def __repr__(self):
        return f"<forwarder {self.host}:{self.port}>"

    def invalidate(self) -> None:
        """Invalidate the connection of the forwarder"""
        self.reader = self.writer = None

    def connected(self) -> bool:
        """Return if the forwarder is properly connected"""
        return self.writer is not None

    async def connect(self) -> None:
        """Connect the forwarder to the server"""
        self.reader, self.writer = await asyncio.open_connection(
            self.host,
            self.port,
            ssl=self.ssl_context,
        )

        if self.token:
            await self.process_message({"token": self.token})

    async def process_message(self, message: dict) -> None:
        """Process a single message"""
        data = json.dumps(message)
        self.writer.write(struct.pack(">L", len(data)))
        self.writer.write(data.encode())
        await self.writer.drain()
