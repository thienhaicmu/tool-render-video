"""
test_ai_director_phase4_pacing.py — AI Director Phase 4: Beat + Emotion Pacing.

All tests are pure-Python. No CUDA, no cloud API keys, no real video rendering.
Optional libraries (librosa, sentence-transformers, faiss) may be missing.

Covers:
- beat_analyzer import safety (no librosa required)
- analyze_beats(None) safe warning
- analyze_beats missing library graceful fallback
- beat analyzer return shape completeness
- emotion analyzer keyword detection
- emotion analyzer pacing aggregation
- AIPacingPlan schema and to_dict()
- AIEditPlan.pacing field existence
- AI Director with unavailable beat analysis
- AI Director plan includes compact pacing dict
- pacing dict is compact (no large arrays)
- ai_modes pacing config per mode
- no API key required
- no GPU required
- no real rendering required
"""
from __future__ import annotations

import types
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_req(**kwargs):
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
    {"start": 10.5, "end": 65.0, "text": "here is why you need to stop doing this now"},
    {"start": 65.5, "end": 90.0, "text": "the truth is simple and clear for everyone"},
]

_CURIOSITY_TEXT = "why does nobody tell you the truth about this secret hidden thing?"
_URGENCY_TEXT = "stop immediately now before it's too late you must act fast"
_NEUTRAL_TEXT = "the cat sat on the mat and looked around slowly"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Beat analyzer — import and availability
# ─────────────────────────────────────────────────────────────────────────────

def test_beat_analyzer_imports_without_librosa():
    """Importing beat_analyzer must never require librosa."""
    from app.ai.analyzers import beat_analyzer  # noqa: F401
    from app.ai.analyzers.beat_analyzer import (
        is_beat_analysis_available,
        analyze_beats,
    )
    assert callable(is_beat_analysis_available)
    assert callable(analyze_beats)


def test_beat_analyzer_availability_is_bool():
    from app.ai.analyzers.beat_analyzer import is_beat_analysis_available

    result = is_beat_analysis_available()
    assert isinstance(result, bool)


def test_analyze_beats_none_path_returns_safe_warning():
    from app.ai.analyzers.beat_analyzer import analyze_beats

    result = analyze_beats(None)
    assert isinstance(result, dict)
    assert "available" in result
    assert "bpm" in result
    assert "beats" in result
    assert "energy" in result
    assert "warnings" in result
    assert "no_audio_path" in result["warnings"]
    assert result["available"] is False


def test_analyze_beats_missing_library_returns_available_false(monkeypatch):
    """When librosa is absent, analyze_beats must return available=False."""
    import app.ai.analyzers.beat_analyzer as ba
    monkeypatch.setattr(ba, "has_librosa", lambda: False)

    result = ba.analyze_beats("/some/path/audio.mp3")
    assert result["available"] is False
    assert "librosa_not_installed" in result["warnings"]


def test_analyze_beats_nonexistent_file_with_librosa(monkeypatch):
    """If librosa is present but file not found, return a warning."""
    import app.ai.analyzers.beat_analyzer as ba

    monkeypatch.setattr(ba, "has_librosa", lambda: True)

    # Simulate librosa raising FileNotFoundError on load.
    class FakeLibrosa:
        @staticmethod
        def load(*a, **kw):
            raise FileNotFoundError("not found")
        class beat:
            @staticmethod
            def beat_track(**kw):
                return (120.0, [])
        class feature:
            @staticmethod
            def rms(**kw):
                return [[]]

    import sys
    sys.modules["librosa"] = FakeLibrosa()
    try:
        result = ba.analyze_beats("/nonexistent/audio.mp3")
        assert "audio_file_not_found" in result["warnings"]
        assert result["bpm"] is None
    finally:
        sys.modules.pop("librosa", None)


def test_analyze_beats_return_shape_complete():
    from app.ai.analyzers.beat_analyzer import analyze_beats

    result = analyze_beats(None)
    # Shape must always be complete regardless of availability.
    assert set(result.keys()) >= {"available", "bpm", "beats", "energy", "warnings"}
    energy = result["energy"]
    assert set(energy.keys()) >= {"mean", "peak", "curve"}
    assert isinstance(energy["curve"], list)


