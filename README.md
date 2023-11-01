# jockey

Generic Python library for running asynchronous workers. Useful for building event handlers, web frameworks, and alike. You write a simple adapter, and jockey takes care of registering handlers, routing events, running jobs concurrently, priorities, capping the max number of workers, cancellation, waiting on exit, etc.

**Features:**

* Flexible, can be used as a web framework, as an event consumer, for background job processing, for parallel computing, and much more.
* Can run jobs in asyncio event loop, threads, or processes.
* 100% type safe.
* Reliable, battle-tested, and has 100% test coverage.
* Supports job priorities and all kinds of capping of the workers' number.

If you need an event-driven framework for distributed systems, take a look at [walnats](https://github.com/orsinium-labs/walnats/). It's a type-safe batteries-included Python library on top of [nats.py](https://github.com/nats-io/nats.py) designed to be safe, fast, and reliable. Jockey is based on walnats and the projects share lots of goals and design choices and even some API.

## Usage

Let's make a simple collection of functions for handling math operations.

Most of the classes jockey provides are generic and need to be parametrized. There are 3 type variables you need to define:

* `Payload` is the input argument for handlers. It's the request for web frameworks or the message for event handlers
* `Key` is the routing key which is used for selecting a handler. If is the URL path for web frameworks or routing key for event handlers.
* `Result` is the response of a handler. It's the response for web frameworks or None for event handlers.

For convenience, let's define them as type aliases:

```python
# each math operation accepts 2 integer numbers
Payload = tuple[int, int]
# each math operation is identified by a symbol (like "+" or "/")
Key = str
# each math operation returns a float
Result = float
```

The most important component to define is an Adapter. It's a collection of callbacks that tell how to convert a raw message into a routing key and a payload and how to handle successes and failures. In our case, we'll simply `print` from all callbacks:

```python
import asyncio
from dataclasses import dataclass
from typing import Iterator
import jockey

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
```

Next, we make a registry of math operations:

```python
class Registry(jockey.Registry[Payload, Key, Result]):
    pass

registry = Registry()
```

And in this registry, we can register all math operations ("handlers"):

```python
@registry.add('+')
def _add(payload: Payload) -> Result:
    left, right = payload
    return left + right
```

You can tell jockey to execute the task in a separate process (or thread):

```python
@registry.add('/', execute_in=jockey.ExecuteIn.PROCESS)
def _div(payload: Payload) -> Result:
    left, right = payload
    return left / right
```

Or make handlers async:

```python
@registry.add('-')
async def _sub(payload: Payload) -> Result:
    left, right = payload
    await asyncio.sleep(1)
    return left / right
```

And the last thing, we make an executor and schedule messages:

```python
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
```

That's it! The output should look like this:

```yaml
SUCCESS: 4 + 5 = 9
SUCCESS: 3 + 0 = 3
SUCCESS: 3 / 2 = 1.5
FAILURE: 3 / 0 caused ZeroDivisionError('division by zero')
SUCCESS: 3 - 2 = 1.5
```

Notice that we send `Message(3, '-', 2)` first but because of `await asyncio.sleep(1)` it arrived last. It show 2 important things:

1. `executor.execute` runs all messages concurrently. So, while the first message is blocked, the rest can be processed. You canspecify for how long when you want the executor to return with the `wait_for` argument.
1. When leaving the context, the executor will block and wait for all messages to finish. Similarly, if the executor is cancelled, it will make sure to cancel all running handlers (and execute `Adapter.on_cancel`).

## More examples

The [examples](./examples/) directory has some examples that you can run yourself and see the projecti n action:

* [math.py](./examples/math.py) is the code from the Usage section above.
* [rabbitmq_consumer.py](./examples/rabbitmq_consumer.py) shows how to consume and handle messages from RabbitMQ using jockey and [aio-pika](https://github.com/mosquito/aio-pika).
* [web_framework.py](./examples/web_framework.py) shows how to write a simple web framework using jockey and [uvicorn](https://www.uvicorn.org/).

## Advanced usage

The library can do surprisingly many things but nobody would read a big wordy documentation about what and why. Instead, we provide a few examples (see above) and extensive docstrings for every public method. Hence the best way to get started is to take one of the examples, adjust it for your needs, and then have a look at docstrings of the stuff you use to see what you can and should configure.

## QnA

1. **Is it maintained?** The project is pretty much feature-complete, so there is nothing for me to commit and release daily. However, I accept contributions (see below).
1. **What if I found a bug?** Fork the project, fix the bug, write some tests, and open a Pull Request. I usually merge and release any contributions within a day.
1. **Does it have retries?** Web frameworks don't do retries and event consumers handle retries on the message broker side, so for most use cases having retries in the jockey itself is redundant. You can always implement your own retry logic by sending a new message from `Adapter.on_failure`.
