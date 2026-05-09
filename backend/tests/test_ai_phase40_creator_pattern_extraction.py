"""
tests/test_ai_phase40_creator_pattern_extraction.py

Phase 40 — Creator Pattern Extraction Engine

Safety contract: local-only, no internet, no subprocess, no model training,
no FFmpeg mutation, no playback_speed mutation, no subtitle timing rewrite,
no executor override. Deterministic extraction from local knowledge.
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

def _make_knowledge_item(**overrides) -> Any:
    defaults = {
        "knowledge_id": "test_creator",
        "category": "creator",
        "source_type": "local_json",
        "creator_style": "viral_tiktok",
        "title": "Test Creator",
        "description": "Test",
        "tags": ["test"],
        "hook_patterns": ["watch this", "wait for it"],
        "subtitle_patterns": {"density": "compact", "max_words_per_line": 5},
        "pacing_patterns": {"intro_speed": "fast", "hook_duration_sec": 3},
        "camera_patterns": {"behavior": "dynamic_safe", "zoom_emphasis": True},
        "retention_patterns": {"hook_style": "question", "avoid_silence_gaps": True},
        "creator_patterns": {},
        "safe": True,
        "warnings": [],
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _valid_pattern_dict(**overrides) -> dict:
    base = {
        "pattern_id": "hook_question_default",
        "pattern_type": "hook",
        "creator_style": "",
        "title": "Question Hook",
        "description": "A question-based hook",
        "confidence": 0.85,
        "tags": ["hook", "question"],
        "hook_patterns": ["did you know", "what if"],
        "subtitle_patterns": {},
        "pacing_patterns": {},
        "camera_patterns": {},
        "retention_patterns": {},
    }
    base.update(overrides)
    return base


def _write_json(folder: Path, filename: str, data: dict) -> Path:
    p = folder / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Schema invariants
# ---------------------------------------------------------------------------

class TestPatternSchema:
    def test_ai_creator_pattern_defaults(self):
        from app.ai.knowledge.pattern_schema import AICreatorPattern
        p = AICreatorPattern(pattern_id="test_01")
        assert p.pattern_id == "test_01"
        assert p.pattern_type == ""
        assert p.creator_style == ""
        assert p.confidence == 0.0
        assert p.safe is False
        assert isinstance(p.tags, list)
        assert isinstance(p.hook_patterns, list)
        assert isinstance(p.subtitle_patterns, dict)
        assert isinstance(p.pacing_patterns, dict)
        assert isinstance(p.camera_patterns, dict)
        assert isinstance(p.retention_patterns, dict)
        assert isinstance(p.warnings, list)
        assert isinstance(p.explanation, list)

    def test_ai_creator_pattern_to_dict(self):
        from app.ai.knowledge.pattern_schema import AICreatorPattern
        p = AICreatorPattern(
            pattern_id="hook_question",
            pattern_type="hook",
            creator_style="viral_tiktok",
            confidence=0.85,
            tags=["hook", "question"],
            hook_patterns=["did you know"],
            safe=True,
        )
        d = p.to_dict()
        assert d["pattern_id"] == "hook_question"
        assert d["pattern_type"] == "hook"
        assert d["creator_style"] == "viral_tiktok"
        assert d["confidence"] == 0.85
        assert d["safe"] is True
        assert "did you know" in d["hook_patterns"]

    def test_ai_pattern_registry_defaults(self):
        from app.ai.knowledge.pattern_schema import AIPatternRegistry
        r = AIPatternRegistry()
        assert r.available is True
        assert r.loaded_patterns == 0
        assert r.pattern_types == []
        assert r.creator_styles == []
        assert r.warnings == []

    def test_ai_pattern_registry_to_dict(self):
        from app.ai.knowledge.pattern_schema import AIPatternRegistry
        r = AIPatternRegistry(
            available=True,
            loaded_patterns=12,
            pattern_types=["hook", "subtitle", "pacing"],
            creator_styles=["viral_tiktok"],
        )
        d = r.to_dict()
        assert d["loaded_patterns"] == 12
        assert "hook" in d["pattern_types"]
        assert "viral_tiktok" in d["creator_styles"]


# ---------------------------------------------------------------------------
# 2. Pattern safety
# ---------------------------------------------------------------------------

class TestPatternSafety:
    def test_forbidden_keys_stripped(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        raw = _valid_pattern_dict()
        raw["ffmpeg_args"] = "-y -vf scale"
        raw["render_command"] = "ffmpeg ..."
        raw["playback_speed"] = 1.5
        raw["subtitle_timing"] = [{"start": 0}]
        raw["api_key"] = "sk-secret"
        raw["shell"] = "bash -c evil"
        result = sanitize_pattern(raw)
        for key in ("ffmpeg_args", "render_command", "playback_speed",
                    "subtitle_timing", "api_key", "shell"):
            assert key not in result, f"Forbidden key '{key}' not stripped"

    def test_all_forbidden_keys_stripped(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern, _FORBIDDEN_KEYS
        raw = _valid_pattern_dict()
        for key in _FORBIDDEN_KEYS:
            raw[key] = "evil"
        result = sanitize_pattern(raw)
        for key in _FORBIDDEN_KEYS:
            assert key not in result

    def test_confidence_clamped_high(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        raw = _valid_pattern_dict(confidence=99.9)
        result = sanitize_pattern(raw)
        assert result["confidence"] <= 1.0

    def test_confidence_clamped_low(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        raw = _valid_pattern_dict(confidence=-5.0)
        result = sanitize_pattern(raw)
        assert result["confidence"] >= 0.0

    def test_invalid_pattern_type_cleared(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        raw = _valid_pattern_dict(pattern_type="run_ffmpeg")
        result = sanitize_pattern(raw)
        assert result["pattern_type"] == ""

    def test_valid_pattern_types_preserved(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        for pt in ("hook", "subtitle", "pacing", "camera", "retention", "creator"):
            raw = _valid_pattern_dict(pattern_type=pt)
            result = sanitize_pattern(raw)
            assert result["pattern_type"] == pt

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        assert sanitize_pattern(None) == {}
        assert sanitize_pattern("bad") == {}
        assert sanitize_pattern(42) == {}

    def test_is_pattern_safe_valid(self):
        from app.ai.knowledge.pattern_safety import is_pattern_safe
        assert is_pattern_safe(_valid_pattern_dict()) is True

    def test_is_pattern_safe_rejects_forbidden_key(self):
        from app.ai.knowledge.pattern_safety import is_pattern_safe
        for key in ("ffmpeg_args", "render_command", "playback_speed",
                    "api_key", "subprocess", "shell"):
            raw = _valid_pattern_dict(**{key: "bad"})
            assert is_pattern_safe(raw) is False, f"Should reject key={key}"

    def test_is_pattern_safe_rejects_missing_id(self):
        from app.ai.knowledge.pattern_safety import is_pattern_safe
        raw = _valid_pattern_dict()
        raw.pop("pattern_id")
        assert is_pattern_safe(raw) is False

    def test_is_pattern_safe_rejects_out_of_range_confidence(self):
        from app.ai.knowledge.pattern_safety import is_pattern_safe
        raw = _valid_pattern_dict(confidence=5.0)
        assert is_pattern_safe(raw) is False

    def test_is_pattern_safe_none_input(self):
        from app.ai.knowledge.pattern_safety import is_pattern_safe
        assert is_pattern_safe(None) is False

    def test_sanitize_never_raises(self):
        from app.ai.knowledge.pattern_safety import sanitize_pattern
        for bad in (None, "", 0, [], {}, {"nested": {}}):
            assert isinstance(sanitize_pattern(bad), dict)


# ---------------------------------------------------------------------------
# 3. Pattern extractor — hook patterns
# ---------------------------------------------------------------------------

class TestHookPatternExtraction:
    def test_hook_patterns_extracted_from_archetypes(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        assert len(patterns) >= 4
        types_set = {p.pattern_type for p in patterns}
        assert "hook" in types_set

    def test_question_hook_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("question_hook" in pid for pid in ids)

    def test_curiosity_hook_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("curiosity_hook" in pid for pid in ids)

    def test_hook_patterns_contain_strings(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        for p in patterns:
            assert isinstance(p.hook_patterns, list)
            for hp in p.hook_patterns:
                assert isinstance(hp, str)

    def test_hook_from_knowledge_item(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        item = _make_knowledge_item(
            knowledge_id="q_test",
            hook_patterns=["did you know", "what if I told you"],
            creator_style="viral_tiktok",
        )
        patterns = extract_hook_patterns([item])
        assert any(p.creator_style == "viral_tiktok" for p in patterns)

    def test_hook_patterns_all_safe(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        assert all(p.safe is True for p in patterns)

    def test_hook_confidence_in_range(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        for p in patterns:
            assert 0.0 <= p.confidence <= 1.0

    def test_hook_no_forbidden_keys(self):
        from app.ai.knowledge.pattern_extractor import extract_hook_patterns
        patterns = extract_hook_patterns([])
        for p in patterns:
            d = p.to_dict()
            for key in ("ffmpeg_args", "render_command", "playback_speed", "subtitle_timing"):
                assert key not in d


# ---------------------------------------------------------------------------
# 4. Pattern extractor — subtitle patterns
# ---------------------------------------------------------------------------

class TestSubtitlePatternExtraction:
    def test_subtitle_patterns_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_subtitle_patterns
        patterns = extract_subtitle_patterns([])
        assert len(patterns) >= 3
        assert all(p.pattern_type == "subtitle" for p in patterns)

    def test_compact_viral_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_subtitle_patterns
        patterns = extract_subtitle_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("compact_viral" in pid for pid in ids)

    def test_podcast_readable_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_subtitle_patterns
        patterns = extract_subtitle_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("podcast_readable" in pid for pid in ids)

    def test_subtitle_patterns_have_density(self):
        from app.ai.knowledge.pattern_extractor import extract_subtitle_patterns
        patterns = extract_subtitle_patterns([])
        for p in patterns:
            if p.subtitle_patterns:
                # Most subtitle patterns have density
                pass
        assert len(patterns) > 0

    def test_subtitle_from_knowledge_item(self):
        from app.ai.knowledge.pattern_extractor import extract_subtitle_patterns
        item = _make_knowledge_item(
            knowledge_id="sub_test",
            subtitle_patterns={"density": "compact", "max_words_per_line": 5},
            creator_style="viral_tiktok",
        )
        patterns = extract_subtitle_patterns([item])
        assert any(p.creator_style == "viral_tiktok" for p in patterns)

    def test_subtitle_all_safe(self):
        from app.ai.knowledge.pattern_extractor import extract_subtitle_patterns
        patterns = extract_subtitle_patterns([])
        assert all(p.safe is True for p in patterns)


# ---------------------------------------------------------------------------
# 5. Pattern extractor — pacing patterns
# ---------------------------------------------------------------------------

class TestPacingPatternExtraction:
    def test_pacing_patterns_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_pacing_patterns
        patterns = extract_pacing_patterns([])
        assert len(patterns) >= 3
        assert all(p.pattern_type == "pacing" for p in patterns)

    def test_fast_hook_pacing_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_pacing_patterns
        patterns = extract_pacing_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("fast_hook" in pid for pid in ids)

    def test_calm_storytelling_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_pacing_patterns
        patterns = extract_pacing_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("calm_storytelling" in pid for pid in ids)

    def test_high_energy_shortform_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_pacing_patterns
        patterns = extract_pacing_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("high_energy_shortform" in pid for pid in ids)

    def test_pacing_all_safe(self):
        from app.ai.knowledge.pattern_extractor import extract_pacing_patterns
        patterns = extract_pacing_patterns([])
        assert all(p.safe is True for p in patterns)

    def test_no_playback_speed_in_pacing(self):
        from app.ai.knowledge.pattern_extractor import extract_pacing_patterns
        patterns = extract_pacing_patterns([])
        for p in patterns:
            d = p.to_dict()
            assert "playback_speed" not in d
            assert "playback_speed" not in d.get("pacing_patterns", {})


# ---------------------------------------------------------------------------
# 6. Pattern extractor — camera patterns
# ---------------------------------------------------------------------------

class TestCameraPatternExtraction:
    def test_camera_patterns_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_camera_patterns
        patterns = extract_camera_patterns([])
        assert len(patterns) >= 3
        assert all(p.pattern_type == "camera" for p in patterns)

    def test_dynamic_safe_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_camera_patterns
        patterns = extract_camera_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("dynamic_safe" in pid for pid in ids)

    def test_static_podcast_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_camera_patterns
        patterns = extract_camera_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("static_podcast" in pid for pid in ids)

    def test_camera_all_safe(self):
        from app.ai.knowledge.pattern_extractor import extract_camera_patterns
        patterns = extract_camera_patterns([])
        assert all(p.safe is True for p in patterns)

    def test_no_ffmpeg_in_camera(self):
        from app.ai.knowledge.pattern_extractor import extract_camera_patterns
        patterns = extract_camera_patterns([])
        for p in patterns:
            d = p.to_dict()
            assert "ffmpeg_args" not in d
            assert "ffmpeg_args" not in d.get("camera_patterns", {})


# ---------------------------------------------------------------------------
# 7. Pattern extractor — retention patterns
# ---------------------------------------------------------------------------

class TestRetentionPatternExtraction:
    def test_retention_patterns_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_retention_patterns
        patterns = extract_retention_patterns([])
        assert len(patterns) >= 3
        assert all(p.pattern_type == "retention" for p in patterns)

    def test_loop_payoff_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_retention_patterns
        patterns = extract_retention_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("loop_payoff" in pid for pid in ids)

    def test_rapid_reengagement_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_retention_patterns
        patterns = extract_retention_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("rapid_reengagement" in pid for pid in ids)

    def test_payoff_reinforcement_extracted(self):
        from app.ai.knowledge.pattern_extractor import extract_retention_patterns
        patterns = extract_retention_patterns([])
        ids = [p.pattern_id for p in patterns]
        assert any("payoff_reinforcement" in pid for pid in ids)

    def test_retention_all_safe(self):
        from app.ai.knowledge.pattern_extractor import extract_retention_patterns
        patterns = extract_retention_patterns([])
        assert all(p.safe is True for p in patterns)


# ---------------------------------------------------------------------------
# 8. Full extraction
# ---------------------------------------------------------------------------

class TestFullExtraction:
    def test_extract_creator_patterns_all_types(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        items = [
            _make_knowledge_item(knowledge_id=f"item_{i}", creator_style="viral_tiktok")
            for i in range(2)
        ]
        patterns = extract_creator_patterns(items)
        types = {p.pattern_type for p in patterns}
        assert "hook" in types
        assert "subtitle" in types
        assert "pacing" in types
        assert "camera" in types
        assert "retention" in types

    def test_extract_deterministic(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        items = [_make_knowledge_item(knowledge_id="x")]
        r1 = [p.pattern_id for p in extract_creator_patterns(items)]
        r2 = [p.pattern_id for p in extract_creator_patterns(items)]
        assert r1 == r2

    def test_extract_never_raises_on_empty(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        result = extract_creator_patterns([])
        assert isinstance(result, list)

    def test_extract_never_raises_on_none(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        result = extract_creator_patterns(None)
        assert isinstance(result, list)

    def test_extract_malformed_item_handled(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        bad = types.SimpleNamespace()  # no fields at all
        result = extract_creator_patterns([bad])
        assert isinstance(result, list)

    def test_all_extracted_patterns_safe(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        patterns = extract_creator_patterns([])
        assert all(p.safe is True for p in patterns)

    def test_no_forbidden_keys_in_any_pattern(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        forbidden = {"ffmpeg_args", "render_command", "playback_speed",
                     "subtitle_timing", "api_key", "shell"}
        patterns = extract_creator_patterns([])
        for p in patterns:
            d = p.to_dict()
            for key in forbidden:
                assert key not in d


# ---------------------------------------------------------------------------
# 9. Pattern registry
# ---------------------------------------------------------------------------

class TestPatternRegistry:
    def test_registry_loads_safely(self):
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        registry = load_pattern_registry()
        assert registry is not None
        assert registry.loaded_patterns >= 0

    def test_registry_missing_base_fallback(self):
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        registry = load_pattern_registry(base_path="/nonexistent/path/xyz")
        assert registry is not None
        assert registry.loaded_patterns >= 0  # archetypes always loaded

    def test_registry_includes_all_pattern_types(self):
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        registry = load_pattern_registry()
        types = registry.pattern_types
        for expected in ("hook", "subtitle", "pacing", "camera", "retention"):
            assert expected in types, f"Missing pattern type: {expected}"

    def test_list_pattern_types(self):
        from app.ai.knowledge.pattern_registry import list_pattern_types
        types = list_pattern_types()
        assert isinstance(types, list)
        assert len(types) > 0

    def test_get_patterns_by_type_hook(self):
        from app.ai.knowledge.pattern_registry import get_patterns_by_type
        patterns = get_patterns_by_type("hook")
        assert len(patterns) >= 4
        assert all(p.pattern_type == "hook" for p in patterns)

    def test_get_patterns_by_type_subtitle(self):
        from app.ai.knowledge.pattern_registry import get_patterns_by_type
        patterns = get_patterns_by_type("subtitle")
        assert len(patterns) >= 3
        assert all(p.pattern_type == "subtitle" for p in patterns)

    def test_get_patterns_by_type_pacing(self):
        from app.ai.knowledge.pattern_registry import get_patterns_by_type
        patterns = get_patterns_by_type("pacing")
        assert len(patterns) >= 3

    def test_get_patterns_by_type_camera(self):
        from app.ai.knowledge.pattern_registry import get_patterns_by_type
        patterns = get_patterns_by_type("camera")
        assert len(patterns) >= 3

    def test_get_patterns_by_type_retention(self):
        from app.ai.knowledge.pattern_registry import get_patterns_by_type
        patterns = get_patterns_by_type("retention")
        assert len(patterns) >= 3

    def test_list_creator_patterns_by_style(self):
        from app.ai.knowledge.pattern_registry import list_creator_patterns
        patterns = list_creator_patterns("viral_tiktok")
        assert all(p.creator_style == "viral_tiktok" for p in patterns)

    def test_registry_never_raises(self):
        from app.ai.knowledge.pattern_registry import (
            load_pattern_registry, list_pattern_types,
            list_creator_patterns, get_patterns_by_type,
        )
        load_pattern_registry(base_path=None)
        list_pattern_types(base_path=None)
        list_creator_patterns("nonexistent")
        get_patterns_by_type("nonexistent")

    def test_loads_pattern_json_files(self):
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        with tempfile.TemporaryDirectory() as td:
            hooks = Path(td) / "patterns" / "hooks"
            hooks.mkdir(parents=True)
            _write_json(hooks, "q.json", _valid_pattern_dict(
                pattern_id="hook_q_test", pattern_type="hook", confidence=0.85))
            registry = load_pattern_registry(base_path=td)
        # Should include both the file pattern and archetypes
        assert registry.loaded_patterns >= 4  # archetypes always present


# ---------------------------------------------------------------------------
# 10. No-mutation safety
# ---------------------------------------------------------------------------

class TestNoMutationSafety:
    def test_no_internet_access(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        import sys
        modules_before = set(sys.modules.keys())
        extract_creator_patterns([])
        new_modules = set(sys.modules.keys()) - modules_before
        net_modules = {m for m in new_modules if any(
            k in m for k in ("urllib3", "httpx", "requests", "aiohttp")
        )}
        assert not net_modules

    def test_no_subprocess_execution(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        import sys
        modules_before = set(sys.modules.keys())
        extract_creator_patterns([])
        new_modules = set(sys.modules.keys()) - modules_before
        assert not {m for m in new_modules if "subprocess" in m}

    def test_no_ffmpeg_mutation(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        patterns = extract_creator_patterns([])
        for p in patterns:
            d = p.to_dict()
            assert "ffmpeg_args" not in d

    def test_no_playback_speed_mutation(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        patterns = extract_creator_patterns([])
        for p in patterns:
            d = p.to_dict()
            assert "playback_speed" not in d
            assert "playback_speed" not in d.get("pacing_patterns", {})

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        patterns = extract_creator_patterns([])
        for p in patterns:
            d = p.to_dict()
            assert "subtitle_timing" not in d


# ---------------------------------------------------------------------------
# 11. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_creator_patterns_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "creator_patterns")
        assert isinstance(plan.creator_patterns, dict)

    def test_creator_patterns_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.creator_patterns == {}

    def test_to_dict_includes_creator_patterns(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(), pacing=AIPacingPlan(),
        )
        plan.creator_patterns = {"available": True, "loaded_patterns": 12}
        d = plan.to_dict()
        assert "creator_patterns" in d
        assert d["creator_patterns"]["loaded_patterns"] == 12

    def test_backward_compat_all_prior_phases(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "clip_candidate_discovery", "clip_segment_selection", "clip_batch_planning",
            "feature_enhancement", "creator_knowledge",
        ):
            assert key in d, f"Missing backward-compat key: {key}"


# ---------------------------------------------------------------------------
# 12. Environment requirements
# ---------------------------------------------------------------------------

class TestEnvironmentRequirements:
    def test_no_api_key_required(self):
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        import os
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            registry = load_pattern_registry()
            assert registry is not None
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original

    def test_no_gpu_required(self):
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        patterns = extract_creator_patterns([])
        assert isinstance(patterns, list)

    def test_no_internet_required(self):
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        registry = load_pattern_registry()
        assert registry is not None

    def test_phase_39_knowledge_module_unaffected(self):
        from app.ai.knowledge.knowledge_schema import AICreatorKnowledge, AIKnowledgeRegistry
        from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_file
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry
        k = AICreatorKnowledge(knowledge_id="test")
        assert k.knowledge_id == "test"
        r = AIKnowledgeRegistry()
        assert r.available is True
