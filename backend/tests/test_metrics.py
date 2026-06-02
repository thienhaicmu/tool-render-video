"""test_metrics.py — Sprint 6.C.

Verifies the Prometheus instrumentation surface:
- /metrics returns 200 with the Prometheus text content-type
- /metrics body includes all registered metric names
- Counter inc() shows up in the exposition body
- Histogram observe() produces _bucket / _count / _sum lines
- Gauge set() shows up
- The no-op shim path produces 503 when prometheus_client is unavailable
- is_available() correctly reflects the import state
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


# ── /metrics endpoint ────────────────────────────────────────────────────────


class TestMetricsEndpoint:
    def test_returns_200_with_prometheus_content_type(self):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # Prometheus exposition format: text/plain; version=<x>; charset=utf-8
        # The exact version (0.0.4 in old prometheus_client, 1.0.0 in newer)
        # depends on the installed dep, so assert structure not value.
        ct = resp.headers["content-type"]
        assert ct.startswith("text/plain")
        assert "version=" in ct

    def test_body_includes_all_registered_metric_names(self):
        resp = client.get("/metrics")
        body = resp.text
        for name in (
            "render_jobs_total",
            "render_job_duration_seconds",
            "ffmpeg_invocations_total",
            "ffmpeg_duration_seconds",
            "nvenc_acquire_wait_seconds",
            "nvenc_active_sessions",
            "job_queue_pending",
            "job_queue_active",
            "db_backups_total",
        ):
            assert name in body, f"{name} missing from /metrics body"

    def test_includes_help_and_type_lines_for_each_metric(self):
        """Prometheus convention — each metric has # HELP and # TYPE."""
        resp = client.get("/metrics")
        body = resp.text
        for name in ("render_jobs_total", "ffmpeg_duration_seconds"):
            assert f"# HELP {name}" in body
            assert f"# TYPE {name}" in body


# ── Counter + Histogram observability ────────────────────────────────────────


class TestCounterIncrementsVisible:
    def test_counter_inc_reflected_in_exposition_body(self):
        from app.services.metrics import RENDER_JOBS_TOTAL
        # Pre-increment to capture the visible delta
        RENDER_JOBS_TOTAL.labels(status="succeeded").inc()
        resp = client.get("/metrics")
        body = resp.text
        # The labeled counter name with status="succeeded" must appear
        assert 'render_jobs_total{status="succeeded"}' in body

    def test_histogram_observe_produces_bucket_count_sum(self):
        from app.services.metrics import FFMPEG_DURATION
        FFMPEG_DURATION.labels(result="ok").observe(12.5)
        resp = client.get("/metrics")
        body = resp.text
        # Prometheus histogram exposition has _bucket, _count, _sum lines
        assert "ffmpeg_duration_seconds_bucket" in body
        assert 'ffmpeg_duration_seconds_count{result="ok"}' in body
        assert 'ffmpeg_duration_seconds_sum{result="ok"}' in body

    def test_gauge_set_reflected(self):
        from app.services.metrics import JOB_QUEUE_PENDING
        JOB_QUEUE_PENDING.set(7)
        resp = client.get("/metrics")
        body = resp.text
        assert "job_queue_pending 7" in body or "job_queue_pending 7.0" in body


# ── Availability flag ────────────────────────────────────────────────────────


class TestIsAvailable:
    def test_returns_true_when_prometheus_client_installed(self):
        from app.services.metrics import is_available
        # The test environment HAS prometheus_client (per requirements.txt).
        # If is_available() returned False, the rest of the suite would
        # crash on the labeled-metric calls above; this assertion documents
        # the expected env.
        assert is_available() is True


# ── 503 path ─────────────────────────────────────────────────────────────────


class TestMetricsUnavailable503:
    """When prometheus_client is missing the route returns 503.

    We don't physically uninstall the dep for the test — we patch the
    is_available() flag to simulate the degraded state, then re-exercise
    the route.
    """

    def test_returns_503_when_unavailable(self, monkeypatch):
        import app.routes.metrics as route_mod
        monkeypatch.setattr(route_mod, "is_available", lambda: False)
        resp = client.get("/metrics")
        assert resp.status_code == 503
        assert "prometheus_client not installed" in resp.text


# ── No-op shim contract ──────────────────────────────────────────────────────


class TestNoOpShim:
    """Confirms _NoOpMetric / _NoOpTimer behave like real Counter/Histogram/Gauge.

    Important so that any future deprecation of prometheus_client doesn't
    break the codebase's call sites. Direct unit test of the shim classes.
    """

    def test_noop_metric_methods_accept_args_and_return_none(self):
        from app.services.metrics import _NoOpMetric
        m = _NoOpMetric()
        assert m.labels(status="x", result="y") is m  # chainable
        assert m.inc() is None
        assert m.dec(2) is None
        assert m.set(42) is None
        assert m.observe(1.0) is None

    def test_noop_timer_context_manager(self):
        from app.services.metrics import _NoOpTimer
        with _NoOpTimer() as t:
            assert t is not None