def test_analyze_beats_energy_curve_capped(monkeypatch):
    """Energy curve must never exceed 64 points."""
    import app.ai.analyzers.beat_analyzer as ba

    monkeypatch.setattr(ba, "has_librosa", lambda: True)

    import numpy as np

    # Simulate librosa with a long RMS array (200 frames).
    class FakeLibrosa:
        @staticmethod
        def load(path, sr=None, mono=True):
            return (np.zeros(44100), 22050)

        class beat:
            @staticmethod
            def beat_track(y=None, sr=None):
                return (np.array([128.0]), np.array([10, 20, 30]))

        @staticmethod
        def frames_to_time(frames, sr=None):
            return np.array([float(f) * 0.01 for f in frames])

        class feature:
            @staticmethod
            def rms(y=None):
                return (np.random.rand(200),)

    import sys
    sys.modules["librosa"] = FakeLibrosa()
    try:
        result = ba.analyze_beats("/fake/audio.mp3")
        if result.get("available"):
            assert len(result["energy"]["curve"]) <= 64
    finally:
        sys.modules.pop("librosa", None)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Emotion analyzer
# ─────────────────────────────────────────────────────────────────────────────

def test_emotion_analyzer_imports_safely():
    from app.ai.analyzers import emotion_analyzer  # noqa: F401
    from app.ai.analyzers.emotion_analyzer import (
        analyze_text_emotion,
        analyze_pacing_emotion,
    )
    assert callable(analyze_text_emotion)
    assert callable(analyze_pacing_emotion)


def test_emotion_analyzer_returns_correct_shape():
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    result = analyze_text_emotion("hello world")
    assert "dominant" in result
    assert "score" in result
    assert "signals" in result
    assert "warnings" in result
    assert isinstance(result["score"], float)
    assert 0.0 <= result["score"] <= 100.0


def test_curiosity_text_beats_neutral():
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    curiosity = analyze_text_emotion(_CURIOSITY_TEXT)
    neutral = analyze_text_emotion(_NEUTRAL_TEXT)
    assert curiosity["score"] > neutral["score"], (
        f"Curiosity ({curiosity['score']}) should beat neutral ({neutral['score']})"
    )


def test_urgency_text_detects_urgency():
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    result = analyze_text_emotion(_URGENCY_TEXT)
    assert result["dominant"] == "urgency", f"Expected urgency, got {result['dominant']}"
    assert result["score"] > 0


def test_curiosity_text_detects_curiosity():
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    result = analyze_text_emotion(_CURIOSITY_TEXT)
    assert result["dominant"] == "curiosity", f"Expected curiosity, got {result['dominant']}"


def test_neutral_text_returns_neutral_or_low_score():
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    result = analyze_text_emotion(_NEUTRAL_TEXT)
    assert result["score"] <= 50.0 or result["dominant"] == "neutral"


def test_empty_text_returns_neutral():
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    result = analyze_text_emotion("")
    assert result["dominant"] == "neutral"
    assert "empty_text" in result["warnings"]


def test_analyze_pacing_emotion_from_chunks():
    from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion

    result = analyze_pacing_emotion(_SAMPLE_CHUNKS)
    assert "dominant" in result
    assert "score" in result
    assert 0.0 <= result["score"] <= 100.0


def test_analyze_pacing_emotion_empty_chunks():
    from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion

    result = analyze_pacing_emotion([])
    assert result["dominant"] == "neutral"
    assert "no_chunks" in result["warnings"]


def test_analyze_pacing_emotion_strong_curiosity_chunks():
    from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion

    chunks = [
        {"text": "why does nobody know this secret truth?"},
        {"text": "how can you discover what's really hidden?"},
        {"text": "the truth nobody tells you about this"},
    ]
    result = analyze_pacing_emotion(chunks)
    assert result["score"] > 0
    assert result["dominant"] in ("curiosity",)


