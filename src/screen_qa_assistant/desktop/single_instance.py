from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLockFile


class SingleInstanceGuard:
    def __init__(self, lock_path: Path) -> None:
        self._lock = QLockFile(str(lock_path))
        self._lock.setStaleLockTime(0)

    def acquire(self) -> bool:
        return self._lock.tryLock(50)

    def release(self) -> None:
        if self._lock.isLocked():
            self._lock.unlock()
