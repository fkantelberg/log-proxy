import json
import logging
import socket
from unittest.mock import MagicMock, patch

import pytest

from log_proxy.handlers import DatabaseHandler, JSONSocketHandler


def test_json_handler_socket(unused_tcp_port):
    sock = socket.socket()

    sock.bind(("127.0.0.1", unused_tcp_port))
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


def test_database_handler():
    with pytest.raises(ValueError):
        DatabaseHandler("abc-def", "postgres", "log")

    with pytest.raises(NotImplementedError):
        DatabaseHandler("log", "unknown", "log")


@patch("log_proxy.handlers.pg_connect")
def test_postgres_handler(mock):
    handler = DatabaseHandler(
        table="log",
        db_type="postgres",
        db_name="test",
        db_host="127.0.0.1",
    )

    record = MagicMock()
    handler.emit(record)
    mock.assert_called_once_with(dbname="test", host="127.0.0.1", port=5432)
    assert handler.connection == mock.return_value

    mock.return_value.cursor.side_effect = [AssertionError]
    handler.emit(record)


@patch("log_proxy.handlers.mongo_connect")
def test_mongodb_handler(mock):
    handler = DatabaseHandler(
        table="log",
        db_type="mongodb",
        db_name="test",
        db_host="127.0.0.1",
    )

    record = MagicMock()
    handler.emit(record)
    mock.assert_called_once_with(database="test", host="127.0.0.1")
    assert handler.connection == mock.return_value

    mock.return_value.cursor.side_effect = [AssertionError]
    handler.emit(record)


@patch("log_proxy.handlers.my_connect")
def test_mysql_handler(mock):
    with pytest.raises(ValueError):
        DatabaseHandler("abc-def", "postgres", "log")

    with pytest.raises(NotImplementedError):
        DatabaseHandler("log", "unknown", "log")

    handler = DatabaseHandler(
        table="log",
        db_type="mysql",
        db_name="test",
        db_host="127.0.0.1",
    )

    record = MagicMock()
    handler.emit(record)
    mock.assert_called_once_with(database="test", host="127.0.0.1", port=3306)
    assert handler.connection == mock.return_value

    mock.return_value.cursor.side_effect = [AssertionError]
    handler.emit(record)


@patch("log_proxy.handlers.influx_connect")
def test_influx_handler(mock):
    with pytest.raises(ValueError):
        DatabaseHandler("abc-def", "influxdb", "log")

    with pytest.raises(NotImplementedError):
        DatabaseHandler("log", "unknown", "log")

    handler = DatabaseHandler(
        table="log",
        db_type="influxdb",
        db_name="test",
        db_host="127.0.0.1",
    )

    record = MagicMock()
    handler.emit(record)
    mock.assert_called_once_with(database="test", host="127.0.0.1", port=8086)
    assert handler.connection == mock.return_value

    mock.return_value.cursor.side_effect = [AssertionError]
    handler.emit(record)
