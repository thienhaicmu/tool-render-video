"""
test_ai_phase53c_camera_knowledge.py — Phase 53C camera knowledge injection tests.

Tests cover:
  - camera knowledge pack loading
  - camera knowledge retrieval by domain and tags
  - stable framing pack retrieval
  - talking-head / interview pack retrieval
  - vertical short-form pack retrieval
  - anti-jitter pack retrieval
  - malformed/missing knowledge handled gracefully
  - deterministic retrieval ordering
  - no camera mutation in returned packs
  - no crash on empty or None input
  - Phase 52B evaluator knowledge integration
  - Phase 50B inference knowledge integration

All tests are pure-Python. No video rendering, no network, no cloud API.
Audit reference: docs/review/render_audit.md — Phase 53C
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_camera_json(knowledge_id: str, tags: list, creator_style: str = "") -> dict:
    return {
        "knowledge_id": knowledge_id,
        "category": "camera",
        "source_type": "style_pattern",
        "creator_style": creator_style,
        "title": f"Test: {knowledge_id}",
        "description": f"Test description for {knowledge_id}.",
        "tags": tags,
        "hook_patterns": [],
        "subtitle_patterns": {},
        "pacing_patterns": {},
        "camera_patterns": {"deadzone": "normal", "smoothing": "medium"},
        "retention_patterns": {},
        "creator_patterns": {},
    }


def _write_knowledge_dir(base: Path, items: list) -> Path:
    """Write camera JSON items to a temp knowledge directory."""
    sub = base / "camera"
    sub.mkdir(parents=True, exist_ok=True)
    for item in items:
        (sub / f"{item['knowledge_id']}.json").write_text(
            json.dumps(item), encoding="utf-8"
        )
    return base


# ---------------------------------------------------------------------------
# 1. Schema — basic construction and to_dict
# ---------------------------------------------------------------------------

def test_schema_item_to_dict():
    from app.ai.knowledge.camera_knowledge_schema import AICameraKnowledgeItem

    item = AICameraKnowledgeItem(
        knowledge_id="test_cam_item",
        title="Test Camera Title",
        description="Test camera desc.",
        tags=["stable_framing", "jitter"],
        camera_patterns={"deadzone": "wide", "smoothing": "high"},
        creator_style="podcast",
    )
    d = item.to_dict()
    assert d["knowledge_id"] == "test_cam_item"
    assert d["tags"] == ["stable_framing", "jitter"]
    assert d["camera_patterns"]["deadzone"] == "wide"
    assert d["creator_style"] == "podcast"


def test_schema_pack_to_dict_empty():
    from app.ai.knowledge.camera_knowledge_schema import AICameraKnowledgePack

    pack = AICameraKnowledgePack()
    d = pack.to_dict()
    assert d["available"] is False
    assert d["domain"] == "camera"
    assert d["items"] == []
    assert d["reasoning_hints"] == []
    assert d["warnings"] == []


def test_schema_pack_to_dict_with_items():
    from app.ai.knowledge.camera_knowledge_schema import (
        AICameraKnowledgeItem,
        AICameraKnowledgePack,
    )

    item = AICameraKnowledgeItem(knowledge_id="k1", title="T", description="D")
    pack = AICameraKnowledgePack(
        available=True,
        domain="camera",
        items=[item],
        reasoning_hints=["camera hint one"],
        warnings=[],
    )
    d = pack.to_dict()
    assert d["available"] is True
    assert len(d["items"]) == 1
    assert d["items"][0]["knowledge_id"] == "k1"
    assert d["reasoning_hints"] == ["camera hint one"]


# ---------------------------------------------------------------------------
# 2. Retrieval — no crash on empty / None input
# ---------------------------------------------------------------------------

def test_retrieve_empty_tags_no_crash():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=[])
    assert pack is not None
    assert hasattr(pack, "available")


def test_retrieve_none_tags_no_crash():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=None)
    assert pack is not None


def test_retrieve_empty_domain_no_crash():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="", tags=["jitter"])
    assert pack is not None


def test_retrieve_none_base_path_no_crash():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=["stable_framing"], base_path=None)
    assert pack is not None


# ---------------------------------------------------------------------------
# 3. Retrieval from temp knowledge directory
# ---------------------------------------------------------------------------

def test_retrieve_returns_matching_items():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("stable_framing_camera", ["stable_framing", "jitter", "smooth"]),
        _make_camera_json("vertical_shortform_camera", ["vertical", "shortform", "tiktok"]),
        _make_camera_json("interview_camera", ["interview", "talking_head", "podcast"],
                          creator_style="podcast"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["stable_framing"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "stable_framing_camera" in ids
    assert "vertical_shortform_camera" not in ids


def test_retrieve_no_match_returns_unavailable():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [_make_camera_json("stable_framing_camera", ["stable_framing", "smooth"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["tiktok"], base_path=base)

    assert pack.available is False
    assert len(pack.items) == 0
    assert len(pack.warnings) > 0


# ---------------------------------------------------------------------------
# 4. Stable framing retrieval
# ---------------------------------------------------------------------------

def test_stable_framing_retrieval():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("stable_framing_camera", ["stable_framing", "jitter", "smooth"]),
        _make_camera_json("dynamic_viral_camera", ["dynamic", "viral", "shortform"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["stable_framing"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "stable_framing_camera" in ids
    assert "dynamic_viral_camera" not in ids


# ---------------------------------------------------------------------------
# 5. Talking-head / interview retrieval
# ---------------------------------------------------------------------------

def test_interview_talking_head_retrieval():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("interview_talking_head_camera",
                          ["interview", "talking_head", "centered", "podcast"],
                          creator_style="podcast"),
        _make_camera_json("dynamic_viral_camera", ["dynamic", "viral"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["talking_head"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "interview_talking_head_camera" in ids
    assert "dynamic_viral_camera" not in ids


# ---------------------------------------------------------------------------
# 6. Vertical short-form retrieval
# ---------------------------------------------------------------------------

def test_vertical_shortform_retrieval():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("vertical_shortform_camera",
                          ["vertical", "shortform", "mobile", "tiktok", "9_16"],
                          creator_style="viral_tiktok"),
        _make_camera_json("interview_talking_head_camera", ["interview", "talking_head"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["vertical"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "vertical_shortform_camera" in ids
    assert "interview_talking_head_camera" not in ids


# ---------------------------------------------------------------------------
# 7. Anti-jitter retrieval
# ---------------------------------------------------------------------------

def test_anti_jitter_retrieval():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("anti_jitter_camera",
                          ["anti_jitter", "jitter", "whip_pan", "smoothing", "deadzone"]),
        _make_camera_json("dynamic_viral_camera", ["dynamic", "viral"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["anti_jitter", "jitter"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "anti_jitter_camera" in ids


def test_anti_jitter_camera_patterns_present():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    item = _make_camera_json("anti_jitter_camera",
                             ["anti_jitter", "jitter", "smoothing"])
    item["camera_patterns"] = {
        "deadzone": "wide",
        "smoothing": "high",
        "overreactive_tracking_risk": True,
        "whip_pan_prevention": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), [item])
        pack = retrieve_knowledge(domain="camera", tags=["anti_jitter"], base_path=base)

    assert pack.available is True
    patterns = pack.items[0].camera_patterns
    assert patterns.get("deadzone") == "wide"
    assert patterns.get("smoothing") == "high"
    assert patterns.get("overreactive_tracking_risk") is True


# ---------------------------------------------------------------------------
# 8. Malformed knowledge files are ignored
# ---------------------------------------------------------------------------

def test_malformed_knowledge_ignored():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "camera"
        sub.mkdir()
        # malformed JSON
        (sub / "bad.json").write_text("{ not valid json }", encoding="utf-8")
        # missing knowledge_id
        (sub / "no_id.json").write_text(
            json.dumps({"category": "camera", "source_type": "style_pattern", "tags": ["jitter"]}),
            encoding="utf-8",
        )
        # valid item
        (sub / "good.json").write_text(
            json.dumps(_make_camera_json("good_camera_item", ["jitter"])),
            encoding="utf-8",
        )
        pack = retrieve_knowledge(domain="camera", tags=["jitter"], base_path=Path(tmp))

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "good_camera_item" in ids
    assert "bad" not in ids


# ---------------------------------------------------------------------------
# 9. Deterministic retrieval order
# ---------------------------------------------------------------------------

def test_deterministic_retrieval_order():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("zzz_last_camera", ["jitter"]),
        _make_camera_json("aaa_first_camera", ["jitter"]),
        _make_camera_json("mmm_middle_camera", ["jitter"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack1 = retrieve_knowledge(domain="camera", tags=["jitter"], base_path=base)
        pack2 = retrieve_knowledge(domain="camera", tags=["jitter"], base_path=base)

    ids1 = [i.knowledge_id for i in pack1.items]
    ids2 = [i.knowledge_id for i in pack2.items]
    assert ids1 == ids2
    assert ids1 == sorted(ids1)


def test_creator_style_prioritized_in_order():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [
        _make_camera_json("zzz_generic_camera", ["stable_framing"]),
        _make_camera_json("aaa_podcast_camera", ["stable_framing"], creator_style="podcast"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(
            domain="camera",
            tags=["stable_framing"],
            creator_style="podcast",
            base_path=base,
        )

    ids = [i.knowledge_id for i in pack.items]
    assert ids.index("aaa_podcast_camera") < ids.index("zzz_generic_camera")


# ---------------------------------------------------------------------------
# 10. No camera mutation in returned packs
# ---------------------------------------------------------------------------

def test_no_camera_mutation_keys_in_pack():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    _FORBIDDEN = {
        "motion_crop", "tracking_config", "ffmpeg_args", "render_command",
        "scene_detection", "executor", "subprocess", "executable",
        "crop_rewrite", "tracking_rewrite",
    }

    items = [_make_camera_json("safe_cam_item", ["stable_framing", "jitter"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["stable_framing"], base_path=base)

    pack_str = str(pack.to_dict())
    for forbidden in _FORBIDDEN:
        assert forbidden not in pack_str, f"Forbidden key '{forbidden}' found in pack"


def test_pack_has_no_executable_content():
    from app.ai.knowledge.camera_knowledge_schema import AICameraKnowledgePack, AICameraKnowledgeItem

    item = AICameraKnowledgeItem(
        knowledge_id="safe_cam",
        camera_patterns={"deadzone": "wide", "smoothing": "high"},
    )
    pack = AICameraKnowledgePack(available=True, items=[item])
    d = pack.to_dict()
    assert "ffmpeg_args" not in str(d)
    assert "render_command" not in str(d)
    assert "subprocess" not in str(d)
    assert "motion_crop" not in str(d)


# ---------------------------------------------------------------------------
# 11. Reasoning hints
# ---------------------------------------------------------------------------

def test_reasoning_hints_populated():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [_make_camera_json("stable_framing_camera", ["stable_framing", "smooth"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["stable_framing"], base_path=base)

    assert pack.available is True
    assert len(pack.reasoning_hints) > 0
    hint = pack.reasoning_hints[0]
    assert isinstance(hint, str)
    assert len(hint) > 0


def test_build_camera_reasoning_returns_list():
    from app.ai.knowledge.camera_knowledge_retriever import (
        retrieve_knowledge,
        build_camera_reasoning,
    )

    items = [
        _make_camera_json("interview_cam", ["interview", "talking_head"], creator_style="podcast")
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["interview"], base_path=base)

    hints = build_camera_reasoning(pack, creator_style="podcast", motion_style="static_center")
    assert isinstance(hints, list)
    for h in hints:
        assert isinstance(h, str)


def test_build_camera_reasoning_empty_pack():
    from app.ai.knowledge.camera_knowledge_schema import AICameraKnowledgePack
    from app.ai.knowledge.camera_knowledge_retriever import build_camera_reasoning

    empty_pack = AICameraKnowledgePack(available=False)
    hints = build_camera_reasoning(empty_pack, creator_style="podcast", motion_style="static_center")
    assert hints == []


# ---------------------------------------------------------------------------
# 12. Max results bound
# ---------------------------------------------------------------------------

def test_max_results_respected():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [_make_camera_json(f"cam_item_{i}", ["jitter"]) for i in range(8)]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["jitter"], base_path=base, max_results=3)

    assert pack.available is True
    assert len(pack.items) <= 3


def test_max_results_clamped_to_bounds():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    items = [_make_camera_json(f"cam_item_{i}", ["jitter"]) for i in range(20)]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="camera", tags=["jitter"], base_path=base, max_results=999)

    assert len(pack.items) <= 10


# ---------------------------------------------------------------------------
# 13. Real camera knowledge files load (integration smoke tests)
# ---------------------------------------------------------------------------

def test_real_camera_knowledge_packs_load():
    """Smoke: real knowledge/camera/ files parse without error."""
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=["stable_framing"])
    assert pack is not None
    assert isinstance(pack.available, bool)


def test_real_anti_jitter_pack_loads():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=["anti_jitter"])
    assert pack is not None


def test_real_talking_head_pack_loads():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=["talking_head"])
    assert pack is not None


def test_real_vertical_pack_loads():
    from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="camera", tags=["vertical"])
    assert pack is not None


# ---------------------------------------------------------------------------
# 14. Phase 52B knowledge integration — camera quality evaluator
# ---------------------------------------------------------------------------

def test_camera_quality_evaluator_no_crash_with_knowledge():
    """Phase 52B evaluate_camera_quality_v2 doesn't crash with knowledge available."""
    from app.ai.camera_quality.camera_quality_evaluator import evaluate_camera_quality_v2

    result = evaluate_camera_quality_v2(None)
    assert "camera_quality_v2" in result
    assert isinstance(result["camera_quality_v2"], dict)


