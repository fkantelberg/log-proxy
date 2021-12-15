import argparse
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from log_proxy import __main__ as main


def test_parser():
    assert isinstance(main.parse_args([]), argparse.Namespace)

    with patch("sys.exit", side_effect=[AssertionError]) as mock:
        with pytest.raises(AssertionError):
            main.parse_args(["-h"])

        mock.assert_called_once_with(0)


@patch("log_proxy.__main__.JSONSocketHandler")
@patch("log_proxy.utils.configure_logging")
@patch("log_proxy.utils.generate_ssl_context")
def test_configure(ssl_mock, conf_mock, handler_mock):
    mock = MagicMock()
    mock.forward = mock.forward_ca = False

    assert main.configure(mock) == conf_mock.return_value
    conf_mock.assert_called_once()

    mock.forward = "example.org", 2773
    assert main.configure(mock) == conf_mock.return_value

    ssl_mock.assert_not_called()
    handler_mock.assert_called_once()

    mock.forward_ca = True
    assert main.configure(mock) == conf_mock.return_value
    ssl_mock.assert_called_once()


@patch("log_proxy.__main__.LogServer", return_value=AsyncMock())
@patch("log_proxy.__main__.utils", new_callable=AsyncMock)
@patch("log_proxy.__main__.watch", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_run(watch_mock, utils_mock, server_mock):
    mock = AsyncMock()
    mock.no_server, mock.watch, mock.log_stdin = True, False, False

    await main.run(mock)
    await asyncio.sleep(0.1)

    utils_mock.stdin_to_log.assert_not_called()

    mock.log_stdin = True
    await main.run(mock)
    await asyncio.sleep(0.1)
    utils_mock.generate_ssl_context.assert_not_called()
    utils_mock.stdin_to_log.assert_called_once()
    utils_mock.reset_mock()

    watch_mock.assert_not_called()
    server_mock.assert_not_called()

    mock.watch = True
    await main.run(mock)
    await asyncio.sleep(0.1)
    utils_mock.stdin_to_log.assert_called_once()
    watch_mock.assert_called_once()

    mock.log_stdin = False
    await main.run(mock)
    await asyncio.sleep(0.1)
    utils_mock.stdin_to_log.assert_called_once()
    utils_mock.reset_mock()
    watch_mock.reset_mock()

    mock.no_server = False
    mock.listen = "example.org", 2773
    utils_mock.generate_ssl_context = MagicMock()
    await main.run(mock)
    await asyncio.sleep(0.1)
    utils_mock.stdin_to_log.assert_not_called()
    server_mock.assert_called_once_with(
        *mock.listen,
        utils_mock.generate_ssl_context.return_value,
    )

    mock.log_stdin = True
    await main.run(mock)
    await asyncio.sleep(0.1)
    utils_mock.stdin_to_log.assert_called_once()

    mock.cert = False
    server_mock.reset_mock()
    await main.run(mock)
    await asyncio.sleep(0.1)
    server_mock.assert_called_once_with(*mock.listen, None)
