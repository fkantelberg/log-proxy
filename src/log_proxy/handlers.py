import json
import logging
import socket
import ssl
import struct
from datetime import datetime
from logging.handlers import SocketHandler


class JSONSocketHandler(SocketHandler):
    """Logging handler to send the log via a socket to a server in JSON format"""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        ssl_context: ssl.SSLContext = None,
        token: str = None,
    ):
        super().__init__(host, port)
        self.ssl_context = ssl_context
        self.token = token

    def _convert_json(self, data: dict) -> bytes:
        """Convert the data to a simple byte representation"""
        data = json.dumps(data)
        datalen = struct.pack(">L", len(data))
        return datalen + data.encode()

    def makeSocket(self, timeout: float = 1) -> socket.socket:
        """Wrap the socket with a SSL context if passed"""
        sock = super().makeSocket(timeout)

        if self.ssl_context:
            return self.ssl_context.wrap_socket(sock, server_side=True)

        # Send the token for authorization
        if self.token:
            sock.send(self._convert_json({"token": self.token}))

        return sock

    def makePickle(self, record: logging.LogRecord) -> bytes:
        """Use json instead of pickle to prevent code execution"""
        if record.exc_info:
            self.format(record)

        data = {
            "level": record.levelno,
            "pid": record.process,
            "created_at": datetime.fromtimestamp(record.created).isoformat(" "),
            "created_by": record.name,
            "message": record.getMessage(),
            "exception": record.exc_text,
            "path": record.pathname,
            "lineno": record.lineno,
        }
        return self._convert_json(data)
