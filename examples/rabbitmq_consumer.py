"""A simple RabbitMQ consumer on top of aio_pika.
"""
from __future__ import annotations

import asyncio
import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

import aio_pika
import aio_pika.abc

import jockey

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

Payload: TypeAlias = bytes
Key: TypeAlias = str
Result: TypeAlias = None


@dataclass
class Message(jockey.Adapter[Payload, Key, Result]):
    raw: aio_pika.abc.AbstractIncomingMessage

    def get_keys(self) -> Iterator[Key]:
        yield self.raw.routing_key or ''

    async def get_payload(self) -> Payload:
        return self.raw.body

    async def on_success(self, result: Result) -> None:
        await self.raw.ack()

    async def on_failure(self, exc: Exception) -> None:
        logging.exception(exc)
        await self.raw.nack()

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        await self.raw.nack()

    async def on_no_handler(self) -> None:
        logging.error(f'unexpected routing key: {self.raw.routing_key}')


class Registry(jockey.Registry[Payload, Key, Result]):
    pass


registry = Registry()


@registry.add('')
def _root(payload: Payload) -> Result:
    print(f'RECV: {payload.decode()}')


async def main():
    parser = ArgumentParser()
    parser.add_argument('--url', default='amqp://guest:guest@127.0.0.1/')
    parser.add_argument('--queue', default='jockey_queue')
    parser.add_argument('--exchange', default='jockey_exchange')
    args = parser.parse_args()

    connection = await aio_pika.connect_robust(args.url)
    async with connection, jockey.Executor(registry).run() as executor:
        channel = await connection.channel()
        queue = await channel.declare_queue(args.queue, auto_delete=True)
        await queue.bind(args.exchange)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await executor.execute(Message(message))


if __name__ == '__main__':
    asyncio.run(main())
