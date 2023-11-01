from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterator

import jockey

Payload = Any
Key = str
Result = Any


@dataclass
class Message(jockey.Adapter[Payload, Key, Result]):
    key: Key
    payload: Payload
    calls: list[tuple[str, Any]]

    def get_keys(self) -> Iterator[Key]:
        yield self.key

    async def get_payload(self) -> Payload:
        return self.payload

    async def on_success(self, result: Result) -> None:
        self.calls.append(('ok', result))

    async def on_failure(self, exc: Exception) -> None:
        self.calls.append(('fail', type(exc)))

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        self.calls.append(('cancel', type(exc)))

    async def on_no_handler(self) -> None:
        self.calls.append(('no handler', None))

    async def on_pulse(self) -> None:
        self.calls.append(('pulse', None))


@dataclass(frozen=True)
class Middleware(jockey.Middleware[Payload, Key, Result]):
    calls: list[tuple[str, Any]]

    async def on_success(self, result: Result) -> None:
        self.calls.append(('m.ok', result))
        await super().on_success(result)

    async def on_failure(self, exc: Exception) -> None:
        self.calls.append(('m.fail', type(exc)))
        await super().on_failure(exc)

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        self.calls.append(('m.cancel', type(exc)))
        await super().on_cancel(exc)

    async def on_no_handler(self) -> None:
        self.calls.append(('m.no handler', None))
        await super().on_no_handler()

    async def on_pulse(self) -> None:
        self.calls.append(('m.pulse', None))
        await super().on_pulse()


async def test_middleware():
    calls: list[tuple[str, Any]] = []
    msg = Message('key', 'hi', calls)
    mw = Middleware(msg, calls)
    assert list(mw.get_keys()) == ['key']
    assert await mw.get_payload() == 'hi'
    await mw.on_success('res')
    await mw.on_failure(ValueError())
    await mw.on_cancel(asyncio.CancelledError())
    await mw.on_pulse()
    await mw.on_no_handler()
    assert calls == [
        ('m.ok', 'res'),
        ('ok', 'res'),
        ('m.fail', ValueError),
        ('fail', ValueError),
        ('m.cancel', asyncio.CancelledError),
        ('cancel', asyncio.CancelledError),
        ('m.pulse', None),
        ('pulse', None),
        ('m.no handler', None),
        ('no handler', None),
    ]
