import logging
from datetime import datetime

from .base import DatabaseForwarder

try:
    from asyncpg import connect as pg_connect
except ImportError:
    pg_connect = None

_logger = logging.getLogger()


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
