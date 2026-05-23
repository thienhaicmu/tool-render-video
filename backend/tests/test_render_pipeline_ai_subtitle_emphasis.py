"""
test_render_pipeline_ai_subtitle_emphasis.py — Phase 5.5 render pipeline integration tests.

Tests:
- AI disabled → subtitle emphasis not applied, behavior unchanged
- no knowledge/hints → behavior unchanged
- valid "strong" hint → config applied=True
- valid "subtle" hint → config applied=True
- invalid hint → rejected, behavior unchanged
- user subtitle_style preserved (style ID unchanged)
- subtitle timing unchanged after AI hint applied
- trace logs ai.subtitle_emphasis_applied when applied
- trace logs rejection when not applied
- no FFmpeg command changes
"""
from __future__ import annotations

import pytest
from unittest import mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exec_hints(style=None):
    """Build an execution hints dict for testing."""
    h = {}
    if style is not None:
        h["subtitle_emphasis_style"] = style
    h["source_knowledge_ids"] = ["kb_test_001"]
    return h


# ---------------------------------------------------------------------------
# build_ai_subtitle_emphasis_config — used by pipeline
# ---------------------------------------------------------------------------

class TestAISubtitleEmphasisConfigInPipeline:
    """Test that build_ai_subtitle_emphasis_config behaves correctly for pipeline use cases."""

    def test_ai_disabled_produces_disabled_config(self):
        """When AI is disabled, no execution hints → config.enabled=False."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        # AI disabled: no hints available
        cfg = build_ai_subtitle_emphasis_config(None)
        assert cfg.enabled is False
        assert cfg.applied is False

    def test_no_hints_produces_not_applied(self):
        """Empty hints dict → applied=False, behavior unchanged."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        cfg = build_ai_subtitle_emphasis_config({})
        assert cfg.applied is False

    def test_no_subtitle_emphasis_style_hint_rejected(self):
        """Hints present but no subtitle_emphasis_style → rejected."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        cfg = build_ai_subtitle_emphasis_config({
            "cut_interval_min": 2.0,
            "cut_interval_max": 5.0,
            "source_knowledge_ids": ["kb_001"],
        })
        assert cfg.applied is False
        assert cfg.rejected_reason == "no_subtitle_emphasis_hint"

    def test_valid_strong_hint_applied(self):
        """Valid 'strong' hint → applied=True."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        cfg = build_ai_subtitle_emphasis_config(_make_exec_hints("strong"))
        assert cfg.applied is True
        assert cfg.emphasis_style == "strong"

    def test_valid_subtle_hint_applied(self):
        """Valid 'subtle' hint → applied=True."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        cfg = build_ai_subtitle_emphasis_config(_make_exec_hints("subtle"))
        assert cfg.applied is True
        assert cfg.emphasis_style == "subtle"

    def test_invalid_hint_rejected_behavior_unchanged(self):
        """Invalid hint → rejected=invalid_emphasis_style, applied=False."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        cfg = build_ai_subtitle_emphasis_config(_make_exec_hints("ultra_heavy"))
        assert cfg.applied is False
        assert cfg.rejected_reason == "invalid_emphasis_style"

    def test_user_subtitle_style_preserved(self):
        """AI hint config does not change payload.subtitle_style or preset ID."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        cfg = build_ai_subtitle_emphasis_config(_make_exec_hints("strong"))
        # Config only adds emphasis_level_override — never modifies subtitle style ID
        # The "emphasis_style" in config is a LEVEL hint, not a style ID
        assert cfg.emphasis_style in {"subtle", "medium", "strong", "word_only", None}
        # Existing style IDs must not appear in config fields
        known_style_ids = {
            "tiktok_bounce_v1", "viral_bold", "bold_cap", "story_clean_01",
            "clean_pro", "boxed_caption", "viral", "clean", "story", "gaming",
        }
        assert cfg.emphasis_style not in known_style_ids


# ---------------------------------------------------------------------------
# Subtitle timing preservation
# ---------------------------------------------------------------------------

class TestSubtitleTimingPreservation:
    def test_timing_not_mutated_by_ai_strong_hint(self):
        """subtitle_emphasis_pass with AI strong override must not change timestamps."""
        from app.services.subtitles.readability import subtitle_emphasis_pass

        blocks = [
            {"start": 1.000, "end": 2.500, "text": "Amazing secret revealed"},
            {"start": 3.000, "end": 4.000, "text": "Best deal ever"},
        ]
        starts_before = [b["start"] for b in blocks]
        ends_before = [b["end"] for b in blocks]

        subtitle_emphasis_pass(
            blocks,
            preset_id="tiktok_bounce_v1",
            market="US",
            language="en",
            emphasis_level_override="strong",
        )

        assert [b["start"] for b in blocks] == starts_before
        assert [b["end"] for b in blocks] == ends_before

    def test_timing_not_mutated_by_ai_subtle_hint(self):
        """subtitle_emphasis_pass with AI subtle override must not change timestamps."""
        from app.services.subtitles.readability import subtitle_emphasis_pass

        blocks = [
            {"start": 0.100, "end": 1.200, "text": "Save $50 today"},
        ]
        start_before = blocks[0]["start"]
        end_before = blocks[0]["end"]

        subtitle_emphasis_pass(
            blocks,
            preset_id="clean_pro",
            market="US",
            emphasis_level_override="subtle",
        )

        assert blocks[0]["start"] == start_before
        assert blocks[0]["end"] == end_before


# ---------------------------------------------------------------------------
# Trace logger
# ---------------------------------------------------------------------------

class TestTraceLoggerSubtitleEmphasis:
    def test_trace_logs_applied_when_applied(self, tmp_path):
        """Tracer writes ai.subtitle_emphasis_applied when config.applied=True."""
        import json
        from app.ai.tracing import AITraceLogger
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config

        tracer = AITraceLogger("job_test_123", log_dir=tmp_path)
        cfg = build_ai_subtitle_emphasis_config(_make_exec_hints("strong"))
        assert cfg.applied is True

        tracer.log_subtitle_emphasis_applied({
            **cfg.to_dict(),
            "reason": "valid_ai_subtitle_hint",
        })

        log_file = tmp_path / "job_test_123_ai_trace.jsonl"
        assert log_file.exists()
        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        assert any(r["event"] == "ai.subtitle_emphasis_applied" for r in records)
        applied_record = next(r for r in records if r["event"] == "ai.subtitle_emphasis_applied")
        assert applied_record["applied"] is True
        assert applied_record["emphasis_style"] == "strong"

    def test_trace_logs_rejection_when_not_applied(self, tmp_path):
        """Tracer writes decision_rejected when config.applied=False."""
        import json
        from app.ai.tracing import AITraceLogger
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config

        tracer = AITraceLogger("job_test_456", log_dir=tmp_path)
        cfg = build_ai_subtitle_emphasis_config(None)  # no hints → not applied
        assert cfg.applied is False

        tracer.log_decision_rejected(
            str(cfg.rejected_reason or "no_subtitle_emphasis_hint"),
            detail={"hint": "subtitle_emphasis_style", "phase": "5.5"},
        )

        log_file = tmp_path / "job_test_456_ai_trace.jsonl"
        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        assert any(r["event"] == "ai.decision_rejected" for r in records)

    def test_trace_subtitle_emphasis_applied_has_required_fields(self, tmp_path):
        """ai.subtitle_emphasis_applied record has all required payload fields."""
        import json
        from app.ai.tracing import AITraceLogger

        tracer = AITraceLogger("job_test_789", log_dir=tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "medium",
            "source_knowledge_ids": ["k1", "k2"],
            "reason": "valid_ai_subtitle_hint",
        })

        log_file = tmp_path / "job_test_789_ai_trace.jsonl"
        record = json.loads(
            log_file.read_text(encoding="utf-8").strip().splitlines()[0]
        )
        for field in ("applied", "emphasis_style", "source_knowledge_ids", "target", "reason"):
            assert field in record, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# No FFmpeg command changes
# ---------------------------------------------------------------------------

class TestNoFFmpegChanges:
    def test_subtitle_emphasis_config_does_not_import_ffmpeg(self):
        """subtitle_hints.py must not import ffmpeg or subprocess."""
        import inspect
        import app.ai.subtitle_hints as m
        src = inspect.getsource(m)
        # Check that there are no import statements referencing ffmpeg or subprocess
        import_lines = [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "ffmpeg" not in line.lower(), f"Unexpected ffmpeg import: {line}"
            assert "subprocess" not in line.lower(), f"Unexpected subprocess import: {line}"

    def test_emphasis_level_override_does_not_touch_ass_generation(self):
        """emphasis_level_override only affects text transforms, not ASS generation."""
        from app.services.subtitles.readability import subtitle_emphasis_pass
        # ASS generation happens AFTER subtitle_emphasis_pass (in srt_to_ass_bounce).
        # This test verifies the blocks returned are still valid SRT block dicts
        # (no ASS tags injected by emphasis pass itself).
        blocks = [
            {"start": 0.0, "end": 1.0, "text": "Watch this now"},
        ]
        subtitle_emphasis_pass(
            blocks,
            preset_id="tiktok_bounce_v1",
            market="US",
            emphasis_level_override="strong",
        )
        # text may have emphasis markers (PUA chars) but should not have raw ASS
        # block-level ASS like \an or \pos (those come from srt_to_ass_bounce).
        text = blocks[0]["text"]
        assert r"\an" not in text
        assert r"\pos" not in text


# ---------------------------------------------------------------------------
# Garbage-safe pipeline behavior
# ---------------------------------------------------------------------------

class TestGarbageSafePipeline:
    def test_config_never_raises_in_pipeline_context(self):
        """Simulate pipeline context: any garbage input must not raise."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        for bad_input in [None, {}, [], 42, "string", {"random": True}]:
            cfg = build_ai_subtitle_emphasis_config(bad_input)
            # Must produce a valid config with bool fields
            assert isinstance(cfg.applied, bool)
            assert isinstance(cfg.enabled, bool)

    def test_config_to_dict_always_valid(self):
        """to_dict() always returns a dict with required keys."""
        from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
        for hints in [None, {}, {"subtitle_emphasis_style": "strong"}, {"subtitle_emphasis_style": "bad"}]:
            cfg = build_ai_subtitle_emphasis_config(hints)
            d = cfg.to_dict()
            assert isinstance(d, dict)
            assert "applied" in d
            assert "emphasis_style" in d
            assert "source_knowledge_ids" in d
