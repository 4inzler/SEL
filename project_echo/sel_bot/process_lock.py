from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import TracebackType


class AlreadyRunningError(RuntimeError):
    """Raised when another running process already holds the lock."""


def _pid_exists(pid: int) -> bool:
    """Return True when a PID appears to be alive on this host."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class SingleInstanceLock:
    """Cross-platform single-process guard using an atomic pid file."""

    def __init__(self, lock_path: str | os.PathLike[str] | None = None) -> None:
        default_path = Path(tempfile.gettempdir()) / "sel_bot.pid"
        self.path = Path(lock_path) if lock_path else default_path
        self._fd: int | None = None

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.write(self._fd, f"{os.getpid()}\n".encode("utf-8"))
                return
            except FileExistsError:
                existing_pid = self._read_lock_pid()
                if existing_pid is not None and _pid_exists(existing_pid):
                    raise AlreadyRunningError(
                        f"Sel already running with PID {existing_pid}; lock file: {self.path}"
                    )
                # Stale or malformed lock file; remove and retry.
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass

    def release(self) -> None:
        if self._fd is None:
            return

        try:
            os.close(self._fd)
        finally:
            self._fd = None

        if self._read_lock_pid() != os.getpid():
            return

        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _read_lock_pid(self) -> int | None:
        try:
            raw_pid = self.path.read_text(encoding="utf-8").strip().splitlines()[0]
            return int(raw_pid)
        except (FileNotFoundError, IndexError, ValueError):
            return None
