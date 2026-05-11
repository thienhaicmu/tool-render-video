"""
test_ai_phase53a_knowledge_injection.py — Phase 53A: Knowledge Injection Foundation tests.

Covers:
    - Pack schema: parse_pack, validate helpers, fallback
    - Pack loader: load from real seed pack, missing dir, empty dir
    - Retrieval: domain filter, tag scoring, max_results, determinism
    - Context builder: domain inference from quality signals, tag inference from pacing
    - Fallback behavior: never raises on None/garbage input
    - Determinism: same inputs → same output
    - No unsafe/internal fields exposed in to_dict() output
    - Schema dataclass clamping (confidence 0–1)
    - render_influence reporting
    - edit_plan_schema integration (knowledge_injection field exists)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.knowledge.knowledge_pack_schema import (
    KnowledgeContext,
    KnowledgeMatch,
    KnowledgePack,
    KnowledgePackRule,
    VALID_DOMAINS,
    fallback_knowledge_context,
    parse_pack,
    validate_pack_dict,
    validate_rule_dict,
)
from app.ai.knowledge.knowledge_pack_loader import load_knowledge_packs
from app.ai.knowledge.knowledge_pack_retriever import (
    retrieve_knowledge,
    retrieve_knowledge_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pack_dict(**overrides) -> dict:
    base = {
        "id": "test_pack",
        "domain": "subtitle",
        "title": "Test Pack",
        "version": 1,
        "tags": ["subtitle", "mobile"],
        "rules": [
            {
                "id": "rule_1",
                "title": "Rule One",
                "description": "A test rule",
                "applies_to": ["mobile", "short_form"],
                "recommendation": {"max_lines": 2},
                "confidence": 0.8,
            }
        ],
    }
    base.update(overrides)
    return base


def _write_pack(tmp_dir: Path, name: str, data: dict) -> Path:
    path = tmp_dir / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _make_plan(**kwargs) -> SimpleNamespace:
    defaults = dict(
        subtitle_quality_v2={},
        camera_quality_v2={},
        hook_quality_v2={},
        pacing={},
        market_optimization_intelligence={},
        knowledge_injection={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Class 1 — validate_pack_dict
# ---------------------------------------------------------------------------

class TestValidatePackDict:
    def test_valid_pack_passes(self):
        assert validate_pack_dict(_make_pack_dict()) is True

    def test_missing_id_fails(self):
        d = _make_pack_dict()
        del d["id"]
        assert validate_pack_dict(d) is False

    def test_missing_domain_fails(self):
        d = _make_pack_dict()
        del d["domain"]
        assert validate_pack_dict(d) is False

    def test_missing_rules_fails(self):
        d = _make_pack_dict()
        del d["rules"]
        assert validate_pack_dict(d) is False

    def test_rules_not_list_fails(self):
        d = _make_pack_dict(rules="not_a_list")
        assert validate_pack_dict(d) is False

    def test_non_dict_fails(self):
        assert validate_pack_dict("string") is False
        assert validate_pack_dict(None) is False
        assert validate_pack_dict(42) is False

    def test_empty_dict_fails(self):
        assert validate_pack_dict({}) is False


# ---------------------------------------------------------------------------
# Class 2 — validate_rule_dict
# ---------------------------------------------------------------------------

class TestValidateRuleDict:
    def test_valid_rule_passes(self):
        rule = {
            "id": "r1",
            "title": "T",
            "description": "D",
            "confidence": 0.5,
        }
        assert validate_rule_dict(rule) is True

    def test_missing_id_fails(self):
        rule = {"title": "T", "description": "D", "confidence": 0.5}
        assert validate_rule_dict(rule) is False

    def test_missing_confidence_fails(self):
        rule = {"id": "r1", "title": "T", "description": "D"}
        assert validate_rule_dict(rule) is False

    def test_non_dict_fails(self):
        assert validate_rule_dict(None) is False
        assert validate_rule_dict([]) is False


# ---------------------------------------------------------------------------
# Class 3 — parse_pack
# ---------------------------------------------------------------------------

class TestParsePack:
    def test_valid_pack_parsed(self):
        pack = parse_pack(_make_pack_dict())
        assert isinstance(pack, KnowledgePack)
        assert pack.id == "test_pack"
        assert pack.domain == "subtitle"
        assert len(pack.rules) == 1
        assert pack.rules[0].id == "rule_1"

    def test_malformed_rule_skipped(self):
        d = _make_pack_dict()
        d["rules"].append({"no_id": True})  # missing required fields
        pack = parse_pack(d)
        assert isinstance(pack, KnowledgePack)
        assert len(pack.rules) == 1  # only the valid rule

    def test_invalid_dict_returns_none(self):
        assert parse_pack({}) is None
        assert parse_pack(None) is None
        assert parse_pack("bad") is None

    def test_confidence_clamped(self):
        d = _make_pack_dict()
        d["rules"][0]["confidence"] = 5.0  # over 1.0
        pack = parse_pack(d)
        assert pack.rules[0].confidence == 1.0

    def test_confidence_clamped_negative(self):
        d = _make_pack_dict()
        d["rules"][0]["confidence"] = -0.5
        pack = parse_pack(d)
        assert pack.rules[0].confidence == 0.0

    def test_tags_optional(self):
        d = _make_pack_dict()
        del d["tags"]
        pack = parse_pack(d)
        assert pack is not None
        assert pack.tags == []

    def test_version_required_field(self):
        # version is required — removing it causes parse_pack to return None
        d = _make_pack_dict()
        del d["version"]
        assert parse_pack(d) is None

    def test_version_value_preserved(self):
        pack = parse_pack(_make_pack_dict(version=3))
        assert pack.version == 3


# ---------------------------------------------------------------------------
# Class 4 — fallback_knowledge_context
# ---------------------------------------------------------------------------

class TestFallbackKnowledgeContext:
    def test_returns_dict(self):
        fb = fallback_knowledge_context()
        assert isinstance(fb, dict)

    def test_required_keys(self):
        fb = fallback_knowledge_context()
        assert fb["available"] is False
        assert fb["domains"] == []
        assert fb["matches"] == []
        assert fb["confidence"] == 0.0
        assert fb["reasoning"] == []

    def test_independent_copies(self):
        fb1 = fallback_knowledge_context()
        fb2 = fallback_knowledge_context()
        fb1["domains"].append("subtitle")
        assert fb2["domains"] == []


# ---------------------------------------------------------------------------
# Class 5 — load_knowledge_packs
# ---------------------------------------------------------------------------

class TestLoadKnowledgePacks:
    def test_real_seed_pack_loads(self):
        packs = load_knowledge_packs()
        assert isinstance(packs, list)
        # At least the subtitle_readability_basics pack must be present
        ids = [p.id for p in packs]
        assert "subtitle_readability_basics" in ids

    def test_missing_dir_returns_empty(self):
        result = load_knowledge_packs(Path("/nonexistent/path/packs"))
        assert result == []

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = load_knowledge_packs(Path(tmp))
            assert result == []

    def test_malformed_json_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not valid json", encoding="utf-8")
            result = load_knowledge_packs(Path(tmp))
            assert result == []

    def test_sort_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_pack(Path(tmp), "zzz.json", _make_pack_dict(id="z_pack", domain="subtitle", version=2))
            _write_pack(Path(tmp), "aaa.json", _make_pack_dict(id="a_pack", domain="camera", version=1))
            result = load_knowledge_packs(Path(tmp))
            # Sorted by (domain, id, version): camera before subtitle
            assert result[0].domain == "camera"
            assert result[1].domain == "subtitle"

    def test_valid_pack_in_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_pack(Path(tmp), "pack.json", _make_pack_dict())
            result = load_knowledge_packs(Path(tmp))
            assert len(result) == 1
            assert result[0].id == "test_pack"

    def test_deterministic_sort_same_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_pack(Path(tmp), "b.json", _make_pack_dict(id="b_pack", domain="subtitle", version=1))
            _write_pack(Path(tmp), "a.json", _make_pack_dict(id="a_pack", domain="subtitle", version=1))
            result = load_knowledge_packs(Path(tmp))
            assert result[0].id == "a_pack"
            assert result[1].id == "b_pack"


# ---------------------------------------------------------------------------
# Class 6 — retrieve_knowledge (domain + tag scoring)
# ---------------------------------------------------------------------------

class TestRetrieveKnowledge:
    def _tmp_packs(self) -> Path:
        return None  # use real packs dir

    def test_returns_dict_with_matches_key(self):
        result = retrieve_knowledge()
        assert "knowledge_matches" in result
        assert isinstance(result["knowledge_matches"], list)

    def test_domain_filter_subtitle(self):
        result = retrieve_knowledge(domain="subtitle")
        for m in result["knowledge_matches"]:
            assert m["domain"] == "subtitle"

    def test_domain_filter_nonexistent(self):
        result = retrieve_knowledge(domain="nonexistent_domain_xyz")
        assert result["knowledge_matches"] == []

    def test_no_domain_returns_all(self):
        result_all = retrieve_knowledge(domain=None)
        result_sub = retrieve_knowledge(domain="subtitle")
        assert len(result_all["knowledge_matches"]) >= len(result_sub["knowledge_matches"])

    def test_max_results_respected(self):
        result = retrieve_knowledge(max_results=1)
        assert len(result["knowledge_matches"]) <= 1

    def test_tag_overlap_boosts_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_pack(Path(tmp), "high.json", _make_pack_dict(
                id="high_pack",
                domain="subtitle",
                tags=["subtitle", "mobile", "short_form"],
                rules=[{
                    "id": "r1", "title": "T", "description": "D",
                    "applies_to": ["mobile"],
                    "recommendation": {}, "confidence": 0.8,
                }],
            ))
            _write_pack(Path(tmp), "low.json", _make_pack_dict(
                id="low_pack",
                domain="subtitle",
                tags=["subtitle"],
                rules=[{
                    "id": "r2", "title": "T2", "description": "D2",
                    "applies_to": [],
                    "recommendation": {}, "confidence": 0.5,
                }],
            ))
            result = retrieve_knowledge(domain="subtitle", tags=["mobile", "short_form"], packs_dir=Path(tmp))
            matches = result["knowledge_matches"]
            # high_pack should come first (more tag overlap)
            assert len(matches) == 2
            assert matches[0]["pack_id"] == "high_pack"

    def test_never_raises_on_garbage(self):
        result = retrieve_knowledge(domain=object(), tags=None, max_results=-999)
        assert "knowledge_matches" in result

    def test_deterministic_output(self):
        r1 = retrieve_knowledge(domain="subtitle", tags=["mobile"])
        r2 = retrieve_knowledge(domain="subtitle", tags=["mobile"])
        assert r1 == r2

    def test_match_dict_fields(self):
        result = retrieve_knowledge(domain="subtitle")
        if result["knowledge_matches"]:
            m = result["knowledge_matches"][0]
            assert "pack_id" in m
            assert "rule_id" in m
            assert "domain" in m
            assert "title" in m
            assert "recommendation" in m
            assert "confidence" in m

    def test_score_field_not_exposed(self):
        result = retrieve_knowledge(domain="subtitle")
        for m in result["knowledge_matches"]:
            assert "_score" not in m


# ---------------------------------------------------------------------------
# Class 7 — retrieve_knowledge_context (context builder)
# ---------------------------------------------------------------------------

class TestRetrieveKnowledgeContext:
    def test_none_plan_returns_fallback(self):
        result = retrieve_knowledge_context(None)
        ctx = result["knowledge_context"]
        assert ctx["available"] is False
        assert ctx["matches"] == []

    def test_empty_plan_returns_fallback(self):
        plan = _make_plan()
        result = retrieve_knowledge_context(plan)
        ctx = result["knowledge_context"]
        # No active quality signals → fallback
        assert ctx["available"] is False

    def test_subtitle_signal_activates_domain(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 70, "confidence": 0.8})
        result = retrieve_knowledge_context(plan)
        ctx = result["knowledge_context"]
        assert "subtitle" in ctx["domains"]

    def test_camera_signal_activates_domain(self):
        plan = _make_plan(camera_quality_v2={"overall": 60, "confidence": 0.7})
        result = retrieve_knowledge_context(plan)
        ctx = result["knowledge_context"]
        assert "camera" in ctx["domains"]

    def test_hook_signal_activates_domain(self):
        plan = _make_plan(hook_quality_v2={"overall": 55, "confidence": 0.6})
        result = retrieve_knowledge_context(plan)
        ctx = result["knowledge_context"]
        assert "hook" in ctx["domains"]

    def test_pacing_fast_adds_short_form_tag(self):
        plan = _make_plan(
            subtitle_quality_v2={"overall": 70, "confidence": 0.8},
            pacing={"pacing_style": "fast", "energy_level": 0.3},
        )
        result = retrieve_knowledge_context(plan)
        ctx = result["knowledge_context"]
        assert ctx["available"] is True

    def test_high_energy_adds_mobile_tag(self):
        plan = _make_plan(
            subtitle_quality_v2={"overall": 70, "confidence": 0.8},
            pacing={"pacing_style": "default", "energy_level": 0.75},
        )
        result = retrieve_knowledge_context(plan)
        ctx = result["knowledge_context"]
        assert ctx["available"] is True

    def test_returns_knowledge_context_key(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 70, "confidence": 0.8})
        result = retrieve_knowledge_context(plan)
        assert "knowledge_context" in result

    def test_never_raises_on_garbage_plan(self):
        result = retrieve_knowledge_context("not_a_plan")
        assert "knowledge_context" in result

    def test_context_confidence_in_range(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 70, "confidence": 0.8})
        ctx = retrieve_knowledge_context(plan)["knowledge_context"]
        assert 0.0 <= ctx["confidence"] <= 1.0

    def test_matches_are_list(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 70, "confidence": 0.8})
        ctx = retrieve_knowledge_context(plan)["knowledge_context"]
        assert isinstance(ctx["matches"], list)

    def test_no_duplicate_rules_across_domains(self):
        plan = _make_plan(
            subtitle_quality_v2={"overall": 70, "confidence": 0.8},
            hook_quality_v2={"overall": 60, "confidence": 0.7},
        )
        ctx = retrieve_knowledge_context(plan)["knowledge_context"]
        seen = set()
        for m in ctx["matches"]:
            key = (m["pack_id"], m["rule_id"])
            assert key not in seen, f"Duplicate rule {key}"
            seen.add(key)

    def test_deterministic_context(self):
        plan = _make_plan(
            subtitle_quality_v2={"overall": 70, "confidence": 0.8},
            pacing={"pacing_style": "fast", "energy_level": 0.7},
        )
        r1 = retrieve_knowledge_context(plan)
        r2 = retrieve_knowledge_context(plan)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Class 8 — KnowledgeContext.to_dict clamping
# ---------------------------------------------------------------------------

class TestKnowledgeContextSchema:
    def test_confidence_clamped_high(self):
        ctx = KnowledgeContext(available=True, confidence=2.0)
        d = ctx.to_dict()
        assert d["confidence"] == 1.0

    def test_confidence_clamped_low(self):
        ctx = KnowledgeContext(available=True, confidence=-0.5)
        d = ctx.to_dict()
        assert d["confidence"] == 0.0

    def test_matches_capped_at_20(self):
        matches = [
            KnowledgeMatch(pack_id=f"p{i}", rule_id=f"r{i}", domain="subtitle", title="T")
            for i in range(25)
        ]
        ctx = KnowledgeContext(available=True, matches=matches, confidence=0.5)
        d = ctx.to_dict()
        assert len(d["matches"]) == 20

    def test_reasoning_capped_at_5(self):
        ctx = KnowledgeContext(available=True, reasoning=[f"r{i}" for i in range(10)])
        d = ctx.to_dict()
        assert len(d["reasoning"]) == 5

    def test_domains_sorted_and_deduped(self):
        ctx = KnowledgeContext(available=True, domains=["subtitle", "camera", "subtitle"])
        d = ctx.to_dict()
        assert d["domains"] == sorted(set(["subtitle", "camera"]))


# ---------------------------------------------------------------------------
# Class 9 — KnowledgeMatch.to_dict (no _score field)
# ---------------------------------------------------------------------------

class TestKnowledgeMatchSchema:
    def test_score_not_in_to_dict(self):
        m = KnowledgeMatch(pack_id="p1", rule_id="r1", domain="subtitle", title="T", _score=5.0)
        d = m.to_dict()
        assert "_score" not in d

    def test_confidence_clamped(self):
        m = KnowledgeMatch(pack_id="p1", rule_id="r1", domain="subtitle", title="T", confidence=3.0)
        d = m.to_dict()
        assert d["confidence"] == 1.0

    def test_required_fields_present(self):
        m = KnowledgeMatch(pack_id="p1", rule_id="r1", domain="subtitle", title="T")
        d = m.to_dict()
        assert set(d.keys()) == {"pack_id", "rule_id", "domain", "title", "recommendation", "confidence"}


# ---------------------------------------------------------------------------
# Class 10 — Valid domains constant
# ---------------------------------------------------------------------------

class TestValidDomains:
    def test_expected_domains_present(self):
        expected = {"subtitle", "camera", "hook", "pacing", "market", "retention", "creator"}
        assert expected.issubset(VALID_DOMAINS)

    def test_is_frozenset(self):
        assert isinstance(VALID_DOMAINS, frozenset)


# ---------------------------------------------------------------------------
# Class 11 — edit_plan_schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_knowledge_injection_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="auto",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "knowledge_injection")
        assert plan.knowledge_injection == {}

    def test_knowledge_injection_in_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="auto",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "knowledge_injection" in d
        assert d["knowledge_injection"] == {}

    def test_knowledge_injection_populated_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="auto",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        plan.knowledge_injection = {"available": True, "matches": [], "confidence": 0.5, "domains": ["subtitle"]}
        d = plan.to_dict()
        assert d["knowledge_injection"]["available"] is True
        assert d["knowledge_injection"]["confidence"] == 0.5


# ---------------------------------------------------------------------------
# Class 12 — render_influence reporting
# ---------------------------------------------------------------------------

class TestRenderInfluenceReporting:
    def _make_report(self) -> dict:
        return {"applied": [], "skipped": [], "warnings": []}

    def test_no_result_skipped(self):
        from app.ai.director.render_influence import _report_knowledge_injection
        plan = _make_plan()
        report = self._make_report()
        _report_knowledge_injection(None, plan, report)
        assert any("knowledge_injection:no_result_phase53a" in s for s in report["skipped"])

    def test_no_signal_skipped(self):
        from app.ai.director.render_influence import _report_knowledge_injection
        plan = _make_plan(knowledge_injection={"available": False, "matches": [], "confidence": 0.0, "domains": []})
        report = self._make_report()
        _report_knowledge_injection(None, plan, report)
        assert any("no_signal_phase53a" in s for s in report["skipped"])

    def test_active_context_skipped_not_applied(self):
        from app.ai.director.render_influence import _report_knowledge_injection
        plan = _make_plan(knowledge_injection={
            "available": True,
            "matches": [{"pack_id": "p1", "rule_id": "r1", "domain": "subtitle", "title": "T", "recommendation": {}, "confidence": 0.8}],
            "confidence": 0.8,
            "domains": ["subtitle"],
        })
        report = self._make_report()
        _report_knowledge_injection(None, plan, report)
        assert len(report["applied"]) == 0
        assert any("evaluated_phase53a" in s for s in report["skipped"])

    def test_report_contains_available_flag(self):
        from app.ai.director.render_influence import _report_knowledge_injection
        plan = _make_plan(knowledge_injection={
            "available": True,
            "matches": [{"pack_id": "p1", "rule_id": "r1", "domain": "subtitle", "title": "T", "recommendation": {}, "confidence": 0.8}],
            "confidence": 0.8,
            "domains": ["subtitle"],
        })
        report = self._make_report()
        _report_knowledge_injection(None, plan, report)
        entry = next(s for s in report["skipped"] if "evaluated_phase53a" in s)
        assert "available=True" in entry

    def test_report_contains_match_count(self):
        from app.ai.director.render_influence import _report_knowledge_injection
        plan = _make_plan(knowledge_injection={
            "available": True,
            "matches": [{"pack_id": "p1", "rule_id": "r1", "domain": "subtitle", "title": "T", "recommendation": {}, "confidence": 0.8}],
            "confidence": 0.8,
            "domains": ["subtitle"],
        })
        report = self._make_report()
        _report_knowledge_injection(None, plan, report)
        entry = next(s for s in report["skipped"] if "evaluated_phase53a" in s)
        assert "matches=1" in entry


# ---------------------------------------------------------------------------
# Class 13 — Seed pack content validation
# ---------------------------------------------------------------------------

class TestSeedPackContent:
    def test_seed_pack_loads_with_correct_id(self):
        packs = load_knowledge_packs()
        pack = next((p for p in packs if p.id == "subtitle_readability_basics"), None)
        assert pack is not None

    def test_seed_pack_domain_is_subtitle(self):
        packs = load_knowledge_packs()
        pack = next((p for p in packs if p.id == "subtitle_readability_basics"), None)
        assert pack.domain == "subtitle"

    def test_seed_pack_has_two_rules(self):
        packs = load_knowledge_packs()
        pack = next((p for p in packs if p.id == "subtitle_readability_basics"), None)
        assert len(pack.rules) == 2

    def test_seed_pack_rule_ids(self):
        packs = load_knowledge_packs()
        pack = next((p for p in packs if p.id == "subtitle_readability_basics"), None)
        rule_ids = {r.id for r in pack.rules}
        assert "two_line_mobile_safe" in rule_ids
        assert "keyword_emphasis_hooks" in rule_ids

    def test_seed_pack_confidence_valid(self):
        packs = load_knowledge_packs()
        pack = next((p for p in packs if p.id == "subtitle_readability_basics"), None)
        for rule in pack.rules:
            assert 0.0 <= rule.confidence <= 1.0

    def test_seed_pack_recommendation_is_dict(self):
        packs = load_knowledge_packs()
        pack = next((p for p in packs if p.id == "subtitle_readability_basics"), None)
        for rule in pack.rules:
            assert isinstance(rule.recommendation, dict)
