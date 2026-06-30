"""D-2-motion Phase 1 deliverable D1.3 (2026-06-30) — dispatcher contract scaffolding.

Pins the structural contract of ``motion/path.py``'s multi-scene dispatcher
so the Phase 3 detector swap (replace pixel-diff with SceneMap) cannot
silently regress the EMA state-carry semantics that production renders
depend on.

Why scaffolding (not runtime tests):
  The test venv currently lacks ``cv2`` (opencv-python), so importing
  ``motion/path.py`` fails at collection time. Rather than skip the
  contract entirely, this file uses two cv2-free techniques:

    1. AST inspection — load path.py as source, parse with ast.parse,
       assert the dispatcher's structural invariants (loop exists,
       warmup_center is assigned, multi-scene condition is checked).

    2. Content grep — read path.py / path_scene.py as text and assert
       contract-critical identifiers and call shapes are present.

  Phase 3 (with cv2 installed) extends these with runtime tests that
  actually exercise ``build_subject_path(_scene_ranges=[...])`` with
  mocked OpenCV. This file's tests stay; they catch accidental refactors
  that pass runtime tests but break the contract (e.g. "developer removed
  the warmup_center carry but tests still pass because they only test
  single-scene paths").

Contract pinned:
  C1 — Multi-scene dispatch loop exists in path.py: ``for index,
       (start_sec, end_sec) in enumerate(_scene_ranges):``
  C2 — Loop calls ``build_subject_path_scene`` per range with
       ``scene_index`` AND ``warmup_center`` kwargs
  C3 — ``warmup_center`` is updated from each scene's final crop center
       AFTER the scene returns
  C4 — Trigger condition: ``_scene_ranges and len(_scene_ranges) > 1``
       (single-range fallthrough to single-pass)
  C5 — ``build_subject_path_scene`` signature includes ``start_sec``,
       ``end_sec``, ``scene_index``, ``warmup_center``
  C6 — path_scene.py honours ``warmup_center`` by seeding
       ``smooth_cx``/``smooth_cy`` from it
  C7 — path_scene.py's docstring / comment notes "Subject identity is NOT
       carried over" — the swap MUST preserve this behaviour
  C8 — Single-scene fast path exists (when scene_ranges is None or 1 range)

Sacred Contract impact: these tests run in any venv (no cv2 needed).
They protect the CRITICAL ``motion/path.py`` file from refactors that
break the EMA contract without requiring full integration tests.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PATH_PY = _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "motion" / "path.py"
_PATH_SCENE_PY = _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "motion" / "path_scene.py"


@pytest.fixture(scope="module")
def path_py_source() -> str:
    return _PATH_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def path_scene_py_source() -> str:
    return _PATH_SCENE_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def path_py_ast(path_py_source) -> ast.Module:
    return ast.parse(path_py_source)


# ---------------------------------------------------------------------------
# Files exist
# ---------------------------------------------------------------------------


def test_path_py_exists():
    assert _PATH_PY.exists(), "motion/path.py missing — repo state broken"


def test_path_scene_py_exists():
    assert _PATH_SCENE_PY.exists(), "motion/path_scene.py missing — repo state broken"


# ---------------------------------------------------------------------------
# C1 + C4 — Multi-scene dispatch loop exists with the right trigger
# ---------------------------------------------------------------------------


def test_c1_multi_scene_dispatch_loop_present(path_py_source):
    """Pin the exact loop signature so a refactor that renames the iteration
    variables (e.g. drops scene_index numbering) is caught."""
    assert "for index, (start_sec, end_sec) in enumerate(_scene_ranges):" in path_py_source, (
        "C1 contract broken: multi-scene dispatch loop missing or renamed. "
        "Phase 3 swap MUST preserve the (start_sec, end_sec) iteration shape "
        "because SceneMap.slice() output uses the same tuple shape."
    )


def test_c4_multi_scene_trigger_condition(path_py_source):
    """The condition ``_scene_ranges and len(_scene_ranges) > 1`` decides
    between multi-scene dispatch and single-pass. A SceneMap that resolves
    to 0 or 1 ranges MUST fall through to single-pass."""
    assert "if _scene_ranges and len(_scene_ranges) > 1:" in path_py_source, (
        "C4 contract broken: multi-scene trigger condition missing or renamed."
    )


# ---------------------------------------------------------------------------
# C2 — Per-scene call signature
# ---------------------------------------------------------------------------


def test_c2_per_scene_call_carries_index_and_warmup(path_py_source):
    """``build_subject_path_scene`` MUST be called with both ``scene_index``
    AND ``warmup_center`` kwargs. If a refactor drops either, EMA continuity
    breaks at scene boundaries — the camera snaps back to frame center."""
    assert "scene_index=index" in path_py_source, "C2: scene_index kwarg dropped"
    assert "warmup_center=_warmup_center" in path_py_source, (
        "C2 contract broken: warmup_center kwarg dropped — EMA continuity lost."
    )


# ---------------------------------------------------------------------------
# C3 — warmup_center carry-forward update
# ---------------------------------------------------------------------------


def test_c3_warmup_center_updated_from_final_crop(path_py_source):
    """The dispatcher MUST update _warmup_center FROM each scene's final
    crop center BEFORE the next iteration. The pattern is:
        _last_x, _last_y = scene_centers[-1]
        _warmup_center = (_last_x + crop_w / 2.0, _last_y + crop_h / 2.0)
    """
    assert "_last_x, _last_y = scene_centers[-1]" in path_py_source, (
        "C3: final crop center extraction missing"
    )
    assert "_warmup_center = (_last_x + crop_w / 2.0, _last_y + crop_h / 2.0)" in path_py_source, (
        "C3 contract broken: warmup_center carry update missing — "
        "previous scene's final position no longer seeds next scene's EMA."
    )


# ---------------------------------------------------------------------------
# C5 — build_subject_path_scene signature shape
# ---------------------------------------------------------------------------


def test_c5_build_subject_path_scene_signature(path_scene_py_source):
    """The per-scene function MUST accept all four contract parameters.
    A signature change here breaks the dispatcher's call site."""
    # Strip a possible UTF-8 BOM (file was saved with BOM marker) before
    # handing to ast.parse.
    src = path_scene_py_source.lstrip("﻿")
    fn_def = ast.parse(src)
    target = None
    for node in ast.walk(fn_def):
        if isinstance(node, ast.FunctionDef) and node.name == "build_subject_path_scene":
            target = node
            break
    assert target is not None, "C5: build_subject_path_scene definition missing"

    arg_names = [a.arg for a in target.args.args]
    required = {"start_sec", "end_sec", "scene_index", "warmup_center"}
    missing = required - set(arg_names)
    assert not missing, (
        f"C5 contract broken: build_subject_path_scene signature missing {missing}. "
        f"Phase 3 swap MUST NOT change this signature — the dispatcher's call site "
        f"in path.py:114-118 depends on the exact kwarg names."
    )


