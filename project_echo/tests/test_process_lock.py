from __future__ import annotations

import os

import pytest

from sel_bot.process_lock import AlreadyRunningError, SingleInstanceLock


def test_second_lock_fails_while_first_is_active(tmp_path) -> None:
    lock_path = tmp_path / "sel_bot.pid"
    with SingleInstanceLock(lock_path):
        with pytest.raises(AlreadyRunningError):
            with SingleInstanceLock(lock_path):
                pass


def test_stale_lock_is_replaced(tmp_path) -> None:
    lock_path = tmp_path / "sel_bot.pid"
    lock_path.write_text("99999999\n", encoding="utf-8")

    with SingleInstanceLock(lock_path):
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_release_removes_owned_lock_file(tmp_path) -> None:
    lock_path = tmp_path / "sel_bot.pid"
    lock = SingleInstanceLock(lock_path)
    lock.acquire()

    assert lock_path.exists()
    lock.release()
    assert not lock_path.exists()
