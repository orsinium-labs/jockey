from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar

Payload = TypeVar('Payload')
Key = TypeVar('Key')
Result = TypeVar('Result')


class Adapter(ABC, Generic[Payload, Key, Result]):
    @abstractmethod
    def get_keys(self) -> Iterator[Key]:
        """Get the routing keys that will be used to pick the handler for the message.

        If several keys are yeilded, they will be tried one by one until one matches
        a handler. If not match found, Adapter.on_no_handler is called.

        Tip: if you want to have a fallback handler that will be called if no handler
        found (instead of calling Adapter.on_no_handler), make sure to yield
        as the last key the key of that handler.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_payload(self) -> Payload:
        """
        """
        raise NotImplementedError

    @abstractmethod
    async def on_success(self, result: Result) -> None:
        """
        """
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


@dataclass(frozen=True)
class Middleware(Generic[Payload, Key, Result], Adapter[Payload, Key, Result]):
    """An adapter that forwards all callbacks to the wrapped adapter.

    You can redefine only one (for example, on_success) or a few methods
    to provide and additional logic for an existing adapter (for example, logging),
    and the rest of the calls would be forwarded to the real Adapter
    (or another middleware).
    """
    adapter: Adapter[Payload, Key, Result]

    def get_keys(self) -> Iterator[Key]:
        return self.adapter.get_keys()

    async def get_payload(self) -> Payload:
        return await self.adapter.get_payload()

    async def on_success(self, result: Result) -> None:
        return await self.adapter.on_success(result)

    async def on_failure(self, exc: Exception) -> None:
        return await self.adapter.on_failure(exc)

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        return await self.adapter.on_cancel(exc)

    async def on_pulse(self) -> None:
        return await self.adapter.on_pulse()

    async def on_no_handler(self) -> None:
        return await self.adapter.on_no_handler()