# ---------------------------------------------------------------------------
# C6 — path_scene.py honours warmup_center
# ---------------------------------------------------------------------------


def test_c6_path_scene_seeds_ema_from_warmup_center(path_scene_py_source):
    """Inside ``build_subject_path_scene``, when ``warmup_center is not None``
    the EMA state (``smooth_cx``, ``smooth_cy``) MUST be seeded from it.
    Otherwise the dispatcher's carry is decorative — camera snaps to frame
    center at each scene boundary anyway."""
    # This pattern lives at path_scene.py:133-135 currently.
    assert "if warmup_center is not None:" in path_scene_py_source, (
        "C6: warmup_center None-check missing in path_scene.py"
    )
    assert "smooth_cx, smooth_cy = float(warmup_center[0]), float(warmup_center[1])" in path_scene_py_source, (
        "C6 contract broken: warmup_center is not unpacked into EMA state. "
        "Camera will snap to frame center at scene boundaries."
    )


# ---------------------------------------------------------------------------
# C7 — Subject identity NOT carried across scenes
# ---------------------------------------------------------------------------


def test_c7_subject_identity_not_carried_doc_comment(path_scene_py_source):
    """The architectural decision "subject identity does NOT carry over scene
    cuts" is currently documented as a comment. The Phase 3 swap MUST
    preserve this — the tracker re-locks per scene. If a refactor changes
    that behaviour, the comment will be stale.

    Looser assertion (case-insensitive substring): if the comment is
    rewritten, this test asks the engineer to consciously decide whether
    the contract changed."""
    src_lower = path_scene_py_source.lower()
    assert "subject identity is not carried" in src_lower or "subject identity not carried" in src_lower, (
        "C7 contract documentation broken: please re-verify the per-scene "
        "tracker re-lock behaviour is preserved. Read path_scene.py:130-132."
    )


# ---------------------------------------------------------------------------
# C8 — Single-scene fast path
# ---------------------------------------------------------------------------


