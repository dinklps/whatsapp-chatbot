import asyncio
from collections import defaultdict


class PhoneQueue:
    """Runs one turn at a time per phone number, so two quick messages can't race each other."""

    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: set[asyncio.Task] = set()

    def submit(self, phone: str, job) -> None:
        """`job` is a zero-argument coroutine function."""

        async def run() -> None:
            async with self._locks[phone]:
                await job()

        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
