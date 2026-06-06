"""Audit FINDING-BR10 / ST-14 closure (Batch 10A 2026-06-06).

``process_render`` is the worker entry-point invoked by the
``ThreadPoolExecutor`` in ``app.jobs.manager.submit_job``. ``run_render_pipeline``
already calls ``close_thread_conn()`` in its own outer ``finally`` for the
normal happy / failure paths.

But: if the pipeline dies BEFORE reaching its outer ``try`` (e.g., during
``setup_render_pipeline`` or ``prepare_output_dir`` — both run before the
try block at render_pipeline.py:433), the pipeline-level cleanup never
runs. The thread-local SQLite connection cached by ``_thread_conn`` then
lives until the worker thread is garbage-collected, which on a long-lived
process is effectively a leak.

The fix is a belt-and-suspenders ``close_thread_conn()`` in
``process_render``'s own ``finally``. Two regression tests:

1. ``close_thread_conn`` IS called even when ``run_render_pipeline`` raises
   immediately (simulating pre-pipeline death).
2. ``close_thread_conn`` IS called on the happy path too (idempotent — the
   second close after pipeline-internal cleanup is a no-op).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_metrics(monkeypatch):
    """``process_render`` increments Prometheus counters in its finally.
    The real ones bind to the global registry; swap with cheap mocks so a
    test failure doesn't depend on Prometheus availability/state."""
    from app.features.render.routers import _common

    class _NoopLabels:
        def inc(self, *a, **kw): pass
        def observe(self, *a, **kw): pass

    class _NoopMetric:
        def labels(self, **kw): return _NoopLabels()

    # _common imports these lazily inside process_render; mock the actual
    # services module so the lazy import resolves to mocks.
    import app.services.metrics as metrics
    monkeypatch.setattr(metrics, "RENDER_JOBS_TOTAL", _NoopMetric(), raising=False)
    monkeypatch.setattr(metrics, "RENDER_JOB_DURATION", _NoopMetric(), raising=False)


def _make_payload():
    """Minimal RenderRequest that satisfies pydantic — never actually used
    because we mock run_render_pipeline."""
    from app.models.schemas import RenderRequest
    return RenderRequest(
        channel_code="test",
        source_mode="local_file",
        source_video_path="C:/does-not-matter.mp4",
        output_dir="C:/test/test/upload/video_output",
    )


def test_close_thread_conn_called_when_pipeline_raises_before_own_try(monkeypatch):
    """ST-14: simulate ``setup_render_pipeline`` raising before
    ``run_render_pipeline`` reaches its outer try. The pipeline-internal
    ``close_thread_conn`` then never runs — but the new ``process_render``
    finally MUST still call it."""
    from app.features.render.routers import _common

    calls: list[str] = []

    def _boom(*args, **kwargs):
        # Mimics setup_render_pipeline raising on a malformed payload —
        # exception happens BEFORE the run_render_pipeline outer try.
        raise RuntimeError("setup_render_pipeline boom (pre-try)")

    def _record_close():
        calls.append("close_thread_conn")

    monkeypatch.setattr(_common, "run_render_pipeline", _boom)
    monkeypatch.setattr(_common, "close_thread_conn", _record_close)
    # cancel_registry.register + update_job_progress must not blow up in the
    # except branch — stub them.
    from app.jobs import cancel as cancel_registry

    class _Ev:
        def is_set(self): return False
    monkeypatch.setattr(cancel_registry, "register", lambda job_id: _Ev())
    monkeypatch.setattr(_common, "update_job_progress", lambda *a, **kw: None)

    with pytest.raises(RuntimeError, match="setup_render_pipeline boom"):
        _common.process_render("job-pre-pipeline-death", _make_payload(), resume_mode=False)

    assert calls == ["close_thread_conn"], (
        "close_thread_conn must run in process_render.finally even when "
        "run_render_pipeline raises before its own outer try. Leak window: "
        "setup_render_pipeline / prepare_output_dir raising."
    )


def test_close_thread_conn_called_on_happy_path(monkeypatch):
    """Belt-and-suspenders: the new finally also fires on the success path.
    Calling close_thread_conn twice (once inside run_render_pipeline, once
    here) is idempotent — the second call sees ``_tls.conn is None`` and
    short-circuits. This test pins that behaviour: the call IS made."""
    from app.features.render.routers import _common

    calls: list[str] = []

    def _noop_pipeline(*args, **kwargs):
        # Simulates a clean render — returns normally.
        calls.append("run_render_pipeline")

    def _record_close():
        calls.append("close_thread_conn")

    monkeypatch.setattr(_common, "run_render_pipeline", _noop_pipeline)
    monkeypatch.setattr(_common, "close_thread_conn", _record_close)

    from app.jobs import cancel as cancel_registry

    class _Ev:
        def is_set(self): return False
    monkeypatch.setattr(cancel_registry, "register", lambda job_id: _Ev())

    _common.process_render("job-happy", _make_payload(), resume_mode=False)

    assert calls == ["run_render_pipeline", "close_thread_conn"], (
        "close_thread_conn must run in process_render.finally on success "
        "too. Idempotency makes this safe; the test pins the call ordering."
    )


def test_close_thread_conn_exception_does_not_mask_pipeline_error(monkeypatch):
    """The belt-and-suspenders cleanup must NEVER eat the original exception.
    If close_thread_conn itself raises (e.g., SQLite handle in a bad state),
    the pipeline's exception still wins — we use a swallowing ``try`` so the
    outer ``raise`` in the ``except Exception`` arm of process_render still
    sees the right error."""
    from app.features.render.routers import _common

    def _pipeline_raises(*args, **kwargs):
        raise ValueError("original pipeline error")

    def _close_also_raises():
        raise RuntimeError("close_thread_conn itself blew up")

    monkeypatch.setattr(_common, "run_render_pipeline", _pipeline_raises)
    monkeypatch.setattr(_common, "close_thread_conn", _close_also_raises)
    from app.jobs import cancel as cancel_registry

    class _Ev:
        def is_set(self): return False
    monkeypatch.setattr(cancel_registry, "register", lambda job_id: _Ev())

    with pytest.raises(ValueError, match="original pipeline error"):
        _common.process_render("job-double-fault", _make_payload(), resume_mode=False)
