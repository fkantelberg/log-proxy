import asyncio
import logging
import socket
import uuid
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
    server = LogServer("127.0.0.1", unused_tcp_port, use_auth=False)
    server.run = AsyncMock()
    server.start()
    server.run.assert_called_once()


@pytest.mark.asyncio
async def test_server(unused_tcp_port, null_handler):
    server = LogServer("127.0.0.1", unused_tcp_port, use_auth=False)
    # Start the server
    asyncio.create_task(server.run())
    null_handler.handle = MagicMock()

    # Connect a handler to the server
    json_handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)
    await asyncio.sleep(0.1)

    # Send a normal log
    record = logging.makeLogRecord({"msg": "hello", "levelno": logging.INFO})
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


@pytest.mark.asyncio
async def test_server_token(unused_tcp_port, null_handler):
    token = str(uuid.uuid4())
    server = LogServer("127.0.0.1", unused_tcp_port, use_auth=True)
    server.add_token(token, name="test-client")
    # Start the server
    asyncio.create_task(server.run())
    null_handler.handle = MagicMock()

    # Connect a handler to the server
    json_handler = JSONSocketHandler("127.0.0.1", unused_tcp_port, token=token)
    await asyncio.sleep(0.1)

    # Send a normal log
    record = logging.makeLogRecord({"msg": "hello", "levelno": logging.INFO})
    json_handler.handle(record)
    await asyncio.sleep(0.1)
    null_handler.handle.assert_called_once()

    await server.stop()


@pytest.mark.asyncio
async def test_server_token_invalid(unused_tcp_port, null_handler):
    server = LogServer("127.0.0.1", unused_tcp_port)
    # Start the server
    asyncio.create_task(server.run())
    null_handler.handle = MagicMock()

    record = logging.makeLogRecord({"msg": "hello", "levelno": logging.INFO})

    # Connect a handler to the server
    json_handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)
    json_handler.handle(record)
    await asyncio.sleep(0.1)

    # Connect a handler to the server
    json_handler = JSONSocketHandler("127.0.0.1", unused_tcp_port)
    json_handler.handle(record)
    await asyncio.sleep(0.1)

    # Send wrong data length should be silent
    sock = socket.socket()
    sock.connect(("127.0.0.1", unused_tcp_port))
    sock.send(b"\x00\x00\x00\x00")
    await asyncio.sleep(0.1)

    sock = socket.socket()
    sock.connect(("127.0.0.1", unused_tcp_port))
    sock.send(b"\x00\x00\x00\x01{")
    await asyncio.sleep(0.1)

    sock = socket.socket()
    sock.connect(("127.0.0.1", unused_tcp_port))
    sock.send(b"\x00\x00\x00\x02{}")
    await asyncio.sleep(0.1)

    null_handler.handle.assert_not_called()
    await server.stop()
