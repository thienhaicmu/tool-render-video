"""
test_ai_phase53b_subtitle_knowledge.py — Phase 53B subtitle knowledge injection tests.

Tests cover:
  - subtitle knowledge pack loading
  - subtitle knowledge retrieval by domain and tags
  - mobile readability pack retrieval
  - TikTok short-form pack retrieval
  - podcast subtitle pack retrieval
  - malformed/missing knowledge handled gracefully
  - deterministic retrieval ordering
  - no subtitle mutation in returned packs
  - no crash on empty or None input

All tests are pure-Python. No video rendering, no network, no cloud API.
Audit reference: docs/review/render_audit.md — Phase 53B
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_subtitle_json(knowledge_id: str, tags: list, creator_style: str = "") -> dict:
    return {
        "knowledge_id": knowledge_id,
        "category": "subtitle",
        "source_type": "subtitle_pattern",
        "creator_style": creator_style,
        "title": f"Test: {knowledge_id}",
        "description": f"Test description for {knowledge_id}.",
        "tags": tags,
        "hook_patterns": [],
        "subtitle_patterns": {"density": "compact", "readability_first": True},
        "pacing_patterns": {},
        "camera_patterns": {},
        "retention_patterns": {},
        "creator_patterns": {},
    }


def _write_knowledge_dir(base: Path, items: list) -> Path:
    """Write subtitle JSON items to a temp knowledge directory."""
    sub = base / "subtitles"
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
    from app.ai.knowledge.subtitle_knowledge_schema import AISubtitleKnowledgeItem

    item = AISubtitleKnowledgeItem(
        knowledge_id="test_item",
        title="Test Title",
        description="Test desc.",
        tags=["mobile", "readability"],
        subtitle_patterns={"density": "compact"},
        creator_style="viral_tiktok",
    )
    d = item.to_dict()
    assert d["knowledge_id"] == "test_item"
    assert d["tags"] == ["mobile", "readability"]
    assert d["subtitle_patterns"]["density"] == "compact"
    assert d["creator_style"] == "viral_tiktok"


def test_schema_pack_to_dict_empty():
    from app.ai.knowledge.subtitle_knowledge_schema import AISubtitleKnowledgePack

    pack = AISubtitleKnowledgePack()
    d = pack.to_dict()
    assert d["available"] is False
    assert d["domain"] == "subtitle"
    assert d["items"] == []
    assert d["reasoning_hints"] == []
    assert d["warnings"] == []


def test_schema_pack_to_dict_with_items():
    from app.ai.knowledge.subtitle_knowledge_schema import (
        AISubtitleKnowledgeItem,
        AISubtitleKnowledgePack,
    )

    item = AISubtitleKnowledgeItem(knowledge_id="k1", title="T", description="D")
    pack = AISubtitleKnowledgePack(
        available=True,
        domain="subtitle",
        items=[item],
        reasoning_hints=["hint one"],
        warnings=[],
    )
    d = pack.to_dict()
    assert d["available"] is True
    assert len(d["items"]) == 1
    assert d["items"][0]["knowledge_id"] == "k1"
    assert d["reasoning_hints"] == ["hint one"]


# ---------------------------------------------------------------------------
# 2. Retrieval — no crash on empty / None input
# ---------------------------------------------------------------------------

def test_retrieve_empty_tags_no_crash():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="subtitle", tags=[])
    assert pack is not None
    assert hasattr(pack, "available")


def test_retrieve_none_tags_no_crash():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="subtitle", tags=None)
    assert pack is not None


def test_retrieve_empty_domain_no_crash():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="", tags=["mobile"])
    assert pack is not None


def test_retrieve_none_base_path_no_crash():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    # Uses the real knowledge/ directory — should not crash regardless of outcome
    pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=None)
    assert pack is not None


# ---------------------------------------------------------------------------
# 3. Retrieval from temp knowledge directory
# ---------------------------------------------------------------------------

def test_retrieve_returns_matching_items():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [
        _make_subtitle_json("mobile_pack", ["mobile", "readability"]),
        _make_subtitle_json("tiktok_pack", ["tiktok", "shortform"]),
        _make_subtitle_json("podcast_pack", ["podcast", "clean"], creator_style="podcast"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "mobile_pack" in ids
    assert "tiktok_pack" not in ids


def test_retrieve_no_match_returns_unavailable():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [_make_subtitle_json("mobile_pack", ["mobile", "readability"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["podcast"], base_path=base)

    assert pack.available is False
    assert len(pack.items) == 0
    assert len(pack.warnings) > 0


# ---------------------------------------------------------------------------
# 4. Mobile readability retrieval
# ---------------------------------------------------------------------------

def test_mobile_readability_retrieval():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [
        _make_subtitle_json("mobile_readability_subtitle", ["mobile", "readability", "compact"]),
        _make_subtitle_json("tiktok_shortform_subtitle", ["tiktok", "shortform"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile", "readability"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "mobile_readability_subtitle" in ids


# ---------------------------------------------------------------------------
# 5. TikTok subtitle retrieval
# ---------------------------------------------------------------------------

def test_tiktok_subtitle_retrieval():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [
        _make_subtitle_json("mobile_readability_subtitle", ["mobile", "readability"]),
        _make_subtitle_json("tiktok_shortform_subtitle", ["tiktok", "shortform", "mobile"],
                            creator_style="viral_tiktok"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["tiktok"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "tiktok_shortform_subtitle" in ids
    assert "mobile_readability_subtitle" not in ids


# ---------------------------------------------------------------------------
# 6. Podcast subtitle retrieval
# ---------------------------------------------------------------------------

def test_podcast_subtitle_retrieval():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [
        _make_subtitle_json("podcast_talking_head_subtitle", ["podcast", "clean", "readability"],
                            creator_style="podcast"),
        _make_subtitle_json("tiktok_shortform_subtitle", ["tiktok", "shortform"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["podcast"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "podcast_talking_head_subtitle" in ids
    assert "tiktok_shortform_subtitle" not in ids


# ---------------------------------------------------------------------------
# 7. Malformed knowledge files are ignored
# ---------------------------------------------------------------------------

def test_malformed_knowledge_ignored():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "subtitles"
        sub.mkdir()
        # malformed JSON
        (sub / "bad.json").write_text("{ not valid json }", encoding="utf-8")
        # missing knowledge_id
        (sub / "no_id.json").write_text(
            json.dumps({"category": "subtitle", "source_type": "subtitle_pattern", "tags": ["mobile"]}),
            encoding="utf-8",
        )
        # valid item
        (sub / "good.json").write_text(
            json.dumps(_make_subtitle_json("good_item", ["mobile"])),
            encoding="utf-8",
        )
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=Path(tmp))

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "good_item" in ids
    assert "bad" not in ids


# ---------------------------------------------------------------------------
# 8. Deterministic retrieval order
# ---------------------------------------------------------------------------

def test_deterministic_retrieval_order():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [
        _make_subtitle_json("zzz_last", ["mobile"]),
        _make_subtitle_json("aaa_first", ["mobile"]),
        _make_subtitle_json("mmm_middle", ["mobile"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack1 = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base)
        pack2 = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base)

    # Same call → same order (deterministic)
    ids1 = [i.knowledge_id for i in pack1.items]
    ids2 = [i.knowledge_id for i in pack2.items]
    assert ids1 == ids2
    # Alphabetical by knowledge_id
    assert ids1 == sorted(ids1)


def test_creator_style_prioritized_in_order():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [
        _make_subtitle_json("zzz_generic", ["mobile"]),
        _make_subtitle_json("aaa_tiktok", ["mobile"], creator_style="viral_tiktok"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(
            domain="subtitle",
            tags=["mobile"],
            creator_style="viral_tiktok",
            base_path=base,
        )

    ids = [i.knowledge_id for i in pack.items]
    # viral_tiktok match should appear before generic item
    assert ids.index("aaa_tiktok") < ids.index("zzz_generic")


# ---------------------------------------------------------------------------
# 9. No subtitle mutation in returned packs
# ---------------------------------------------------------------------------

def test_no_subtitle_mutation_keys_in_pack():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    _FORBIDDEN = {
        "start_time", "end_time", "timestamp", "subtitle_timing", "subtitle_shift",
        "playback_speed", "ffmpeg_args", "full_text_rewrite", "generated_script",
        "output_path", "render_command", "subprocess", "executable",
    }

    items = [_make_subtitle_json("clean_item", ["mobile", "readability"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base)

    pack_dict = pack.to_dict()
    pack_str = str(pack_dict)
    for forbidden in _FORBIDDEN:
        assert forbidden not in pack_str, f"Forbidden key '{forbidden}' found in pack"


def test_pack_has_no_executable_content():
    from app.ai.knowledge.subtitle_knowledge_schema import AISubtitleKnowledgePack, AISubtitleKnowledgeItem

    item = AISubtitleKnowledgeItem(
        knowledge_id="safe_item",
        subtitle_patterns={"density": "compact", "readability_first": True},
    )
    pack = AISubtitleKnowledgePack(available=True, items=[item])
    d = pack.to_dict()
    assert "ffmpeg_args" not in str(d)
    assert "render_command" not in str(d)
    assert "subprocess" not in str(d)


# ---------------------------------------------------------------------------
# 10. Reasoning hints
# ---------------------------------------------------------------------------

def test_reasoning_hints_populated():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [_make_subtitle_json("mobile_readability_subtitle", ["mobile", "readability"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base)

    assert pack.available is True
    assert len(pack.reasoning_hints) > 0
    hint = pack.reasoning_hints[0]
    assert isinstance(hint, str)
    assert len(hint) > 0


def test_build_subtitle_reasoning_returns_list():
    from app.ai.knowledge.subtitle_knowledge_retriever import (
        retrieve_knowledge,
        build_subtitle_reasoning,
    )

    items = [
        _make_subtitle_json("podcast_pack", ["podcast", "clean"], creator_style="podcast")
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["podcast"], base_path=base)

    hints = build_subtitle_reasoning(pack, creator_style="podcast", subtitle_style="clean")
    assert isinstance(hints, list)
    for h in hints:
        assert isinstance(h, str)


def test_build_subtitle_reasoning_empty_pack():
    from app.ai.knowledge.subtitle_knowledge_schema import AISubtitleKnowledgePack
    from app.ai.knowledge.subtitle_knowledge_retriever import build_subtitle_reasoning

    empty_pack = AISubtitleKnowledgePack(available=False)
    hints = build_subtitle_reasoning(empty_pack, creator_style="podcast", subtitle_style="clean")
    assert hints == []


# ---------------------------------------------------------------------------
# 11. Max results bound
# ---------------------------------------------------------------------------

def test_max_results_respected():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [_make_subtitle_json(f"item_{i}", ["mobile"]) for i in range(8)]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base, max_results=3)

    assert pack.available is True
    assert len(pack.items) <= 3


def test_max_results_clamped_to_bounds():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    items = [_make_subtitle_json(f"item_{i}", ["mobile"]) for i in range(20)]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        # max_results=999 should be clamped to 10
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile"], base_path=base, max_results=999)

    assert len(pack.items) <= 10


# ---------------------------------------------------------------------------
# 12. Real knowledge files load (integration smoke test)
# ---------------------------------------------------------------------------

def test_real_subtitle_knowledge_packs_load():
    """Smoke: real knowledge/subtitles/ files parse without error."""
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="subtitle", tags=["mobile"])
    # Should not crash; available depends on whether files are present
    assert pack is not None
    assert isinstance(pack.available, bool)


def test_real_tiktok_pack_loads():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="subtitle", tags=["tiktok"])
    assert pack is not None


def test_real_podcast_pack_loads():
    from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="subtitle", tags=["podcast"])
    assert pack is not None


# ---------------------------------------------------------------------------
# 13. Phase 52A knowledge integration — quality evaluator (requirement #5)
# ---------------------------------------------------------------------------

def test_quality_evaluator_no_crash_with_knowledge():
    """Phase 52A evaluate_subtitle_quality_v2 doesn't crash with knowledge available."""
    from app.ai.subtitle_quality.subtitle_quality_evaluator import evaluate_subtitle_quality_v2

    result = evaluate_subtitle_quality_v2(None)
    assert "subtitle_quality_v2" in result
    assert isinstance(result["subtitle_quality_v2"], dict)


