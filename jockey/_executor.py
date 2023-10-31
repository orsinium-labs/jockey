from __future__ import annotations

import asyncio
from concurrent import futures
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Generic, Iterator

from ._adapter import Adapter, Payload, Key, Result
from ._execute_in import ExecuteIn
from ._actor import Actor
from ._registry import Registry


@dataclass(frozen=True)
class Executor(Generic[Payload, Key, Result]):
    registry: Registry[Key]
    max_jobs: int = 16
    max_processes: int | None = None
    max_threads: int | None = None

    @contextmanager
    def get_executor(
        self: Executor[Payload, Key, Result],
    ) -> Iterator[RunningExecutor[Payload, Key, Result]]:
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
            yield RunningExecutor(actors)


@dataclass(frozen=True)
class RunningExecutor(Generic[Payload, Key, Result]):
    _actors: dict[Key, Actor]

    async def execute(self, msg: Adapter[Payload, Key, Result]) -> bool:
        for key in await msg.get_keys():
            actor = self._actors.get(key)
            if actor is not None:
                await actor.handle(msg)
                return True
        return False
