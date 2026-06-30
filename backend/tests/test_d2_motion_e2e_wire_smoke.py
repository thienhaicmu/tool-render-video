"""D-2-motion end-to-end wire smoke test (2026-06-30).

Validates the producer→consumer wire built across D-2-thin + D-2-snap +
D-2-motion (Phases 1+2+3+default flip):

  scene_map_stage produces SceneMap (cached in jobs.scene_map_json)
        │
        ▼
  part_render_encode loads SceneMap from DB (Phase 3 wire)
        │
        ▼
  clip_renderer.render_part_smart forwards scene_map kwarg
        │
        ▼
  render_motion_aware_crop: MOTION_USE_SCENE_MAP=1 + scene_map present
        │                  → SceneMap.slice(start, end) picked
        ▼
  Policy A fallback: pixel-diff runs when SceneMap empty / missing /
                     env var disabled

Strategy
  Pure mock-based. NO real cv2.VideoCapture, NO real FFmpeg, NO real
  scene_detector. The render_motion_aware_crop function is HEAVY (opens
  video, runs OpenCV pipeline, spawns FFmpeg) so we test the Policy A
  gate decision in isolation via SceneMap.slice() contract + the
  pixel-diff symbol used as the fallback target.

What it catches
  - SceneMap.slice() return shape regression vs pixel-diff expectations
  - Default env value regression (MOTION_USE_SCENE_MAP flip from 1 → 0)
  - clip_renderer drops scene_map kwarg → motion/crop.py gets None
  - part_render_encode skips SceneMap load → motion/crop.py runs
    pixel-diff even when SceneMap exists in DB

What it does NOT catch
  - Visual quality of subject tracking with SceneMap boundaries
  - NVENC encode path interactions
  - Multi-clip multi-job real workflows
"""
from __future__ import annotations

import inspect
import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_scene_map():
    """A realistic 3-shot SceneMap that the scene_map_stage might persist
    for a 60-second clip from a 2-hour source."""
    from app.domain.scene_map import SceneMap, Shot
    return SceneMap(
        shots=[
            Shot(start=10.0, end=22.5),    # shot 1 inside the window
            Shot(start=22.5, end=45.0),    # shot 2 fully inside
            Shot(start=45.0, end=70.0),    # shot 3 partially outside
        ],
        source_fps=30.0,
        total_duration_sec=7200.0,
    )


# ---------------------------------------------------------------------------
# Smoke 1 — MOTION_USE_SCENE_MAP default ON after the flip
# ---------------------------------------------------------------------------


def test_motion_use_scene_map_default_is_on(monkeypatch):
    """Phase 3 default-flip (commit 50cefcd) set MOTION_USE_SCENE_MAP=1.
    A render with no env var set MUST default to the SceneMap path."""
    # Strip every override of the flag.
    monkeypatch.delenv("MOTION_USE_SCENE_MAP", raising=False)
    # The default in motion/crop.py reads this env var with default "1".
    src_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine" / "motion" / "crop.py"
    )
    src = src_path.read_text(encoding="utf-8")
    # Pin the default in the source.
    assert 'os.getenv("MOTION_USE_SCENE_MAP", "1")' in src, (
        "Default flip regressed — MOTION_USE_SCENE_MAP no longer defaults to '1'."
    )


# ---------------------------------------------------------------------------
# Smoke 2 — SceneMap.slice() output is drop-in compatible with pixel-diff
# ---------------------------------------------------------------------------


def test_slice_output_matches_detect_scene_ranges_shape(synthetic_scene_map):
    """The motion/crop.py gate hands SceneMap.slice() OR
    _detect_scene_ranges_in_clip output to the dispatcher. Both must
    return the same shape: list of (start, end) float tuples in
    source-global seconds."""
    # SceneMap side.
    sliced = synthetic_scene_map.slice(0.0, 100.0)
    assert isinstance(sliced, list)
    for entry in sliced:
        assert isinstance(entry, tuple) and len(entry) == 2
        assert isinstance(entry[0], float) and isinstance(entry[1], float)
        assert entry[1] > entry[0]

    # Pixel-diff side — pin the return-shape contract via source inspection
    # (the function imports cv2 at call time so we don't instantiate it here).
    pd_src = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine" / "motion" / "pixel_diff.py"
    ).read_text(encoding="utf-8")
    assert "ranges: List[Tuple[float, float]]" in pd_src, (
        "Pixel-diff return shape regressed — would break the Policy A fallback chain"
    )


# ---------------------------------------------------------------------------
# Smoke 3 — render_motion_aware_crop accepts scene_map kwarg
# ---------------------------------------------------------------------------


def test_render_motion_aware_crop_accepts_scene_map_kwarg():
    """Phase 3 added the kwarg with default None. clip_renderer +
    part_render_encode rely on this signature."""
    from app.features.render.engine.motion.crop import render_motion_aware_crop
    sig = inspect.signature(render_motion_aware_crop)
    assert "scene_map" in sig.parameters, (
        "render_motion_aware_crop dropped scene_map kwarg — Phase 3 wire broken"
    )
    assert sig.parameters["scene_map"].default is None, (
        "scene_map default must be None for Sacred Contract #2"
    )


def test_render_part_smart_accepts_and_forwards_scene_map():
    """clip_renderer.render_part_smart accepts the kwarg AND forwards it
    via the scene_map=scene_map line at the render_motion_aware_crop call."""
    from app.features.render.engine.encoder import clip_renderer
    sig = inspect.signature(clip_renderer.render_part_smart)
    assert "scene_map" in sig.parameters
    # Source-level grep — pin the forwarding call. Cheap and durable.
    src = inspect.getsource(clip_renderer.render_part_smart)
    assert "scene_map=scene_map" in src, (
        "render_part_smart accepts scene_map but doesn't forward it to "
        "render_motion_aware_crop — wire is incomplete"
    )


