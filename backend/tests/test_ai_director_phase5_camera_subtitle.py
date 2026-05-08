"""
test_ai_director_phase5_camera_subtitle.py — AI Director Phase 5: Camera + Subtitle Intelligence.

All tests are pure-Python. No CUDA, no cloud API keys, no real video rendering.
No optional library (librosa, sentence-transformers, faiss, mediapipe) required.

Covers:
- Camera planner behavior rules (fast_follow, dramatic_push, slow_reveal, none)
- Camera planner subtitle_safe invariant
- Subtitle planner mode defaults (hype/punch, clean/keyword, story/soft, clean/none)
- Subtitle planner beat_aware and emotion_aware overrides
- AIEditPlan expanded camera/subtitle schema
- to_dict() includes new camera/subtitle fields
- AI Director integration with planners
- Planner failure fallback safety
- ai_modes Phase 5 fields
- Regression guard (Phase 1-4 keys still present)
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


def _mode_cfg(mode: str, **extra) -> dict:
    from app.ai.config.ai_modes import get_mode_config
    cfg = get_mode_config(mode)
    cfg["mode_name"] = mode
    cfg.update(extra)
    return cfg


def _pacing(
    pacing_style: str = "default",
    energy_level=None,
    emotion: str = "neutral",
    emotion_score: float = 0.0,
    beat_available: bool = False,
    bpm=None,
) -> dict:
    return {
        "pacing_style": pacing_style,
        "energy_level": energy_level,
        "emotion": emotion,
        "emotion_score": emotion_score,
        "beat_available": beat_available,
        "bpm": bpm,
    }


_SAMPLE_CHUNKS = [
    {"start": 0.0,  "end": 5.0,  "text": "nobody tells you this secret"},
    {"start": 5.5,  "end": 65.0, "text": "here is why you need to stop doing this now"},
    {"start": 65.5, "end": 90.0, "text": "the truth is simple and clear for everyone"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Camera planner — behavior rules
# ─────────────────────────────────────────────────────────────────────────────

def test_camera_planner_imports_safely():
    from app.ai.director.camera_planner import plan_camera_behavior
    assert callable(plan_camera_behavior)


def test_camera_planner_fast_pacing_returns_fast_follow():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast"),
    )
    assert plan.behavior == "fast_follow"


def test_camera_planner_high_energy_returns_fast_follow():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("podcast_shorts"),
        pacing_context=_pacing(pacing_style="medium", energy_level=0.85),
    )
    assert plan.behavior == "fast_follow"


def test_camera_planner_energy_threshold_boundary():
    """Energy at exactly 0.75 should NOT trigger fast_follow (must be > 0.75)."""
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("podcast_shorts"),
        pacing_context=_pacing(pacing_style="medium", energy_level=0.75),
    )
    assert plan.behavior != "fast_follow"


def test_camera_planner_urgency_returns_dramatic_push():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast", emotion="urgency"),
    )
    assert plan.behavior == "dramatic_push"


def test_camera_planner_surprise_returns_dramatic_push():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("podcast_shorts"),
        pacing_context=_pacing(pacing_style="medium", emotion="surprise"),
    )
    assert plan.behavior == "dramatic_push"


def test_camera_planner_dramatic_push_zoom_strength():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(emotion="urgency"),
    )
    assert plan.zoom_strength == pytest.approx(1.12)


def test_camera_planner_storytelling_returns_slow_reveal():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("storytelling"),
        pacing_context=_pacing(pacing_style="slow_build"),
    )
    assert plan.behavior == "slow_reveal"


def test_camera_planner_slow_build_pacing_returns_slow_reveal():
    from app.ai.director.camera_planner import plan_camera_behavior

    # Non-storytelling mode but slow_build pacing
    plan = plan_camera_behavior(
        _mode_cfg("podcast_shorts"),
        pacing_context=_pacing(pacing_style="slow_build"),
    )
    assert plan.behavior == "slow_reveal"


def test_camera_planner_slow_reveal_zoom_strength():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("storytelling"),
        pacing_context=_pacing(pacing_style="slow_build"),
    )
    assert plan.zoom_strength == pytest.approx(1.05)
    assert plan.follow_strength == pytest.approx(0.45)


def test_camera_planner_clean_subtitle_returns_none():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("clean_subtitle"),
        pacing_context=_pacing(pacing_style="fast"),  # fast pacing ignored
    )
    assert plan.behavior == "none"
    assert plan.zoom_strength == pytest.approx(1.0)


def test_camera_planner_subtitle_safe_always_true():
    """subtitle_safe must be True for every combination."""
    from app.ai.director.camera_planner import plan_camera_behavior

    configs = [
        (_mode_cfg("viral_tiktok"), _pacing(pacing_style="fast")),
        (_mode_cfg("viral_tiktok"), _pacing(emotion="urgency")),
        (_mode_cfg("storytelling"), _pacing(pacing_style="slow_build")),
        (_mode_cfg("clean_subtitle"), _pacing(pacing_style="stable")),
        (_mode_cfg("podcast_shorts"), _pacing()),
    ]
    for cfg, pacing in configs:
        plan = plan_camera_behavior(cfg, pacing_context=pacing)
        assert plan.subtitle_safe is True, f"subtitle_safe=False for behavior={plan.behavior}"


def test_camera_planner_returns_reason():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast"),
    )
    assert isinstance(plan.reason, str)
    assert len(plan.reason) > 0


def test_camera_planner_never_raises_on_bad_input():
    from app.ai.director.camera_planner import plan_camera_behavior
    from app.ai.director.edit_plan_schema import AICameraPlan

    result = plan_camera_behavior({}, pacing_context=None, memory_context=None, transcript_context=None)
    assert isinstance(result, AICameraPlan)


def test_camera_planner_fast_follow_zoom_strength():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast"),
    )
    assert plan.zoom_strength == pytest.approx(1.10)
    assert plan.follow_strength == pytest.approx(0.75)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Subtitle planner — mode defaults
# ─────────────────────────────────────────────────────────────────────────────

def test_subtitle_planner_imports_safely():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior
    assert callable(plan_subtitle_behavior)


def test_subtitle_planner_viral_tiktok_defaults():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(_mode_cfg("viral_tiktok"), pacing_context=_pacing())
    assert plan.tone == "hype"
    assert plan.emphasis_style == "punch"
    assert plan.highlight_keywords is True
    assert plan.max_words_per_line == 4


def test_subtitle_planner_podcast_shorts_defaults():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(_mode_cfg("podcast_shorts"), pacing_context=_pacing())
    assert plan.tone == "clean"
    assert plan.emphasis_style == "keyword"
    assert plan.max_words_per_line == 6


def test_subtitle_planner_storytelling_defaults():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(_mode_cfg("storytelling"), pacing_context=_pacing())
    assert plan.tone == "story"
    assert plan.emphasis_style == "soft"
    assert plan.max_words_per_line == 6


def test_subtitle_planner_clean_subtitle_defaults():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(_mode_cfg("clean_subtitle"), pacing_context=_pacing())
    assert plan.tone == "clean"
    assert plan.emphasis_style == "none"
    assert plan.max_words_per_line == 7
    assert plan.highlight_keywords is False


def test_subtitle_planner_beat_aware_when_beat_available_and_fast():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast", beat_available=True),
    )
    assert plan.beat_aware is True
    assert plan.density == "compact"


def test_subtitle_planner_no_beat_aware_when_beat_unavailable():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast", beat_available=False),
    )
    assert plan.beat_aware is False


def test_subtitle_planner_no_beat_aware_when_not_fast():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("podcast_shorts"),
        pacing_context=_pacing(pacing_style="medium", beat_available=True),
    )
    assert plan.beat_aware is False


def test_subtitle_planner_emotion_aware_curiosity():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("storytelling"),
        pacing_context=_pacing(emotion="curiosity"),
    )
    assert plan.emotion_aware is True
    assert plan.highlight_keywords is True


def test_subtitle_planner_emotion_aware_surprise():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("podcast_shorts"),
        pacing_context=_pacing(emotion="surprise"),
    )
    assert plan.emotion_aware is True
    assert plan.highlight_keywords is True


def test_subtitle_planner_emotion_aware_urgency():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("clean_subtitle"),
        pacing_context=_pacing(emotion="urgency"),
    )
    assert plan.emotion_aware is True
    assert plan.highlight_keywords is True


def test_subtitle_planner_neutral_emotion_not_emotion_aware():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(emotion="neutral"),
    )
    assert plan.emotion_aware is False


def test_subtitle_planner_returns_reason():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(_mode_cfg("viral_tiktok"), pacing_context=_pacing())
    assert isinstance(plan.reason, str)
    assert len(plan.reason) > 0


def test_subtitle_planner_reason_includes_beat_and_emotion():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior

    plan = plan_subtitle_behavior(
        _mode_cfg("viral_tiktok"),
        pacing_context=_pacing(pacing_style="fast", beat_available=True, emotion="curiosity"),
    )
    assert "beat" in plan.reason.lower()
    assert "curiosity" in plan.reason.lower()


def test_subtitle_planner_never_raises_on_bad_input():
    from app.ai.director.subtitle_planner import plan_subtitle_behavior
    from app.ai.director.edit_plan_schema import AISubtitlePlan

    result = plan_subtitle_behavior({}, pacing_context=None, memory_context=None, transcript_context=None)
    assert isinstance(result, AISubtitlePlan)


# ─────────────────────────────────────────────────────────────────────────────
# 3. AIEditPlan schema — expanded fields
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_camera_plan_has_new_fields():
    from app.ai.director.edit_plan_schema import AICameraPlan

    plan = AICameraPlan()
    assert hasattr(plan, "zoom_strength")
    assert hasattr(plan, "follow_strength")
    assert hasattr(plan, "motion_energy")
    assert hasattr(plan, "reason")
    assert plan.zoom_strength == pytest.approx(1.0)
    assert plan.follow_strength == pytest.approx(0.5)
    assert plan.motion_energy is None
    assert plan.reason == ""


def test_ai_subtitle_plan_has_new_fields():
    from app.ai.director.edit_plan_schema import AISubtitlePlan

    plan = AISubtitlePlan()
    assert hasattr(plan, "emphasis_style")
    assert hasattr(plan, "density")
    assert hasattr(plan, "beat_aware")
    assert hasattr(plan, "emotion_aware")
    assert hasattr(plan, "reason")
    assert plan.emphasis_style == "none"
    assert plan.density == "normal"
    assert plan.beat_aware is False
    assert plan.emotion_aware is False
    assert plan.reason == ""


def test_ai_edit_plan_to_dict_camera_has_new_keys():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(zoom_strength=1.12, follow_strength=0.75, reason="test"),
    )
    d = plan.to_dict()
    cam = d["camera"]
    assert "zoom_strength" in cam
    assert "follow_strength" in cam
    assert "motion_energy" in cam
    assert "reason" in cam
    assert cam["zoom_strength"] == pytest.approx(1.12)
    assert cam["reason"] == "test"


def test_ai_edit_plan_to_dict_subtitle_has_new_keys():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(
            emphasis_style="punch",
            density="compact",
            beat_aware=True,
            emotion_aware=True,
            reason="mode:viral_tiktok, beat_sync",
        ),
        camera=AICameraPlan(),
    )
    d = plan.to_dict()
    sub = d["subtitle"]
    assert "emphasis_style" in sub
    assert "density" in sub
    assert "beat_aware" in sub
    assert "emotion_aware" in sub
    assert "reason" in sub
    assert sub["emphasis_style"] == "punch"
    assert sub["beat_aware"] is True


def test_ai_edit_plan_default_camera_subtitle_safe():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    assert plan.camera.subtitle_safe is True
    assert plan.camera.zoom_strength == pytest.approx(1.0)
    assert plan.subtitle.beat_aware is False
    assert plan.subtitle.emotion_aware is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. AI Director integration
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_director_plan_has_expanded_camera():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req(ai_mode="viral_tiktok")
    context = {"job_id": "p5-cam-1", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert hasattr(plan.camera, "zoom_strength")
    assert hasattr(plan.camera, "reason")
    assert plan.camera.subtitle_safe is True


def test_ai_director_plan_has_expanded_subtitle():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req(ai_mode="viral_tiktok")
    context = {"job_id": "p5-sub-1", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert hasattr(plan.subtitle, "emphasis_style")
    assert hasattr(plan.subtitle, "beat_aware")
    assert hasattr(plan.subtitle, "emotion_aware")


def test_ai_director_viral_tiktok_subtitle_is_hype():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req(ai_mode="viral_tiktok")
    context = {"job_id": "p5-hype-1", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.subtitle.tone == "hype"
    assert plan.subtitle.emphasis_style == "punch"


def test_ai_director_clean_subtitle_camera_is_none():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req(ai_mode="clean_subtitle")
    context = {"job_id": "p5-clean-1", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.camera.behavior == "none"
    assert plan.camera.subtitle_safe is True


def test_ai_director_to_dict_includes_new_camera_subtitle_keys():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    context = {"job_id": "p5-dict-1", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    d = plan.to_dict()
    cam = d["camera"]
    sub = d["subtitle"]

    for key in ("behavior", "subtitle_safe", "zoom_strength", "follow_strength", "reason"):
        assert key in cam, f"Camera dict missing: {key}"

    for key in ("tone", "highlight_keywords", "emphasis_style", "density", "beat_aware", "emotion_aware", "reason"):
        assert key in sub, f"Subtitle dict missing: {key}"


def test_ai_director_works_if_camera_planner_fails(monkeypatch):
    """Camera planner crash must not crash the director."""
    import app.ai.director.ai_director as ad

    def _crash(*a, **kw):
        raise RuntimeError("camera planner simulated crash")

    monkeypatch.setattr(ad, "plan_camera_behavior", _crash)

    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.director.edit_plan_schema import AICameraPlan

    req = _make_req()
    context = {"job_id": "p5-crash-cam", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert isinstance(plan.camera, AICameraPlan)
    assert any("camera_planner_error" in w for w in plan.warnings)


def test_ai_director_works_if_subtitle_planner_fails(monkeypatch):
    """Subtitle planner crash must not crash the director."""
    import app.ai.director.ai_director as ad

    def _crash(*a, **kw):
        raise RuntimeError("subtitle planner simulated crash")

    monkeypatch.setattr(ad, "plan_subtitle_behavior", _crash)

    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.director.edit_plan_schema import AISubtitlePlan

    req = _make_req()
    context = {"job_id": "p5-crash-sub", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert isinstance(plan.subtitle, AISubtitlePlan)
    assert any("subtitle_planner_error" in w for w in plan.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ai_modes — Phase 5 config fields
# ─────────────────────────────────────────────────────────────────────────────

def test_all_modes_have_phase5_camera_fields():
    from app.ai.config.ai_modes import VALID_AI_MODES, get_mode_config

    for mode in VALID_AI_MODES:
        cfg = get_mode_config(mode)
        assert "subtitle_emphasis_style" in cfg, f"Mode {mode} missing subtitle_emphasis_style"
        assert "subtitle_density" in cfg, f"Mode {mode} missing subtitle_density"
        assert "camera_zoom_strength" in cfg, f"Mode {mode} missing camera_zoom_strength"
        assert isinstance(cfg["camera_zoom_strength"], float)


def test_viral_tiktok_camera_zoom_strength():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    assert cfg["camera_zoom_strength"] == pytest.approx(1.12)
    assert cfg["subtitle_emphasis_style"] == "punch"
    assert cfg["subtitle_density"] == "compact"


def test_clean_subtitle_camera_zoom_is_1():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("clean_subtitle")
    assert cfg["camera_zoom_strength"] == pytest.approx(1.0)
    assert cfg["subtitle_emphasis_style"] == "none"
    assert cfg["subtitle_density"] == "comfortable"


def test_storytelling_emphasis_is_soft():
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("storytelling")
    assert cfg["subtitle_emphasis_style"] == "soft"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Safety / regression guards
# ─────────────────────────────────────────────────────────────────────────────

def test_no_api_key_required():
    from app.ai.director import camera_planner    # noqa: F401
    from app.ai.director import subtitle_planner  # noqa: F401
    from app.ai.director import edit_plan_schema  # noqa: F401
    from app.ai.director import ai_director       # noqa: F401


def test_no_gpu_required():
    from app.ai.director.camera_planner import plan_camera_behavior

    plan = plan_camera_behavior(_mode_cfg("viral_tiktok"), pacing_context=_pacing())
    assert plan is not None


def test_no_real_rendering_required():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    plan = create_ai_edit_plan(req, {"job_id": "p5-safe", "duration": 60.0})
    assert plan is not None


def test_phase1_to_phase4_keys_still_present():
    """All prior to_dict() keys must survive Phase 5 additions."""
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _make_req()
    plan = create_ai_edit_plan(req, {
        "job_id": "p5-reg",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
    })
    assert plan is not None
    d = plan.to_dict()
    for key in ("enabled", "mode", "selected_segments", "subtitle", "camera",
                "warnings", "fallback_used", "memory_context", "pacing"):
        assert key in d, f"Regression: missing key {key!r} in to_dict()"


def test_all_modes_still_have_phase1_to_phase4_config():
    from app.ai.config.ai_modes import VALID_AI_MODES, get_mode_config

    required = (
        "preferred_duration_min", "preferred_duration_max",
        "subtitle_tone", "camera_behavior",
        "pacing_style", "prefer_beat_sync", "emotion_bias",
    )
    for mode in VALID_AI_MODES:
        cfg = get_mode_config(mode)
        for k in required:
            assert k in cfg, f"Mode {mode!r} lost key {k!r}"
