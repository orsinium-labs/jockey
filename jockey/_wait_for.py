from enum import Enum, auto


class WaitFor(Enum):
    """Used by Executor.execute to decide when to return.
    """

    NOTHING = auto()
    """Return as soon as the handler execution is scheduled.

    It is enough to be sure that the message is eventually handled
    but you don't know when. It may lead to your service fetching more messages
    than it can handle, and you don't want to do that if you run multiple instances.
    """

    NO_PRESSURE = auto()
    """Wait until the number of running jobs is below the global max_jobs limit.

    It is good enough for a basic back pressure, especially if you have only one
    or a few handlers or these handlers don't have a max_jobs limit of their own.
    Otherwise, it is possible that the message may still need to wait until
    a job for this specific handler finishes.
    """

    START = auto()
    """Wait until the handler starts and only then return.

    In this scenario, you know for sure that the message won't wait to be
    picked up by the handler. However, you may have to wait quite a bit.
    """

    FINISH = auto()
    """Wait until the handler finishes processing the message.

    It includes waiting for the Adapter callbacks to be executed and everything else.
    The highest guarantee, the longest wait. It makes sense to use it if you don't
    want to rely on back pressure provided by the library and instead want to supervise
    the executing jobs yourself. Or if you want to process messages sequentially.
    """
