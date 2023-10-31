from __future__ import annotations

import asyncio
from concurrent.futures import Executor
from dataclasses import dataclass
from typing import (
    Awaitable,
    Callable,
    Generic,
)

from ._adapter import Adapter, Key, Payload, Result
from ._execute_in import ExecuteIn
from ._priority import Priority


@dataclass(frozen=True)
class ActorConfig(Generic[Payload, Key, Result]):
    """All info about actor provided by the user.

    See Registry.add to learn more about arguments and their defaults.
    """
    handler: Callable[[Payload], Awaitable[Result] | Result]
    max_jobs: int
    job_timeout: float
    pulse_every: float
    execute_in: ExecuteIn
    priority: Priority


@dataclass(frozen=True)
class Actor(Generic[Payload, Key, Result]):
    """Actor is created by Executor. It's ActorConfig plus execution context.
    """
    config: ActorConfig[Payload, Key, Result]
    actor_sem: asyncio.Semaphore
    global_sem: asyncio.Semaphore
    executor: Executor | None

    async def handle(self, msg: Adapter[Payload, Key, Result]) -> None:
        """Process using handler the payload provided by Adapter and trigger callbacks.
        """
        pulse_task: asyncio.Task[None] | None = None
        if self.config.pulse_every:
            pulse_task = asyncio.create_task(self._pulse(msg))
        try:
            async with self.actor_sem:
                async with self.config.priority.acquire(self.global_sem):
                    payload = await msg.get_payload()
                    result = await self._handle(payload)
        except Exception as exc:
            if pulse_task is not None:
                pulse_task.cancel()
            await msg.on_failure(exc)
        except asyncio.CancelledError as exc:
            if pulse_task is not None:
                pulse_task.cancel()
            await msg.on_cancel(exc)
        else:
            if pulse_task is not None:
                pulse_task.cancel()
            await msg.on_success(result)

    async def _handle(self, payload: Payload) -> Result:
        if self.executor is not None:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self.executor,
                self.config.handler,
                payload,
            )
            result = await asyncio.wait_for(future, timeout=self.config.job_timeout)
            return result  # type: ignore[return-value]
        result = self.config.handler(payload)
        if asyncio.iscoroutine(result):
            return await asyncio.wait_for(
                result,
                timeout=self.config.job_timeout,
            )
        return result  # type: ignore[return-value]

    async def _pulse(self, msg: Adapter[Payload, Key, Result]) -> None:
        """Keep notifying Adapter that the message handling is in progress.
        """
        while True:
            await asyncio.sleep(self.config.pulse_every)
            await msg.on_pulse()
