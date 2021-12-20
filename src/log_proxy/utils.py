import argparse
import asyncio
import logging
import os
import re
import ssl
import sys
from argparse import ArgumentParser, Namespace
from typing import List, Tuple, Union
from urllib.parse import urlsplit

from .handlers import DatabaseHandler, JSONSocketHandler

_logger = logging.getLogger()

DEFAULT_LOG_FORMAT = "{asctime} [{levelname:^8}] {name}: {message}"


def configure_logging(
    log_file: str = None,
    level: int = logging.INFO,
    log_format: str = DEFAULT_LOG_FORMAT,
    *,
    database: DatabaseHandler = None,
    forward: JSONSocketHandler = None,
    stdout: bool = True,
) -> None:
    """Helper to configure the logger and handlers"""
    _logger.setLevel(level)
    formatter = logging.Formatter(log_format, style="{")

    handlers = [forward, database]

    # Echo the logs on the stdout
    if stdout:
        handlers.append(logging.StreamHandler(sys.stdout))

    # Write the logs additional into a file
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    # Forward the logs further
    for handler in handlers:
        if handler:
            handler.setLevel(level)
            handler.setFormatter(formatter)
            _logger.addHandler(handler)


def generate_ssl_context(
    *,
    cert: str = None,
    key: str = None,
    ca: str = None,
    server: bool = False,
    ciphers: List[str] = None,
    check_hostname: bool = False,
) -> ssl.SSLContext:
    """Generate a SSL context for the tunnel"""

    # Set the protocol and create the basic context
    proto = ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT
    ctx = ssl.SSLContext(proto)

    ctx.check_hostname = check_hostname
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    # Prevent the reuse of parameters
    if server:
        ctx.options |= ssl.OP_SINGLE_DH_USE | ssl.OP_SINGLE_ECDH_USE

    # Load a certificate and key for the connection
    if cert:
        ctx.load_cert_chain(cert, keyfile=key)

    # Load the CA to verify the other side
    if ca:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=ca)

    # Set possible ciphers to use
    if ciphers:
        ctx.set_ciphers(ciphers)

    # Output debugging
    _logger.info("CA usage: %s", bool(ca))
    _logger.info("Certificate: %s", bool(cert))
    _logger.info("Hostname verification: %s", bool(check_hostname))
    _logger.info("Minimal TLS Versions: %s", ctx.minimum_version.name)

    ciphers = sorted(c["name"] for c in ctx.get_ciphers())
    _logger.info("Ciphers: %s", ", ".join(ciphers))

    return ctx


def parse_address(
    address: str, host: str = None, port: int = None, multiple: bool = False
) -> Tuple[Union[str, List[str]], int]:
    """Parse an address and split hostname and port. The port is required. The
    default host is "" which means all"""

    # Only the address without scheme and path. We only support IPs if multiple hosts
    # are activated
    pattern = r"[0-9.:\[\],]*?" if multiple else r"[0-9a-zA-Z.:\[\],]*?"
    match = re.match(fr"^(?P<hosts>{pattern})(:(?P<port>\d+))?$", address)
    if not match:
        raise argparse.ArgumentTypeError(
            "Invalid address parsed. Only host and port are supported."
        )

    # Try to parse the port first
    data = match.groupdict()
    if data.get("port"):
        port = int(data["port"])
        if port <= 0 or port >= 65536:
            raise argparse.ArgumentTypeError("Invalid address parsed. Invalid port.")

    if port is None:
        raise argparse.ArgumentTypeError("Port required.")

    # Try parsing the different host addresses
    hosts = set()
    for h in data.get("hosts", "").split(","):
        if not h:
            hosts.add(h or host)
            continue

        try:
            parsed = urlsplit(f"http://{h}")
            hosts.add(parsed.hostname)
        except Exception as e:
            raise argparse.ArgumentTypeError(
                "Invalid address parsed. Invalid host."
            ) from e

    # Multiple hosts are supported if the flag is set
    if len(hosts) > 1 and multiple:
        return sorted(hosts), port

    # Otherwise we fail
    if len(hosts) > 1:
        raise argparse.ArgumentTypeError(
            "Invalid address parsed. Only one host is required."
        )

    if len(hosts) == 1:
        host = hosts.pop() or host
        if host is not None:
            return host, port

    raise argparse.ArgumentTypeError("Invalid address parsed. Host required.")


async def stdin_to_log():
    """Use the stdin and pass it to the logger"""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            return

        _logger.info(line.decode().strip())


def valid_file(path: str) -> str:
    """Check if a file exists and return the absolute path otherwise raise an
    error. This function is used for the argument parsing"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError("Not a file.")
    return path


class ConfigArgumentParser(ArgumentParser):
    """Helper class for the configuration management"""

    def parse_with_config(
        self,
        args: Tuple[str] = None,
        config: dict = None,
    ) -> Namespace:
        """Parse the arguments using additional configuration"""
        args = list(sys.argv[1:] if args is None else args[:])

        actions = {act.dest: act for act in self._actions if act.option_strings}

        for key, value in (config or {}).items():
            action = actions.get(key)

            # Skip if it's not a action or if already present in the arguments
            if not action or any(opt in args for opt in action.option_strings):
                continue

            if isinstance(action, argparse._StoreConstAction):
                args.append(action.option_strings[0])
            elif isinstance(action, argparse._StoreAction):
                args.extend((action.option_strings[0], str(value)))

        return self.parse_args(args)
