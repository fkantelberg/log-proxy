import json
import socket
import struct
from logging.handlers import SocketHandler


class JSONSocketHandler(SocketHandler):
    def __init__(self, host, port, *, uuid=None, ssl_context=None, token=None):
        super().__init__(host, port)
        self.ssl_context = ssl_context
        self.token = token
        self.uuid = uuid or socket.gethostname()

    def _convert_json(self, data):
        data = json.dumps(data)
        datalen = struct.pack(">L", len(data))
        return datalen + data.encode()

    def makeSocket(self, timeout=1):
        """Wrap the socket with a SSL context if passed"""
        sock = super().makeSocket(timeout)

        if self.ssl_context:
            return self.ssl_context.wrap_socket(sock, server_side=True)

        if self.token:
            sock.send(self._convert_json({"token": self.token}))

        return sock

    def makePickle(self, record):
        """Use json instead of pickle to prevent code execution"""
        if record.exc_info:
            self.format(record)

        data = dict(record.__dict__)
        data.update(
            {
                "msg": record.getMessage(),
                "args": None,
                "exc_info": None,
                "name": f"{self.uuid}~{record.name}",
            }
        )
        data.pop("message", None)
        return self._convert_json(data)
