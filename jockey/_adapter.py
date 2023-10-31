from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Generic, Iterator, TypeVar

Payload = TypeVar('Payload')
Key = TypeVar('Key')
Result = TypeVar('Result')


class Adapter(ABC, Generic[Payload, Key, Result]):
    @abstractmethod
    def get_keys(self) -> Iterator[Key]:
        raise NotImplementedError

    @abstractmethod
    async def get_payload(self) -> Payload:
        raise NotImplementedError

    @abstractmethod
    async def on_success(self, result: Result) -> None:
        raise NotImplementedError

    @abstractmethod
    async def on_failure(self, exc: Exception) -> None:
        raise NotImplementedError

    @abstractmethod
    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        raise NotImplementedError

    async def on_pulse(self) -> None:
        pass

    async def on_no_handler(self) -> None:
        pass
