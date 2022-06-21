import logging

from .base import DatabaseForwarder

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

_logger = logging.getLogger()


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
