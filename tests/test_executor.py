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

    async def on_pulse(self) -> None:
        self.calls.append(('pulse', None))


class Registry(jockey.Registry[Payload, Key, Result]):
    pass


async def test_one_actor_execute__wait_for_finish():
    """The execute method must immediately execute the task.
    """
    registry = Registry()

    @registry.add('upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg, wait_for=jockey.WaitFor.FINISH)
        assert msg.calls == [('ok', 'HI')]


async def test_on_failure():
    """If actor fails, Adapter.on_failure is triggered.
    """
    registry = Registry()

    @registry.add('upper')
    def _upper(payload: Payload) -> Result:
        raise ValueError

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
    assert msg.calls == [('fail', ValueError)]


@pytest.mark.parametrize('execute_in', list(jockey.ExecuteIn))
async def test_one_actor_execute_in(execute_in: jockey.ExecuteIn):
    """Execution in loop, thread, and process always returns the same result.
    """
    registry = Registry()
    registry.add('upper', execute_in=execute_in)(upper)

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
    assert msg.calls == [('ok', 'HI')]


async def test_one_actor_schedule():
    """The execute method runs the task in the backgorund.
    """
    registry = Registry()

    @registry.add('upper')
    async def _upper(payload: Payload) -> Result:
        return payload.upper()

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
        assert msg.calls == []
    assert msg.calls == [('ok', 'HI')]


async def test_one_actor_schedule_wait():
    """When exiting the context, the executor must wait for all scheduled tasks.
    """
    registry = Registry()

    @registry.add('upper')
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.1)
        return payload.upper()

    msg = Message('upper', 'hi')
    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            await executor.execute(msg)
    assert msg.calls == [('ok', 'HI')]


async def test_no_actor_schedule():
    """If no handler available for message, Adapter.on_no_handler is called.
    """
    registry = Registry()

    @registry.add('upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    msg = Message('unknown', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
    assert msg.calls == [('no handler', None)]


async def test_asyncio_concurrency():
    """Running multiple asyncio tasks with execute method is concurrent.
    """
    registry = Registry()

    @registry.add('upper')
    async def _upper(_: Payload) -> Result:
        await asyncio.sleep(.1)

    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            for n in range(10):
                await executor.execute(Message('upper', str(n)))


async def test_threading_concurrency():
    """Running multiple threading tasks with execute method is concurrent.
    """
    registry = Registry()

    @registry.add('upper', execute_in=jockey.ExecuteIn.THREAD)
    def _upper(_: Payload) -> Result:
        time.sleep(.1)

    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            for n in range(10):
                await executor.execute(Message('upper', str(n)))


async def test_process_concurrency():
    """Running multiple process pool tasks with execute method is concurrent.
    """
    registry = Registry()
    registry.add('upper', execute_in=jockey.ExecuteIn.PROCESS)(pause)

    with duration_between(.1, .2):
        async with jockey.Executor(registry).run() as executor:
            for n in range(10):
                await executor.execute(Message('upper', str(n)))


async def test_sealed_registry():
    """After executor was started, new actors cannot be added to the registry.
    """
    registry = Registry()

    @registry.add('upper')
    def _upper(payload: Payload) -> Result:
        return payload.upper()

    async with jockey.Executor(registry).run():
        pass

    exp = 'Registry is already sealed, cannot add more actors'
    with pytest.raises(RuntimeError, match=exp):
        @registry.add('echo')
        def _echo(payload: Payload) -> Result:
            return payload


async def test_cancel_executor():
    """When executor is cancelled, executing actor is also cancelled.
    """
    registry = Registry()

    @registry.add('upper')
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(2)
        return payload.upper()

    msg = Message('upper', 'hi')

    async def _execute() -> None:
        with duration_between(.1, .2):
            async with jockey.Executor(registry).run() as executor:
                await executor.execute(msg)

    task = asyncio.create_task(_execute())
    await asyncio.sleep(.1)
    task.cancel()
    await asyncio.sleep(.1)
    assert msg.calls == [('cancel', asyncio.CancelledError)]


async def test_cancel_executor_cancel_scheduled():
    """When executor is cancelled, scheduled actors are also cancelled.
    """
    registry = Registry()

    @registry.add('upper')
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(2)
        return payload.upper()

    msg = Message('upper', 'hi')

    async def _execute() -> None:
        with duration_between(.1, .2):
            async with jockey.Executor(registry).run() as executor:
                await executor.execute(msg)
                await asyncio.sleep(.1)

    task = asyncio.create_task(_execute())
    await asyncio.sleep(.1)
    task.cancel()
    await asyncio.sleep(.1)
    assert msg.calls == [('cancel', asyncio.CancelledError)]


async def test_pulse():
    """If pulse_every is specified, pulse is sent in intervals.
    """
    registry = Registry()

    @registry.add('upper', pulse_every=.1)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.45)
        return payload.upper()

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
    assert msg.calls == [('pulse', None)] * 4 + [('ok', 'HI')]


