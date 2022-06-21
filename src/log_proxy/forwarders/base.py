import asyncio
import logging

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

    async def process_message(self, message: dict) -> None:
        """Process a single message"""

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
