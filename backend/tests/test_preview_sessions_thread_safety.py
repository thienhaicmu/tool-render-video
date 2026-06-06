"""Thread-safety tests for _PREVIEW_SESSIONS (audit FINDING-BR01).

Before Batch 2, the dict was mutated from at least four code paths without
any synchronization:
- _save_session (write + nested eviction)
- _load_session (write on disk-fallback rehydrate)
- _cleanup_preview_session (delete + disk rmtree)
- evict_stale_preview_sessions (bulk delete via _cleanup_preview_session)

The race window is: WS subscriber rehydrates from disk while the eviction
loop pops the same key — pre-fix this could produce KeyError or a stale
in-memory entry. The fix wraps every read/write in an RLock.

These tests stress the public surface with concurrent workers and assert
no exception escapes and the dict shape stays sane.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app.features.render.engine.preview import session_service as ss


@pytest.fixture(autouse=True)
def _reset_sessions():
    """Each test starts with an empty _PREVIEW_SESSIONS."""
    with ss._PREVIEW_SESSIONS_LOCK:
        ss._PREVIEW_SESSIONS.clear()
    yield
    with ss._PREVIEW_SESSIONS_LOCK:
        ss._PREVIEW_SESSIONS.clear()


def _make_session_data(tmp_path: Path, sid: str) -> dict:
    work_dir = tmp_path / sid
    work_dir.mkdir(parents=True, exist_ok=True)
    return {
        "video_path": str(tmp_path / f"{sid}.mp4"),
        "duration": 10.0,
        "title": sid,
        "work_dir": str(work_dir),
        "created_at": time.time(),
    }


def test_save_and_cleanup_under_concurrency(tmp_path: Path):
    """N writer threads + N deleter threads must not raise or leave torn state."""
    N = 40
    errors: list[BaseException] = []

    def writer(sid: str):
        try:
            ss._save_session(sid, _make_session_data(tmp_path, sid))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def deleter(sid: str):
        try:
            ss._cleanup_preview_session(sid)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads: list[threading.Thread] = []
    for i in range(N):
        sid = f"s{i:03d}"
        threads.append(threading.Thread(target=writer, args=(sid,)))
        # Schedule a deleter for the same SID after a tiny delay so the
        # threads race the writer for the dict slot.
        threads.append(threading.Thread(target=deleter, args=(sid,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)
        assert not t.is_alive(), "thread hung — possible deadlock"

    assert not errors, f"exceptions raised under concurrency: {errors!r}"

    # Final state: every entry must be a dict (no torn writes).
    with ss._PREVIEW_SESSIONS_LOCK:
        for sid, data in ss._PREVIEW_SESSIONS.items():
            assert isinstance(data, dict), f"torn entry at {sid!r}: {type(data)}"
            assert "created_at" in data


def test_evict_during_save_does_not_raise(tmp_path: Path):
    """An eviction sweep interleaved with new saves must not raise.

    Pre-fix this was the textbook race: evict iterates → cleanup pops →
    save's `min()` on a now-empty dict can raise ValueError.
    """
    N = 60
    errors: list[BaseException] = []
    stop = threading.Event()

    def evictor():
        while not stop.is_set():
            try:
                ss.evict_stale_preview_sessions()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            time.sleep(0.001)

    def writer(sid: str):
        try:
            # Use an old created_at so evictor may pick it up immediately.
            data = _make_session_data(tmp_path, sid)
            data["created_at"] = 0.0
            ss._save_session(sid, data)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    ev_thread = threading.Thread(target=evictor, daemon=True)
    ev_thread.start()
    try:
        writer_threads = [threading.Thread(target=writer, args=(f"e{i:03d}",)) for i in range(N)]
        for t in writer_threads:
            t.start()
        for t in writer_threads:
            t.join(timeout=15.0)
            assert not t.is_alive()
    finally:
        stop.set()
        ev_thread.join(timeout=2.0)

    assert not errors, f"exceptions raised under eviction race: {errors!r}"


def test_load_during_cleanup_no_keyerror(tmp_path: Path):
    """Concurrent _load_session + _cleanup_preview_session on the same SID
    must not raise — both are valid in any order; either returns the data
    or None / no-op respectively.
    """
    N = 80
    errors: list[BaseException] = []

    sid = "shared-sid"
    ss._save_session(sid, _make_session_data(tmp_path, sid))

    def loader():
        try:
            ss._load_session(sid)  # may return dict or None depending on race
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def deleter():
        try:
            ss._cleanup_preview_session(sid)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = []
    for _ in range(N):
        threads.append(threading.Thread(target=loader))
        threads.append(threading.Thread(target=deleter))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)
        assert not t.is_alive()

    assert not errors, f"exceptions raised on load/cleanup race: {errors!r}"


def test_lock_is_reentrant():
    """Sanity: the documented RLock must allow the nested
    _save_session → _cleanup_preview_session path to acquire from one thread
    without deadlocking.
    """
    # Acquire once, then call a function that re-acquires. RLock allows this.
    with ss._PREVIEW_SESSIONS_LOCK:
        # _cleanup_preview_session re-enters the lock on the same thread.
        ss._cleanup_preview_session("nope-not-present")
