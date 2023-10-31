from __future__ import annotations

import asyncio
from concurrent import futures
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Generic

from ._actor import Actor
from ._adapter import Adapter, Key, Payload, Result
from ._execute_in import ExecuteIn
from ._registry import Registry
from ._tasks import Tasks


@dataclass(frozen=True)
class Executor(Generic[Payload, Key, Result]):
    registry: Registry[Payload, Key, Result]
    max_jobs: int = 16
    max_processes: int | None = None
    max_threads: int | None = None

    @asynccontextmanager
    async def run(
        self: Executor[Payload, Key, Result],
    ) -> AsyncIterator[RunningExecutor[Payload, Key, Result]]:
        self.registry._sealed = True
        global_sem = asyncio.Semaphore(self.max_jobs)
        thread_pool: futures.ThreadPoolExecutor | None = None
        proc_pool: futures.ProcessPoolExecutor | None = None
        with ExitStack() as stack:
            configs = list(self.registry._actors.values())
            if any(a.execute_in == ExecuteIn.THREAD for a in configs):
                thread_pool = stack.enter_context(
                    futures.ThreadPoolExecutor(self.max_threads),
                )
            if any(a.execute_in == ExecuteIn.PROCESS for a in configs):
                proc_pool = stack.enter_context(
                    futures.ProcessPoolExecutor(self.max_processes),
                )

            actors: dict[Key, Actor] = {}
            for key, config in self.registry._actors.items():
                executor: futures.Executor | None
                if config.execute_in == ExecuteIn.THREAD:
                    executor = thread_pool
                elif config.execute_in == ExecuteIn.PROCESS:
                    executor = proc_pool
                else:
                    executor = None
                actors[key] = Actor(
                    config=config,
                    actor_sem=asyncio.Semaphore(config.max_jobs),
                    global_sem=global_sem,
                    executor=executor,
                )
            tasks = Tasks()
            try:
                yield RunningExecutor(actors, tasks)
            except (Exception, asyncio.CancelledError):
                tasks.cancel()
                raise
            await tasks.wait()


@dataclass(frozen=True)
class RunningExecutor(Generic[Payload, Key, Result]):
    _actors: dict[Key, Actor]
    _tasks: Tasks

    def schedule(self, msg: Adapter[Payload, Key, Result]) -> None:
        coro = self.execute(msg)
        self._tasks.start(coro)

    async def execute(self, msg: Adapter[Payload, Key, Result]) -> None:
        for key in msg.get_keys():
            actor = self._actors.get(key)
            if actor is not None:
                await actor.handle(msg)
                return
        await msg.on_no_handler()
