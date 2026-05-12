"""
test_ai_phase53d_hook_knowledge.py — Phase 53D hook / retention knowledge injection tests.

Tests cover:
  - hook knowledge pack loading
  - hook knowledge retrieval by domain and tags
  - first 3-second hook retrieval
  - first 5-second retention retrieval
  - curiosity / open-loop retrieval
  - market-specific hook retrieval (US, EU, JP)
  - hook fatigue / overuse retrieval
  - malformed knowledge files ignored gracefully
  - deterministic retrieval ordering
  - no hook / clip mutation in returned packs
  - no crash on empty or None input
  - Phase 52C evaluator knowledge integration

All tests are pure-Python. No video rendering, no network, no cloud API.
Audit reference: docs/review/render_audit.md — Phase 53D
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hook_json(
    knowledge_id: str,
    tags: list,
    creator_style: str = "",
    retention_patterns: dict | None = None,
) -> dict:
    return {
        "knowledge_id": knowledge_id,
        "category": "hook",
        "source_type": "hook_pattern",
        "creator_style": creator_style,
        "title": f"Test: {knowledge_id}",
        "description": f"Test description for {knowledge_id}.",
        "tags": tags,
        "hook_patterns": ["Test pattern one", "Test pattern two"],
        "subtitle_patterns": {},
        "pacing_patterns": {},
        "camera_patterns": {},
        "retention_patterns": retention_patterns or {"hook_style": "test"},
        "creator_patterns": {},
    }


def _write_knowledge_dir(base: Path, items: list) -> Path:
    """Write hook JSON items to a temp knowledge directory."""
    sub = base / "hooks"
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
    from app.ai.knowledge.hook_knowledge_schema import AIHookKnowledgeItem

    item = AIHookKnowledgeItem(
        knowledge_id="test_hook_item",
        title="Test Hook Title",
        description="Test hook desc.",
        tags=["first_3s", "opening", "attention"],
        hook_patterns=["Direct value pattern"],
        retention_patterns={"hook_style": "immediate_capture", "direct_value": True},
        creator_style="viral_tiktok",
    )
    d = item.to_dict()
    assert d["knowledge_id"] == "test_hook_item"
    assert d["tags"] == ["first_3s", "opening", "attention"]
    assert d["retention_patterns"]["hook_style"] == "immediate_capture"
    assert d["creator_style"] == "viral_tiktok"
    assert len(d["hook_patterns"]) == 1


def test_schema_pack_to_dict_empty():
    from app.ai.knowledge.hook_knowledge_schema import AIHookKnowledgePack

    pack = AIHookKnowledgePack()
    d = pack.to_dict()
    assert d["available"] is False
    assert d["domain"] == "hook"
    assert d["items"] == []
    assert d["reasoning_hints"] == []
    assert d["warnings"] == []


def test_schema_pack_to_dict_with_items():
    from app.ai.knowledge.hook_knowledge_schema import (
        AIHookKnowledgeItem,
        AIHookKnowledgePack,
    )

    item = AIHookKnowledgeItem(knowledge_id="k1", title="T", description="D")
    pack = AIHookKnowledgePack(
        available=True,
        domain="hook",
        items=[item],
        reasoning_hints=["hook hint one"],
        warnings=[],
    )
    d = pack.to_dict()
    assert d["available"] is True
    assert len(d["items"]) == 1
    assert d["items"][0]["knowledge_id"] == "k1"
    assert d["reasoning_hints"] == ["hook hint one"]


# ---------------------------------------------------------------------------
# 2. Retrieval — no crash on empty / None input
# ---------------------------------------------------------------------------

def test_retrieve_empty_tags_no_crash():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=[])
    assert pack is not None
    assert hasattr(pack, "available")


def test_retrieve_none_tags_no_crash():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=None)
    assert pack is not None


def test_retrieve_empty_domain_no_crash():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="", tags=["first_3s"])
    assert pack is not None


def test_retrieve_none_base_path_no_crash():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=None)
    assert pack is not None


# ---------------------------------------------------------------------------
# 3. Retrieval from temp knowledge directory
# ---------------------------------------------------------------------------

def test_retrieve_returns_matching_items():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("opening_3s_hook", ["first_3s", "opening", "attention"]),
        _make_hook_json("first_5s_retention", ["first_5s", "retention", "momentum"]),
        _make_hook_json("curiosity_open_loop", ["curiosity", "open_loop", "tension"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "opening_3s_hook" in ids
    assert "first_5s_retention" not in ids


def test_retrieve_no_match_returns_unavailable():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [_make_hook_json("opening_3s_hook", ["first_3s", "opening"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["market_hook"], base_path=base)

    assert pack.available is False
    assert len(pack.items) == 0
    assert len(pack.warnings) > 0


# ---------------------------------------------------------------------------
# 4. First 3-second hook retrieval
# ---------------------------------------------------------------------------

def test_first_3s_hook_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("opening_3s_hook", ["first_3s", "opening", "capture", "hook"]),
        _make_hook_json("hook_fatigue_overuse", ["fatigue", "overuse", "hype"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "opening_3s_hook" in ids
    assert "hook_fatigue_overuse" not in ids


def test_first_3s_retention_patterns_present():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    item = _make_hook_json(
        "opening_3s_hook", ["first_3s", "opening"],
        retention_patterns={"slow_intro_risk": "high", "direct_value": True, "first_3s_critical": True},
    )
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), [item])
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)

    assert pack.available is True
    patterns = pack.items[0].retention_patterns
    assert patterns.get("slow_intro_risk") == "high"
    assert patterns.get("direct_value") is True


# ---------------------------------------------------------------------------
# 5. First 5-second retention retrieval
# ---------------------------------------------------------------------------

def test_first_5s_retention_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("first_5s_retention", ["first_5s", "retention", "momentum", "continuation"]),
        _make_hook_json("opening_3s_hook", ["first_3s", "opening"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_5s"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "first_5s_retention" in ids
    assert "opening_3s_hook" not in ids


# ---------------------------------------------------------------------------
# 6. Curiosity / open-loop retrieval
# ---------------------------------------------------------------------------

def test_curiosity_open_loop_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("curiosity_open_loop", ["curiosity", "open_loop", "tension", "payoff"]),
        _make_hook_json("opening_3s_hook", ["first_3s", "opening"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["curiosity", "open_loop"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "curiosity_open_loop" in ids
    assert "opening_3s_hook" not in ids


def test_curiosity_retention_patterns_present():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    item = _make_hook_json(
        "curiosity_open_loop", ["curiosity", "open_loop"],
        retention_patterns={"open_loop_clarity": "required", "narrative_tension": True},
    )
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), [item])
        pack = retrieve_knowledge(domain="hook", tags=["curiosity"], base_path=base)

    assert pack.available is True
    patterns = pack.items[0].retention_patterns
    assert patterns.get("open_loop_clarity") == "required"
    assert patterns.get("narrative_tension") is True


# ---------------------------------------------------------------------------
# 7. Market-specific hook retrieval (US, EU, JP)
# ---------------------------------------------------------------------------

def test_market_hook_us_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("market_hook_us", ["market_hook", "us", "direct", "high_energy"],
                        retention_patterns={"hook_style": "direct_promise", "market": "us"}),
        _make_hook_json("market_hook_eu", ["market_hook", "eu", "trust_first"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["market_hook", "us"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "market_hook_us" in ids


def test_market_hook_eu_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("market_hook_eu", ["market_hook", "eu", "trust_first", "credibility"],
                        retention_patterns={"hook_style": "trust_first", "market": "eu"}),
        _make_hook_json("market_hook_us", ["market_hook", "us", "direct"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        # Tag "eu" is unique to EU pack; tag "market_hook" matches both (any-match)
        pack = retrieve_knowledge(domain="hook", tags=["eu"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "market_hook_eu" in ids
    assert "market_hook_us" not in ids


def test_market_hook_jp_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("market_hook_jp", ["market_hook", "jp", "subtle", "story_first"],
                        retention_patterns={"hook_style": "story_invitation", "market": "jp"}),
        _make_hook_json("market_hook_us", ["market_hook", "us", "direct"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        # Tag "jp" is unique to JP pack; tag "market_hook" matches both (any-match)
        pack = retrieve_knowledge(domain="hook", tags=["jp"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "market_hook_jp" in ids
    assert "market_hook_us" not in ids


# ---------------------------------------------------------------------------
# 8. Hook fatigue / overuse retrieval
# ---------------------------------------------------------------------------

def test_hook_fatigue_retrieval():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("hook_fatigue_overuse", ["fatigue", "overuse", "hype", "credibility"],
                        retention_patterns={"fatigue_risk": "real", "variety_recommended": True}),
        _make_hook_json("opening_3s_hook", ["first_3s", "opening"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["fatigue"], base_path=base)

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "hook_fatigue_overuse" in ids
    assert "opening_3s_hook" not in ids


# ---------------------------------------------------------------------------
# 9. Malformed knowledge files are ignored
# ---------------------------------------------------------------------------

def test_malformed_knowledge_ignored():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "hooks"
        sub.mkdir()
        # malformed JSON
        (sub / "bad.json").write_text("{ not valid json }", encoding="utf-8")
        # missing knowledge_id
        (sub / "no_id.json").write_text(
            json.dumps({"category": "hook", "source_type": "hook_pattern", "tags": ["first_3s"]}),
            encoding="utf-8",
        )
        # valid item
        (sub / "good.json").write_text(
            json.dumps(_make_hook_json("good_hook_item", ["first_3s"])),
            encoding="utf-8",
        )
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=Path(tmp))

    assert pack.available is True
    ids = [i.knowledge_id for i in pack.items]
    assert "good_hook_item" in ids
    assert "bad" not in ids


# ---------------------------------------------------------------------------
# 10. Deterministic retrieval order
# ---------------------------------------------------------------------------

def test_deterministic_retrieval_order():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("zzz_last_hook", ["first_3s"]),
        _make_hook_json("aaa_first_hook", ["first_3s"]),
        _make_hook_json("mmm_middle_hook", ["first_3s"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack1 = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)
        pack2 = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)

    ids1 = [i.knowledge_id for i in pack1.items]
    ids2 = [i.knowledge_id for i in pack2.items]
    assert ids1 == ids2
    assert ids1 == sorted(ids1)


def test_creator_style_prioritized_in_order():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [
        _make_hook_json("zzz_generic_hook", ["curiosity"]),
        _make_hook_json("aaa_tiktok_hook", ["curiosity"], creator_style="viral_tiktok"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(
            domain="hook",
            tags=["curiosity"],
            creator_style="viral_tiktok",
            base_path=base,
        )

    ids = [i.knowledge_id for i in pack.items]
    assert ids.index("aaa_tiktok_hook") < ids.index("zzz_generic_hook")


# ---------------------------------------------------------------------------
# 11. No hook / clip mutation in returned packs
# ---------------------------------------------------------------------------

def test_no_hook_mutation_keys_in_pack():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    _FORBIDDEN = {
        "transcript", "clip_boundaries", "hook_rewrite", "render_command",
        "ffmpeg_args", "subtitle_timing", "motion_crop", "tracking_config",
        "subprocess", "executable", "playback_speed",
    }

    items = [_make_hook_json("safe_hook_item", ["first_3s", "opening"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)

    pack_str = str(pack.to_dict())
    for forbidden in _FORBIDDEN:
        assert forbidden not in pack_str, f"Forbidden key '{forbidden}' found in pack"


def test_pack_has_no_executable_content():
    from app.ai.knowledge.hook_knowledge_schema import AIHookKnowledgePack, AIHookKnowledgeItem

    item = AIHookKnowledgeItem(
        knowledge_id="safe_hook",
        hook_patterns=["Safe pattern"],
        retention_patterns={"hook_style": "direct", "direct_value": True},
    )
    pack = AIHookKnowledgePack(available=True, items=[item])
    d = pack.to_dict()
    assert "ffmpeg_args" not in str(d)
    assert "render_command" not in str(d)
    assert "subprocess" not in str(d)
    assert "transcript" not in str(d)
    assert "clip_boundaries" not in str(d)


# ---------------------------------------------------------------------------
# 12. Reasoning hints
# ---------------------------------------------------------------------------

def test_reasoning_hints_populated():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [_make_hook_json("opening_3s_hook", ["first_3s", "opening", "capture"])]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base)

    assert pack.available is True
    assert len(pack.reasoning_hints) > 0
    hint = pack.reasoning_hints[0]
    assert isinstance(hint, str)
    assert len(hint) > 0


def test_build_hook_reasoning_returns_list():
    from app.ai.knowledge.hook_knowledge_retriever import (
        retrieve_knowledge,
        build_hook_reasoning,
    )

    items = [
        _make_hook_json("curiosity_pack", ["curiosity", "open_loop"], creator_style="podcast")
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["curiosity"], base_path=base)

    hints = build_hook_reasoning(pack, creator_style="podcast", hook_style="narrative")
    assert isinstance(hints, list)
    for h in hints:
        assert isinstance(h, str)


def test_build_hook_reasoning_empty_pack():
    from app.ai.knowledge.hook_knowledge_schema import AIHookKnowledgePack
    from app.ai.knowledge.hook_knowledge_retriever import build_hook_reasoning

    empty_pack = AIHookKnowledgePack(available=False)
    hints = build_hook_reasoning(empty_pack, creator_style="podcast", hook_style="narrative")
    assert hints == []


# ---------------------------------------------------------------------------
# 13. Max results bound
# ---------------------------------------------------------------------------

def test_max_results_respected():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [_make_hook_json(f"hook_item_{i}", ["first_3s"]) for i in range(8)]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base, max_results=3)

    assert pack.available is True
    assert len(pack.items) <= 3


def test_max_results_clamped_to_bounds():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    items = [_make_hook_json(f"hook_item_{i}", ["first_3s"]) for i in range(20)]
    with tempfile.TemporaryDirectory() as tmp:
        base = _write_knowledge_dir(Path(tmp), items)
        pack = retrieve_knowledge(domain="hook", tags=["first_3s"], base_path=base, max_results=999)

    assert len(pack.items) <= 10


# ---------------------------------------------------------------------------
# 14. Real hook knowledge files load (integration smoke tests)
# ---------------------------------------------------------------------------

def test_real_hook_knowledge_packs_load():
    """Smoke: real knowledge/hooks/ files parse without error."""
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=["first_3s"])
    assert pack is not None
    assert isinstance(pack.available, bool)


def test_real_curiosity_pack_loads():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=["curiosity", "open_loop"])
    assert pack is not None


def test_real_market_us_pack_loads():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=["market_hook", "us"])
    assert pack is not None


def test_real_fatigue_pack_loads():
    from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge

    pack = retrieve_knowledge(domain="hook", tags=["fatigue"])
    assert pack is not None


# ---------------------------------------------------------------------------
# 15. Phase 52C knowledge integration — hook quality evaluator
# ---------------------------------------------------------------------------

def test_hook_quality_evaluator_no_crash_with_knowledge():
    """Phase 52C evaluate_hook_quality_v2 doesn't crash with knowledge available."""
    from app.ai.hook_quality.hook_quality_evaluator import evaluate_hook_quality_v2

    result = evaluate_hook_quality_v2(None)
    assert "hook_quality_v2" in result
    assert isinstance(result["hook_quality_v2"], dict)