def test_quality_evaluator_returns_valid_schema():
    """Phase 52A output shape is unchanged after Phase 53B integration."""
    from app.ai.subtitle_quality.subtitle_quality_evaluator import evaluate_subtitle_quality_v2

    result = evaluate_subtitle_quality_v2(None)
    q = result["subtitle_quality_v2"]
    for key in ("mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
                "safe_zone_fit", "creator_fit", "overload_risk", "fatigue_risk",
                "overall", "confidence", "reasoning"):
        assert key in q, f"Missing key: {key}"


def test_quality_evaluator_reasoning_is_list():
    """Phase 52A reasoning list remains a list after Phase 53B enrichment."""
    from app.ai.subtitle_quality.subtitle_quality_evaluator import evaluate_subtitle_quality_v2

    result = evaluate_subtitle_quality_v2(None)
    reasoning = result["subtitle_quality_v2"]["reasoning"]
    assert isinstance(reasoning, list)
    for hint in reasoning:
        assert isinstance(hint, str)


def test_mobile_knowledge_hint_no_crash():
    """_mobile_knowledge_hint() never raises and returns str."""
    from app.ai.subtitle_quality.subtitle_quality_evaluator import _mobile_knowledge_hint

    hint = _mobile_knowledge_hint()
    assert isinstance(hint, str)


