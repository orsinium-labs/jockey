from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Generic,
    Protocol,
    TypeVar,
)

from ._actor import ActorConfig
from ._adapter import Key, Payload, Result
from ._execute_in import ExecuteIn
from ._priority import Priority

if TYPE_CHECKING:
    Handler = Callable[[Payload], 'Awaitable[Result] | Result']
    H = TypeVar('H', bound=Handler)

    class Wrapper(Protocol, Generic[H]):
        def __call__(self, h: H) -> H:
            pass


class Registry(Generic[Payload, Key, Result]):
    """A collection of handlers to be used by an Executor.
    """

    def __init__(self) -> None:
        self._actors: dict[Key, ActorConfig] = {}
        self._sealed: bool = False

    def add(
        self,
        key: Key,
        *,
        max_jobs: int = 16,
        job_timeout: float = 32,
        execute_in: ExecuteIn = ExecuteIn.MAIN,
        pulse_every: float = 0,
        priority: Priority = Priority.NORMAL,
    ) -> Wrapper[Handler[Payload, Result]]:
        """A decorator to add a new handler into the registry.

        After you start an executor, no new handlers can be added into the registry.

        Args:
            key: the value that Adapter.get_keys must return to be handled
                by this handler.
            max_jobs: The maximum jobs that can be run for this handler at the same time.
                Internally, controlled by a semaphore.
            job_timeout: If the handler takes that many seconds or more to run,
                it will be cancelled (by raising asyncio.CancelledError).
            execute_in: If the handler jobs must be executed in the current
                event loop (default), in a separate thread, or in a separate process.
            pulse_every: how often Adapter.on_pulse should be trigger.
                If 0 (default), it is never triggered.
            priority: handlers with a higher priority start sooner under high load.
        """
        def wrapper(handler: H) -> H:
            if self._sealed:
                raise RuntimeError('Registry is already sealed, cannot add more actors')
            assert pulse_every >= 0
            self._actors[key] = ActorConfig(
                handler=handler,
                max_jobs=max_jobs,
                job_timeout=job_timeout,
                execute_in=execute_in,
                pulse_every=pulse_every,
                priority=priority,
            )
            return handler
        return wrapper  # type: ignore[return-value]
