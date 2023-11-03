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
from ._wait_for import WaitFor


@dataclass(frozen=True)
class Executor(Generic[Payload, Key, Result]):
    """Executor takes care of running tasks and managing pools of tasks.

    Args:
        registry: the Registry to be used to get a handler for the given message.
        max_jobs: how many jobs can be running at the same time across all handlers.
        max_processes: the pool size for handlers executing in a process.
            Defaults to the number of CPUs. The process pool will not be created
            if no handlers need it.
        max_threads: the pool size for handlers executing in a thread.
            Defaults to the number of CPUs + 4. The thread pool will not be created
            if no handlers need it.
    """
    registry: Registry[Payload, Key, Result]
    max_jobs: int = 16
    max_processes: int | None = None
    max_threads: int | None = None

    @asynccontextmanager
    async def run(
        self: Executor[Payload, Key, Result],
    ) -> AsyncIterator[RunningExecutor[Payload, Key, Result]]:
        """An async context manager that starts the executor.

        On enter, it creates task pools and a lookup table for handlers.

        On exit, it waits for all tasks to finish and destroys task pools.
        """
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
                yield RunningExecutor(actors, tasks, global_sem)
            except (Exception, asyncio.CancelledError):
                tasks.cancel()
                raise
            await tasks.wait()


@dataclass(frozen=True)
class RunningExecutor(Generic[Payload, Key, Result]):
    _actors: dict[Key, Actor]
    _tasks: Tasks
    _global_sem: asyncio.Semaphore

    async def execute(
        self,
        msg: Adapter[Payload, Key, Result],
        *,
        wait_for: WaitFor = WaitFor.NO_PRESSURE,
    ) -> None:
        """Process the given message using a registered handler.

        It respect the maximum number of jobs specified in the Executor instance
        and in the individual handlers. The wait_for argument allows you to
        make execute block until the message processing reaches a certain stage.
        It's useful for "back pressure" to not fetch from the message broker
        more messages than you can process.
        """
        if wait_for is WaitFor.NOTHING:
            coro = self._execute(msg)
            self._tasks.start(coro)
            return
        if wait_for is WaitFor.FINISH:
            await self._execute(msg)
            return
        if wait_for is WaitFor.NO_PRESSURE:
            on_prestart: asyncio.Future[None] = asyncio.Future()
            coro = self._execute(msg, on_prestart=on_prestart)
            self._tasks.start(coro)
            await on_prestart
            return
        if wait_for is WaitFor.START:
            on_start: asyncio.Future[None] = asyncio.Future()
            coro = self._execute(msg, on_start=on_start)
            self._tasks.start(coro)
            await on_start
            return
        raise RuntimeError('unreachable')

    async def _execute(
        self,
        msg: Adapter[Payload, Key, Result],
        on_prestart: asyncio.Future[None] | None = None,
        on_start: asyncio.Future[None] | None = None,
    ) -> None:
        try:
            for key in msg.get_keys():
                actor = self._actors.get(key)
                if actor is not None:
                    await actor.handle(
                        msg,
                        _on_prestart=on_prestart,
                        _on_start=on_start,
                    )
                    return
            await msg.on_no_handler()
        finally:
            # in case futures aren't completed by the handler
            # (because there is no handler or because it failed early),
            # finish these futures to unblock Executor.execute.
            if on_prestart is not None:
                try:
                    on_prestart.set_result(None)
                except asyncio.InvalidStateError:
                    pass
            if on_start is not None:
                try:
                    on_start.set_result(None)
                except asyncio.InvalidStateError:
                    pass
