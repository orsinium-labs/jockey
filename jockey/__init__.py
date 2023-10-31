"""Generic and type safe runner for asynchronous workers.
"""
from ._adapter import Adapter
from ._execute_in import ExecuteIn
from ._executor import Executor
from ._priority import Priority
from ._registry import Registry

__version__ = '1.0.0'
__all__ = [
    'Adapter',
    'ExecuteIn',
    'Executor',
    'Priority',
    'Registry',
]