def test_analyze_pacing_emotion_score_clamped():
    from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion

    extreme_chunks = [{"text": " ".join(["secret", "why", "truth", "nobody"] * 20)}] * 10
    result = analyze_pacing_emotion(extreme_chunks)
    assert result["score"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. AIPacingPlan schema
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_pacing_plan_default_fields():
    from app.ai.director.edit_plan_schema import AIPacingPlan

    plan = AIPacingPlan()
    assert plan.beat_available is False
    assert plan.bpm is None
    assert plan.beat_count == 0
    assert plan.energy_level is None
    assert plan.pacing_style == "default"
    assert plan.emotion == "neutral"
    assert plan.emotion_score == 0.0
    assert plan.suggested_cut_style == "standard"
    assert isinstance(plan.warnings, list)


def test_ai_pacing_plan_to_dict_shape():
    from app.ai.director.edit_plan_schema import AIPacingPlan

    plan = AIPacingPlan(
        beat_available=True,
        bpm=128.0,
        beat_count=42,
        energy_level=0.71,
        pacing_style="fast",
        emotion="curiosity",
        emotion_score=75.0,
        suggested_cut_style="fast_cut",
    )
    d = plan.to_dict()
    assert d["beat_available"] is True
    assert d["bpm"] == pytest.approx(128.0)
    assert d["beat_count"] == 42
    assert d["energy_level"] == pytest.approx(0.71)
    assert d["pacing_style"] == "fast"
    assert d["emotion"] == "curiosity"
    assert d["emotion_score"] == pytest.approx(75.0)
    assert d["suggested_cut_style"] == "fast_cut"
    assert isinstance(d["warnings"], list)


def test_ai_pacing_plan_no_large_arrays():
    """Pacing dict must not contain beat timestamps or large energy curve."""
    from app.ai.director.edit_plan_schema import AIPacingPlan

    plan = AIPacingPlan()
    d = plan.to_dict()
    assert "beats" not in d
    assert "curve" not in d
    assert "energy" not in d


# ─────────────────────────────────────────────────────────────────────────────
# 4. AIEditPlan.pacing field
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_edit_plan_has_pacing_field():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan,
    )

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    assert hasattr(plan, "pacing")
    assert isinstance(plan.pacing, AIPacingPlan)


def test_ai_edit_plan_to_dict_includes_pacing():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan,
    )

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(emotion="curiosity", emotion_score=60.0),
    )
    d = plan.to_dict()
    assert "pacing" in d
    assert d["pacing"]["emotion"] == "curiosity"


def test_ai_edit_plan_pacing_default_is_safe():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan,
    )

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    d = plan.to_dict()
    assert "pacing" in d
    pacing = d["pacing"]
    assert pacing["beat_available"] is False
    assert pacing["emotion"] == "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# 5. AI modes — pacing config
# ─────────────────────────────────────────────────────────────────────────────

def test_all_modes_have_pacing_config():
    from app.ai.config.ai_modes import VALID_AI_MODES, get_mode_config

    for mode in VALID_AI_MODES:
        cfg = get_mode_config(mode)
        assert "pacing_style" in cfg, f"Mode {mode} missing pacing_style"
        assert "prefer_beat_sync" in cfg, f"Mode {mode} missing prefer_beat_sync"
        assert "emotion_bias" in cfg, f"Mode {mode} missing emotion_bias"
        assert isinstance(cfg["prefer_beat_sync"], bool)


def test_viral_tiktok_is_fast_pacing():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    assert cfg["pacing_style"] == "fast"
    assert cfg["prefer_beat_sync"] is True


def test_podcast_shorts_is_medium_pacing():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("podcast_shorts")
    assert cfg["pacing_style"] == "medium"
    assert cfg["prefer_beat_sync"] is False


def test_storytelling_is_slow_build():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("storytelling")
    assert cfg["pacing_style"] == "slow_build"


