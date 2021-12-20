import json
import re
import socket
import struct
import time
from logging import Handler
from logging.handlers import SocketHandler

try:
    from influxdb import InfluxDBClient as influx_connect
except ImportError:
    influx_connect = None

try:
    from psycopg2 import connect as pg_connect
except ImportError:
    pg_connect = None

try:
    from pymysql import connect as my_connect
except ImportError:
    my_connect = None


# Aggregate the possible database choices based on the available imports
DatabaseChoices = []
if pg_connect:
    DatabaseChoices.append("postgres")
if my_connect:
    DatabaseChoices.extend(("mariadb", "mysql"))
if influx_connect:
    DatabaseChoices.append("influxdb")


class DatabaseHandler(Handler):
    """Logging handler to send the log to a database"""

    def __init__(
        self,
        table,
        db_type,
        db_name,
        db_user=None,
        db_password=None,
        db_host=None,
        db_port=None,
    ):
        super().__init__()

        if re.match(r"^[\w_]+$", table):
            self.table = table
        else:
            raise ValueError("Invalid database table name")

        self.db_type = db_type
        if db_type == "postgres":
            kwargs = {
                "dbname": db_name,
                "host": db_host,
                "password": db_password,
                "port": db_port or 5432,
                "user": db_user,
            }
            self.connection = pg_connect(**{k: v for k, v in kwargs.items() if v})
        elif db_type in ("mariadb", "mysql"):
            kwargs = {
                "database": db_name,
                "host": db_host,
                "password": db_password,
                "port": db_port or 3306,
                "user": db_user,
            }
            self.connection = my_connect(**{k: v for k, v in kwargs.items() if v})
        elif db_type == "influxdb":
            kwargs = {
                "database": db_name,
                "host": db_host,
                "password": db_password,
                "port": db_port or 8086,
                "username": db_user,
            }
            self.connection = influx_connect(**{k: v for k, v in kwargs.items() if v})
        else:
            raise NotImplementedError()

    def _store(self, *args, **kwargs):
        """Pass the log to the right database handler"""
        if self.db_type == "postgres":
            self._pg_store(*args, **kwargs)
        elif self.db_type in ("mariadb", "mysql"):
            self._my_store(*args, **kwargs)
        elif self.db_type == "influxdb":
            self._influx_store(*args, **kwargs)

    def _influx_store(self, level, message, created_at, created_by):
        """Store the log within the influxdb"""
        self.connection.write_points(
            [
                {
                    "measurement": "log",
                    "tags": {
                        "name": created_by,
                        "level": level,
                    },
                    "time": created_at,
                    "fields": {"message": message},
                }
            ]
        )

    def _my_store(self, level, message, created_at, created_by):
        """Store the log within the mysql/mariadb database"""
        with self.connection.cursor() as cr:
            cr.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{self.table}` (
                    `id` INT AUTO_INCREMENT,
                    `level` LONGTEXT NOT NULL,
                    `message` LONGTEXT NOT NULL,
                    `created_at` LONGTEXT NOT NULL,
                    `created_by` LONGTEXT NOT NULL,
                    PRIMARY KEY (`id`)
                )
                """
            )

            query = f"""
                INSERT INTO `{self.table}`
                (`level`, `message`, `created_at`, `created_by`)
                VALUES (%s, %s, %s, %s)"""

            cr.execute(
                query,
                (level, message, created_at, created_by),
            )

        self.connection.commit()

    def _pg_store(self, level, message, created_at, created_by):
        """Store the log within the postgres database"""
        with self.connection.cursor() as cr:
            cr.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self.table}" (
                    "id" SERIAL,
                    "level" VARCHAR NOT NULL,
                    "message" VARCHAR NOT NULL,
                    "created_at" VARCHAR NOT NULL,
                    "created_by" VARCHAR NOT NULL,
                    PRIMARY KEY ("id")
                )
                """
            )

            query = (
                f'INSERT INTO "{self.table}"'
                f'("level", "message", "created_at", "created_by")'
                f"VALUES (%s, %s, %s, %s)"
            )

            cr.execute(
                query,
                (level, message, created_at, created_by),
            )

        self.connection.commit()

    def emit(self, record):
        """Emit the record to the database"""
        try:
            self._store(
                record.levelname or str(record.levelno),
                record.msg,
                time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(record.created),
                ),
                record.name,
            )
        except Exception:
            pass


class JSONSocketHandler(SocketHandler):
    """Logging handler to send the log via a socket to a server in JSON format"""

    def __init__(self, host, port, *, uuid=None, ssl_context=None, token=None):
        super().__init__(host, port)
        self.ssl_context = ssl_context
        self.token = token
        self.uuid = uuid or socket.gethostname()

    def _convert_json(self, data):
        """Convert the data to a simple byte representation"""
        data = json.dumps(data)
        datalen = struct.pack(">L", len(data))
        return datalen + data.encode()

    def makeSocket(self, timeout=1):
        """Wrap the socket with a SSL context if passed"""
        sock = super().makeSocket(timeout)

        if self.ssl_context:
            return self.ssl_context.wrap_socket(sock, server_side=True)

        if self.token:
            sock.send(self._convert_json({"token": self.token}))

        return sock

    def makePickle(self, record):
        """Use json instead of pickle to prevent code execution"""
        if record.exc_info:
            self.format(record)

        data = dict(record.__dict__)
        data.update(
            {
                "msg": record.getMessage(),
                "args": None,
                "exc_info": None,
                "name": f"{self.uuid}~{record.name}",
            }
        )
        data.pop("message", None)
        return self._convert_json(data)