def test_c8_single_scene_fast_path_present(path_py_source):
    """When ``_scene_ranges`` is None or has ≤1 entries, execution MUST fall
    through to the single-pass tracking implementation. The Phase 3 swap
    relies on this: when SceneMap is missing OR produces only 1 range,
    we fall back to single-pass behaviour."""
    # The fast path lives at path.py:158+ — the single-pass implementation
    # follows the multi-scene return on line 156.
    assert "return all_centers, fps" in path_py_source, (
        "C8: multi-scene path's terminating return missing"
    )
    # After the multi-scene block returns, the rest of the file IS the
    # single-pass path. Spot-check a content_type setup line that lives in
    # the single-pass path (path.py:158).
    assert "cfg = _apply_content_type_to_cfg(cfg, content_type)" in path_py_source, (
        "C8 contract broken: single-pass fallback configuration missing. "
        "Phase 3 swap MUST preserve the single-pass path for SceneMap-empty jobs."
    )


# ---------------------------------------------------------------------------
# Cross-cutting — the slice helper's output shape matches the loop's input
# ---------------------------------------------------------------------------


def test_slice_output_shape_matches_dispatcher_input():
    """The dispatcher iterates ``for index, (start_sec, end_sec) in
    enumerate(_scene_ranges)`` — expects a list of (start, end) float
    tuples. The D1.2 SceneMap.slice helper MUST produce exactly this shape."""
    from app.domain.scene_map import SceneMap, Shot

    sm = SceneMap(shots=[
        Shot(start=0.0, end=10.0),
        Shot(start=10.0, end=25.5),
    ])
    result = sm.slice(0.0, 25.5)
    # Iterate exactly the way path.py:111 does.
    for index, (start_sec, end_sec) in enumerate(result):
        assert isinstance(index, int)
        assert isinstance(start_sec, float)
        assert isinstance(end_sec, float)
        assert end_sec > start_sec


# ---------------------------------------------------------------------------
# Drop-in compatibility — pixel-diff returns the same shape
# ---------------------------------------------------------------------------


def test_pixel_diff_function_signature_matches_replacement_target():
    """Pixel-diff's ``_detect_scene_ranges_in_clip`` is the function the
    Phase 3 swap replaces. Its return shape MUST equal the slice helper's
    return shape: ``List[Tuple[float, float]]``. Verified via source
    inspection (cv2 import blocks runtime call)."""
    pixel_diff_src = (
        _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "motion" / "pixel_diff.py"
    ).read_text(encoding="utf-8")
    # The function returns `ranges or [(0.0, duration)]` at pixel_diff.py:270.
    assert "return ranges or [(0.0, duration)]" in pixel_diff_src, (
        "pixel-diff's worst-case-non-empty return shape changed. "
        "Phase 3 fallback policy assumes pixel-diff is always non-empty."
    )
    # Ranges accumulated as (start, cut) and (start, duration) — float tuples.
    assert "ranges.append((start, cut))" in pixel_diff_src, (
        "pixel-diff range append shape changed"
    )


# ---------------------------------------------------------------------------
# Phase 3 readiness — the audit's decision tree is implementable
# ---------------------------------------------------------------------------


def test_audit_recommendation_policy_a_implementable():
    """The audit recommends Policy A: SceneMap when available, fall back to
    pixel-diff when not. This test verifies both sides of the policy are
    still callable: ``SceneMap.slice`` (D1.2) and ``_detect_scene_ranges_in_clip``
    (legacy pixel-diff). Source inspection only (no runtime)."""
    # SceneMap.slice exists.
    from app.domain.scene_map import SceneMap
    assert hasattr(SceneMap, "slice"), "Policy A SceneMap side missing"

    # Pixel-diff function signature unchanged.
    pixel_diff_src = (
        _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "motion" / "pixel_diff.py"
    ).read_text(encoding="utf-8")
    assert "def _detect_scene_ranges_in_clip(video_path: str, cfg: MotionCropConfig):" in pixel_diff_src, (
        "Policy A pixel-diff fallback side: function signature changed"
    )


def test_crop_py_call_site_unchanged_since_audit():
    """The audit identifies motion/crop.py:529 as the exact line where Phase 3
    inserts the SceneMap branch. If the surrounding code changes (e.g. the
    gate variable is renamed from `_scene_aware`), the audit's line citation
    becomes stale."""
    crop_src = (
        _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "motion" / "crop.py"
    ).read_text(encoding="utf-8")
    assert "_scene_aware = cfg.scene_aware_tracking and not _fuse_window_mode" in crop_src, (
        "Audit's gate-variable citation stale; re-verify Phase 3 insertion point."
    )
    assert "scene_ranges = _detect_scene_ranges_in_clip(input_path, cfg)" in crop_src, (
        "Audit's pixel-diff call-site citation stale; re-verify Phase 3 swap target."
    )
