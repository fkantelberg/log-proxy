import json
import logging
import socket
from unittest.mock import MagicMock

from log_proxy.handlers import JSONSocketHandler


def test_json_handler_socket(unused_tcp_port):
    sock = socket.socket()
    sock.bind(("127.0.0.1", unused_tcp_port))
    sock.listen()

    handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)

    assert isinstance(handler.makeSocket(), socket.socket)

    handler.ssl_context = MagicMock()
    # Force the SSL wrapping of the socket
    handler.makeSocket()
    handler.ssl_context.wrap_socket.assert_called_once()
    args, kwargs = handler.ssl_context.wrap_socket.call_args
    assert any(isinstance(arg, socket.socket) for arg in args)
    assert kwargs["server_side"] is True


def test_json_handler_token(unused_tcp_port):
    sock = socket.socket()
    sock.bind(("127.0.0.1", unused_tcp_port))
    sock.listen()

    handler = JSONSocketHandler("127.0.0.1", unused_tcp_port, token="hello")

    handler._convert_json = MagicMock(return_value=b"it works")

    handler.makeSocket()
    handler._convert_json.assert_called_once_with({"token": "hello"})


def test_convert_json(unused_tcp_port):
    sock = socket.socket()
    sock.bind(("127.0.0.1", unused_tcp_port))
    sock.listen()

    handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)
    assert (
        handler._convert_json({"token": "hello"})
        == b'\x00\x00\x00\x12{"token": "hello"}'
    )


def test_json_handler_pickle():
    record = logging.makeLogRecord({"msg": "hello"})
    record.exc_info = (None, None, None)

    handler = JSONSocketHandler("127.0.0.1", 0)
    ret = handler.makePickle(record)
    ret = json.loads(ret[4:].decode())
    assert ret["message"] == "hello"
