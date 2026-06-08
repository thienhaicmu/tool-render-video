"""T2.2 closure regression guard — Audit 2026-06-08 (Batch A V9-F3).

Pre-T2.2 the OpenCV motion-tracking loops in engine/motion/ had zero
cancel awareness. A user clicking Cancel during motion-aware crop
tracking waited for either max_tracking_seconds (~60s) or natural
loop completion (minutes on long videos). The cancel signal sat
queued in cancel_registry; the OpenCV code could not see it.

T2.2 (commit 2c2c201) reused the existing per-thread cancel-event
mechanism (set in part_renderer.py:162 for each render part, already
consumed by FFmpeg subprocess monitoring) and added a
``check_thread_cancel()`` raiser called at the top of each OpenCV
per-frame loop.

This file pins T2.2 with three complementary checks:

1. **Behavioural** — ``check_thread_cancel()`` raises
   ``JobCancelledError`` when the thread-local cancel event is set,
   and is a no-op (returns None) when the event is unset OR no event
   was registered.

2. **Structural** — ``check_thread_cancel`` is imported into each of
   the 5 motion modules T2.2 touched (path.py, path_scene.py,
   pixel_diff.py, crop.py, detection.py). A future refactor that
   drops one of the imports would silently break cancel for that
   loop.

3. **Adjacency** — the import + at least one call to
   ``check_thread_cancel()`` appears in each motion module. The call
   sits at the top of the per-frame loop body so the cancel poll
   arrives within ~1 frame iteration.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Behavioural — the helper itself.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_thread_cancel_event(monkeypatch):
    """Ensure no stray cancel event from a prior test bleeds into this
    one. The helper reads from a thread-local; we explicitly clear it
    via the public setter before each test."""
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        set_thread_cancel_event,
    )
    set_thread_cancel_event(None)
    yield
    set_thread_cancel_event(None)


def test_check_thread_cancel_is_noop_when_no_event_registered():
    """The default state on a fresh thread (no set_thread_cancel_event
    call yet) must be a clean no-op. Tests + direct CLI calls into
    motion modules rely on this — they don't register cancel events,
    and they must not raise."""
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        check_thread_cancel,
    )
    # Should not raise.
    check_thread_cancel()


def test_check_thread_cancel_is_noop_when_event_is_unset():
    """A registered-but-unset cancel event must not raise. The
    rendering happy path runs through here every frame; a false-raise
    here would kill every render."""
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        check_thread_cancel,
        set_thread_cancel_event,
    )
    ev = threading.Event()  # not set
    set_thread_cancel_event(ev)
    # Should not raise.
    check_thread_cancel()


def test_check_thread_cancel_raises_job_cancelled_when_event_is_set():
    """The behavioural core of T2.2: a SET cancel event raises
    JobCancelledError. The render pipeline's outer except
    JobCancelledError handler translates this into status=CANCELLED."""
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        check_thread_cancel,
        set_thread_cancel_event,
    )
    from app.jobs.cancel import JobCancelledError

    ev = threading.Event()
    ev.set()
    set_thread_cancel_event(ev)

    with pytest.raises(JobCancelledError):
        check_thread_cancel()


# ---------------------------------------------------------------------------
# 2. Structural — every motion module imports + uses the helper.
# ---------------------------------------------------------------------------


_MOTION_DIR = (
    Path(__file__).resolve().parent.parent
    / "app" / "features" / "render" / "engine" / "motion"
)

# Five modules T2.2 wired the cancel poll into. Adding a sixth motion
# module that runs an OpenCV per-frame loop without check_thread_cancel
# is the regression class this set guards against.
_MOTION_MODULES_WITH_OPENCV_LOOPS = (
    "path.py",
    "path_scene.py",
    "pixel_diff.py",
    "crop.py",
    "detection.py",
)


@pytest.mark.parametrize("module_name", _MOTION_MODULES_WITH_OPENCV_LOOPS)
def test_motion_module_imports_check_thread_cancel(module_name: str):
    """Each motion module with an OpenCV per-frame loop must import
    ``check_thread_cancel`` from ``ffmpeg_helpers``. Without the
    import, a call to the helper would be a NameError and the cancel
    poll silently disappears."""
    path = _MOTION_DIR / module_name
    source = path.read_text(encoding="utf-8-sig")

    assert "check_thread_cancel" in source, (
        f"T2.2 regression — engine/motion/{module_name} no longer "
        f"references check_thread_cancel. The OpenCV per-frame loop in "
        f"this file would become uninterruptible again. Restore the "
        f"import from app.features.render.engine.encoder.ffmpeg_helpers "
        f"AND the check_thread_cancel() call at the top of the loop."
    )


@pytest.mark.parametrize("module_name", _MOTION_MODULES_WITH_OPENCV_LOOPS)
def test_motion_module_calls_check_thread_cancel(module_name: str):
    """Defence-in-depth — the import alone isn't enough. A future
    refactor could keep the import for ``# noqa: F401`` reasons but
    drop the actual call. This test pins that the call appears
    AS A CALL SITE, not just a reference."""
    path = _MOTION_DIR / module_name
    source = path.read_text(encoding="utf-8-sig")

    # Look for the actual invocation: check_thread_cancel() with parens.
    # Tolerate optional newline/whitespace between name and parens
    # (e.g. wrapped call).
    import re
    assert re.search(r"\bcheck_thread_cancel\s*\(", source), (
        f"T2.2 regression — engine/motion/{module_name} imports "
        f"check_thread_cancel but never calls it. The OpenCV per-frame "
        f"loop's cancel poll is dead code. Add the "
        f"check_thread_cancel() call at the top of the per-frame loop "
        f"body so the poll fires once per iteration."
    )


# ---------------------------------------------------------------------------
# 3. Adjacency — helper is defined in ffmpeg_helpers (single source of truth).
# ---------------------------------------------------------------------------


def test_check_thread_cancel_lives_in_ffmpeg_helpers():
    """The helper is exposed from ffmpeg_helpers (alongside
    set_thread_cancel_event + NVENC_SEMAPHORE). Keeping all three on
    one symbol surface means there's a single source of truth for the
    thread-local cancel mechanism."""
    from app.features.render.engine.encoder import ffmpeg_helpers

    assert hasattr(ffmpeg_helpers, "check_thread_cancel"), (
        "T2.2 regression — check_thread_cancel was removed from "
        "ffmpeg_helpers. Every motion module imports it from there; "
        "moving the symbol breaks 5+ import sites at once."
    )
    assert hasattr(ffmpeg_helpers, "set_thread_cancel_event"), (
        "The companion setter must stay on the same surface — "
        "part_renderer.py:162 calls it to wire each part's cancel "
        "event into the thread-local before render starts."
    )
    assert hasattr(ffmpeg_helpers, "get_thread_cancel_event"), (
        "The getter was added in T2.2 for callers that want to query "
        "the event without raising. Keep it on the surface for "
        "symmetry with the setter."
    )
