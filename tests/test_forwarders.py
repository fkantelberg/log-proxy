import asyncio
import socket
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from log_proxy import forwarders


@pytest.mark.asyncio
async def test_forwarder_base():
    forwarder = forwarders.Forwarder(max_size=2)
    assert isinstance(forwarder.queue, asyncio.Queue)
    assert str(forwarder) == "<forwarder>"

    # These function shouldn't raise anything
    await forwarder.process_message({})
    forwarder.invalidate()

    # Test the queue and overflow it with messages
    assert forwarder.empty()
    await forwarder.put({"a": 42})
    await forwarder.put({"a": 43})
    await forwarder.put({"a": 44})

    assert not forwarder.empty()
    assert await forwarder.get() == {"a": 43}
    assert await forwarder.get() == {"a": 44}
    assert forwarder.empty()

    # Process the queue
    forwarder.queue.get = AsyncMock(side_effect=[(0, 0, {"a": 42}), AssertionError()])
    forwarder.invalidate = MagicMock(side_effect=[AssertionError()])
    forwarder.process_message = AsyncMock()

    with pytest.raises(AssertionError):
        await forwarder.process()

    forwarder.process_message.assert_called_once_with({"a": 42})


@pytest.mark.asyncio
async def test_forwarder_database():
    forwarder = forwarders.DatabaseForwarder(host=None, port=42)
    assert forwarder.args == {"port": 42}


@pytest.mark.asyncio
async def test_forwarder_mongo():
    forwarder = forwarders.MongoDBForwarder(database="db", host=None, port=42)
    assert forwarder.args == {"port": 42}
    assert str(forwarder) == "<forwarder mongo:logs>"

    # Test the connected
    assert not forwarder.connected()
    forwarder.client = MagicMock()
    assert forwarder.connected()
    forwarder.invalidate()
    assert not forwarder.connected()

    # Test connection and message processing
    with patch("log_proxy.forwarders.MongoClient") as mock:
        await forwarder.connect()
        mock.assert_called_once_with(**forwarder.args)

        msg = {"message": "hello"}
        await forwarder.process_message(msg)
        forwarder.client["db"]["logs"].insert_one.assert_called_once_with(msg)


@pytest.mark.asyncio
async def test_forwarder_postgres():
    # Postgres is special and use peer auth if no host is specified
    forwarder = forwarders.PostgresForwarder(database="db")
    assert forwarder.args == {"database": "db", "host": None}

    # Postgres is special and use peer auth if no host is specified
    forwarder = forwarders.PostgresForwarder(database="db", host="127.0.0.1")
    assert forwarder.args == {"database": "db", "host": "127.0.0.1"}
    assert str(forwarder) == "<forwarder postgres:logs>"

    # Test the connected
    assert not forwarder.connected()
    forwarder.connection = MagicMock()
    assert forwarder.connected()
    forwarder.invalidate()
    assert not forwarder.connected()

    # Test connection and message processing
    with patch("log_proxy.forwarders.pg_connect", new_callable=AsyncMock) as mock:
        await forwarder.connect()
        mock.assert_called_once_with(**forwarder.args)

        exc = forwarder.connection.execute
        assert exc.call_count == 4
        assert "CREATE TABLE" in exc.call_args_list[0][0][0]
        for call in exc.call_args_list[1:]:
            assert "CREATE INDEX" in call[0][0]

        msg = {
            "message": "hello",
            "level": 42,
            "pid": 123,
            "created_at": datetime.now().isoformat(),
            "created_by": "me",
        }
        exc.reset_mock()
        await forwarder.process_message(msg)
        assert "INSERT INTO" in exc.call_args[0][0]
        assert len(exc.call_args.args) == 10


@pytest.mark.asyncio
async def test_forwarder_socket(unused_tcp_port):
    sock = socket.socket()
    sock.bind(("127.0.0.1", unused_tcp_port))
    sock.listen()

    forwarder = forwarders.SocketForwarder("127.0.0.1", unused_tcp_port, token="abc")
    assert str(forwarder) == f"<forwarder 127.0.0.1:{unused_tcp_port}>"

    # Test the connected
    assert not forwarder.connected()
    await forwarder.connect()
    assert forwarder.connected()

    # Read and check the token
    conn = sock.accept()[0]
    assert conn.recv(1024) == b'\x00\x00\x00\x10{"token": "abc"}'

    await forwarder.process_message({"a": 42})
    assert conn.recv(1024) == b'\x00\x00\x00\x09{"a": 42}'

    forwarder.invalidate()
    assert not forwarder.connected()