def test_camera_quality_evaluator_returns_valid_schema():
    """Phase 52B output shape is unchanged after Phase 53C integration."""
    from app.ai.camera_quality.camera_quality_evaluator import evaluate_camera_quality_v2

    result = evaluate_camera_quality_v2(None)
    q = result["camera_quality_v2"]
    for key in ("micro_jitter_risk", "whip_pan_risk", "crop_smoothness",
                "subject_stability", "scene_continuity", "creator_fit",
                "overall", "confidence", "reasoning"):
        assert key in q, f"Missing key: {key}"


def test_camera_quality_evaluator_reasoning_is_list():
    """Phase 52B reasoning list remains a list after Phase 53C enrichment."""
    from app.ai.camera_quality.camera_quality_evaluator import evaluate_camera_quality_v2

    result = evaluate_camera_quality_v2(None)
    reasoning = result["camera_quality_v2"]["reasoning"]
    assert isinstance(reasoning, list)
    for hint in reasoning:
        assert isinstance(hint, str)


def test_jitter_knowledge_hint_no_crash():
    """_jitter_knowledge_hint() never raises and returns str."""
    from app.ai.camera_quality.camera_quality_evaluator import _jitter_knowledge_hint

    hint = _jitter_knowledge_hint()
    assert isinstance(hint, str)


