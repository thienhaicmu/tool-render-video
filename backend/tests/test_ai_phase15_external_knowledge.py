"""
test_ai_phase15_external_knowledge.py — Phase 15: External Knowledge Learning Foundation.

74 tests covering:
  - Knowledge schema (ExternalKnowledgeItem, KnowledgeSearchResult, VALID_SOURCE_TYPES)
  - Knowledge ingest (parse_knowledge_json, ingest_knowledge_file)
  - Knowledge store (add, count, keyword search, filter, vector fallback)
  - Knowledge retriever (never raises, structure, filters)
  - AIEditPlan external_knowledge field
  - AI Director integration (attach helpers, explainability)
  - No external dependencies
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.ai.knowledge.knowledge_schema import (
    ExternalKnowledgeItem,
    KnowledgeSearchResult,
    VALID_SOURCE_TYPES,
)
from app.ai.knowledge.knowledge_ingest import parse_knowledge_json, ingest_knowledge_file
from app.ai.knowledge.knowledge_store import LocalKnowledgeStore
from app.ai.knowledge.knowledge_retriever import retrieve_external_knowledge
from app.ai.director.edit_plan_schema import (
    AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan,
)
from app.ai.director.ai_director import (
    _attach_external_knowledge,
    _append_knowledge_explainability,
    _build_knowledge_summary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_item(
    id="k001",
    source_type="hook_pattern",
    text="Curiosity-led hooks perform well for podcast clips.",
    market="US",
    style="podcast_viral",
    confidence=0.8,
    tags=None,
) -> ExternalKnowledgeItem:
    return ExternalKnowledgeItem(
        id=id,
        source_type=source_type,
        text=text,
        market=market,
        style=style,
        confidence=confidence,
        tags=tags or ["hook", "curiosity"],
    )


def _make_plan() -> AIEditPlan:
    return AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )


def _make_store_with_items() -> LocalKnowledgeStore:
    store = LocalKnowledgeStore()
    store.add_item(_make_item("k001", "hook_pattern", "Curiosity hooks work well.", market="US", style="podcast_viral"))
    store.add_item(_make_item("k002", "pacing_pattern", "Fast pacing suits short clips.", market="US", style="high_energy_reaction"))
    store.add_item(_make_item("k003", "subtitle_pattern", "Bold text improves retention.", market=None, style=None))
    return store


# ---------------------------------------------------------------------------
# 1. Knowledge Schema
# ---------------------------------------------------------------------------

class TestKnowledgeSchema:
    def test_external_knowledge_item_required_fields(self):
        item = ExternalKnowledgeItem(id="x1", source_type="hook_pattern", text="test text")
        assert item.id == "x1"
        assert item.source_type == "hook_pattern"
        assert item.text == "test text"

    def test_external_knowledge_item_defaults(self):
        item = ExternalKnowledgeItem(id="x1", source_type="hook_pattern", text="t")
        assert item.market is None
        assert item.platform is None
        assert item.style is None
        assert item.topic is None
        assert item.tags == []
        assert item.confidence == 0.5
        assert item.metadata == {}

    def test_external_knowledge_item_optional_fields(self):
        item = ExternalKnowledgeItem(
            id="x2", source_type="trend_summary", text="t",
            market="US", platform="tiktok", style="podcast_viral",
            topic="hooks", tags=["a", "b"], confidence=0.9,
            metadata={"extra": 1},
        )
        assert item.market == "US"
        assert item.platform == "tiktok"
        assert item.style == "podcast_viral"
        assert item.topic == "hooks"
        assert item.tags == ["a", "b"]
        assert item.confidence == 0.9
        assert item.metadata == {"extra": 1}

    def test_knowledge_search_result_defaults(self):
        r = KnowledgeSearchResult(id="r1", score=0.75, text="some text")
        assert r.id == "r1"
        assert r.score == 0.75
        assert r.text == "some text"
        assert r.metadata == {}

    def test_knowledge_search_result_to_dict_has_required_keys(self):
        r = KnowledgeSearchResult(id="r1", score=0.75, text="text", metadata={"k": "v"})
        d = r.to_dict()
        assert "id" in d
        assert "score" in d
        assert "text" in d
        assert "metadata" in d

    def test_knowledge_search_result_to_dict_caps_text_at_500(self):
        long_text = "x" * 1000
        r = KnowledgeSearchResult(id="r1", score=0.5, text=long_text)
        d = r.to_dict()
        assert len(d["text"]) <= 500

    def test_valid_source_types_contains_required(self):
        required = {
            "manual_note", "trend_summary", "style_pattern",
            "hook_pattern", "subtitle_pattern", "pacing_pattern", "market_pattern",
        }
        assert required.issubset(VALID_SOURCE_TYPES)

    def test_valid_source_types_is_frozenset(self):
        assert isinstance(VALID_SOURCE_TYPES, frozenset)


# ---------------------------------------------------------------------------
# 2. Knowledge Ingest
# ---------------------------------------------------------------------------

class TestKnowledgeIngest:
    def test_parse_valid_json_returns_items(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "Hook text", "confidence": 0.8},
        ]}
        items = parse_knowledge_json(data)
        assert len(items) == 1
        assert items[0].id == "u1"

    def test_parse_returns_external_knowledge_item_instances(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "Hook text"},
        ]}
        items = parse_knowledge_json(data)
        assert isinstance(items[0], ExternalKnowledgeItem)

    def test_malformed_item_skipped_safely(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "Valid"},
            "not a dict",
            {"id": "u3", "source_type": "hook_pattern", "text": "Also valid"},
        ]}
        items = parse_knowledge_json(data)
        assert len(items) == 2

    def test_missing_id_skipped(self):
        data = {"items": [
            {"source_type": "hook_pattern", "text": "No id"},
        ]}
        items = parse_knowledge_json(data)
        assert items == []

    def test_missing_text_skipped(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern"},
        ]}
        items = parse_knowledge_json(data)
        assert items == []

    def test_invalid_source_type_skipped(self):
        data = {"items": [
            {"id": "u1", "source_type": "not_valid_type", "text": "Some text"},
        ]}
        items = parse_knowledge_json(data)
        assert items == []

    def test_empty_items_list_returns_empty(self):
        items = parse_knowledge_json({"items": []})
        assert items == []

    def test_non_dict_input_returns_empty(self):
        assert parse_knowledge_json(None) == []
        assert parse_knowledge_json("string") == []
        assert parse_knowledge_json([]) == []

    def test_confidence_clamped_to_valid_range(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "t", "confidence": 5.0},
            {"id": "u2", "source_type": "hook_pattern", "text": "t", "confidence": -1.0},
        ]}
        items = parse_knowledge_json(data)
        for item in items:
            assert 0.0 <= item.confidence <= 1.0

    def test_tags_normalized_to_list_of_strings(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "t", "tags": ["a", "b"]},
        ]}
        items = parse_knowledge_json(data)
        assert items[0].tags == ["a", "b"]

    def test_bad_tags_field_yields_empty_list(self):
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "t", "tags": "not-a-list"},
        ]}
        items = parse_knowledge_json(data)
        assert items[0].tags == []

    def test_all_optional_fields_parsed(self):
        data = {"items": [
            {
                "id": "u1", "source_type": "market_pattern", "text": "t",
                "market": "US", "platform": "tiktok", "style": "podcast_viral",
                "topic": "hooks", "tags": ["x"], "confidence": 0.7,
            },
        ]}
        items = parse_knowledge_json(data)
        assert items[0].market == "US"
        assert items[0].platform == "tiktok"
        assert items[0].style == "podcast_viral"
        assert items[0].topic == "hooks"

    def test_ingest_file_not_found_returns_warning(self):
        result = ingest_knowledge_file("/nonexistent/path/file.json")
        assert result["loaded"] == 0
        assert any("file_not_found" in w for w in result["warnings"])

    def test_ingest_file_valid_returns_loaded_count(self):
        data = {"items": [
            {"id": "k1", "source_type": "hook_pattern", "text": "text"},
        ]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            result = ingest_knowledge_file(tmp_path)
            assert result["loaded"] == 1
            assert len(result["items"]) == 1
            assert result["warnings"] == []
        finally:
            os.unlink(tmp_path)

    def test_ingest_file_includes_items_in_result(self):
        data = {"items": [
            {"id": "k1", "source_type": "hook_pattern", "text": "text"},
        ]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            result = ingest_knowledge_file(tmp_path)
            assert "items" in result
            assert isinstance(result["items"][0], ExternalKnowledgeItem)
        finally:
            os.unlink(tmp_path)

    def test_ingest_file_never_raises_on_corrupt_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("{not valid json{{")
            tmp_path = f.name
        try:
            result = ingest_knowledge_file(tmp_path)
            assert result["loaded"] == 0
            assert result["warnings"]
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 3. Knowledge Store
# ---------------------------------------------------------------------------

class TestKnowledgeStore:
    def test_empty_store_count_zero(self):
        store = LocalKnowledgeStore()
        assert store.count() == 0

    def test_add_item_returns_true(self):
        store = LocalKnowledgeStore()
        result = store.add_item(_make_item())
        assert result is True

    def test_count_increases_after_add(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1"))
        store.add_item(_make_item("k2"))
        assert store.count() == 2

    def test_add_items_returns_count(self):
        store = LocalKnowledgeStore()
        items = [_make_item(f"k{i}") for i in range(5)]
        count = store.add_items(items)
        assert count == 5

    def test_add_item_invalid_type_returns_false(self):
        store = LocalKnowledgeStore()
        assert store.add_item("not an item") is False
        assert store.add_item(None) is False
        assert store.count() == 0

    def test_search_empty_store_returns_empty(self):
        store = LocalKnowledgeStore()
        results = store.search("hook curiosity")
        assert results == []

    def test_search_returns_list_of_knowledge_search_results(self):
        store = _make_store_with_items()
        results = store.search("hook curiosity")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, KnowledgeSearchResult)

    def test_keyword_search_finds_matching_item(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", text="Curiosity-led hooks perform well for podcast"))
        store.add_item(_make_item("k2", text="Completely unrelated content about music"))
        results = store.search("curiosity hooks podcast")
        assert results, "Expected at least one result"
        assert results[0].id == "k1"

    def test_search_top_k_respected(self):
        store = _make_store_with_items()
        results = store.search("podcast hook", top_k=1)
        assert len(results) <= 1

    def test_search_returns_score_field(self):
        store = _make_store_with_items()
        results = store.search("hook pacing")
        for r in results:
            assert isinstance(r.score, float)

    def test_search_never_raises_on_garbage_query(self):
        store = _make_store_with_items()
        results = store.search("")
        assert isinstance(results, list)
        results = store.search("   ")
        assert isinstance(results, list)

    def test_filter_by_market_excludes_other_market(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", text="US content", market="US"))
        store.add_item(_make_item("k2", text="JP content", market="JP"))
        results = store.search("content", top_k=5, filters={"market": "US"})
        ids = {r.id for r in results}
        assert "k1" in ids
        assert "k2" not in ids

    def test_filter_allows_none_market_items(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", text="global content", market=None))
        store.add_item(_make_item("k2", text="US content", market="US"))
        results = store.search("content", top_k=5, filters={"market": "US"})
        ids = {r.id for r in results}
        # k1 has market=None → passes through filter
        assert "k1" in ids

    def test_search_result_metadata_contains_source_type(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", source_type="hook_pattern", text="hook text"))
        results = store.search("hook text")
        assert results
        assert results[0].metadata.get("source_type") == "hook_pattern"

    def test_search_result_metadata_contains_market_and_style(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", market="US", style="podcast_viral", text="hook"))
        results = store.search("hook")
        assert results
        assert results[0].metadata.get("market") == "US"
        assert results[0].metadata.get("style") == "podcast_viral"

    def test_add_items_empty_list_returns_zero(self):
        store = LocalKnowledgeStore()
        assert store.add_items([]) == 0

    def test_add_items_none_handled_safely(self):
        store = LocalKnowledgeStore()
        assert store.add_items(None) == 0


# ---------------------------------------------------------------------------
# 4. Knowledge Retriever
# ---------------------------------------------------------------------------

class TestKnowledgeRetriever:
    def test_never_raises_on_none_args(self):
        result = retrieve_external_knowledge(None)
        assert isinstance(result, dict)

    def test_never_raises_on_empty_context(self):
        result = retrieve_external_knowledge("query", context={})
        assert isinstance(result, dict)

    def test_returns_available_false_without_store(self):
        result = retrieve_external_knowledge("query", context={})
        assert result["available"] is False

    def test_returns_required_keys(self):
        result = retrieve_external_knowledge("query")
        assert "available" in result
        assert "results" in result
        assert "warnings" in result

    def test_returns_available_true_with_populated_store(self):
        store = _make_store_with_items()
        result = retrieve_external_knowledge(
            "hook curiosity",
            context={"knowledge_store": store},
        )
        assert result["available"] is True

    def test_results_is_list(self):
        store = _make_store_with_items()
        result = retrieve_external_knowledge(
            "hook curiosity",
            context={"knowledge_store": store},
        )
        assert isinstance(result["results"], list)

    def test_results_capped_at_top_k(self):
        store = _make_store_with_items()
        result = retrieve_external_knowledge(
            "hook pacing",
            context={"knowledge_store": store},
            top_k=1,
        )
        assert len(result["results"]) <= 1

    def test_empty_store_returns_available_false(self):
        store = LocalKnowledgeStore()
        result = retrieve_external_knowledge(
            "query",
            context={"knowledge_store": store},
        )
        assert result["available"] is False

    def test_market_filter_passed_through(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", text="US hooks", market="US"))
        store.add_item(_make_item("k2", text="JP hooks", market="JP"))
        result = retrieve_external_knowledge(
            "hooks",
            context={"knowledge_store": store, "market": "US"},
        )
        ids = {r.get("id") for r in result.get("results", [])}
        assert "k1" in ids
        assert "k2" not in ids

    def test_warnings_is_list(self):
        result = retrieve_external_knowledge("query")
        assert isinstance(result["warnings"], list)


# ---------------------------------------------------------------------------
# 5. AIEditPlan external_knowledge field
# ---------------------------------------------------------------------------

class TestEditPlanExternalKnowledge:
    def test_ai_edit_plan_has_external_knowledge_field(self):
        plan = _make_plan()
        assert hasattr(plan, "external_knowledge")

    def test_external_knowledge_defaults_to_empty_dict(self):
        plan = _make_plan()
        assert plan.external_knowledge == {}

    def test_ai_edit_plan_to_dict_includes_external_knowledge(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "external_knowledge" in d

    def test_external_knowledge_value_propagated_to_dict(self):
        plan = _make_plan()
        plan.external_knowledge = {"available": True, "matched_items": 2}
        d = plan.to_dict()
        assert d["external_knowledge"]["available"] is True


# ---------------------------------------------------------------------------
# 6. AI Director Integration
# ---------------------------------------------------------------------------

class TestAIDirectorKnowledgeIntegration:
    def test_attach_sets_external_knowledge_dict(self):
        plan = _make_plan()
        store = _make_store_with_items()
        _attach_external_knowledge(plan, [], {}, {"knowledge_store": store}, "viral_tiktok", "job1")
        assert isinstance(plan.external_knowledge, dict)

    def test_attach_available_false_when_no_store(self):
        plan = _make_plan()
        _attach_external_knowledge(plan, [], {}, {}, "viral_tiktok", "job1")
        assert plan.external_knowledge.get("available") is False

    def test_attach_never_raises_on_empty_chunks(self):
        plan = _make_plan()
        store = _make_store_with_items()
        _attach_external_knowledge(plan, [], {}, {"knowledge_store": store}, "viral_tiktok", "job1")
        assert isinstance(plan.external_knowledge, dict)

    def test_attach_never_raises_on_none_context_value(self):
        plan = _make_plan()
        _attach_external_knowledge(plan, [], {}, {}, "viral_tiktok", "job1")
        assert isinstance(plan.external_knowledge, dict)

    def test_attach_available_true_with_populated_store(self):
        plan = _make_plan()
        store = _make_store_with_items()
        _attach_external_knowledge(
            plan,
            [{"text": "hook curiosity"}],
            {},
            {"knowledge_store": store},
            "viral_tiktok",
            "job1",
        )
        assert plan.external_knowledge.get("available") is True

    def test_attach_external_knowledge_includes_top_matches(self):
        plan = _make_plan()
        store = _make_store_with_items()
        _attach_external_knowledge(
            plan,
            [{"text": "hook curiosity"}],
            {},
            {"knowledge_store": store},
            "viral_tiktok",
            "job1",
        )
        if plan.external_knowledge.get("available"):
            assert "top_matches" in plan.external_knowledge
            assert isinstance(plan.external_knowledge["top_matches"], list)

    def test_attach_top_matches_capped_at_5(self):
        store = LocalKnowledgeStore()
        for i in range(10):
            store.add_item(_make_item(f"k{i}", text=f"hook item {i}"))
        plan = _make_plan()
        _attach_external_knowledge(plan, [{"text": "hook"}], {}, {"knowledge_store": store}, "viral_tiktok", "job1")
        if plan.external_knowledge.get("available"):
            assert len(plan.external_knowledge.get("top_matches", [])) <= 5

    def test_build_knowledge_summary_available_false(self):
        result = {"available": False, "warnings": ["no_knowledge_store"]}
        summary = _build_knowledge_summary(result)
        assert summary["available"] is False
        assert summary["warnings"] == ["no_knowledge_store"]

    def test_build_knowledge_summary_available_true(self):
        result = {
            "available": True,
            "results": [
                {
                    "id": "k1", "score": 0.8, "text": "hook text",
                    "metadata": {"source_type": "hook_pattern", "market": "US", "style": "podcast_viral"},
                }
            ],
        }
        summary = _build_knowledge_summary(result)
        assert summary["available"] is True
        assert summary["matched_items"] == 1
        assert len(summary["top_matches"]) == 1
        assert summary["top_matches"][0]["source_type"] == "hook_pattern"
        assert summary["top_matches"][0]["market"] == "US"

    def test_build_knowledge_summary_text_capped_at_300(self):
        result = {
            "available": True,
            "results": [
                {
                    "id": "k1", "score": 0.5, "text": "x" * 1000,
                    "metadata": {"source_type": "trend_summary"},
                }
            ],
        }
        summary = _build_knowledge_summary(result)
        assert len(summary["top_matches"][0]["text"]) <= 300

    def test_explainability_append_never_raises_no_explainability(self):
        plan = _make_plan()
        result = {"available": True, "results": []}
        _append_knowledge_explainability(plan, result)   # no explainability dict

    def test_explainability_line_added_when_results_exist(self):
        plan = _make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        result = {
            "available": True,
            "results": [
                {
                    "id": "k1", "score": 0.8, "text": "hook",
                    "metadata": {"source_type": "hook_pattern"},
                }
            ],
        }
        _append_knowledge_explainability(plan, result)
        lines = plan.explainability["summary"]["summary_lines"]
        assert any("External curated knowledge" in l for l in lines)

    def test_hook_pattern_adds_market_line(self):
        plan = _make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        result = {
            "available": True,
            "results": [
                {
                    "id": "k1", "score": 0.8, "text": "hook",
                    "metadata": {"source_type": "hook_pattern"},
                }
            ],
        }
        _append_knowledge_explainability(plan, result)
        lines = plan.explainability["summary"]["summary_lines"]
        assert any("hook guidance" in l for l in lines)

    def test_no_duplicate_explainability_lines(self):
        plan = _make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        result = {
            "available": True,
            "results": [
                {
                    "id": "k1", "score": 0.8, "text": "hook",
                    "metadata": {"source_type": "hook_pattern"},
                }
            ],
        }
        _append_knowledge_explainability(plan, result)
        _append_knowledge_explainability(plan, result)
        lines = plan.explainability["summary"]["summary_lines"]
        knowledge_lines = [l for l in lines if "External curated knowledge" in l]
        assert len(knowledge_lines) == 1

    def test_attach_never_raises_on_garbage_store(self):
        plan = _make_plan()
        _attach_external_knowledge(plan, [], {}, {"knowledge_store": "not a store"}, "viral_tiktok", "job1")
        assert isinstance(plan.external_knowledge, dict)

    def test_style_hint_extracted_from_creator_style(self):
        plan = _make_plan()
        plan.creator_style = {"dominant_style": "podcast_viral", "available": True}
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", style="podcast_viral", text="podcast hook tips"))
        _attach_external_knowledge(
            plan, [], {}, {"knowledge_store": store}, "viral_tiktok", "job1"
        )
        # Should not raise regardless of match result
        assert isinstance(plan.external_knowledge, dict)


# ---------------------------------------------------------------------------
# 7. No External Dependencies
# ---------------------------------------------------------------------------

class TestNoExternalDependencies:
    def test_no_api_key_required(self):
        import os
        # Remove any API keys to verify no call needed
        env_backup = os.environ.copy()
        for key in list(os.environ.keys()):
            if "API_KEY" in key or "OPENAI" in key or "ANTHROPIC" in key:
                os.environ.pop(key, None)
        try:
            store = _make_store_with_items()
            result = retrieve_external_knowledge("hook curiosity", context={"knowledge_store": store})
            assert isinstance(result, dict)
        finally:
            os.environ.update(env_backup)

    def test_no_gpu_required(self):
        store = LocalKnowledgeStore()
        store.add_item(_make_item())
        results = store.search("hook curiosity")
        assert isinstance(results, list)

    def test_no_internet_required(self):
        # All operations should work without any network call
        data = {"items": [
            {"id": "u1", "source_type": "hook_pattern", "text": "Test"},
        ]}
        items = parse_knowledge_json(data)
        store = LocalKnowledgeStore()
        store.add_items(items)
        result = retrieve_external_knowledge("hook", context={"knowledge_store": store})
        assert isinstance(result, dict)

    def test_no_real_rendering_required(self):
        plan = _make_plan()
        _attach_external_knowledge(plan, [], {}, {}, "viral_tiktok", "job1")
        assert isinstance(plan.external_knowledge, dict)

    def test_knowledge_modules_import_safely(self):
        import importlib
        for mod in [
            "app.ai.knowledge.knowledge_schema",
            "app.ai.knowledge.knowledge_ingest",
            "app.ai.knowledge.knowledge_store",
            "app.ai.knowledge.knowledge_retriever",
        ]:
            importlib.import_module(mod)  # must not raise

    def test_store_works_without_sentence_transformers(self):
        # Even if sentence-transformers is unavailable, keyword search must work
        store = LocalKnowledgeStore()
        store.add_item(_make_item("k1", text="curiosity hooks podcast viral"))
        results = store.search("curiosity hooks")
        assert isinstance(results, list)

    def test_no_copyrighted_creator_names_in_schema(self):
        import inspect
        import app.ai.knowledge.knowledge_schema as mod
        src = inspect.getsource(mod)
        banned = ["MrBeast", "PewDiePie", "Logan Paul", "Jake Paul"]
        for name in banned:
            assert name not in src, f"Copyrighted name {name!r} found in knowledge_schema"

    def test_retriever_never_raises_on_exception_in_store(self):
        class BrokenStore:
            def count(self):
                raise RuntimeError("broken")
            def search(self, *a, **k):
                raise RuntimeError("broken")

        result = retrieve_external_knowledge("query", context={"knowledge_store": BrokenStore()})
        assert isinstance(result, dict)
        assert result["available"] is False
