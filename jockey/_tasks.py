from __future__ import annotations

import asyncio
from typing import Coroutine, final


@final
class Tasks:
    """Supervise multiple async tasks.
    """
    __slots__ = ('_tasks', '_done')
    _tasks: set[asyncio.Task]
    _done: bool

    def __init__(self) -> None:
        self._tasks = set()
        self._done = False

    def start(self, coro: Coroutine[None, None, None]) -> None:
        """Create a new task and track it in the supervisor.
        """
        assert not self._done
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def cancel(self) -> None:
        """Cancel all supervised tasks.
        """
        if self._done:  # pragma: no cover
            return
        for task in self._tasks:
            task.cancel()

    async def wait(self) -> None:
        """Wait for all supervised tasks to finish.
        """
        assert not self._done
        await asyncio.gather(*self._tasks)
        self._done = True
