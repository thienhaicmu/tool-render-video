"""Tests for ``app.core.tracing`` (audit A08 part 2).

workflow_trace moved from
``app.features.render.engine.pipeline.workflow_trace`` to
``app.core.tracing``. These tests verify:

1. The canonical public surface (``dl_job_start``, ``dl_job_done``,
   ``dl_job_fail``, ``_feed_render_event``, ``_RENDER_EVENT_MAP``)
   lives at the new home.
2. The legacy import path keeps resolving via the backwards-compat
   shim — so any internal code that still imports from the old path
   keeps working without an edit.
3. Both callers (the download router and the render-events emitter)
   use the new location.
"""
from __future__ import annotations

import importlib


def test_canonical_surface_at_core_tracing():
    mod = importlib.import_module("app.core.tracing")
    assert hasattr(mod, "dl_job_start")
    assert hasattr(mod, "dl_job_done")
    assert hasattr(mod, "dl_job_fail")
    assert hasattr(mod, "_feed_render_event")
    assert hasattr(mod, "_RENDER_EVENT_MAP")
    assert isinstance(mod._RENDER_EVENT_MAP, dict)
    assert mod._RENDER_EVENT_MAP, "event map must not be empty"


def test_legacy_path_is_shim_pointing_at_core():
    """``app.features.render.engine.pipeline.workflow_trace`` must
    still resolve and expose the same functions (object identity).
    """
    legacy = importlib.import_module(
        "app.features.render.engine.pipeline.workflow_trace"
    )
    canon = importlib.import_module("app.core.tracing")
    for name in ("dl_job_start", "dl_job_done", "dl_job_fail",
                 "_feed_render_event", "_RENDER_EVENT_MAP"):
        assert getattr(legacy, name) is getattr(canon, name), (
            f"{name!r} on the legacy shim is not the same object as the "
            f"canonical export — re-export is broken."
        )


def test_render_event_map_lookups_for_known_events():
    """A handful of high-traffic render events must still map to a
    workflow step + action so the trace lines stay populated.
    """
    mod = importlib.import_module("app.core.tracing")
    m = mod._RENDER_EVENT_MAP
    assert m.get("render.start")    == ("job", "job_start")
    assert m.get("render.complete") == ("job", "job_done")
    assert m.get("render.error")    == ("job", "job_fail")


def test_dl_helpers_swallow_exceptions(tmp_path, monkeypatch):
    """The download lifecycle helpers MUST NOT raise. They are called
    from background workers and any propagated exception would crash
    the worker thread silently.
    """
    mod = importlib.import_module("app.core.tracing")

    # Force every disk write to fail so we exercise the swallow path.
    def _boom(*a, **kw):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(mod, "_write_trace_line", _boom, raising=False)

    # None of these may propagate.
    mod.dl_job_start(
        "job-1",
        url="https://example.com/x",
        platform="generic",
        quality="best",
        cookies="",
    )
    mod.dl_job_done(
        "job-1",
        filename="out.mp4",
        filesize=12345,
        platform="generic",
    )
    mod.dl_job_fail("job-1", error="boom", platform="generic")
