from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import pytest

import jockey

Payload = Any
Key = str
Result = Any


@contextmanager
def duration_between(min_dur: float, max_dur: float):
    start = time.perf_counter()
    yield
    actual_dur = time.perf_counter() - start
    assert min_dur <= actual_dur < max_dur, f'time spent: {actual_dur}'


def upper(payload: Payload) -> Result:
    return payload.upper()


def pause(payload: Payload) -> Result:
    time.sleep(.1)


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


@pytest.mark.parametrize('execute_in', list(jockey.ExecuteIn))
async def test_one_actor_execute_in(execute_in: jockey.ExecuteIn):
    registry = Registry()
    registry.add(key='upper', execute_in=execute_in)(upper)

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


async def test_asyncio_concurrency():
    registry = Registry()

    @registry.add(key='upper')
    async def _upper(_: Payload) -> Result:
        await asyncio.sleep(.1)

    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            for n in range(10):
                executor.schedule(Message('upper', str(n)))


async def test_threading_concurrency():
    registry = Registry()

    @registry.add(key='upper', execute_in=jockey.ExecuteIn.THREAD)
    def _upper(_: Payload) -> Result:
        time.sleep(.1)

    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            for n in range(10):
                executor.schedule(Message('upper', str(n)))


async def test_process_concurrency():
    registry = Registry()
    registry.add(key='upper', execute_in=jockey.ExecuteIn.PROCESS)(pause)

    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            for n in range(10):
                executor.schedule(Message('upper', str(n)))


async def test_sealed_registry():
    registry = Registry()

    @registry.add(key='upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    async with jockey.Executor(registry).run():
        pass

    exp = 'Registry is already sealed, cannot add more actors'
    with pytest.raises(RuntimeError, match=exp):
        @registry.add(key='echo')
        def _echo(payload: Payload) -> Result:
            return payload
