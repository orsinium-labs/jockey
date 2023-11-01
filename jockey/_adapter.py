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

        Tip: If you want to have a fallback handler that will be called if no handler
        found (instead of calling Adapter.on_no_handler), make sure to yield
        as the last key the key of that handler.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_payload(self) -> Payload:
        """Get the data to be passed into the handler.

        For a web framework, it might be a Request instance,
        and for a event handler it might be a Message instance or the message body.
        In any case, it's up to you want info you want to provide for handlers.

        Tip: Avoid returning the adapter itself or the raw message it wraps
        so that logic from Adapter.on_success and other Adapter hooks cannot be
        triggered from handlers directly. In other words, don't let handlers to
        ack or nak messages directly, let Adapter always do it.
        It's especially important if double nak may cause troubles.
        """
        raise NotImplementedError

    @abstractmethod
    async def on_success(self, result: Result) -> None:
        """Callback triggered when the handler succesfully returns a result.

        The function argument is the value returned by the handler.

        For a web framework, the result might be a Response instance,
        and on_success sends the response to the client.
        For an event handler, the response is usually None
        (unless you want to support the Request/Reply pattern)
        and on_success sends an ack (acknowledgment) into the message broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def on_failure(self, exc: Exception) -> None:
        """Callback triggered when the handler raises an exception.

        It is also called if Adapter.get_payload fails.

        The argument is the raised exception.

        In a web framework, it might render a 500 error page.
        In an event handler, it might send a nak into the message broker
        so that the event can be immediately redelivered.
        Also, it's a good idea to log the exception here.

        It will not be called for BaseException but not Exception instances,
        like asyncio.CancelledError.

        It is possible in some specific scenarios for some exceptions
        to be raised bypassing the hook. For example, if Adapter.on_success fails.
        For such situations, you should have timeouts and redeliveries configured
        in the outside system (message broker, HTTP client, or network gateway).
        """
        raise NotImplementedError

    @abstractmethod
    async def on_cancel(self, exc: asyncio.CancelledError) -> None:
        """Callback triggered when the handler is cancelled.

        It won't be triggered if cancelled during executing Adapter.on_no_handler
        or Adapter.on_failure.
        """
        raise NotImplementedError

    async def on_pulse(self) -> None:
        """Callback triggered periodically while running a handler.

        The frequency of calling the callback is configured with `pulse_every`
        argument to `Registry.add`. The first pulse is sent only when `pulse_every`
        seconds has passed, not when the handler starts. So, if the handler finishes
        sooner, no pulse might be sent.

        Since it's scheduled on the event loop, it might be delayed if there is
        a long blocking task running in the same thread as the Executor.
        To prevent this, make sure to run slow CPU-bound or non-async/await tasks
        in a separate thread or process by specifying `execute_in`.

        This callback is optional and is often used by event handlers to send
        periodic "in progress" messages back into the message broker
        so that the message won't be redelivered to another handler.
        """
        pass

    async def on_no_handler(self) -> None:
        """Callback triggered when there is no handler matching any of the keys.

        In a web framework, you might want to send a 404 response.
        In an event consumer, you might want to raise an exception
        because the service had subscribed to an event which
        it doesn't know how to handle.
        """
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
