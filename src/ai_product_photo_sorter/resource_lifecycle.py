"""Deterministic runtime resource cleanup for the Product Sorter engine.

The compatibility-preserved engine has several early-return paths and historically
relied on interpreter shutdown to release its SQLite connection and operation
lock. That is usually invisible in one-shot CLI runs, but it keeps files locked
on Windows and makes embedded/repeated invocations unreliable. This extension
tracks resources opened during each ``main()`` invocation and releases them in a
``finally`` block without changing the processing path or database semantics.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


_LOCAL = threading.local()


def apply_resource_lifecycle(module: Any) -> None:
    """Patch deterministic database/lock cleanup into the shared engine."""

    base_connect_db = module.connect_db
    base_operation_lock = module.OperationLock
    base_main = module.main

    def connect_db(path: Path):
        db = base_connect_db(path)
        connections = getattr(_LOCAL, "connections", None)
        if connections is not None:
            connections.append(db)
        return db

    class ManagedOperationLock(base_operation_lock):
        def __init__(self, output: Path):
            super().__init__(output)
            locks = getattr(_LOCAL, "locks", None)
            if locks is not None:
                locks.append(self)

    def main() -> int:
        previous_connections = getattr(_LOCAL, "connections", None)
        previous_locks = getattr(_LOCAL, "locks", None)
        connections: list[Any] = []
        locks: list[Any] = []
        _LOCAL.connections = connections
        _LOCAL.locks = locks
        try:
            return base_main()
        finally:
            # Close DBs before releasing the operation lock so no other process
            # can enter the operation while this process still owns DB handles.
            for db in reversed(connections):
                try:
                    db.close()
                except Exception:
                    pass
            for lock in reversed(locks):
                try:
                    lock.release()
                except Exception:
                    pass

            if previous_connections is None:
                try:
                    del _LOCAL.connections
                except AttributeError:
                    pass
            else:
                _LOCAL.connections = previous_connections

            if previous_locks is None:
                try:
                    del _LOCAL.locks
                except AttributeError:
                    pass
            else:
                _LOCAL.locks = previous_locks

    module.connect_db = connect_db
    module.OperationLock = ManagedOperationLock
    module.main = main
