import asyncio
import json
import logging
import socket
from logging import NullHandler
from unittest.mock import AsyncMock, MagicMock

import pytest

from log_proxy import JSONSocketHandler, LogServer


@pytest.fixture
def null_handler():
    logger = logging.getLogger()
    handler = NullHandler()
    logger.addHandler(handler)
    return handler


def test_server_start(unused_tcp_port):
    server = LogServer("127.0.0.1", unused_tcp_port)
    server.run = AsyncMock()
    server.start()
    server.run.assert_called_once()


@pytest.mark.asyncio
async def test_server(unused_tcp_port, null_handler):
    server = LogServer("127.0.0.1", unused_tcp_port)
    # Start the server
    asyncio.create_task(server.run())
    null_handler.handle = MagicMock()

    # Connect a handler to the server
    json_handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)

    await asyncio.sleep(0.1)

    # Send a normal log
    record = logging.makeLogRecord({"msg": "hello"})
    json_handler.handle(record)
    await asyncio.sleep(0.1)
    null_handler.handle.assert_called_once()

    # Send wrong data length should be silent
    null_handler.handle.reset_mock()
    sock = socket.socket()
    sock.connect(("127.0.0.1", unused_tcp_port))
    sock.send(b"\x00\x00\x00\x00")
    await asyncio.sleep(0.1)
    null_handler.handle.assert_not_called()

    # Send invalid JSON should be silent
    sock = socket.socket()
    sock.connect(("127.0.0.1", unused_tcp_port))
    sock.send(b"\x00\x00\x00\x01{")
    await asyncio.sleep(0.1)
    null_handler.handle.assert_not_called()

    await server.stop()


def test_json_handler_socket(unused_tcp_port):
    sock = socket.socket()

    sock.bind(("", unused_tcp_port))
    sock.listen()

    handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)

    assert isinstance(handler.makeSocket(), socket.socket)

    # Force the SSL wrapping of the socket
    handler.ssl_context = MagicMock()
    handler.makeSocket()
    handler.ssl_context.wrap_socket.assert_called_once()
    args, kwargs = handler.ssl_context.wrap_socket.call_args
    assert any(isinstance(arg, socket.socket) for arg in args)
    assert kwargs["server_side"] is True


def test_json_handler_pickle():
    record = logging.makeLogRecord({"msg": "hello"})
    record.exc_info = (None, None, None)

    handler = JSONSocketHandler("127.0.0.1", 0)
    ret = handler.makePickle(record)
    ret = json.loads(ret[4:].decode())
    assert ret["msg"] == "hello"
