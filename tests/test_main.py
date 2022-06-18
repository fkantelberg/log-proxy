from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from log_proxy import SocketForwarder
from log_proxy.__main__ import main, parser_watcher, run_server


@patch("log_proxy.__main__.JSONSocketHandler")
@patch("log_proxy.utils.generate_ssl_context")
@patch("log_proxy.utils.stdin_to_log", new_callable=AsyncMock)
@patch("log_proxy.__main__.configure")
def test_client(conf_mock, stdin_mock, ssl_mock, handler_mock, unused_tcp_port):
    main(["client", "--forward", f"localhost:{unused_tcp_port}", "--log-stdin"])
    ssl_mock.assert_not_called()
    stdin_mock.assert_called_once()
    handler_mock.assert_called_once()

    stdin_mock.reset_mock()
    handler_mock.reset_mock()

    with NamedTemporaryFile() as fp:
        main(
            [
                "client",
                "--forward",
                f"localhost:{unused_tcp_port}",
                "--log-stdin",
                "--forward-ca",
                fp.name,
            ]
        )
    ssl_mock.assert_called_once()
    stdin_mock.assert_called_once()
    handler_mock.assert_called_once()
    assert handler_mock.call_args.kwargs["ssl_context"] == ssl_mock.return_value


@patch("log_proxy.__main__.JSONSocketHandler")
@patch("log_proxy.__main__.watch", new_callable=AsyncMock)
@patch("log_proxy.utils.stdin_to_log", new_callable=AsyncMock)
@patch("log_proxy.__main__.configure")
def test_client_watch(conf_mock, stdin_mock, watch_mock, handler_mock, unused_tcp_port):
    watch_mock.__bool__.return_value = True

    main(["client", "--forward", f"localhost:{unused_tcp_port}", "--watch", "/tmp"])
    watch_mock.assert_called_once()
    handler_mock.assert_called_once()

    watch_mock.reset_mock()
    handler_mock.reset_mock()

    main(
        [
            "client",
            "--forward",
            f"localhost:{unused_tcp_port}",
            "--watch",
            "/tmp",
            "--log-stdin",
        ]
    )
    stdin_mock.assert_called_once()
    watch_mock.assert_called_once()
    handler_mock.assert_called_once()


@patch("log_proxy.__main__.LogServer", return_value=AsyncMock())
@patch("log_proxy.utils.generate_ssl_context")
@patch("sys.exit", side_effect=[AssertionError()])
def test_run_server_socket(exit_mock, ssl_mock, server_mock, unused_tcp_port):
    # Spawn a server with a socket forwarder with SSL context
    with NamedTemporaryFile() as fp:
        main(
            [
                "server",
                "socket",
                "--forward",
                f"localhost:{unused_tcp_port}",
                "--forward-ca",
                fp.name,
            ]
        )
    ssl_mock.assert_called_once()
    server_mock.assert_called_once()
    assert isinstance(server_mock.call_args.kwargs["forwarder"], SocketForwarder)

    # Spawn a server with a socket forwarder without SSL context
    ssl_mock.reset_mock()
    server_mock.reset_mock()
    main(["server", "socket", "--forward", f"localhost:{unused_tcp_port}"])
    ssl_mock.assert_not_called()
    server_mock.assert_called_once()
    assert isinstance(server_mock.call_args.kwargs["forwarder"], SocketForwarder)

    # Missing forward argument
    server_mock.reset_mock()
    with pytest.raises(AssertionError):
        main(["server", "socket"])
    server_mock.assert_not_called()


@patch("log_proxy.forwarders.PostgresForwarder")
@patch("log_proxy.__main__.LogServer", return_value=AsyncMock())
@patch("log_proxy.utils.generate_ssl_context")
@patch("sys.exit", side_effect=[AssertionError()])
def test_run_server_postgres(exit_mock, ssl_mock, server_mock, forward_mock):
    # Spawn a server with a socket forwarder with SSL context
    with NamedTemporaryFile() as fp:
        main(
            [
                "server",
                "postgres",
                "--db",
                "log",
                "--db-table",
                "log",
                "--cert",
                fp.name,
                "--key",
                fp.name,
            ]
        )
    server_mock.assert_called_once()
    ssl_mock.assert_called_once()
    assert server_mock.call_args.kwargs["forwarder"] == forward_mock.return_value

    # Missing forward argument
    server_mock.reset_mock()
    with pytest.raises(AssertionError):
        main(["server", "postgres"])
    server_mock.assert_not_called()


@patch("log_proxy.forwarders.MongoDBForwarder")
@patch("log_proxy.__main__.LogServer", return_value=AsyncMock())
@patch("log_proxy.utils.generate_ssl_context")
@patch("sys.exit", side_effect=[AssertionError()])
def test_run_server_mongodb(exit_mock, ssl_mock, server_mock, forward_mock):
    # Spawn a server with a socket forwarder with SSL context
    main(["server", "mongodb", "--db", "log", "--db-table", "log"])
    server_mock.assert_called_once()
    assert server_mock.call_args.kwargs["forwarder"] == forward_mock.return_value

    # Missing forward argument
    server_mock.reset_mock()
    with pytest.raises(AssertionError):
        main(["server", "mongodb"])
    server_mock.assert_not_called()


@patch("log_proxy.forwarders.MongoDBForwarder")
@patch("log_proxy.__main__.LogServer", return_value=AsyncMock())
@patch("log_proxy.utils.generate_ssl_context")
@patch("sys.exit", side_effect=[AssertionError()])
def test_run_server_with_config(exit_mock, ssl_mock, server_mock, forward_mock):
    # Spawn a server with a socket forwarder with SSL context
    with NamedTemporaryFile() as fp:
        fp.write(b"[log_proxy]\ndatabase=log\ndb_table=log")
        fp.flush()
        main(["server", "mongodb", "--config", fp.name])

    server_mock.assert_called_once()
    assert server_mock.call_args.kwargs["forwarder"] == forward_mock.return_value

    server_mock.reset_mock()
    with NamedTemporaryFile() as fp, pytest.raises(AssertionError):
        fp.write(b"[invalid]\ndatabase=log\ndb_table=log")
        fp.flush()
        main(["server", "mongodb", "--config", fp.name])
    server_mock.assert_not_called()


@patch("log_proxy.__main__.LogServer", return_value=AsyncMock())
@patch("log_proxy.__main__.configure")
@patch("log_proxy.__main__.watch")
@patch("sys.exit", side_effect=[AssertionError()])
@pytest.mark.asyncio
async def test_run_invalid(exit_mock, watch_mock, conf_mock, server_mock):
    with pytest.raises(NotImplementedError):
        await run_server(MagicMock(forwarder="invalid"))

    # watch isn't available
    watch_mock.__bool__.return_value = False
    with MagicMock() as mock:
        parser_watcher(mock)
        mock.add_argument_group.assert_not_called()