async def test_pulse_cancel_on_failure():
    """When actor fails, pulse is cancelled.
    """
    registry = Registry()

    @registry.add('upper', pulse_every=.1)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.35)
        raise ZeroDivisionError

    msg = Message('upper', 'hi')
    async with jockey.Executor(registry).run() as executor:
        await executor.execute(msg)
        await asyncio.sleep(.1)
    exp = [('pulse', None)] * 3 + [('fail', ZeroDivisionError)]
    assert msg.calls == exp


async def test_pulse_cancel_on_cancel():
    """When actor is cancelled, pulse is also cancelled.
    """
    registry = Registry()

    @registry.add('upper', pulse_every=.1)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(2)
        return payload.upper()

    msg = Message('upper', 'hi')

    async def _execute() -> None:
        with duration_between(.30, .45):
            async with jockey.Executor(registry).run() as executor:
                await executor.execute(msg)

    task = asyncio.create_task(_execute())
    await asyncio.sleep(.35)
    task.cancel()
    await asyncio.sleep(.1)
    exp = [('pulse', None)] * 3 + [('cancel', asyncio.CancelledError)]
    assert msg.calls == exp


async def test_wait_for_nothing():
    """Test how different wait_for settings are affected by max_jobs.
    """
    registry = Registry()

    @registry.add('upper', max_jobs=5)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.1)
        return payload.upper()

    msg = Message('upper', 'hi')
    with duration_between(.3, .31):
        async with jockey.Executor(registry, max_jobs=10).run() as executor:
            with duration_between(.0, .05):
                for _ in range(14):
                    await executor.execute(msg, wait_for=jockey.WaitFor.NOTHING)
    assert msg.calls == [('ok', 'HI')] * 14


async def test_wait_for_no_pressure():
    """Test how different wait_for settings are affected by max_jobs.
    """
    registry = Registry()

    @registry.add('upper', max_jobs=20)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.1)
        return payload.upper()

    msg = Message('upper', 'hi')
    with duration_between(.2, .21):
        async with jockey.Executor(registry, max_jobs=10).run() as executor:
            with duration_between(.1, .15):
                for _ in range(14):
                    await executor.execute(msg, wait_for=jockey.WaitFor.NO_PRESSURE)
    assert msg.calls == [('ok', 'HI')] * 14


async def test_wait_for_start():
    """Test how different wait_for settings are affected by max_jobs.
    """
    registry = Registry()

    @registry.add('upper', max_jobs=5)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.1)
        return payload.upper()

    msg = Message('upper', 'hi')
    with duration_between(.3, .31):
        async with jockey.Executor(registry, max_jobs=10).run() as executor:
            with duration_between(.2, .25):
                for _ in range(14):
                    await executor.execute(msg, wait_for=jockey.WaitFor.START)
    assert msg.calls == [('ok', 'HI')] * 14


async def test_wait_for_finish():
    """Test how different wait_for settings are affected by max_jobs.
    """
    registry = Registry()

    @registry.add('upper', max_jobs=5)
    async def _upper(payload: Payload) -> Result:
        await asyncio.sleep(.1)
        return payload.upper()

    msg = Message('upper', 'hi')
    with duration_between(.3, .31):
        async with jockey.Executor(registry, max_jobs=10).run() as executor:
            with duration_between(.3, .35):
                for _ in range(3):
                    await executor.execute(msg, wait_for=jockey.WaitFor.FINISH)
    assert msg.calls == [('ok', 'HI')] * 3
