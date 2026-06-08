"""Prometheus instrumentation registry.

Sprint 6.C — centralizes counter/histogram/gauge definitions so call sites
just `from app.services.metrics import RENDER_JOBS_TOTAL` and use them. A
single import surface keeps name + label drift from happening across the
codebase.

Falls back to no-op stubs if `prometheus_client` is missing (defensive —
the dep is in requirements.txt but the import-time guard lets the app
boot even on environments where the package failed to install). The
`/metrics` endpoint reports a 503 in that degraded mode.
"""
from __future__ import annotations

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
    )
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


# ── No-op fallback so call sites never need to guard on _AVAILABLE ───────────


class _NoOpMetric:
    """Drop-in shim for Counter/Histogram/Gauge when prometheus_client is missing."""

    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs):
        return None

    def dec(self, *args, **kwargs):
        return None

    def set(self, *args, **kwargs):
        return None

    def observe(self, *args, **kwargs):
        return None

    def time(self):
        return _NoOpTimer()


class _NoOpTimer:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def is_available() -> bool:
    """True iff prometheus_client is installed + metrics are real."""
    return _AVAILABLE


# ── Metric definitions ───────────────────────────────────────────────────────

if _AVAILABLE:
    # Dedicated registry — keeps our metrics separate from any other
    # prometheus_client-using lib in the process. Tests can introspect this
    # registry without touching the global default.
    REGISTRY = CollectorRegistry()

    RENDER_JOBS_TOTAL = Counter(
        "render_jobs_total",
        "Total number of render jobs by terminal status",
        ["status"],
        registry=REGISTRY,
    )
    # Buckets sized to typical render durations: 10s (preview) → 2h (long mixes)
    RENDER_JOB_DURATION = Histogram(
        "render_job_duration_seconds",
        "Wallclock time per render job from start to terminal",
        ["status"],
        buckets=(10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200),
        registry=REGISTRY,
    )

    FFMPEG_INVOCATIONS_TOTAL = Counter(
        "ffmpeg_invocations_total",
        "FFmpeg subprocess invocations by outcome",
        ["result"],
        registry=REGISTRY,
    )
    FFMPEG_DURATION = Histogram(
        "ffmpeg_duration_seconds",
        "Single FFmpeg invocation wallclock time",
        ["result"],
        buckets=(1, 5, 15, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    NVENC_ACQUIRE_WAIT = Histogram(
        "nvenc_acquire_wait_seconds",
        "Time spent blocked on NVENC_SEMAPHORE before acquiring",
        buckets=(0.01, 0.1, 0.5, 1, 5, 15, 60),
        registry=REGISTRY,
    )
    NVENC_ACTIVE_SESSIONS = Gauge(
        "nvenc_active_sessions",
        "Currently-held NVENC encoder sessions",
        registry=REGISTRY,
    )

    JOB_QUEUE_PENDING = Gauge(
        "job_queue_pending",
        "Jobs waiting in the priority queue",
        registry=REGISTRY,
    )
    JOB_QUEUE_ACTIVE = Gauge(
        "job_queue_active",
        "Jobs currently executing",
        registry=REGISTRY,
    )

    DB_BACKUPS_TOTAL = Counter(
        "db_backups_total",
        "Online SQLite backups taken by outcome",
        ["result"],
        registry=REGISTRY,
    )

    # Audit FINDING-DB09 / ST-15 closure (Batch 10A 2026-06-06).
    # Captures the wall-time spent opening + WAL-initing a SQLite connection
    # in the two production paths:
    #   - role="db_conn":      per-call open+PRAGMA inside the HTTP path ctxmgr
    #   - role="_thread_conn": first-call open+PRAGMA on render worker threads
    #                          (cache-hit reuse is NOT observed — it's ~free)
    # Bucket choices: WAL open is typically < 5 ms on a healthy WAL; long
    # tail observations indicate contention or fsync stalls.
    DB_CONN_ACQUIRE_WAIT = Histogram(
        "db_conn_acquire_seconds",
        "Time spent opening + initializing a SQLite connection",
        ["role"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 5),
        registry=REGISTRY,
    )

else:
    REGISTRY = None  # type: ignore[assignment]

    RENDER_JOBS_TOTAL = _NoOpMetric()         # type: ignore[assignment]
    RENDER_JOB_DURATION = _NoOpMetric()       # type: ignore[assignment]
    FFMPEG_INVOCATIONS_TOTAL = _NoOpMetric()  # type: ignore[assignment]
    FFMPEG_DURATION = _NoOpMetric()           # type: ignore[assignment]
    NVENC_ACQUIRE_WAIT = _NoOpMetric()        # type: ignore[assignment]
    NVENC_ACTIVE_SESSIONS = _NoOpMetric()     # type: ignore[assignment]
    JOB_QUEUE_PENDING = _NoOpMetric()         # type: ignore[assignment]
    JOB_QUEUE_ACTIVE = _NoOpMetric()          # type: ignore[assignment]
    DB_BACKUPS_TOTAL = _NoOpMetric()          # type: ignore[assignment]
    DB_CONN_ACQUIRE_WAIT = _NoOpMetric()      # type: ignore[assignment]
