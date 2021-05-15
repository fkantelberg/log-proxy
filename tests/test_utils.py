import argparse
import logging
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from log_proxy import JSONSocketHandler, utils


def test_configure_logging():
    logger = logging.getLogger()

    utils.configure_logging(level=logging.DEBUG)
    assert logger.level == logging.DEBUG
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    utils.configure_logging("test.log", logging.INFO)
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)

    utils.configure_logging(forward=JSONSocketHandler("127.0.0.1", "3773"))
    assert any(isinstance(h, JSONSocketHandler) for h in logger.handlers)

    logger.handlers = []
    record = logging.makeLogRecord({"msg": "hello"})
    utils.configure_logging(log_format="test {message}")
    assert all(h.format(record) == "test hello" for h in logger.handlers)


def test_generate_ssl_context():
    ctx = utils.generate_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)

    with patch("ssl.SSLContext"):
        ctx = utils.generate_ssl_context(
            cert="cert",
            key="key",
            ca="ca",
            ciphers="ciphers",
            server=True,
        )

        ctx.load_cert_chain.assert_called_once_with("cert", keyfile="key")
        ctx.load_verify_locations.assert_called_once_with(cafile="ca")
        ctx.set_ciphers.assert_called_once_with("ciphers")


def test_parse_address():
    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("127.0.0.1:80/test")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("127.0.0.1")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address(":80")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("[:80")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("example.org")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("example:org")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("localhost:123456")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("127.0.0.1,[::1]:80")

    with pytest.raises(argparse.ArgumentTypeError):
        utils.parse_address("127.0.0.1,example.org:80")

    assert utils.parse_address("127.0.0.1:80") == ("127.0.0.1", 80)
    assert utils.parse_address("[::]:80") == ("::", 80)
    assert utils.parse_address(":80", host="::") == ("::", 80)
    assert utils.parse_address("[::]", port=80) == ("::", 80)
    assert utils.parse_address("", host="::", port=80) == ("::", 80)
    assert utils.parse_address("example.org", port=80) == ("example.org", 80)
    assert utils.parse_address("example.org:80") == ("example.org", 80)

    hosts = ["127.0.0.1", "::1"]
    addresses = "127.0.0.1,[::1]:80"
    assert utils.parse_address(addresses, multiple=True), (hosts, 80)


@pytest.mark.asyncio
async def test_stdin_to_log():
    log = logging.getLogger().info = MagicMock()

    with patch("asyncio.get_event_loop") as mock:
        with patch("asyncio.StreamReader") as reader:
            mock.return_value = AsyncMock()
            reader.return_value.readline = AsyncMock(side_effect=[b"hello\n", ""])
            await utils.stdin_to_log()
            mock.assert_called_once()
            log.assert_called_once_with("hello")


def test_valid_file():
    with pytest.raises(argparse.ArgumentTypeError):
        assert utils.valid_file(__file__ + "a")
    assert utils.valid_file(__file__) == __file__
