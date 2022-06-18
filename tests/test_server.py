import asyncio
import json
from asyncio.exceptions import IncompleteReadError
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from log_proxy import LogServer, LogTokenFileError, SocketForwarder
from log_proxy.server import RequiredFields


def test_server_start(unused_tcp_port):
    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock(), use_auth=False)
    server.run = AsyncMock()
    server.start()
    server.run.assert_called_once()


@pytest.mark.asyncio
async def test_server_stop(unused_tcp_port):
    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock(), use_auth=False)

    reader, writer = AsyncMock(), AsyncMock()
    reader.feed_eof = feed_eof = MagicMock()
    writer.close = close = MagicMock()
    await server._stop(reader, writer)

    feed_eof.assert_called_once()
    close.assert_called_once()
    writer.wait_closed.assert_called_once()

    server.sock = AsyncMock()
    server.sock.close = MagicMock()
    await server.stop()
    server.sock.close.assert_called_once()
    server.sock.wait_closed.assert_called_once()


@pytest.mark.asyncio
async def test_server_token_file(unused_tcp_port):
    tokens = {"abc": {}, "def": {"name": "def"}}

    with NamedTemporaryFile("w+") as fp:
        json.dump(tokens, fp)
        fp.flush()
        fp.seek(0)

        server = LogServer(
            "127.0.0.1",
            unused_tcp_port,
            AsyncMock(),
            token_file=fp.name,
            use_auth=True,
        )

        assert server.tokens == {}
        server._update_tokens()
        assert server.tokens == tokens

        tokens["def"]["name"] = "hello"
        assert server.tokens != tokens
        json.dump(tokens, fp)
        fp.flush()

        server._update_tokens()
        assert server.tokens == tokens
        assert server.tokens["def"]["name"] == "hello"

        with pytest.raises(LogTokenFileError):
            server.add_token("abc")

        assert server.tokens == tokens

        with pytest.raises(LogTokenFileError):
            server.delete_token("abc")

        assert server.tokens == tokens

        # Remove the token file and check if no updates comes in
        server.token_file = None
        tokens["def"]["name"] = "abc"
        fp.seek(0)
        json.dump(tokens, fp)
        fp.flush()
        server._update_tokens()
        assert server.tokens != tokens


@pytest.mark.asyncio
async def test_server_token_management(unused_tcp_port):
    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock(), use_auth=True)

    assert server.tokens == {}
    server.add_token("abc", name="hello")
    assert server.tokens == {"abc": {"name": "hello"}}
    server.delete_token("def")
    assert server.tokens
    server.delete_token("abc")
    assert server.tokens == {}


def test_server_auth(unused_tcp_port):
    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock(), use_auth=True)
    server.tokens = {"abc": {}, "def": {"name": "me"}}

    assert server.auth_client(None) is None
    assert server.auth_client({}) is None
    assert server.auth_client({"token": "b"}) is None
    assert server.auth_client({"token": "abc"}) == {"name": "abc"}
    assert server.auth_client({"token": "def"}) == {"name": "me"}


@pytest.mark.asyncio
async def test_server_reading(unused_tcp_port):
    message = {
        "level": 42,
        "pid": 123,
        "message": "hello",
        "created_at": 0,
        "created_by": "me",
    }

    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock(), use_auth=True)
    reader = AsyncMock()
    reader.readexactly = AsyncMock(
        side_effect=[
            b"\x00\x00\x00\x00",
            b"\x00\x00\x00\x02",
            b"{}",
            b"\x00\x00\x00\x12",
            json.dumps(message).encode(),
            json.JSONDecodeError("", "", 0),
            IncompleteReadError("", ""),
        ]
    )

    assert await server._read_message(reader) is None
    assert await server._read_message(reader) == {}
    assert reader.readexactly.call_count == 3
    reader.readexactly.reset_mock()
    assert await server._read_message(reader) == message
    assert reader.readexactly.call_args_list == [call(4), call(18)]
    assert await server._read_message(reader) is None
    assert await server._read_message(reader) is None

    assert server._validate_message(message, RequiredFields) == message
    message.pop("pid", None)
    assert server._validate_message(message, RequiredFields) is None
    assert server._validate_message(None, RequiredFields) is None


@pytest.mark.asyncio
async def test_server_processing(unused_tcp_port):
    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock())
    message = {"abc": "hello"}
    await server._process_message(message)
    server.forwarder.put.assert_called_once_with(message)
    server.forwarder.put.reset_mock()

    await server._process_message(message, "remote")
    server.forwarder.put.assert_called_once_with({**message, "host": "remote"})
    server.forwarder.put.reset_mock()

    message["host"] = "rem"
    await server._process_message(message, "remote")
    server.forwarder.put.assert_called_once_with({**message, "host": "rem"})
    server.forwarder.put.reset_mock()


@pytest.mark.asyncio
async def test_server(unused_tcp_port):
    message = {
        "level": 42,
        "pid": 123,
        "message": "hello",
        "created_at": 0,
        "created_by": "me",
    }

    server = LogServer("127.0.0.1", unused_tcp_port, AsyncMock())
    server.add_token("abc", name="client")

    asyncio.create_task(server.run())
    await asyncio.sleep(0.1)

    client = SocketForwarder("127.0.0.1", unused_tcp_port, token="abc")

    await client.connect()
    assert client.connected()

    # Process a valid message and transfer
    await client.process_message(message)
    await asyncio.sleep(0.1)

    # The host is set to the client name specified above
    message["host"] = "client"
    server.forwarder.put.assert_called_once_with(message)
    server.forwarder.put.reset_mock()

    # Process an invalid message closes the connection
    await client.process_message({})
    await asyncio.sleep(0.1)

    with pytest.raises(ConnectionResetError):
        await client.process_message({})
    server.forwarder.put.assert_not_called()

    # Client with invalid token shouldn't be able to connect
    client.token = "invalid"
    await client.connect()
    await asyncio.sleep(0.1)

    with pytest.raises(ConnectionResetError):
        await client.process_message({})
    server.forwarder.put.assert_not_called()

    # Disable auth on server side. Client will still send token message but it's
    # an invalid message for the server. breaking the connection
    server.use_auth = False
    await client.connect()
    await asyncio.sleep(0.1)
    with pytest.raises(ConnectionResetError):
        await client.process_message({})

    server.forwarder.put.assert_not_called()

    await server.stop()
    await asyncio.sleep(0.1)