def test_mobile_knowledge_hint_no_forbidden_keys():
    """_mobile_knowledge_hint() output contains no execution-related content."""
    from app.ai.subtitle_quality.subtitle_quality_evaluator import _mobile_knowledge_hint

    hint = _mobile_knowledge_hint()
    for forbidden in ("ffmpeg", "render_command", "subtitle_timing", "playback_speed",
                      "subprocess", "executable"):
        assert forbidden not in hint


# ---------------------------------------------------------------------------
# 14. Phase 50A knowledge integration — preference inference (requirement #4)
# ---------------------------------------------------------------------------

def test_preference_inference_no_crash_with_knowledge():
    """Phase 50A infer_subtitle_preference doesn't crash with knowledge available."""
    from app.ai.creator_subtitle.subtitle_preference_inference import infer_subtitle_preference

    result = infer_subtitle_preference(None)
    assert "subtitle_preference" in result


def test_preference_inference_signals_are_strings():
    """Phase 50A signals list elements are all strings after Phase 53B enrichment."""
    from app.ai.creator_subtitle.subtitle_preference_inference import infer_subtitle_preference

    result = infer_subtitle_preference(None)
    signals = result["subtitle_preference"].get("signals", [])
    assert isinstance(signals, list)
    for sig in signals:
        assert isinstance(sig, str)