# ---------------------------------------------------------------------------
# Smoke 4 — part_render_encode loads SceneMap and forwards
# ---------------------------------------------------------------------------


def test_part_render_encode_loads_scene_map_for_non_fused_path():
    """The Phase 3 wire-in loads SceneMap once at the top of the encode
    block (before the fused/non-fused if/else) and passes it via
    scene_map=_scene_map_obj at the render_part_smart call."""
    pre_src = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine" / "stages" / "part_render_encode.py"
    ).read_text(encoding="utf-8")
    # Load site.
    assert "from app.db.jobs_repo import get_scene_map" in pre_src
    assert "from app.domain.scene_map import SceneMap" in pre_src
    assert "_sm_blob = get_scene_map(ctx.job_id)" in pre_src
    assert "SceneMap.from_json(_sm_blob)" in pre_src
    # Forwarding call.
    assert "scene_map=_scene_map_obj" in pre_src, (
        "part_render_encode loads SceneMap but doesn't forward to "
        "render_part_smart — wire incomplete"
    )
    # Non-fused path only (fused mode is force-OFF for scene-aware tracking).
    assert "not fuse_active" in pre_src, (
        "SceneMap load should be gated to non-fused mode"
    )


# ---------------------------------------------------------------------------
# Smoke 5 — Policy A fallback when SceneMap missing / empty
# ---------------------------------------------------------------------------


def test_policy_a_fallback_to_pixel_diff_when_scene_map_empty(synthetic_scene_map):
    """SceneMap.slice() on an empty window returns []. Policy A says:
    motion/crop.py falls back to _detect_scene_ranges_in_clip when
    SceneMap.slice() returns falsy. Verified via source inspection."""
    # Empty window.
    assert synthetic_scene_map.slice(1000.0, 2000.0) == [], (
        "Slice should be empty when window is past all shots"
    )

    crop_src = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine" / "motion" / "crop.py"
    ).read_text(encoding="utf-8")
    # The Policy A fallback chain.
    assert "scene_map.slice(_slice_start, _slice_end) or None" in crop_src, (
        "Policy A short-circuit (slice() or None) missing — empty slice no longer "
        "triggers pixel-diff fallback"
    )
    assert "scene_ranges = _detect_scene_ranges_in_clip(input_path, cfg)" in crop_src, (
        "Pixel-diff fallback call missing — Policy A chain broken"
    )


# ---------------------------------------------------------------------------
# Smoke 6 — Policy A also fallbacks when env var is OFF
# ---------------------------------------------------------------------------


def test_policy_a_fallback_when_env_var_off():
    """MOTION_USE_SCENE_MAP=0 disables the SceneMap path entirely, even
    when scene_map kwarg is provided. Pixel-diff runs (rollback path)."""
    crop_src = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine" / "motion" / "crop.py"
    ).read_text(encoding="utf-8")
    # The double-condition gate.
    assert 'os.getenv("MOTION_USE_SCENE_MAP", "1") == "1" and scene_map is not None' in crop_src, (
        "Gate logic regressed — should be (env_var_on AND scene_map_present)"
    )


# ---------------------------------------------------------------------------
# Smoke 7 — round-trip via DB column
# ---------------------------------------------------------------------------


def test_scene_map_round_trip_through_jobs_repo(tmp_path, monkeypatch, synthetic_scene_map):
    """The producer (scene_map_stage) persists via update_scene_map() ;
    the consumer (part_render_encode) reads via get_scene_map() and
    deserialises via SceneMap.from_json(). Verify the round-trip works
    against a real (temp) SQLite DB."""
    db_path = tmp_path / "smoke.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()

    # Seed a job row.
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status, stage, "
            "progress_percent, message, payload_json, result_json) "
            "VALUES (?, 'render', 'test', 'running', 'rendering', 50, '', '{}', '{}')",
            ("smoke-d2-motion",),
        )
        conn.commit()
    finally:
        conn.close()

    # Producer side.
    from app.db.jobs_repo import update_scene_map, get_scene_map
    update_scene_map("smoke-d2-motion", synthetic_scene_map.to_json())

    # Consumer side.
    raw = get_scene_map("smoke-d2-motion")
    assert raw is not None
    from app.domain.scene_map import SceneMap
    restored = SceneMap.from_json(raw)
    assert restored is not None
    assert restored.shot_count() == 3
    # Slicing the restored map produces the same shape as the original.
    assert restored.slice(0.0, 100.0) == synthetic_scene_map.slice(0.0, 100.0)


# ---------------------------------------------------------------------------
# Smoke 8 — Slice produces ranges that motion/path.py dispatcher accepts
# ---------------------------------------------------------------------------


def test_slice_output_consumable_by_dispatcher_loop(synthetic_scene_map):
    """The dispatcher in motion/path.py iterates
    ``for index, (start_sec, end_sec) in enumerate(_scene_ranges):``
    Pin the consumability of slice() output via that exact iteration."""
    sliced = synthetic_scene_map.slice(0.0, 100.0)
    # Mimic the dispatcher's exact unpacking.
    seen: list = []
    for index, (start_sec, end_sec) in enumerate(sliced):
        seen.append((index, start_sec, end_sec))
    assert len(seen) == 3
    assert seen[0][0] == 0
    assert seen[-1][1] > 0
