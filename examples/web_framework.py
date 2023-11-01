"""A simple web framework on top of uvicorn.

While uvcorn takes care of concurrency, jockey adds a very simple routing,
simplified endpoint implementation, and type safety. It also gives some unique
features that you can't find in other web frameworks, like setting priority
for endpoints.

https://www.uvicorn.org/
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Iterator, cast

import uvicorn
from asgiref.typing import (
    ASGIReceiveCallable,
    ASGISendCallable,
    HTTPRequestEvent,
    HTTPScope,
    Scope,
)

import jockey

Body = bytes        # Payload
Path = str          # Key
Response = bytes    # Result


@dataclass
class Request(jockey.Adapter[Body, Path, Response]):
    scope: HTTPScope
    receive: ASGIReceiveCallable
    send: ASGISendCallable

    def get_keys(self) -> Iterator[Path]:
        yield self.scope['path']

    async def get_payload(self) -> Body:
        body = b''
        more_body = True
        while more_body:
            message = await self.receive()
            message = cast(HTTPRequestEvent, message)
            body += message.get('body', b'')
            more_body = message.get('more_body', False)
        return body

    async def on_success(self, body: Response) -> None:
        await self._send_response(200, body)

    async def on_failure(self, exc: Exception) -> None:
        await self._send_response(502, repr(exc).encode())

    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        await self._send_response(504, b'timeout')

    async def on_no_handler(self) -> None:
        await self._send_response(404, b'not found')

    async def _send_response(self, status: int, body: Response) -> None:
        await self.send({
            'type': 'http.response.start',
            'status': status,
            'headers': [
                (b'content-type', b'application/json'),
            ],
        })
        await self.send({
            'type': 'http.response.body',
            'body': body,
            'more_body': False,
        })


class Registry(jockey.Registry[Body, Path, Response]):
    pass


registry = Registry()


@registry.add('/')
def _root(body: Body) -> Response:
    return b'hello world!'


@registry.add('/echo/')
def _echo(body: Body) -> Response:
    return body


class Server:
    executor: jockey.RunningExecutor[Body, Path, Response]
    on_exit: Callable

    async def app(self, scope: Scope, receive, send):
        if scope['type'] == 'lifespan':
            message = await receive()

            # create executor on startup
            if message['type'] == 'lifespan.startup':
                executor = jockey.Executor(registry).run()
                self.executor = await executor.__aenter__()
                self.on_exit = executor.__aexit__
                await send({'type': 'lifespan.startup.complete'})
                return

            # stop executor on shutdown
            if message['type'] == 'lifespan.shutdown':
                await self.on_exit()
                await send({'type': 'lifespan.shutdown.complete'})
                return

        # handle the request using executor
        assert scope['type'] == 'http'
        request = Request(scope, receive, send)
        await self.executor.execute(request)


def main() -> None:
    config = uvicorn.Config(Server().app, interface='asgi3')
    server = uvicorn.Server(config)
    server.run()


if __name__ == '__main__':
    main()
