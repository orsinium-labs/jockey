from __future__ import annotations

from typing import (
    Awaitable, Callable, Generic, Protocol, TypeVar,
)

from ._adapter import Payload, Key, Result
from ._execute_in import ExecuteIn
from ._priority import Priority
from ._actor import ActorConfig

Handler = Callable[[Payload], Awaitable[Result] | Result]
H = TypeVar('H', bound=Handler)


class Wrapper(Protocol, Generic[H]):
    def __call__(self, h: H) -> H:
        pass


class Registry(Generic[Payload, Key, Result]):
    def __init__(self) -> None:
        self._actors: dict[Key, ActorConfig] = {}
        self._sealed: bool = False

    def add(
        self, *,
        key: Key,
        max_jobs: int = 16,
        job_timeout: float = 32,
        execute_in: ExecuteIn = ExecuteIn.MAIN,
        pulse: bool = True,
        priority: Priority = Priority.NORMAL,
    ) -> Wrapper[Handler[Payload, Result]]:
        def wrapper(handler: H) -> H:
            if self._sealed:
                raise RuntimeError('Registry is already sealed, cannot add more actors')
            self._actors[key] = ActorConfig(
                handler=handler,
                max_jobs=max_jobs,
                job_timeout=job_timeout,
                execute_in=execute_in,
                pulse=pulse,
                priority=priority,
            )
            return handler
        return wrapper  # type: ignore[return-value]
