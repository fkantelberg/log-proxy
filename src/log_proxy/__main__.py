#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
from configparser import ConfigParser
from typing import Tuple

from . import base, forwarders, utils
from .handlers import JSONSocketHandler
from .server import LogServer

try:
    from .watcher import watch
except ImportError:
    watch = None


_logger = logging.getLogger(__name__)


class CustomHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action: argparse.Action) -> str:
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)

        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return f"{'/'.join(action.option_strings)} {args_string}"


def require(check: bool, msg: str) -> None:
    if not check:
        _logger.error(msg)
        sys.exit()


def parser_base(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Basic configuration")
    group.add_argument(
        "-c",
        "--config",
        default=None,
        type=argparse.FileType(),
        help="Load everything from a configuration file. Additional arguments can "
        "override the configuration.",
    )
    group.add_argument(
        "--log-file",
        help="File to use for logging. If not set logs will be put to stdout. "
        "(configuration: %(dest)s)",
    )
    group.add_argument(
        "--log-level",
        choices=sorted(base.LOG_LEVELS),
        default="info",
        help="Set the log level to use. (default: %(default)s, configuration: %(dest)s)",
    )
    group.add_argument(
        "--log-stdin",
        default=False,
        action="store_true",
        help="Pipe the stdin into the log. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--log-format",
        default=utils.DEFAULT_LOG_FORMAT,
        help="Configure the log format using the { style formatting. "
        "(configuration: %(dest)s)",
    )
    group.add_argument(
        "--no-stdout",
        default=False,
        action="store_true",
        help="Don't echo logs on the stdout. (configuration: %(dest)s)",
    )


def parser_server(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Server configuration")
    group.add_argument(
        "-l",
        "--listen",
        dest="listen",
        default=("", base.DEFAULT_PORT),
        metavar="[host[,host]*][:port]",
        type=lambda x: utils.parse_address(
            x,
            host="",
            port=base.DEFAULT_PORT,
            multiple=True,
        ),
        help=f"The address to listen on. If host is not given the server will "
        f"listen for connections from all IPs. If you want to listen on multiple "
        f"interfaces you can separate them by comma. If the port is not given "
        f"the server will listen on port {base.DEFAULT_PORT}. "
        "(configuration: %(dest)s)",
    )
    group.add_argument(
        "--ca",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="CA certificate to use. Will enforce client certificates. "
        "(configuration: %(dest)s)",
    )
    group.add_argument(
        "--cert",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Certificate to use for establishing the connection. "
        "(configuration: %(dest)s)",
    )
    group.add_argument(
        "--key",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Private key for the certificate. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--cipher",
        default=None,
        help="Ciphers to use for the TLS connection. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--token-file",
        type=utils.valid_file,
        default=None,
        help="Enable token authentication using the given json file to store the "
        "trusted tokens. (configuration: %(dest)s)",
    )


def parser_forward_database(parser: argparse.ArgumentParser, db: str) -> None:
    group = parser.add_argument_group("Forwarding configuration")
    group.add_argument(
        "--db",
        dest="database",
        default=None,
        help="The database name to log the messages to. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--db-table",
        default=None,
        help="The database table or collection to forward the messages. "
        "(default: %(default)s, configuration: %(dest)s)",
    )
    group.add_argument(
        "--db-host",
        default=None,
        help="The host of the database. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--db-port",
        type=int,
        default=None,
        help="The port of the database (default: %(default)s, configuration: %(dest)s)",
    )
    group.add_argument(
        "--db-user",
        default=None,
        help="The database user. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--db-password",
        default=None,
        help="The password for the database. (configuration: %(dest)s)",
    )


def parser_forward_socket(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Forwarding configuration")
    group.add_argument(
        "--forward",
        dest="forward",
        metavar="host[:port]",
        default=None,
        type=lambda x: utils.parse_address(x, port=base.DEFAULT_PORT),
        help=f"Connect to a different log server to forward the log messages further."
        f" (default: {base.DEFAULT_PORT}, configuration: %(dest)s)",
    )
    group.add_argument(
        "--forward-ca",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="CA certificate to use. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--forward-cert",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Certificate to use for establishing the connection. Required if the "
        "target server enforces the client certificates. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--forward-key",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Private key for the certificate. Required if the target server enforces "
        "the client certificates. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--forward-cipher",
        default=None,
        help="Ciphers to use for the TLS connection. (configuration: %(dest)s)",
    )
    group.add_argument(
        "--forward-token",
        default=None,
        help="Token to initialize the connection to the log server. "
        "(configuration: %(dest)s)",
    )
    group.add_argument(
        "--no-verify-hostname",
        action="store_true",
        default=False,
        help="Disable the hostname verification. Only useful for forwarding. "
        "(configuration: %(dest)s)",
    )


def parser_watcher(parser: argparse.ArgumentParser) -> None:
    if not watch:
        return

    group = parser.add_argument_group("Watcher configuration")
    group.add_argument(
        "--watch",
        default=None,
        help="Watch on a folder for changes. This only works for clients.",
    )
    group.add_argument(
        "-wi",
        "--watch-include",
        default=[],
        action="append",
        help="Define patterns for files to include in the watcher. You can specify "
        "this options multiple times. (configuration: %(dest)s)",
    )
    group.add_argument(
        "-we",
        "--watch-exclude",
        default=[],
        action="append",
        help="Define patterns for files to exclude in the watcher. You can specify "
        "this options multiple times. (configuration: %(dest)s)",
    )
    group.add_argument(
        "-wc",
        "--watch-case-sensitive",
        default=False,
        action="store_true",
        help="Enable case sensitivity for file names. (configuration: %(dest)s)",
    )


def parse_args(args: Tuple[str] = None) -> argparse.Namespace:
    # Aggregate which databases are available
    parser = utils.ConfigArgumentParser(
        formatter_class=CustomHelpFormatter,
        prog="",
        description="",
    )

    mode_parser = parser.add_subparsers(dest="mode", required=True)

    client = mode_parser.add_parser(
        "client",
        formatter_class=CustomHelpFormatter,
        help="Run in client mode enabling to forward logs to a server. "
        "This is useful for testing of log servers.",
    )
    parser_base(client)
    parser_forward_socket(client)
    parser_watcher(client)

    server = mode_parser.add_parser(
        "server",
        formatter_class=CustomHelpFormatter,
        help="Run in server mode enabling to aggregate logs from clients and "
        "forward them further to the next server or a database.",
    )
    forward_parser = server.add_subparsers(
        dest="forwarder",
        required=True,
        help="Specifies the target to forward the logs further. It can be a "
        "database or another log server.",
    )

    database_parser = forward_parser.add_parser("postgres")
    parser_base(database_parser)
    parser_server(database_parser)
    parser_forward_database(database_parser, "postgres")

    database_parser = forward_parser.add_parser("mongodb")
    parser_base(database_parser)
    parser_server(database_parser)
    parser_forward_database(database_parser, "mongodb")

    socket_parser = forward_parser.add_parser("socket")
    parser_base(socket_parser)
    parser_server(socket_parser)
    parser_forward_socket(socket_parser)

    parsed = parser.parse_args(args or sys.argv[1:])
    if not getattr(parsed, "config", None):
        return parsed

    cp = ConfigParser()
    cp.read_file(parsed.config)
    if not cp.has_section(base.CONFIG_SECTION):
        return parsed
    return parser.parse_with_config(args, dict(cp.items(base.CONFIG_SECTION)))


def configure(args: argparse.Namespace, **kwargs) -> None:
    level = base.LOG_LEVELS.get(args.log_level, logging.INFO)
    kwargs.update({"log_format": args.log_format, "stdout": not args.no_stdout})
    utils.configure_logging(
        args.log_file,
        level,
        **kwargs,
    )


async def run_client(args: argparse.Namespace) -> None:
    """Run it as a client"""

    if args.forward_ca:
        ssl_context = utils.generate_ssl_context(
            ca=args.forward_ca,
            cert=args.forward_cert,
            key=args.forward_key,
            ciphers=args.forward_cipher,
            check_hostname=not args.no_verify_hostname,
        )
    else:
        ssl_context = None

    forward = JSONSocketHandler(
        *args.forward,
        ssl_context=ssl_context,
        token=args.forward_token,
    )

    # Configure the log stream
    configure(args, forward=forward)

    # Watch different files and forward new lines
    require(
        watch and args.watch or args.log_stdin,
        "Neither --log-stdin nor --watch are specified",
    )
    if watch and args.watch:
        if args.log_stdin:
            asyncio.create_task(utils.stdin_to_log())

        await watch(
            args.watch,
            patterns=args.watch_include,
            ignore_patterns=args.watch_exclude,
            case_sensitive=args.watch_case_sensitive,
        )

    elif args.log_stdin:
        # Only log the stdin
        await utils.stdin_to_log()


async def run_server(args: argparse.Namespace) -> None:
    # Configure the log stream
    configure(args)

    # Build the forwarder
    if args.forwarder == "socket":
        # Build the SSL context for the forwarder
        if args.forward_ca:
            ssl_context = utils.generate_ssl_context(
                ca=args.forward_ca,
                cert=args.forward_cert,
                key=args.forward_key,
                ciphers=args.forward_cipher,
                check_hostname=not args.no_verify_hostname,
            )
        else:
            ssl_context = None

        require(args.forward, "--forward is missing")

        # Create the socket forwarder
        forwarder = forwarders.SocketForwarder(
            *args.forward,
            ssl_context=ssl_context,
            token=args.forward_token,
        )
    elif args.forwarder == "postgres":
        require(args.database, "--db is missing")
        require(args.db_table, "--db-table is missing")

        # Create the postgres forwarder
        forwarder = forwarders.PostgresForwarder(
            table=args.db_table,
            database=args.database,
            port=args.db_port or 5432,
            user=args.db_user,
            password=args.db_password,
        )
    elif args.forwarder == "mongodb":
        require(args.database, "--db is missing")
        require(args.db_table, "--db-table is missing")

        # Create the mongodb forwarder
        forwarder = forwarders.MongoDBForwarder(
            table=args.db_table,
            database=args.database,
            port=args.db_port or 27017,
            user=args.db_user,
            password=args.db_password,
        )
    else:
        raise NotImplementedError()

    # Build the SSL context for the server
    if args.cert and args.key:
        ssl_context = utils.generate_ssl_context(
            cert=args.cert,
            ca=args.ca,
            key=args.key,
            ciphers=args.cipher,
            server=True,
        )
    else:
        ssl_context = None

    # Start the server
    server = LogServer(
        *args.listen,
        ssl_context=ssl_context,
        token_file=args.token_file,
        use_auth=bool(args.token_file),
        forwarder=forwarder,
    )

    await server.run()


def main(args: Tuple[str] = None) -> None:
    args = parse_args(args)

    if args.mode == "client":
        asyncio.run(run_client(args))
    else:
        asyncio.run(run_server(args))


if __name__ == "__main__":
    main()
