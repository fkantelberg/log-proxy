import asyncio
import json
import logging
import ssl
import struct
from datetime import datetime

try:
    from asyncpg import connect as pg_connect
except ImportError:
    pg_connect = None

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

_logger = logging.getLogger()


class Forwarder:
    """Common forwarder class. Which already manages the message queue"""

    def __init__(self, max_size: int = 0):
        self.queue = asyncio.PriorityQueue(max_size)
        self.counter = 0

    def __repr__(self) -> str:
        return "<forwarder>"

    def empty(self) -> bool:
        """Return if the queue is empty"""
        return self.queue.empty()

    async def get(self) -> dict:
        """Return the next message from the queue"""
        return (await self.queue.get())[-1]

    def connected(self) -> bool:
        """Return if the forwarder is properly connected"""
        return False

    async def connect(self) -> None:
        """Connect the forwarder to an endpoint"""
        pass

    async def process_message(self, msg: dict) -> None:
        """Process a single message"""
        pass

    async def put(self, message: dict) -> None:
        """Put the message on the queue. If the queue is full the first message will
        be dropped"""
        if self.queue.full():
            await self.queue.get()

        time = message.get("created_at")
        await self.queue.put((time, self.counter, message))
        self.counter += 1

    def invalidate(self) -> None:
        """Invalidate the connection of the forwarder"""
        pass

    async def process(self) -> None:
        """Process the queue a message at a time"""
        while True:
            try:
                if not self.connected():
                    await self.connect()

                msg = await self.get()
                await self.process_message(msg)
            except Exception as e:
                _logger.exception(e)
                self.invalidate()
                await asyncio.sleep(5)


class DatabaseForwarder(Forwarder):
    """Common database forwarder"""

    def __init__(self, *, max_size: int = 0, **kwargs):
        super().__init__(max_size=max_size)
        self.args = {k: v for k, v in kwargs.items() if v}


class MongoDBForwarder(DatabaseForwarder):
    """Forwards messages to a MongoDB database"""

    def __init__(
        self,
        *,
        database: str,
        table: str = "logs",
        max_size: int = 0,
        **kwargs,
    ):
        super().__init__(max_size=max_size, **kwargs)
        self.database = database
        self.table = table
        self.client = None

    def __repr__(self) -> str:
        return f"<forwarder mongo:{self.table}>"

    async def connect(self) -> None:
        """Connect to the database and create the table if needed"""
        self.client = MongoClient(**self.args)

    def invalidate(self) -> None:
        """Invalidate the connection of the forwarder"""
        self.client = None

    def connected(self) -> bool:
        """Return if the forwarder is properly connected"""
        return self.client is not None

    async def process_message(self, message: dict) -> None:
        """Process a single message"""
        self.client[self.database][self.table].insert_one(message)


class PostgresForwarder(DatabaseForwarder):
    """Forwards messages to a PostgreSQL database"""

    def __init__(
        self,
        *,
        table: str = "logs",
        max_size: int = 0,
        **kwargs,
    ):
        super().__init__(max_size=max_size, **kwargs)
        self.args["host"] = self.args.get("host")
        self.table = table
        self.connection = None

    def __repr__(self) -> str:
        return f"<forwarder postgres:{self.table}>"

    async def connect(self) -> None:
        """Connect to the database and create the table if needed"""
        self.connection = await pg_connect(**self.args)
        await self.connection.execute(
            f"""
                CREATE TABLE IF NOT EXISTS "{self.table}" (
                    "id" SERIAL,
                    "level" INT NOT NULL,
                    "pid" INT NOT NULL,
                    "host" VARCHAR,
                    "message" VARCHAR NOT NULL,
                    "created_at" TIMESTAMP NOT NULL,
                    "created_by" VARCHAR NOT NULL,
                    "exception" VARCHAR,
                    "path" VARCHAR,
                    "lineno" INT,
                    PRIMARY KEY ("id")
                )
            """
        )

        for column in ("level", "host", "created_by"):
            await self.connection.execute(
                f'CREATE INDEX IF NOT EXISTS "{self.table}_{column}_idx"'
                f'ON "{self.table}" ("{column}")'
            )

    def invalidate(self) -> None:
        """Invalidate the connection of the forwarder"""
        self.connection = None

    def connected(self) -> bool:
        """Return if the forwarder is properly connected"""
        return self.connection is not None

    async def process_message(self, message: dict) -> None:
        """Process a single message"""
        await self.connection.execute(
            f"""
                INSERT INTO "{self.table}"
                (
                    "level", "pid", "host", "message", "created_at", "created_by",
                    "exception", "path", "lineno"
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            message["level"],
            message["pid"],
            message.get("host"),
            message["message"],
            datetime.fromisoformat(message["created_at"]),
            message["created_by"],
            message.get("exception"),
            message.get("path"),
            message.get("lineno"),
        )


class SocketForwarder(Forwarder):
    """Forwards messages to a log server"""

    def __init__(
        self,
        host,
        port,
        *,
        ssl_context: ssl.SSLContext = None,
        token: str = None,
        max_size: int = 0,
    ):
        super().__init__(max_size)

        self.host, self.port = host, port
        self.ssl_context = ssl_context
        self.token = token
        self.reader = self.writer = None

    def __repr__(self):
        return f"<forwarder {self.host}:{self.port}>"

    def invalidate(self) -> None:
        """Invalidate the connection of the forwarder"""
        self.reader = self.writer = None

    def connected(self) -> bool:
        """Return if the forwarder is properly connected"""
        return self.writer is not None

    async def connect(self) -> None:
        """Connect the forwarder to the server"""
        self.reader, self.writer = await asyncio.open_connection(
            self.host,
            self.port,
            ssl=self.ssl_context,
        )

        if self.token:
            await self.process_message({"token": self.token})

    async def process_message(self, message: dict) -> None:
        """Process a single message"""
        data = json.dumps(message)
        self.writer.write(struct.pack(">L", len(data)))
        self.writer.write(data.encode())
        await self.writer.drain()
