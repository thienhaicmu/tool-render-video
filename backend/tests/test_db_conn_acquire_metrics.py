"""Audit FINDING-DB09 / ST-15 closure (Batch 10A 2026-06-06).

Both production DB-acquire paths record their open + WAL-init time into
the ``db_conn_acquire_seconds`` Prometheus histogram:

- ``db_conn``      — HTTP-path ctxmgr — observed on EVERY enter
- ``_thread_conn`` — render worker thread cache — observed only on FIRST
  acquire (or stale-handle re-open). Cache hits skip the histogram.

Tests:

1. ``db_conn`` records to role="db_conn" on every enter.
2. ``_thread_conn`` records once for the first acquire then NOT again on
   subsequent cache-hit calls within the same thread.
3. Instrumentation failure (forced ImportError on metrics module) never
   propagates — ``_observe_acquire_wait`` swallows.
"""
from __future__ import annotations

import pytest


def _get_histogram_count(role: str) -> float:
    """Return the cumulative sample count for the histogram + role."""
    from app.services.metrics import DB_CONN_ACQUIRE_WAIT
    # prometheus_client Histogram exposes `_metrics` keyed by label tuple
    # but the safe public surface is `collect()` — easier here.
    for fam in DB_CONN_ACQUIRE_WAIT.collect():
        for sample in fam.samples:
            if sample.name.endswith("_count") and sample.labels.get("role") == role:
                return sample.value
    return 0.0


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    """Point connection.py at a fresh SQLite file so tests don't share
    a global handle with the real app DB."""
    db_path = tmp_path / "metrics.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    yield db_path
    # Drop the thread-local cache so the next test gets a clean slate.
    from app.db.connection import close_thread_conn
    close_thread_conn()


def test_db_conn_records_acquire_wait(_isolated_db):
    """Every enter of ``db_conn`` increments the role='db_conn' histogram."""
    from app.db.connection import db_conn

    before = _get_histogram_count("db_conn")
    with db_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    with db_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    after = _get_histogram_count("db_conn")

    assert after - before == 2, (
        f"db_conn must observe acquire time on every enter. "
        f"Before={before}, after={after}, delta should be 2."
    )


def test_thread_conn_records_first_acquire_only(_isolated_db):
    """``_thread_conn`` first call opens + observes. Subsequent calls in
    the same thread reuse the cached handle and do NOT observe (the cache
    hit is essentially free)."""
    from app.db.connection import _thread_conn, close_thread_conn

    # Start from a clean cache so the first call is a real open.
    close_thread_conn()

    before = _get_histogram_count("_thread_conn")
    c1 = _thread_conn()        # FIRST: opens + observes
    c2 = _thread_conn()        # CACHE HIT: skips observe
    c3 = _thread_conn()        # CACHE HIT: skips observe
    after = _get_histogram_count("_thread_conn")

    assert c1 is c2 is c3, "Thread-local cache must return the same handle"
    assert after - before == 1, (
        f"_thread_conn must observe acquire only on first open / stale "
        f"re-open. before={before}, after={after}, delta should be 1."
    )


def test_observe_acquire_wait_is_failure_tolerant(monkeypatch):
    """If ``app.services.metrics`` import fails (e.g., during a partial
    install), ``_observe_acquire_wait`` must swallow rather than break
    the DB acquire path."""
    from app.db import connection as conn_mod

    # Force the lazy import to blow up.
    import sys
    saved = sys.modules.pop("app.services.metrics", None)
    try:
        sys.modules["app.services.metrics"] = None  # type: ignore[assignment]
        # Must not raise.
        conn_mod._observe_acquire_wait("db_conn", 0.001)
        conn_mod._observe_acquire_wait("_thread_conn", 0.001)
    finally:
        sys.modules.pop("app.services.metrics", None)
        if saved is not None:
            sys.modules["app.services.metrics"] = saved


# ---------------------------------------------------------------------------
# DB_TIMEOUT configurable (Sprint B-1)
# ---------------------------------------------------------------------------

def test_db_timeout_default_is_30():
    """DB_TIMEOUT defaults to 30 when DB_TIMEOUT env var is absent."""
    import importlib
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.DB_TIMEOUT == 30


def test_db_timeout_respects_env(monkeypatch):
    """DB_TIMEOUT reads the DB_TIMEOUT env var when present."""
    monkeypatch.setenv("DB_TIMEOUT", "60")
    import importlib
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.DB_TIMEOUT == 60