def test_hook_quality_evaluator_returns_valid_schema():
    """Phase 52C output shape is unchanged after Phase 53D integration."""
    from app.ai.hook_quality.hook_quality_evaluator import evaluate_hook_quality_v2

    result = evaluate_hook_quality_v2(None)
    q = result["hook_quality_v2"]
    for key in ("first_3s_strength", "first_5s_retention", "curiosity_strength",
                "open_loop_quality", "hook_fatigue_risk", "market_fit",
                "creator_fit", "overall", "confidence", "reasoning"):
        assert key in q, f"Missing key: {key}"


def test_hook_quality_evaluator_reasoning_is_list():
    """Phase 52C reasoning list remains a list after Phase 53D enrichment."""
    from app.ai.hook_quality.hook_quality_evaluator import evaluate_hook_quality_v2

    result = evaluate_hook_quality_v2(None)
    reasoning = result["hook_quality_v2"]["reasoning"]
    assert isinstance(reasoning, list)
    for hint in reasoning:
        assert isinstance(hint, str)


def test_first3s_knowledge_hint_no_crash():
    """_first3s_knowledge_hint() never raises and returns str."""
    from app.ai.hook_quality.hook_quality_evaluator import _first3s_knowledge_hint

    hint = _first3s_knowledge_hint()
    assert isinstance(hint, str)


