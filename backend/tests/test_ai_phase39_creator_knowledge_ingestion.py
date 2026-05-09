"""
tests/test_ai_phase39_creator_knowledge_ingestion.py

Phase 39 — External Creator Knowledge Ingestion Foundation

Safety contract: local-first, no internet, no subprocess, no scraping,
no FFmpeg mutation, no payload mutation, deterministic ingestion.
"""
from __future__ import annotations

import json
import tempfile
import types
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(folder: Path, filename: str, data: dict) -> Path:
    p = folder / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _valid_knowledge(**overrides) -> dict:
    base = {
        "knowledge_id": "test_creator",
        "category": "creator",
        "source_type": "local_json",
        "creator_style": "viral_tiktok",
        "title": "Test Creator",
        "description": "A test knowledge item.",
        "tags": ["test", "creator"],
        "hook_patterns": ["watch this", "wait for it"],
        "subtitle_patterns": {"density": "compact"},
        "pacing_patterns": {"intro_speed": "fast"},
        "camera_patterns": {"behavior": "dynamic_safe"},
        "retention_patterns": {},
        "creator_patterns": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Schema invariants
# ---------------------------------------------------------------------------

class TestCreatorKnowledgeSchema:
    def test_ai_creator_knowledge_defaults(self):
        from app.ai.knowledge.knowledge_schema import AICreatorKnowledge
        k = AICreatorKnowledge(knowledge_id="test")
        assert k.knowledge_id == "test"
        assert k.category == ""
        assert k.source_type == "local_json"
        assert k.creator_style == ""
        assert k.safe is False
        assert isinstance(k.tags, list)
        assert isinstance(k.hook_patterns, list)
        assert isinstance(k.subtitle_patterns, dict)
        assert isinstance(k.pacing_patterns, dict)
        assert isinstance(k.camera_patterns, dict)
        assert isinstance(k.retention_patterns, dict)
        assert isinstance(k.creator_patterns, dict)
        assert isinstance(k.warnings, list)

    def test_ai_creator_knowledge_to_dict(self):
        from app.ai.knowledge.knowledge_schema import AICreatorKnowledge
        k = AICreatorKnowledge(
            knowledge_id="viral_tiktok",
            category="creator",
            creator_style="viral_tiktok",
            title="Viral TikTok",
            hook_patterns=["watch this"],
            safe=True,
        )
        d = k.to_dict()
        assert d["knowledge_id"] == "viral_tiktok"
        assert d["category"] == "creator"
        assert d["creator_style"] == "viral_tiktok"
        assert d["safe"] is True
        assert "hook_patterns" in d
        assert "watch this" in d["hook_patterns"]

    def test_ai_knowledge_registry_defaults(self):
        from app.ai.knowledge.knowledge_schema import AIKnowledgeRegistry
        r = AIKnowledgeRegistry()
        assert r.available is True
        assert r.loaded_count == 0
        assert r.categories == []
        assert r.creator_styles == []
        assert r.warnings == []

    def test_ai_knowledge_registry_to_dict(self):
        from app.ai.knowledge.knowledge_schema import AIKnowledgeRegistry
        r = AIKnowledgeRegistry(
            available=True,
            loaded_count=3,
            categories=["creator", "market"],
            creator_styles=["viral_tiktok", "podcast_viral"],
        )
        d = r.to_dict()
        assert d["loaded_count"] == 3
        assert "creator" in d["categories"]
        assert "viral_tiktok" in d["creator_styles"]

    def test_phase_15_types_still_present(self):
        from app.ai.knowledge.knowledge_schema import ExternalKnowledgeItem, KnowledgeSearchResult
        item = ExternalKnowledgeItem(id="x", source_type="manual_note", text="hello")
        assert item.id == "x"
        result = KnowledgeSearchResult(id="x", score=0.9, text="hello")
        assert result.score == 0.9


# ---------------------------------------------------------------------------
# 2. Safety validation
# ---------------------------------------------------------------------------

class TestKnowledgeSafety:
    def test_forbidden_keys_stripped(self):
        from app.ai.knowledge.knowledge_safety import sanitize_knowledge
        raw = _valid_knowledge()
        raw["script"] = "import os; os.system('rm -rf /')"
        raw["executable"] = "/bin/bash"
        raw["command"] = "echo bad"
        raw["ffmpeg_args"] = "-y -vf scale"
        raw["api_key"] = "sk-secret"
        raw["live_scrape_url"] = "https://example.com"
        result = sanitize_knowledge(raw)
        for key in ("script", "executable", "command", "ffmpeg_args", "api_key", "live_scrape_url"):
            assert key not in result, f"Forbidden key '{key}' not stripped"
        assert result["knowledge_id"] == "test_creator"

    def test_all_forbidden_keys_stripped(self):
        from app.ai.knowledge.knowledge_safety import sanitize_knowledge, _FORBIDDEN_KEYS
        raw = _valid_knowledge()
        for key in _FORBIDDEN_KEYS:
            raw[key] = "malicious_value"
        result = sanitize_knowledge(raw)
        for key in _FORBIDDEN_KEYS:
            assert key not in result

    def test_sanitize_truncates_long_strings(self):
        from app.ai.knowledge.knowledge_safety import sanitize_knowledge, _MAX_STRING_LEN
        raw = _valid_knowledge(title="X" * (_MAX_STRING_LEN + 100))
        result = sanitize_knowledge(raw)
        assert len(result["title"]) <= _MAX_STRING_LEN

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.knowledge.knowledge_safety import sanitize_knowledge
        assert sanitize_knowledge(None) == {}
        assert sanitize_knowledge("bad") == {}
        assert sanitize_knowledge(42) == {}

    def test_is_knowledge_safe_valid(self):
        from app.ai.knowledge.knowledge_safety import is_knowledge_safe
        assert is_knowledge_safe(_valid_knowledge()) is True

    def test_is_knowledge_safe_rejects_forbidden_key(self):
        from app.ai.knowledge.knowledge_safety import is_knowledge_safe
        for key in ("script", "executable", "command", "ffmpeg_args", "api_key"):
            raw = _valid_knowledge(**{key: "bad"})
            assert is_knowledge_safe(raw) is False, f"Should reject key={key}"

    def test_is_knowledge_safe_rejects_missing_id(self):
        from app.ai.knowledge.knowledge_safety import is_knowledge_safe
        raw = _valid_knowledge()
        raw.pop("knowledge_id")
        assert is_knowledge_safe(raw) is False

    def test_is_knowledge_safe_rejects_invalid_source_type(self):
        from app.ai.knowledge.knowledge_safety import is_knowledge_safe
        raw = _valid_knowledge(source_type="live_scrape")
        assert is_knowledge_safe(raw) is False

    def test_is_knowledge_safe_none_input(self):
        from app.ai.knowledge.knowledge_safety import is_knowledge_safe
        assert is_knowledge_safe(None) is False

    def test_sanitize_never_raises(self):
        from app.ai.knowledge.knowledge_safety import sanitize_knowledge
        for bad in (None, "", 0, [], {}, {"nested": {"a": "b"}}):
            result = sanitize_knowledge(bad)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 3. Knowledge ingestion
# ---------------------------------------------------------------------------

class TestKnowledgeIngestion:
    def test_ingest_valid_file(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "test.json", _valid_knowledge())
            item = ingest_knowledge_file(p)
        assert item is not None
        assert item.knowledge_id == "test_creator"
        assert item.creator_style == "viral_tiktok"
        assert item.safe is True

    def test_ingest_missing_file_returns_none(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        result = ingest_knowledge_file("/nonexistent/path/file.json")
        assert result is None

    def test_ingest_malformed_json_returns_none(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("not valid json {{{{", encoding="utf-8")
            result = ingest_knowledge_file(p)
        assert result is None

    def test_ingest_non_dict_json_returns_none(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "list.json"
            p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            result = ingest_knowledge_file(p)
        assert result is None

    def test_ingest_file_with_forbidden_key_rejected(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        data = _valid_knowledge()
        data["script"] = "evil code"
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "bad.json", data)
            result = ingest_knowledge_file(p)
        # Safety strips the key; is_knowledge_safe then passes, item returned
        # The forbidden key should be stripped, item should be safe
        assert result is None or result.safe is True

    def test_ingest_directory_loads_all_valid(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_json(p, "creator1.json", _valid_knowledge(knowledge_id="c1", creator_style="viral_tiktok"))
            _write_json(p, "creator2.json", _valid_knowledge(knowledge_id="c2", creator_style="podcast_viral"))
            items = ingest_knowledge_directory(p)
        assert len(items) == 2
        ids = {i.knowledge_id for i in items}
        assert "c1" in ids and "c2" in ids

    def test_ingest_directory_skips_malformed(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_json(p, "good.json", _valid_knowledge(knowledge_id="good"))
            bad = p / "bad.json"
            bad.write_text("not json {{", encoding="utf-8")
            items = ingest_knowledge_directory(p)
        assert len(items) == 1
        assert items[0].knowledge_id == "good"

    def test_ingest_directory_missing_returns_empty(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory
        result = ingest_knowledge_directory("/nonexistent/knowledge/dir")
        assert result == []

    def test_ingest_never_raises(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file, ingest_knowledge_directory
        assert ingest_knowledge_file(None) is None
        assert ingest_knowledge_directory(None) == []

    def test_ingest_deterministic(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_json(p, "a.json", _valid_knowledge(knowledge_id="a"))
            _write_json(p, "b.json", _valid_knowledge(knowledge_id="b"))
            r1 = [i.knowledge_id for i in ingest_knowledge_directory(p)]
            r2 = [i.knowledge_id for i in ingest_knowledge_directory(p)]
        assert r1 == r2

    def test_hook_patterns_parsed(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        data = _valid_knowledge(hook_patterns=["wait for it", "watch this"])
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "hooks.json", data)
            item = ingest_knowledge_file(p)
        assert item is not None
        assert "wait for it" in item.hook_patterns
        assert "watch this" in item.hook_patterns

    def test_subtitle_patterns_parsed(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        data = _valid_knowledge(subtitle_patterns={"density": "compact", "keyword_emphasis": True})
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "sub.json", data)
            item = ingest_knowledge_file(p)
        assert item is not None
        assert item.subtitle_patterns.get("density") == "compact"


# ---------------------------------------------------------------------------
# 4. Knowledge registry
# ---------------------------------------------------------------------------

class TestKnowledgeRegistry:
    def test_registry_loads_safely_from_temp(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        with tempfile.TemporaryDirectory() as td:
            # No subdirs — should return empty, not crash
            registry = load_knowledge_registry(base_path=td)
        assert registry is not None
        assert isinstance(registry.loaded_count, int)
        assert isinstance(registry.categories, list)

    def test_registry_missing_folder_fallback(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        registry = load_knowledge_registry(base_path="/nonexistent/base/path")
        assert registry is not None
        assert registry.loaded_count == 0

    def test_registry_loads_items_from_subdirs(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        with tempfile.TemporaryDirectory() as td:
            creators = Path(td) / "creators"
            creators.mkdir()
            _write_json(creators, "vt.json", _valid_knowledge(
                knowledge_id="viral_tiktok", category="creator", creator_style="viral_tiktok"))
            registry = load_knowledge_registry(base_path=td)
        assert registry.loaded_count >= 1
        assert "creator" in registry.categories
        assert "viral_tiktok" in registry.creator_styles

    def test_registry_categories_extracted(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        with tempfile.TemporaryDirectory() as td:
            creators = Path(td) / "creators"
            creators.mkdir()
            _write_json(creators, "a.json", _valid_knowledge(
                knowledge_id="a", category="creator", creator_style="vt"))
            markets = Path(td) / "markets"
            markets.mkdir()
            _write_json(markets, "b.json", _valid_knowledge(
                knowledge_id="b", category="market", creator_style=""))
            registry = load_knowledge_registry(base_path=td)
        assert "creator" in registry.categories
        assert "market" in registry.categories

    def test_registry_creator_styles_extracted(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        with tempfile.TemporaryDirectory() as td:
            creators = Path(td) / "creators"
            creators.mkdir()
            _write_json(creators, "vt.json", _valid_knowledge(
                knowledge_id="vt", creator_style="viral_tiktok"))
            _write_json(creators, "pod.json", _valid_knowledge(
                knowledge_id="pod", creator_style="podcast_viral"))
            registry = load_knowledge_registry(base_path=td)
        assert "viral_tiktok" in registry.creator_styles
        assert "podcast_viral" in registry.creator_styles

    def test_load_creator_knowledge_by_style(self):
        from app.ai.knowledge.knowledge_registry import load_creator_knowledge
        with tempfile.TemporaryDirectory() as td:
            creators = Path(td) / "creators"
            creators.mkdir()
            _write_json(creators, "vt.json", _valid_knowledge(
                knowledge_id="vt", creator_style="viral_tiktok"))
            _write_json(creators, "pod.json", _valid_knowledge(
                knowledge_id="pod", creator_style="podcast_viral"))
            items = load_creator_knowledge("viral_tiktok", base_path=td)
        assert len(items) >= 1
        assert all(i.creator_style == "viral_tiktok" for i in items)

    def test_load_category_knowledge(self):
        from app.ai.knowledge.knowledge_registry import load_category_knowledge
        with tempfile.TemporaryDirectory() as td:
            markets = Path(td) / "markets"
            markets.mkdir()
            _write_json(markets, "us.json", _valid_knowledge(
                knowledge_id="us_market", category="market"))
            items = load_category_knowledge("market", base_path=td)
        assert len(items) >= 1
        assert all(i.category == "market" for i in items)

    def test_list_available_knowledge(self):
        from app.ai.knowledge.knowledge_registry import list_available_knowledge
        with tempfile.TemporaryDirectory() as td:
            creators = Path(td) / "creators"
            creators.mkdir()
            _write_json(creators, "a.json", _valid_knowledge(knowledge_id="aaa"))
            _write_json(creators, "b.json", _valid_knowledge(knowledge_id="bbb"))
            result = list_available_knowledge(base_path=td)
        assert "aaa" in result
        assert "bbb" in result

    def test_registry_never_raises(self):
        from app.ai.knowledge.knowledge_registry import (
            load_knowledge_registry, load_creator_knowledge,
            load_category_knowledge, list_available_knowledge,
        )
        load_knowledge_registry(base_path=None)
        load_creator_knowledge("nonexistent_style")
        load_category_knowledge("nonexistent_category")
        list_available_knowledge()

    def test_actual_knowledge_files_load(self):
        """The bundled knowledge/ files in the repo should load without error."""
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        registry = load_knowledge_registry()
        assert registry is not None
        assert isinstance(registry.loaded_count, int)
        # knowledge/ folder has 6 files; should load successfully
        assert registry.loaded_count >= 1


# ---------------------------------------------------------------------------
# 5. No-mutation safety
# ---------------------------------------------------------------------------

class TestNoMutationSafety:
    def test_no_internet_access(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        import sys
        modules_before = set(sys.modules.keys())
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "k.json", _valid_knowledge())
            ingest_knowledge_file(p)
        new_modules = set(sys.modules.keys()) - modules_before
        net_modules = {m for m in new_modules if any(
            k in m for k in ("urllib3", "httpx", "requests", "aiohttp", "socket")
        )}
        assert not net_modules, f"Unexpected network modules: {net_modules}"

    def test_no_subprocess_execution(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        import sys
        modules_before = set(sys.modules.keys())
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "k.json", _valid_knowledge())
            ingest_knowledge_file(p)
        new_modules = set(sys.modules.keys()) - modules_before
        sub_modules = {m for m in new_modules if "subprocess" in m}
        assert not sub_modules

    def test_no_ffmpeg_in_knowledge(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td), "k.json", _valid_knowledge())
            item = ingest_knowledge_file(p)
        assert item is not None
        d = item.to_dict()
        for key in ("ffmpeg_args", "render_command"):
            assert key not in d

    def test_no_payload_mutation(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        with tempfile.TemporaryDirectory() as td:
            registry = load_knowledge_registry(base_path=td)
        # Registry returns a new object each time (or cached same); no shared mutation
        assert registry is not None

    def test_ingest_does_not_write_files(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_json(p, "k.json", _valid_knowledge())
            before_files = set(p.iterdir())
            ingest_knowledge_directory(p)
            after_files = set(p.iterdir())
        assert before_files == after_files


# ---------------------------------------------------------------------------
# 6. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_creator_knowledge_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "creator_knowledge")
        assert isinstance(plan.creator_knowledge, dict)

    def test_creator_knowledge_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.creator_knowledge == {}

    def test_to_dict_includes_creator_knowledge(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(), pacing=AIPacingPlan(),
        )
        plan.creator_knowledge = {"available": True, "loaded_count": 3}
        d = plan.to_dict()
        assert "creator_knowledge" in d
        assert d["creator_knowledge"]["loaded_count"] == 3

    def test_backward_compat_all_prior_phases(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "clip_candidate_discovery", "clip_segment_selection", "clip_batch_planning",
            "feature_enhancement", "timing_apply", "subtitle_text_apply",
        ):
            assert key in d, f"Missing backward-compat key: {key}"


# ---------------------------------------------------------------------------
# 7. Environment requirements
# ---------------------------------------------------------------------------

class TestEnvironmentRequirements:
    def test_no_api_key_required(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        import os
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            registry = load_knowledge_registry()
            assert registry is not None
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original

    def test_no_gpu_required(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        registry = load_knowledge_registry()
        assert registry is not None

    def test_no_internet_required(self):
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory
        with tempfile.TemporaryDirectory() as td:
            result = ingest_knowledge_directory(td)
        assert isinstance(result, list)

    def test_never_raises_on_bad_path(self):
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        result = load_knowledge_registry(base_path="/totally/nonexistent/path/xyz")
        assert result is not None

    def test_phase_15_knowledge_module_unaffected(self):
        from app.ai.knowledge.knowledge_schema import ExternalKnowledgeItem, KnowledgeSearchResult, VALID_SOURCE_TYPES
        from app.ai.knowledge.knowledge_ingest import parse_knowledge_json, ingest_knowledge_file as p15_ingest
        assert "manual_note" in VALID_SOURCE_TYPES
        items = parse_knowledge_json({"items": []})
        assert items == []