def test_get_knowledge_signal_no_crash():
    """_get_knowledge_signal() never raises and returns str."""
    from app.ai.creator_subtitle.subtitle_preference_inference import _get_knowledge_signal

    for style, mobile_safe in [
        ("clean_pro", True),
        ("viral_bold", False),
        ("unknown", True),
        ("boxed_caption", False),
    ]:
        result = _get_knowledge_signal(style, mobile_safe)
        assert isinstance(result, str)


def test_get_knowledge_signal_bounded():
    """_get_knowledge_signal() result never exceeds 100 chars."""
    from app.ai.creator_subtitle.subtitle_preference_inference import _get_knowledge_signal

    for style in ("clean_pro", "viral_bold", "unknown"):
        sig = _get_knowledge_signal(style, True)
        assert len(sig) <= 100


def test_knowledge_signal_no_forbidden_content():
    """_get_knowledge_signal() output contains no execution-related content."""
    from app.ai.creator_subtitle.subtitle_preference_inference import _get_knowledge_signal

    for style in ("clean_pro", "viral_bold"):
        sig = _get_knowledge_signal(style, True)
        for forbidden in ("ffmpeg", "render_command", "subtitle_timing", "playback_speed",
                          "subprocess", "executable"):
            assert forbidden not in sig


def test_knowledge_aware_reasoning_example():
    """Knowledge-aware reasoning: clean_pro + podcast → alignment hint produced."""
    from app.ai.knowledge.subtitle_knowledge_retriever import (
        retrieve_knowledge,
        build_subtitle_reasoning,
    )

    pack = retrieve_knowledge(domain="subtitle", tags=["podcast"])
    hints = build_subtitle_reasoning(pack, creator_style="podcast", subtitle_style="clean_pro")
    assert isinstance(hints, list)
    # Each hint is a string; integration is optional (available depends on real files)
    for h in hints:
        assert isinstance(h, str)