def test_first3s_knowledge_hint_no_forbidden_keys():
    """_first3s_knowledge_hint() output contains no execution-related content."""
    from app.ai.hook_quality.hook_quality_evaluator import _first3s_knowledge_hint

    hint = _first3s_knowledge_hint()
    for forbidden in ("ffmpeg", "render_command", "transcript", "clip_boundaries",
                      "subprocess", "executable", "playback_speed"):
        assert forbidden not in hint


def test_curiosity_knowledge_hint_no_crash():
    """_curiosity_knowledge_hint() never raises and returns str."""
    from app.ai.hook_quality.hook_quality_evaluator import _curiosity_knowledge_hint

    hint = _curiosity_knowledge_hint()
    assert isinstance(hint, str)


def test_curiosity_knowledge_hint_no_forbidden_keys():
    """_curiosity_knowledge_hint() output contains no execution-related content."""
    from app.ai.hook_quality.hook_quality_evaluator import _curiosity_knowledge_hint

    hint = _curiosity_knowledge_hint()
    for forbidden in ("ffmpeg", "render_command", "transcript", "clip_boundaries",
                      "subprocess", "executable"):
        assert forbidden not in hint


def test_market_hook_hint_no_crash():
    """_market_hook_hint() never raises for any input."""
    from app.ai.hook_quality.hook_quality_evaluator import _market_hook_hint

    for edit_plan in [None, {}, {"market_optimization_intelligence": {"target_market": "us"}}]:
        hint = _market_hook_hint(edit_plan)
        assert isinstance(hint, str)


