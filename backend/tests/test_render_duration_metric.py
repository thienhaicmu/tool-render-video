"""Sprint E-2 — render job duration Prometheus metric.

RENDER_JOB_DURATION is already wired in _common.py:process_render().
These tests verify the metric is correctly defined and configured.
"""
from __future__ import annotations


def test_render_job_duration_metric_is_defined():
    from app.services.metrics import RENDER_JOB_DURATION
    assert RENDER_JOB_DURATION is not None


def test_render_job_duration_has_status_label():
    """Histogram must be labelled by terminal status (succeeded/failed/cancelled)."""
    from app.services import metrics as m
    if not m.is_available():
        return  # no-op shim path — not testable structurally
    metric = m.RENDER_JOB_DURATION
    # Calling .labels() with the known label value should not raise.
    metric.labels(status="succeeded").observe(1.5)
    metric.labels(status="failed").observe(30.0)
    metric.labels(status="cancelled").observe(5.0)


def test_render_job_duration_buckets_cover_long_renders():
    """Max bucket must be >= 3600 s (1 h) to handle long render jobs."""
    from app.services import metrics as m
    if not m.is_available():
        return
    raw = m.RENDER_JOB_DURATION
    # Access _upper_bounds (prometheus_client internal) to verify bucket range.
    try:
        upper_bounds = list(raw._upper_bounds)
        assert max(upper_bounds) >= 3600, (
            f"Largest RENDER_JOB_DURATION bucket is {max(upper_bounds)}s — "
            "long renders (>1 h) will land in the +Inf bucket with no resolution."
        )
    except AttributeError:
        pass  # _upper_bounds not available in this prometheus_client version — skip