def test_jitter_knowledge_hint_no_forbidden_keys():
    """_jitter_knowledge_hint() output contains no execution-related content."""
    from app.ai.camera_quality.camera_quality_evaluator import _jitter_knowledge_hint

    hint = _jitter_knowledge_hint()
    for forbidden in ("ffmpeg", "render_command", "motion_crop", "tracking_config",
                      "subprocess", "executable", "crop_rewrite"):
        assert forbidden not in hint


# ---------------------------------------------------------------------------
# 15. Phase 50B knowledge integration — camera preference inference
# ---------------------------------------------------------------------------

def test_camera_preference_inference_no_crash_with_knowledge():
    """Phase 50B infer_camera_preference doesn't crash with knowledge available."""
    from app.ai.creator_camera.camera_preference_inference import infer_camera_preference

    result = infer_camera_preference(None)
    assert result is not None


def test_camera_preference_inference_signals_are_strings():
    """Phase 50B signals list elements are all strings after Phase 53C enrichment."""
    from app.ai.creator_camera.camera_preference_inference import infer_camera_preference

    result = infer_camera_preference(None)
    # result is an AICameraPreference object
    signals = getattr(result, "signals", [])
    assert isinstance(signals, list)
    for sig in signals:
        assert isinstance(sig, str)


def test_get_camera_knowledge_signal_no_crash():
    """_get_camera_knowledge_signal() never raises and returns str."""
    from app.ai.creator_camera.camera_preference_inference import _get_camera_knowledge_signal

    for motion_style in ("static_center", "smooth_subject", "dynamic_subject", "unknown", ""):
        result = _get_camera_knowledge_signal(motion_style)
        assert isinstance(result, str)