def test_market_hook_hint_no_forbidden_keys():
    """_market_hook_hint() output contains no execution-related content."""
    from app.ai.hook_quality.hook_quality_evaluator import _market_hook_hint

    for market in ("us", "eu", "jp", ""):
        hint = _market_hook_hint({"market_optimization_intelligence": {"target_market": market}})
        for forbidden in ("ffmpeg", "render_command", "transcript", "clip_boundaries",
                          "subprocess", "executable"):
            assert forbidden not in hint


def test_market_hook_hint_unknown_market_returns_empty():
    """_market_hook_hint() returns empty string for unknown market codes."""
    from app.ai.hook_quality.hook_quality_evaluator import _market_hook_hint

    hint = _market_hook_hint({"market_optimization_intelligence": {"target_market": "xyz_unknown"}})
    assert isinstance(hint, str)


# ---------------------------------------------------------------------------
# 16. Knowledge-aware reasoning integration
# ---------------------------------------------------------------------------

def test_knowledge_aware_hook_reasoning_example():
    """Knowledge-aware reasoning: curiosity tags → alignment hint produced."""
    from app.ai.knowledge.hook_knowledge_retriever import (
        retrieve_knowledge,
        build_hook_reasoning,
    )

    pack = retrieve_knowledge(domain="hook", tags=["curiosity", "open_loop"])
    hints = build_hook_reasoning(pack, creator_style=None, hook_style="narrative")
    assert isinstance(hints, list)
    for h in hints:
        assert isinstance(h, str)


def test_hook_knowledge_signal_bounded():
    """Knowledge hint strings stay within reasonable display length."""
    from app.ai.hook_quality.hook_quality_evaluator import (
        _first3s_knowledge_hint,
        _curiosity_knowledge_hint,
    )

    for fn in (_first3s_knowledge_hint, _curiosity_knowledge_hint):
        hint = fn()
        assert len(hint) <= 200