def test_clean_subtitle_is_stable():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("clean_subtitle")
    assert cfg["pacing_style"] == "stable"
    assert cfg["emotion_bias"] == "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# 6. AI Director integration — pacing
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_director_returns_plan_with_pacing():
    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.director.edit_plan_schema import AIPacingPlan

    req = _make_req()
    context = {
        "job_id": "p4-test-1",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert hasattr(plan, "pacing")
    assert isinstance(plan.pacing, AIPacingPlan)


def test_ai_director_pacing_has_emotion():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    context = {
        "job_id": "p4-test-2",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert isinstance(plan.pacing.emotion, str)
    assert plan.pacing.emotion != ""
    assert 0.0 <= plan.pacing.emotion_score <= 100.0


def test_ai_director_works_without_beat_analysis():
    """No audio_path/source_path → beat analysis unavailable, plan still valid."""
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    context = {
        "job_id": "p4-test-3",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
        # No source_path, audio_path, or video_path
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.pacing.beat_available is False
    assert "beat_analysis_unavailable" in plan.pacing.warnings


def test_ai_director_pacing_style_matches_mode():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req(ai_mode="podcast_shorts")
    context = {
        "job_id": "p4-test-4",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.pacing.pacing_style == "medium"


def test_ai_director_to_dict_pacing_is_compact():
    """to_dict() pacing section must not contain raw beat arrays or energy curves."""
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    context = {
        "job_id": "p4-test-5",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    d = plan.to_dict()
    pacing = d.get("pacing", {})
    assert "beats" not in pacing
    assert "curve" not in pacing
    assert "energy" not in pacing
    # Must have compact fields
    assert "beat_available" in pacing
    assert "emotion" in pacing
    assert "suggested_cut_style" in pacing


def test_ai_director_suggested_cut_style_valid():
    from app.ai.director.ai_director import create_ai_edit_plan

    valid_styles = {"standard", "fast_cut", "medium_cut", "slow_cut"}
    req = _make_req()
    context = {
        "job_id": "p4-test-6",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.pacing.suggested_cut_style in valid_styles


def test_ai_director_beat_unavailable_does_not_crash():
    """Beat analyzer failing must not crash the director."""
    import app.ai.analyzers.beat_analyzer as ba
    original = ba.analyze_beats

    def _raise(*a, **kw):
        raise RuntimeError("simulated crash")

    ba.analyze_beats = _raise
    try:
        from app.ai.director.ai_director import create_ai_edit_plan

        req = _make_req()
        context = {
            "job_id": "p4-crash-test",
            "transcript_blocks": _SAMPLE_CHUNKS,
            "duration": 90.0,
            "source_path": "/fake/video.mp4",
        }
        plan = create_ai_edit_plan(req, context)
        assert plan is not None
        assert plan.pacing.beat_available is False
    finally:
        ba.analyze_beats = original


# ─────────────────────────────────────────────────────────────────────────────
# 7. suggest_cut_style logic
# ─────────────────────────────────────────────────────────────────────────────

def test_suggest_cut_style_high_bpm():
    from app.ai.director.ai_director import _suggest_cut_style

    assert _suggest_cut_style(150.0, "fast") == "fast_cut"


def test_suggest_cut_style_medium_bpm():
    from app.ai.director.ai_director import _suggest_cut_style

    assert _suggest_cut_style(120.0, "medium") == "medium_cut"


def test_suggest_cut_style_low_bpm():
    from app.ai.director.ai_director import _suggest_cut_style

    assert _suggest_cut_style(75.0, "slow_build") == "slow_cut"


def test_suggest_cut_style_no_bpm_uses_pacing_style():
    from app.ai.director.ai_director import _suggest_cut_style

    assert _suggest_cut_style(None, "fast") == "fast_cut"
    assert _suggest_cut_style(None, "slow_build") == "slow_cut"
    assert _suggest_cut_style(None, "medium") == "medium_cut"
    assert _suggest_cut_style(None, "stable") == "standard"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Safety and regression guards
# ─────────────────────────────────────────────────────────────────────────────

def test_no_api_key_required():
    from app.ai.analyzers import beat_analyzer      # noqa: F401
    from app.ai.analyzers import emotion_analyzer   # noqa: F401
    from app.ai.director import edit_plan_schema    # noqa: F401
    from app.ai.director import ai_director         # noqa: F401
    from app.ai.config import ai_modes              # noqa: F401


def test_no_gpu_required():
    from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion

    result = analyze_pacing_emotion(_SAMPLE_CHUNKS)
    assert isinstance(result, dict)


def test_no_real_rendering_required():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    plan = create_ai_edit_plan(req, {"job_id": "p4-safe", "duration": 60.0})
    assert plan is not None


def test_phase1_regression_plan_to_dict_keys():
    """All original to_dict() keys must still be present after Phase 4."""
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    plan = create_ai_edit_plan(req, {"job_id": "p4-reg", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0})
    assert plan is not None
    d = plan.to_dict()
    for key in ("enabled", "mode", "selected_segments", "subtitle", "camera",
                "warnings", "fallback_used", "memory_context", "pacing"):
        assert key in d, f"Missing key in to_dict(): {key}"


def test_all_modes_still_return_valid_config():
    from app.ai.config.ai_modes import VALID_AI_MODES, get_mode_config

    for mode in VALID_AI_MODES:
        cfg = get_mode_config(mode)
        assert "preferred_duration_min" in cfg
        assert "preferred_duration_max" in cfg
        assert cfg["preferred_duration_min"] < cfg["preferred_duration_max"]