def test_get_camera_knowledge_signal_bounded():
    """_get_camera_knowledge_signal() result never exceeds 100 chars."""
    from app.ai.creator_camera.camera_preference_inference import _get_camera_knowledge_signal

    for motion_style in ("static_center", "smooth_subject", "dynamic_subject"):
        sig = _get_camera_knowledge_signal(motion_style)
        assert len(sig) <= 100


def test_camera_knowledge_signal_no_forbidden_content():
    """_get_camera_knowledge_signal() output contains no execution-related content."""
    from app.ai.creator_camera.camera_preference_inference import _get_camera_knowledge_signal

    for motion_style in ("static_center", "smooth_subject", "dynamic_subject"):
        sig = _get_camera_knowledge_signal(motion_style)
        for forbidden in ("ffmpeg", "render_command", "motion_crop", "tracking_config",
                          "subprocess", "executable"):
            assert forbidden not in sig


def test_camera_knowledge_aware_reasoning_example():
    """Knowledge-aware reasoning: static_center + podcast → alignment hint produced."""
    from app.ai.knowledge.camera_knowledge_retriever import (
        retrieve_knowledge,
        build_camera_reasoning,
    )

    pack = retrieve_knowledge(domain="camera", tags=["talking_head"])
    hints = build_camera_reasoning(pack, creator_style="podcast", motion_style="static_center")
    assert isinstance(hints, list)
    for h in hints:
        assert isinstance(h, str)
