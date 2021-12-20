#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
from configparser import ConfigParser
from typing import Tuple

from . import base, utils
from .handlers import DatabaseChoices, DatabaseHandler, JSONSocketHandler
from .server import LogServer

try:
    from .watcher import watch
except ImportError:
    watch = None


class CustomHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action: argparse.Action) -> str:
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)

        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return f"{'/'.join(action.option_strings)} {args_string}"


def parse_args(args: Tuple[str] = None) -> argparse.Namespace:
    parser = utils.ConfigArgumentParser(
        formatter_class=CustomHelpFormatter,
        prog="",
        description="",
    )

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
        help="File to use for logging. If not set logs will be put to stdout.",
    )
    group.add_argument(
        "--log-level",
        choices=sorted(base.LOG_LEVELS),
        default="info",
        help="Set the log level to use. (default: %(default)s)",
    )
    group.add_argument(
        "--log-uuid",
        default=None,
        help="Unique identifier of the log messages. If not set the hostname is used.",
    )
    group.add_argument(
        "--log-stdin",
        default=False,
        action="store_true",
        help="Pipe the stdin into the log",
    )
    group.add_argument(
        "--log-format",
        default=utils.DEFAULT_LOG_FORMAT,
        help="Configure the log format using the { style formatting",
    )
    group.add_argument(
        "--no-server",
        default=False,
        action="store_true",
        help="Disable the server part",
    )
    group.add_argument(
        "--no-stdout",
        default=False,
        action="store_true",
        help="Don't echo logs on the stdout.",
    )

    if watch:
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
            "this options multiple times.",
        )
        group.add_argument(
            "-we",
            "--watch-exclude",
            default=[],
            action="append",
            help="Define patterns for files to exclude in the watcher. You can specify "
            "this options multiple times.",
        )
        group.add_argument(
            "-wc",
            "--watch-case-sensitive",
            default=False,
            action="store_true",
            help="Enable case sensitivity for file names",
        )

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
        f"the server will listen on port {base.DEFAULT_PORT}.",
    )
    group.add_argument(
        "--ca",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="CA certificate to use. Will enforce client certificates.",
    )
    group.add_argument(
        "--cert",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Certificate to use for establishing the connection.",
    )
    group.add_argument(
        "--key",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Private key for the certificate.",
    )
    group.add_argument(
        "--cipher",
        default=None,
        help="Ciphers to use for the TLS connection.",
    )
    group.add_argument(
        "--token",
        default=None,
        help="Token to use to connect. Will enforce token authentication if set.",
    )

    group = parser.add_argument_group("Forwarding configuration")
    group.add_argument(
        "-f",
        "--forward",
        dest="forward",
        metavar="host[:port]",
        default=None,
        type=lambda x: utils.parse_address(x, port=base.DEFAULT_PORT),
        help=f"Connect to a different log server to forward the log messages further."
        f" (default: {base.DEFAULT_PORT})",
    )
    group.add_argument(
        "--forward-ca",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="CA certificate to use.",
    )
    group.add_argument(
        "--forward-cert",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Certificate to use for establishing the connection. Required if the "
        "target server enforces the client certificates.",
    )
    group.add_argument(
        "--forward-key",
        default=None,
        metavar="FILE",
        type=utils.valid_file,
        help="Private key for the certificate. Required if the target server enforces "
        "the client certificates.",
    )
    group.add_argument(
        "--forward-cipher",
        default=None,
        help="Ciphers to use for the TLS connection.",
    )
    group.add_argument(
        "--forward-token",
        default=None,
        help="Token to initialize the connection to the log server.",
    )
    group.add_argument(
        "--no-verify-hostname",
        action="store_true",
        default=False,
        help="Disable the hostname verification. Only useful for forwarding.",
    )

    if DatabaseChoices:
        group = parser.add_argument_group("Database configuration")
        group.add_argument(
            "--db",
            dest="database",
            default=None,
            help="The database name to log the messages to",
        )
        group.add_argument(
            "--db-user",
            default=None,
            help="The database user",
        )
        group.add_argument(
            "--db-password",
            default=None,
            help="The database password",
        )
        group.add_argument(
            "--db-host",
            default=None,
            help="The database host. (default: %(default)s)",
        )
        group.add_argument(
            "--db-port",
            default=None,
            help="The database port. (default: %(default)s)",
        )
        group.add_argument(
            "--db-table",
            default="log",
            help="The database table to log to. (default: %(default)s)",
        )
        group.add_argument(
            "--db-type",
            default=DatabaseChoices[0],
            choices=DatabaseChoices,
            help=f"The database type. Choice: {', '.join(DatabaseChoices)}. "
            "(default: %(default)s)",
        )

    parsed = parser.parse_args(args)
    if not getattr(parsed, "config", None):
        return parsed

    cp = ConfigParser()
    cp.read_file(parsed.config)
    if not cp.has_section(base.CONFIG_SECTION):
        return parsed
    return parser.parse_with_config(args, dict(cp.items(base.CONFIG_SECTION)))


def configure(args: argparse.Namespace) -> None:
    """Configure the logger using the arguments"""
    level = base.LOG_LEVELS.get(args.log_level, logging.INFO)
    kwargs = {"log_format": args.log_format, "stdout": not args.no_stdout}

    sc = forward = database = None
    if args.forward_ca:
        sc = utils.generate_ssl_context(
            ca=args.forward_ca,
            cert=args.forward_cert,
            key=args.forward_key,
            ciphers=args.forward_cipher,
            check_hostname=not args.no_verify_hostname,
        )

    if args.forward:
        forward = JSONSocketHandler(
            *args.forward,
            ssl_context=sc,
            uuid=args.log_uuid,
            token=args.forward_token,
        )

    if args.database:
        database = DatabaseHandler(
            table=args.db_table,
            db_type=args.db_type,
            db_name=args.database,
            db_user=args.db_user,
            db_password=args.db_password,
            db_host=args.db_host,
            db_port=args.db_port,
        )

    return utils.configure_logging(
        args.log_file,
        level,
        forward=forward,
        database=database,
        **kwargs,
    )


async def run(args: argparse.Namespace) -> None:
    if not args.no_server:
        # Server SSL context
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

        server = LogServer(*args.listen, ssl_context, args.token)

        if args.log_stdin:
            asyncio.create_task(utils.stdin_to_log())

        await server.run()

    elif watch and args.watch:
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


def main(args: Tuple[str] = None) -> None:
    args = parse_args(args)

    configure(args)

    asyncio.run(run(args))


if __name__ == "__main__":
    main(sys.argv)
