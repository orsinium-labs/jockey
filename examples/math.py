import asyncio
from dataclasses import dataclass
from typing import Iterator
import jockey

Payload = tuple[int, int]
Key = str
Result = float


@dataclass
class Message(jockey.Adapter[Payload, Key, Result]):
    left: int
    op: Key
    right: int

    def get_keys(self) -> Iterator[Key]:
        yield self.op

    async def get_payload(self) -> Payload:
        return (self.left, self.right)

    async def on_success(self, result: Result) -> None:
        print(f'SUCCESS: {self.left} {self.op} {self.right} = {result}')

    async def on_failure(self, exc: Exception) -> None:
        print(f'FAILURE: {self.left} {self.op} {self.right} caused {repr(exc)}')

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        print(f'CANCELED: {self.left} {self.op} {self.right}')


class Registry(jockey.Registry[Payload, Key, Result]):
    pass


registry = Registry()


@registry.add(key='+')
def _add(payload: Payload) -> Result:
    left, right = payload
    return left + right


@registry.add(key='/')
def _div(payload: Payload) -> Result:
    left, right = payload
    return left / right


@registry.add(key='-')
async def _sub(payload: Payload) -> Result:
    left, right = payload
    await asyncio.sleep(1)
    return left / right


async def main() -> None:
    async with jockey.Executor(registry).run() as executor:
        messages = [
            Message(3, '-', 2),
            Message(4, '+', 5),
            Message(3, '/', 2),
            Message(3, '/', 0),
            Message(3, '+', 0),
        ]
        for msg in messages:
            executor.schedule(msg)
            # await executor.execute(msg)

if __name__ == '__main__':
    asyncio.run(main())
