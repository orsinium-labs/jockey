from __future__ import annotations

from enum import Enum


class ExecuteIn(Enum):
    """Run the handler in the current thread, a thread pool, or a process pool.
    """

    MAIN = 'main'
    """The default behavior, run the handler in the current ("main") thread.

    Use it for async/await handlers or sync but very fast handlers.
    """

    THREAD = 'thread'
    """Run the handler in a thread pool.

    Use it for slow IO-bound non-async/await handlers.
    """

    PROCESS = 'process'
    """Run the handler in a process pool.

    Use it for slow CPU-bound handlers. The handler must be non-async/await.
    """
