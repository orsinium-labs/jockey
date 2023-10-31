from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterator

import jockey

Payload = Any
Key = str
Result = Any


@dataclass
class Message(jockey.Adapter[Payload, Key, Result]):
    key: Key
    payload: Payload
    calls: list[tuple[str, Any]] = field(default_factory=list)

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


class Registry(jockey.Registry[Payload, Key, Result]):
    pass


async def test_one_actor_execute():
    registry = Registry()

    @registry.add(key='upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
    assert msg.calls == [('ok', 'HI')]


async def test_one_actor_schedule():
    registry = Registry()

    @registry.add(key='upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        executor.schedule(msg)
    assert msg.calls == [('ok', 'HI')]


async def test_no_actor_schedule():
    registry = Registry()

    @registry.add(key='upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    msg = Message('unknown', 'hi')
    async with jockey.Executor(registry).run() as executor:
        executor.schedule(msg)
    assert msg.calls == [('no handler', None)]
