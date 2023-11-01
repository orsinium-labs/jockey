import asyncio
from dataclasses import dataclass
from typing import Iterator, Tuple

import jockey

# each math operation accepts 2 integer numbers
Payload = Tuple[int, int]
# each math operation is identified by a symbol (like "+" or "/")
Key = str
# each math operation returns a float
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
        print(f'FAILURE: {self.left} {self.op} {self.right} caused {exc!r}')

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        print(f'CANCELED: {self.left} {self.op} {self.right}')


class Registry(jockey.Registry[Payload, Key, Result]):
    pass


registry = Registry()


@registry.add('+')
def _add(payload: Payload) -> Result:
    left, right = payload
    return left + right


@registry.add('/', execute_in=jockey.ExecuteIn.PROCESS)
def _div(payload: Payload) -> Result:
    left, right = payload
    return left / right


@registry.add('-')
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
            await executor.execute(msg)

if __name__ == '__main__':
    asyncio.run(main())
