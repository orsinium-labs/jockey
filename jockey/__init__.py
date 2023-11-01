"""Generic and type safe runner for asynchronous workers.
"""
from ._adapter import Adapter, Middleware
from ._execute_in import ExecuteIn
from ._executor import Executor, RunningExecutor
from ._priority import Priority
from ._registry import Registry
from ._wait_for import WaitFor

__version__ = '1.0.0'
__all__ = [
    'Adapter',
    'ExecuteIn',
    'Executor',
    'Middleware',
    'Priority',
    'Registry',
    'RunningExecutor',
    'WaitFor',
]
