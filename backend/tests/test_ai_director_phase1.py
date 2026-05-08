"""
test_ai_director_phase1.py — AI Director Phase 1 integration tests.

All tests are pure-Python: no video rendering, no CUDA, no cloud API keys.
Optional AI libraries (sentence-transformers, faiss, librosa, mediapipe)
are allowed to be missing — tests must pass without them.

Audit reference: docs/review/render_audit.md — H. AI Architecture Direction
"""
from __future__ import annotations

import types
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_request(**kwargs):
    """Return a minimal SimpleNamespace render request."""
    defaults = {
        "ai_director_enabled": True,
        "ai_mode": "viral_tiktok",
        "ai_auto_cut": True,
        "ai_target_duration": None,
        "ai_use_semantic_hooks": True,
        "ai_use_rag_memory": False,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


_SAMPLE_CHUNKS = [
    {"start": 0.0,  "end": 5.0,  "text": "nobody tells you this secret"},
    {"start": 5.5,  "end": 10.0, "text": "most people get this wrong every time"},
    {"start": 10.5, "end": 65.0, "text": "here is why you need to stop doing this"},
    {"start": 65.5, "end": 90.0, "text": "the truth is simple and clear for everyone"},
]

_SAMPLE_SCENES = [
    {"start": 0.0, "end": 30.0, "motion_score": 80},
    {"start": 30.0, "end": 60.0, "motion_score": 60},
    {"start": 60.0, "end": 90.0, "motion_score": 90},
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. AI disabled → returns None immediately
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_disabled_returns_none():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_request(ai_director_enabled=False)
    result = create_ai_edit_plan(req, {"job_id": "test"})
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Hook scoring — viral phrase > generic phrase
# ─────────────────────────────────────────────────────────────────────────────

def test_hook_score_strong_beats_weak():
    from app.ai.analyzers.hook_analyzer import score_hook_text

    strong = score_hook_text("nobody tells you this")
    weak = score_hook_text("hello world")
    assert strong > weak, f"Expected strong ({strong}) > weak ({weak})"


def test_hook_score_clamped_to_0_100():
    from app.ai.analyzers.hook_analyzer import score_hook_text

    for text in ("", "x", "nobody tells you this secret truth stop doing"):
        s = score_hook_text(text)
        assert 0.0 <= s <= 100.0, f"Score {s} out of [0, 100] for {text!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Semantic hook path — safe fallback when library missing
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_hook_fallback_safe():
    from app.ai.analyzers.hook_analyzer import (
        is_semantic_hook_available,
        score_hook_text_semantic,
    )

    result = score_hook_text_semantic("nobody tells you this")
    if is_semantic_hook_available():
        assert result is not None
        assert 0.0 <= result <= 100.0
    else:
        assert result is None  # safe None, no exception


# ─────────────────────────────────────────────────────────────────────────────
# 4. Transcript normalization — dict / object / plain-text inputs
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_normalization_dict_list():
    from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks

    chunks = normalize_transcript_chunks(_SAMPLE_CHUNKS)
    assert len(chunks) == len(_SAMPLE_CHUNKS)
    for c in chunks:
        assert "start" in c and "end" in c and "text" in c
        assert "word_count" in c and "speech_density" in c


def test_transcript_normalization_object_list():
    from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks

    class Block:
        def __init__(self, start, end, text):
            self.start = start
            self.end = end
            self.text = text

    blocks = [Block(0.0, 5.0, "nobody tells you this"), Block(5.5, 10.0, "stop doing this")]
    chunks = normalize_transcript_chunks(blocks)
    assert len(chunks) == 2
    assert chunks[0]["text"] == "nobody tells you this"


def test_transcript_normalization_plain_text():
    from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks

    chunks = normalize_transcript_chunks("This is just plain text with no timing info.")
    assert len(chunks) == 1
    assert "plain text" in chunks[0]["text"]


def test_transcript_normalization_srt_string():
    from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks

    srt = (
        "1\n00:00:00,000 --> 00:00:05,000\nnobody tells you this\n\n"
        "2\n00:00:05,500 --> 00:00:10,000\nstop doing this\n\n"
    )
    chunks = normalize_transcript_chunks(srt)
    assert len(chunks) == 2
    assert chunks[0]["start"] == pytest.approx(0.0)
    assert chunks[1]["end"] == pytest.approx(10.0)


def test_transcript_normalization_empty_returns_empty():
    from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks

    assert normalize_transcript_chunks(None) == []
    assert normalize_transcript_chunks([]) == []
    assert normalize_transcript_chunks("") == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. Silence penalty increases with larger gaps
# ─────────────────────────────────────────────────────────────────────────────

def test_silence_penalty_increases_with_gaps():
    from app.ai.analyzers.silence_analyzer import estimate_silence_penalty

    dense = [
        {"start": 0.0, "end": 5.0},
        {"start": 5.1, "end": 10.0},
        {"start": 10.2, "end": 15.0},
    ]
    sparse = [
        {"start": 0.0, "end": 2.0},
        {"start": 8.0, "end": 10.0},   # 6s gap
        {"start": 18.0, "end": 20.0},  # 8s gap
    ]
    p_dense = estimate_silence_penalty(dense)
    p_sparse = estimate_silence_penalty(sparse)
    assert p_sparse > p_dense, f"Sparse penalty ({p_sparse}) should exceed dense ({p_dense})"


def test_silence_penalty_single_chunk_returns_zero():
    from app.ai.analyzers.silence_analyzer import estimate_silence_penalty

    assert estimate_silence_penalty([{"start": 0.0, "end": 5.0}]) == 0.0


def test_silence_penalty_no_gaps_is_zero():
    from app.ai.analyzers.silence_analyzer import estimate_silence_penalty

    chunks = [
        {"start": 0.0, "end": 5.0},
        {"start": 5.0, "end": 10.0},
    ]
    assert estimate_silence_penalty(chunks) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 6. AI Director returns valid AIEditPlan with transcript chunks
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_director_returns_valid_edit_plan_with_transcript():
    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.director.edit_plan_schema import AIEditPlan

    req = _make_request()
    context = {
        "job_id": "test-job-1",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "scenes": _SAMPLE_SCENES,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert isinstance(plan, AIEditPlan)
    assert plan.enabled is True
    assert plan.mode == "viral_tiktok"
    assert isinstance(plan.selected_segments, list)
    assert isinstance(plan.warnings, list)
    assert isinstance(plan.fallback_used, bool)


def test_ai_director_plan_to_dict_has_all_keys():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_request()
    context = {"job_id": "test", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None

    d = plan.to_dict()
    assert "enabled" in d
    assert "mode" in d
    assert "selected_segments" in d
    assert "subtitle" in d
    assert "camera" in d
    assert "warnings" in d
    assert "fallback_used" in d


# ─────────────────────────────────────────────────────────────────────────────
# 7. Missing transcript → fallback_used=True, still returns a plan
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_transcript_falls_back_safely():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_request()
    context = {
        "job_id": "test-no-transcript",
        "scenes": _SAMPLE_SCENES,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    # Should still return a plan (scene fallback), not None
    assert plan is not None
    assert plan.fallback_used is True
    assert "no_transcript_available" in plan.warnings


# ─────────────────────────────────────────────────────────────────────────────
# 8. Missing transcript AND scenes → empty segments, safe result
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_transcript_and_scenes_returns_safe_result():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_request()
    context = {"job_id": "test-empty", "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.fallback_used is True
    assert isinstance(plan.selected_segments, list)


# ─────────────────────────────────────────────────────────────────────────────
# 9. AI mode config — all known modes return valid config dicts
# ─────────────────────────────────────────────────────────────────────────────

def test_all_ai_modes_return_valid_config():
    from app.ai.config.ai_modes import VALID_AI_MODES, get_mode_config

    for mode in VALID_AI_MODES:
        cfg = get_mode_config(mode)
        assert "preferred_duration_min" in cfg
        assert "preferred_duration_max" in cfg
        assert "subtitle_tone" in cfg
        assert "camera_behavior" in cfg
        assert cfg["preferred_duration_min"] < cfg["preferred_duration_max"]


def test_unknown_mode_falls_back_to_viral_tiktok():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("nonexistent_mode_xyz")
    assert cfg["subtitle_tone"] == "hype"  # viral_tiktok default


# ─────────────────────────────────────────────────────────────────────────────
# 10. Imports are safe when optional AI libs are missing
# ─────────────────────────────────────────────────────────────────────────────

def test_director_imports_safe_without_optional_libs():
    # These must not raise regardless of which optional libs are installed.
    from app.ai.director import edit_plan_schema  # noqa: F401
    from app.ai.director import ai_director       # noqa: F401
    from app.ai.director import clip_selector     # noqa: F401
    from app.ai.config import ai_modes            # noqa: F401
    from app.ai.analyzers import transcript_analyzer  # noqa: F401
    from app.ai.analyzers import silence_analyzer     # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 11. Clip selector — direct unit tests
# ─────────────────────────────────────────────────────────────────────────────

def test_clip_selector_returns_list():
    from app.ai.director.clip_selector import select_ai_segments
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    result = select_ai_segments(
        chunks=_SAMPLE_CHUNKS,
        scenes=_SAMPLE_SCENES,
        duration=90.0,
        mode_config=cfg,
    )
    assert isinstance(result, list)


def test_clip_selector_empty_input_returns_empty():
    from app.ai.director.clip_selector import select_ai_segments
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    result = select_ai_segments(
        chunks=[],
        scenes=[],
        duration=0.0,
        mode_config=cfg,
    )
    assert result == []


def test_clip_selector_segments_have_required_fields():
    from app.ai.director.clip_selector import select_ai_segments
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    results = select_ai_segments(
        chunks=_SAMPLE_CHUNKS,
        scenes=_SAMPLE_SCENES,
        duration=90.0,
        mode_config=cfg,
    )
    for r in results:
        assert "start" in r
        assert "end" in r
        assert "score" in r
        assert "reason" in r
        assert "source" in r
        assert 0.0 <= r["score"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 12. RenderRequest schema has all AI director fields
# ─────────────────────────────────────────────────────────────────────────────

def test_render_request_has_ai_director_fields():
    from app.models.schemas import RenderRequest

    req = RenderRequest()
    assert hasattr(req, "ai_director_enabled")
    assert req.ai_director_enabled is False  # default must be False (no regression)
    assert hasattr(req, "ai_mode")
    assert hasattr(req, "ai_auto_cut")
    assert hasattr(req, "ai_target_duration")
    assert hasattr(req, "ai_use_semantic_hooks")
    assert hasattr(req, "ai_use_rag_memory")


def test_render_request_ai_director_disabled_by_default():
    """Old render requests without ai_director_enabled must behave exactly as before."""
    from app.models.schemas import RenderRequest

    req = RenderRequest(source_video_path="/tmp/test.mp4")
    assert req.ai_director_enabled is False
