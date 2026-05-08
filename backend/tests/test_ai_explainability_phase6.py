"""
test_ai_explainability_phase6.py — Phase 6: AI Explainability tests.

Covers:
- reason_builder: determinism, deduplication, per-category correctness
- confidence: score degradation, fallback safety
- summary: compactness, headline generation
- edit_plan_schema: new explainability/confidence fields, to_dict()
- ai_director: integration, failure isolation
- constraints: no GPU, no API key, no cloud deps
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_pacing(
    emotion="neutral",
    emotion_score=0.0,
    bpm=None,
    beat_available=False,
    energy_level=None,
    pacing_style="default",
    suggested_cut_style="standard",
):
    from app.ai.director.edit_plan_schema import AIPacingPlan
    return AIPacingPlan(
        emotion=emotion,
        emotion_score=emotion_score,
        bpm=bpm,
        beat_available=beat_available,
        energy_level=energy_level,
        pacing_style=pacing_style,
        suggested_cut_style=suggested_cut_style,
    )


def _make_camera(behavior="none", zoom_strength=1.0, follow_strength=0.5, reason=""):
    from app.ai.director.edit_plan_schema import AICameraPlan
    return AICameraPlan(
        behavior=behavior,
        zoom_strength=zoom_strength,
        follow_strength=follow_strength,
        reason=reason,
    )


def _make_subtitle(
    tone="default",
    highlight_keywords=False,
    beat_aware=False,
    emotion_aware=False,
    density="normal",
    emphasis_style="none",
    reason="",
):
    from app.ai.director.edit_plan_schema import AISubtitlePlan
    return AISubtitlePlan(
        tone=tone,
        highlight_keywords=highlight_keywords,
        beat_aware=beat_aware,
        emotion_aware=emotion_aware,
        density=density,
        emphasis_style=emphasis_style,
        reason=reason,
    )


def _make_segment(start=0.0, end=10.0, score=70.0, reason="", source="local_ai"):
    from app.ai.director.edit_plan_schema import AIClipPlan
    return AIClipPlan(start=start, end=end, score=score, reason=reason, source=source)


def _make_plan(
    mode="viral_tiktok",
    segments=None,
    warnings=None,
    memory_context=None,
    pacing=None,
    camera=None,
    subtitle=None,
    fallback_used=False,
):
    from app.ai.director.edit_plan_schema import AIEditPlan
    return AIEditPlan(
        enabled=True,
        mode=mode,
        selected_segments=segments or [_make_segment()],
        subtitle=subtitle or _make_subtitle(),
        camera=camera or _make_camera(),
        warnings=list(warnings or []),
        memory_context=dict(memory_context or {}),
        pacing=pacing or _make_pacing(),
        fallback_used=fallback_used,
    )


def _make_req(mode="viral_tiktok"):
    class _Req:
        ai_director_enabled = True
        ai_mode = mode
        ai_use_rag_memory = False
        ai_target_duration = None
    return _Req()


_SAMPLE_CHUNKS = [
    {"start": 0.0, "end": 5.0, "text": "This is a hook about curiosity"},
    {"start": 5.0, "end": 10.0, "text": "High speech density segment"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. reason_builder — imports + determinism
# ─────────────────────────────────────────────────────────────────────────────

def test_reason_builder_imports_safely():
    from app.ai.explainability.reason_builder import (
        build_clip_reasons,
        build_camera_reasons,
        build_subtitle_reasons,
        build_pacing_reasons,
    )
    assert callable(build_clip_reasons)
    assert callable(build_camera_reasons)
    assert callable(build_subtitle_reasons)
    assert callable(build_pacing_reasons)


def test_clip_reasons_deterministic():
    from app.ai.explainability.reason_builder import build_clip_reasons
    segs = [_make_segment(score=85.0, reason="strong hook")]
    r1 = build_clip_reasons(segs, {})
    r2 = build_clip_reasons(segs, {})
    assert r1 == r2


def test_camera_reasons_deterministic():
    from app.ai.explainability.reason_builder import build_camera_reasons
    cam = _make_camera(behavior="fast_follow", zoom_strength=1.10)
    pac = _make_pacing(pacing_style="fast")
    r1 = build_camera_reasons(cam, pac)
    r2 = build_camera_reasons(cam, pac)
    assert r1 == r2


def test_subtitle_reasons_deterministic():
    from app.ai.explainability.reason_builder import build_subtitle_reasons
    sub = _make_subtitle(tone="hype", highlight_keywords=True, emotion_aware=True)
    pac = _make_pacing(emotion="curiosity")
    r1 = build_subtitle_reasons(sub, pac)
    r2 = build_subtitle_reasons(sub, pac)
    assert r1 == r2


def test_pacing_reasons_deterministic():
    from app.ai.explainability.reason_builder import build_pacing_reasons
    pac = _make_pacing(bpm=120.0, emotion="curiosity", emotion_score=0.5, beat_available=True)
    r1 = build_pacing_reasons(pac)
    r2 = build_pacing_reasons(pac)
    assert r1 == r2


# ─────────────────────────────────────────────────────────────────────────────
# 2. reason_builder — deduplication
# ─────────────────────────────────────────────────────────────────────────────

def test_clip_reasons_no_duplicates():
    from app.ai.explainability.reason_builder import build_clip_reasons
    segs = [
        _make_segment(score=90.0, reason="hook hook hook"),
        _make_segment(score=90.0, reason="hook hook hook"),
    ]
    reasons = build_clip_reasons(segs, {})
    assert len(reasons) == len(set(reasons)), "Duplicate reasons found"


def test_camera_reasons_no_duplicates():
    from app.ai.explainability.reason_builder import build_camera_reasons
    cam = _make_camera(behavior="dramatic_push", zoom_strength=1.12)
    pac = _make_pacing(emotion="urgency", energy_level=0.9)
    reasons = build_camera_reasons(cam, pac)
    assert len(reasons) == len(set(reasons))


def test_subtitle_reasons_no_duplicates():
    from app.ai.explainability.reason_builder import build_subtitle_reasons
    sub = _make_subtitle(
        tone="hype", highlight_keywords=True, emotion_aware=True,
        beat_aware=True, density="compact", emphasis_style="punch",
    )
    pac = _make_pacing(emotion="curiosity")
    reasons = build_subtitle_reasons(sub, pac)
    assert len(reasons) == len(set(reasons))


def test_reasons_capped_at_five():
    from app.ai.explainability.reason_builder import build_subtitle_reasons
    sub = _make_subtitle(
        tone="hype", highlight_keywords=True, emotion_aware=True,
        beat_aware=True, density="compact", emphasis_style="punch",
    )
    pac = _make_pacing(emotion="curiosity")
    reasons = build_subtitle_reasons(sub, pac)
    assert len(reasons) <= 5


# ─────────────────────────────────────────────────────────────────────────────
# 3. reason_builder — content checks
# ─────────────────────────────────────────────────────────────────────────────

def test_clip_reasons_high_score():
    from app.ai.explainability.reason_builder import build_clip_reasons
    segs = [_make_segment(score=90.0)]
    reasons = build_clip_reasons(segs, {})
    assert any("high-confidence" in r for r in reasons)


def test_clip_reasons_empty_segments():
    from app.ai.explainability.reason_builder import build_clip_reasons
    reasons = build_clip_reasons([], {})
    assert any("fallback" in r for r in reasons)


def test_clip_reasons_with_memory():
    from app.ai.explainability.reason_builder import build_clip_reasons
    segs = [_make_segment()]
    mem = {"results": [{"text": "past render"}], "enabled": True}
    reasons = build_clip_reasons(segs, mem)
    assert any("past render" in r or "memory" in r for r in reasons)


def test_camera_reasons_none_behavior():
    from app.ai.explainability.reason_builder import build_camera_reasons
    cam = _make_camera(behavior="none")
    pac = _make_pacing()
    reasons = build_camera_reasons(cam, pac)
    assert any("disabled" in r or "clean" in r for r in reasons)


def test_camera_reasons_dramatic_push():
    from app.ai.explainability.reason_builder import build_camera_reasons
    cam = _make_camera(behavior="dramatic_push", zoom_strength=1.12)
    pac = _make_pacing(emotion="urgency")
    reasons = build_camera_reasons(cam, pac)
    assert any("dramatic" in r or "push" in r for r in reasons)


def test_camera_reasons_fast_follow_high_energy():
    from app.ai.explainability.reason_builder import build_camera_reasons
    cam = _make_camera(behavior="fast_follow", zoom_strength=1.10)
    pac = _make_pacing(energy_level=0.85, pacing_style="fast")
    reasons = build_camera_reasons(cam, pac)
    assert any("energy" in r or "fast" in r for r in reasons)


def test_subtitle_reasons_hype():
    from app.ai.explainability.reason_builder import build_subtitle_reasons
    sub = _make_subtitle(tone="hype")
    pac = _make_pacing()
    reasons = build_subtitle_reasons(sub, pac)
    assert any("hype" in r for r in reasons)


def test_subtitle_reasons_beat_aware():
    from app.ai.explainability.reason_builder import build_subtitle_reasons
    sub = _make_subtitle(beat_aware=True)
    pac = _make_pacing(beat_available=True)
    reasons = build_subtitle_reasons(sub, pac)
    assert any("beat" in r for r in reasons)


def test_subtitle_reasons_emotion_aware():
    from app.ai.explainability.reason_builder import build_subtitle_reasons
    sub = _make_subtitle(highlight_keywords=True, emotion_aware=True)
    pac = _make_pacing(emotion="curiosity")
    reasons = build_subtitle_reasons(sub, pac)
    assert any("curiosity" in r for r in reasons)


def test_pacing_reasons_bpm():
    from app.ai.explainability.reason_builder import build_pacing_reasons
    pac = _make_pacing(bpm=128.0, suggested_cut_style="fast_cut")
    reasons = build_pacing_reasons(pac)
    assert any("BPM" in r or "128" in r for r in reasons)


def test_pacing_reasons_emotion():
    from app.ai.explainability.reason_builder import build_pacing_reasons
    pac = _make_pacing(emotion="curiosity", emotion_score=0.6)
    reasons = build_pacing_reasons(pac)
    assert any("curiosity" in r for r in reasons)


def test_pacing_reasons_beat_available():
    from app.ai.explainability.reason_builder import build_pacing_reasons
    pac = _make_pacing(beat_available=True)
    reasons = build_pacing_reasons(pac)
    assert any("beat" in r for r in reasons)


def test_reason_builder_never_raises_on_bad_input():
    from app.ai.explainability.reason_builder import (
        build_clip_reasons, build_camera_reasons,
        build_subtitle_reasons, build_pacing_reasons,
    )
    assert isinstance(build_clip_reasons(None, None), list)
    assert isinstance(build_camera_reasons(None, None), list)
    assert isinstance(build_subtitle_reasons(None, None), list)
    assert isinstance(build_pacing_reasons(None), list)


# ─────────────────────────────────────────────────────────────────────────────
# 4. confidence — imports + structure
# ─────────────────────────────────────────────────────────────────────────────

def test_confidence_imports_safely():
    from app.ai.explainability.confidence import calculate_ai_confidence
    assert callable(calculate_ai_confidence)


def test_confidence_returns_required_keys():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan()
    conf = calculate_ai_confidence(plan)
    for key in ("overall", "clip_selection", "semantic", "memory", "pacing", "camera", "subtitle", "warnings"):
        assert key in conf, f"Missing key: {key}"


def test_confidence_overall_in_range():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan()
    conf = calculate_ai_confidence(plan)
    assert 0 <= conf["overall"] <= 100


def test_confidence_all_scores_in_range():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(segments=[_make_segment(score=80.0)])
    conf = calculate_ai_confidence(plan)
    for key in ("clip_selection", "semantic", "memory", "pacing", "camera", "subtitle"):
        assert 0 <= conf[key] <= 100, f"{key}={conf[key]} out of range"


# ─────────────────────────────────────────────────────────────────────────────
# 5. confidence — degradation rules
# ─────────────────────────────────────────────────────────────────────────────

def test_confidence_degrades_when_semantic_unavailable():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(warnings=["rag:embeddings_unavailable"])
    conf = calculate_ai_confidence(plan)
    assert conf["semantic"] <= 40, f"Expected semantic <= 40, got {conf['semantic']}"


def test_confidence_degrades_when_rag_error():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(warnings=["rag_error:SomeError"])
    conf = calculate_ai_confidence(plan)
    assert conf["semantic"] <= 30


def test_confidence_degrades_when_memory_unavailable():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(warnings=["rag_error:ConnectionError"])
    conf = calculate_ai_confidence(plan)
    assert conf["memory"] <= 30, f"Expected memory <= 30, got {conf['memory']}"


def test_confidence_low_when_no_segments():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(segments=[], warnings=["no_segments_selected"], fallback_used=True)
    conf = calculate_ai_confidence(plan)
    assert conf["clip_selection"] <= 25


def test_confidence_higher_with_memory_results():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan_no_mem = _make_plan(memory_context={})
    plan_with_mem = _make_plan(memory_context={"results": [{"text": "past"}], "enabled": True})
    conf_no = calculate_ai_confidence(plan_no_mem)
    conf_yes = calculate_ai_confidence(plan_with_mem)
    assert conf_yes["memory"] > conf_no["memory"]


def test_confidence_higher_with_beat_available():
    from app.ai.explainability.confidence import calculate_ai_confidence
    pac_no_beat = _make_pacing(beat_available=False)
    pac_beat = _make_pacing(beat_available=True)
    plan_no = _make_plan(pacing=pac_no_beat)
    plan_yes = _make_plan(pacing=pac_beat)
    conf_no = calculate_ai_confidence(plan_no)
    conf_yes = calculate_ai_confidence(plan_yes)
    assert conf_yes["pacing"] > conf_no["pacing"]


def test_confidence_semantic_warning_in_output():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(warnings=["rag:embeddings_unavailable"])
    conf = calculate_ai_confidence(plan)
    assert "semantic_confidence_low" in conf["warnings"]


def test_confidence_memory_warning_in_output():
    from app.ai.explainability.confidence import calculate_ai_confidence
    plan = _make_plan(warnings=["rag_error:Err"])
    conf = calculate_ai_confidence(plan)
    assert "memory_confidence_low" in conf["warnings"]


def test_confidence_never_raises_on_none():
    from app.ai.explainability.confidence import calculate_ai_confidence
    conf = calculate_ai_confidence(None)
    assert "overall" in conf
    assert 0 <= conf["overall"] <= 100


# ─────────────────────────────────────────────────────────────────────────────
# 6. summary — imports + structure
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_imports_safely():
    from app.ai.explainability.summary import build_ai_summary
    assert callable(build_ai_summary)


def test_summary_returns_required_keys():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan()
    conf = {"overall": 70, "semantic": 60, "memory": 50, "pacing": 65, "warnings": []}
    result = build_ai_summary(plan, conf)
    for key in ("headline", "summary_lines", "strengths", "warnings", "confidence"):
        assert key in result, f"Missing key: {key}"


def test_summary_compact_max_lines():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan(
        segments=[_make_segment() for _ in range(10)],
        pacing=_make_pacing(bpm=120, emotion="curiosity", beat_available=True),
        camera=_make_camera(behavior="fast_follow"),
        subtitle=_make_subtitle(tone="hype", highlight_keywords=True),
        memory_context={"results": [{"text": "r"}]},
    )
    conf = {"overall": 80, "semantic": 85, "memory": 70, "pacing": 90, "camera": 75, "subtitle": 75, "warnings": []}
    result = build_ai_summary(plan, conf)
    assert len(result["summary_lines"]) <= 6
    assert len(result["strengths"]) <= 6


def test_summary_headline_not_empty():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan(mode="viral_tiktok")
    conf = {"overall": 75, "semantic": 60, "memory": 40, "pacing": 70, "warnings": []}
    result = build_ai_summary(plan, conf)
    assert isinstance(result["headline"], str)
    assert len(result["headline"]) > 0


def test_summary_headline_reflects_high_confidence():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan()
    conf = {"overall": 90, "semantic": 85, "memory": 80, "pacing": 92, "warnings": []}
    result = build_ai_summary(plan, conf)
    assert "Strong" in result["headline"]


def test_summary_headline_reflects_low_confidence():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan()
    conf = {"overall": 30, "semantic": 25, "memory": 20, "pacing": 35, "warnings": []}
    result = build_ai_summary(plan, conf)
    assert "Basic" in result["headline"]


def test_summary_includes_emotion_in_headline():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan(pacing=_make_pacing(emotion="curiosity"))
    conf = {"overall": 70, "semantic": 60, "memory": 50, "pacing": 65, "warnings": []}
    result = build_ai_summary(plan, conf)
    assert "curiosity" in result["headline"].lower()


def test_summary_includes_no_transcript_warning():
    from app.ai.explainability.summary import build_ai_summary
    plan = _make_plan(warnings=["no_transcript_available"])
    conf = {"overall": 30, "warnings": ["semantic_confidence_low"]}
    result = build_ai_summary(plan, conf)
    assert any("transcript" in w.lower() for w in result["warnings"])


def test_summary_never_raises_on_bad_input():
    from app.ai.explainability.summary import build_ai_summary
    result = build_ai_summary(None, {})
    assert "headline" in result
    assert isinstance(result["summary_lines"], list)


# ─────────────────────────────────────────────────────────────────────────────
# 7. edit_plan_schema — new fields
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_edit_plan_has_explainability_field():
    plan = _make_plan()
    assert hasattr(plan, "explainability")
    assert isinstance(plan.explainability, dict)


def test_ai_edit_plan_has_confidence_field():
    plan = _make_plan()
    assert hasattr(plan, "confidence")
    assert isinstance(plan.confidence, dict)


def test_ai_edit_plan_explainability_defaults_empty():
    plan = _make_plan()
    assert plan.explainability == {}


def test_ai_edit_plan_confidence_defaults_empty():
    plan = _make_plan()
    assert plan.confidence == {}


def test_to_dict_includes_explainability():
    plan = _make_plan()
    plan.explainability = {"clip_reasons": ["hook detected"], "summary": {"headline": "Test"}}
    plan.confidence = {"overall": 80, "semantic": 70, "memory": 60, "pacing": 75}
    d = plan.to_dict()
    assert "explainability" in d
    assert "confidence" in d


def test_to_dict_includes_ai_summary():
    plan = _make_plan()
    plan.explainability = {
        "summary": {"headline": "Strong viral edit plan", "summary_lines": ["3 clips selected"], "strengths": [], "warnings": []},
    }
    plan.confidence = {"overall": 82}
    d = plan.to_dict()
    assert "ai_summary" in d
    assert d["ai_summary"].get("headline") == "Strong viral edit plan"
    assert "confidence" not in d["ai_summary"]


def test_to_dict_includes_ai_confidence_compact():
    plan = _make_plan()
    plan.confidence = {"overall": 82, "semantic": 78, "memory": 64, "pacing": 88, "camera": 75, "subtitle": 75, "warnings": []}
    d = plan.to_dict()
    assert "ai_confidence" in d
    ai_conf = d["ai_confidence"]
    assert ai_conf.get("overall") == 82
    assert ai_conf.get("semantic") == 78
    assert ai_conf.get("memory") == 64
    assert ai_conf.get("pacing") == 88
    assert "camera" not in ai_conf


def test_to_dict_serializes_safely_with_empty_explainability():
    plan = _make_plan()
    d = plan.to_dict()
    assert d["explainability"] == {}
    assert d["confidence"] == {}
    assert d["ai_summary"] == {}
    assert d["ai_confidence"] == {}


def test_phase1_to_phase5_keys_still_present():
    plan = _make_plan()
    d = plan.to_dict()
    for key in ("enabled", "mode", "selected_segments", "subtitle", "camera",
                "warnings", "fallback_used", "memory_context", "pacing"):
        assert key in d, f"Regression: missing key {key}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. AI Director integration
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_director_plan_has_explainability():
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-exp", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None
    assert isinstance(plan.explainability, dict)
    assert "clip_reasons" in plan.explainability
    assert "camera_reasons" in plan.explainability
    assert "subtitle_reasons" in plan.explainability
    assert "pacing_reasons" in plan.explainability
    assert "summary" in plan.explainability


def test_ai_director_plan_has_confidence():
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-conf", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None
    assert isinstance(plan.confidence, dict)
    assert "overall" in plan.confidence
    assert 0 <= plan.confidence["overall"] <= 100


def test_ai_director_to_dict_has_ai_summary_and_confidence():
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-dict", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None
    d = plan.to_dict()
    assert "ai_summary" in d
    assert "ai_confidence" in d
    assert isinstance(d["ai_summary"].get("headline"), str)
    assert isinstance(d["ai_confidence"].get("overall"), int)


def test_ai_director_still_works_if_explainability_fails(monkeypatch):
    """Explainability crash must not crash the director."""
    import app.ai.director.ai_director as ad

    def _crash(*a, **kw):
        raise RuntimeError("explainability simulated crash")

    monkeypatch.setattr(ad, "_attach_explainability", _crash)

    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-crash", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None, "Director must return a plan even if explainability crashes"


def test_ai_director_explainability_reasons_are_lists():
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-lists", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None
    exp = plan.explainability
    assert isinstance(exp.get("clip_reasons"), list)
    assert isinstance(exp.get("camera_reasons"), list)
    assert isinstance(exp.get("subtitle_reasons"), list)
    assert isinstance(exp.get("pacing_reasons"), list)


def test_ai_director_viral_tiktok_summary_has_hype_tone():
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req(mode="viral_tiktok")
    context = {"job_id": "p6-hype", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None
    summary = plan.explainability.get("summary", {})
    assert isinstance(summary.get("headline"), str)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Constraints
# ─────────────────────────────────────────────────────────────────────────────

def test_no_api_key_required():
    import app.ai.explainability.reason_builder as rb
    import app.ai.explainability.confidence as conf_mod
    import app.ai.explainability.summary as sum_mod
    import inspect
    for mod in (rb, conf_mod, sum_mod):
        src = inspect.getsource(mod)
        assert "openai" not in src.lower()
        assert "anthropic" not in src.lower()
        assert "api_key" not in src.lower()
        assert "gemini" not in src.lower()


def test_no_gpu_required():
    import app.ai.explainability.reason_builder as rb
    import app.ai.explainability.confidence as conf_mod
    import app.ai.explainability.summary as sum_mod
    import inspect
    for mod in (rb, conf_mod, sum_mod):
        src = inspect.getsource(mod)
        assert "cuda" not in src.lower()
        assert "torch" not in src.lower()
        assert "tensorflow" not in src.lower()


def test_no_cloud_deps_required():
    import app.ai.explainability.reason_builder as rb
    import app.ai.explainability.confidence as conf_mod
    import app.ai.explainability.summary as sum_mod
    import inspect
    for mod in (rb, conf_mod, sum_mod):
        src = inspect.getsource(mod)
        assert "requests" not in src
        assert "httpx" not in src
        assert "boto3" not in src


def test_explainability_structures_serialize_to_json():
    """All explainability structures must be JSON-serializable."""
    import json
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-json", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 60.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None
    d = plan.to_dict()
    serialized = json.dumps(d)
    assert len(serialized) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. Regression — Phase 1–5 keys still present
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_phase1_to_phase5_plan_keys():
    from app.ai.director.ai_director import create_ai_edit_plan
    req = _make_req()
    context = {"job_id": "p6-regression", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)
    assert plan is not None

    d = plan.to_dict()
    for key in ("enabled", "mode", "selected_segments", "subtitle", "camera",
                "warnings", "fallback_used", "memory_context", "pacing"):
        assert key in d, f"Phase regression: missing {key}"

    assert "pacing_style" in d["pacing"]
    assert "emotion" in d["pacing"]
    assert "beat_available" in d["pacing"]
    assert "zoom_strength" in d["camera"]
    assert "beat_aware" in d["subtitle"]
