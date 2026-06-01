"""
test_groq_pipeline.py — Phase F integration tests for the Groq segment selection pipeline.

Covers:
  F1 — GroqSegment parser: sanitize_clip_name, parse_segment_response
  F2 — PartContext: from_dict / to_dict round-trip, composite score, helpers
  F3 — groq_stage: _to_scored_dict produces correct shape
  F4 — parallel_analysis: ParallelAnalysisResult dataclass defaults and properties
  F5 — AI domain __init__.py: public symbols importable without optional deps
  F6 — Whisper warmup: warmup_fw_model returns False gracefully when unavailable
"""
import json
import pytest


# ── F1: GroqSegment parser ────────────────────────────────────────────────────

class TestSanitizeClipName:
    def test_strips_fs_invalid_chars(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        assert sanitize_clip_name('Hello/World') == 'HelloWorld'
        assert sanitize_clip_name('test:file') == 'testfile'
        assert sanitize_clip_name('a*b?c<d>e|f') == 'abcdef'

    def test_keeps_spaces(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        result = sanitize_clip_name('Bí quyết tăng view nhanh')
        assert result == 'Bí quyết tăng view nhanh'

    def test_keeps_vietnamese_chars(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        assert sanitize_clip_name('Câu chuyện khởi nghiệp') == 'Câu chuyện khởi nghiệp'

    def test_collapses_multiple_spaces(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        assert sanitize_clip_name('a   b') == 'a b'

    def test_strips_backslash(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        assert '\\' not in sanitize_clip_name('path\\file')

    def test_fallback_on_empty(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        assert sanitize_clip_name('') == 'clip'
        assert sanitize_clip_name('///') == 'clip'

    def test_truncates_at_80(self):
        from app.ai.analysis.groq.parser import sanitize_clip_name
        long_name = 'a' * 100
        assert len(sanitize_clip_name(long_name)) <= 80


class TestParseSegmentResponse:
    """parse_segment_response — 3-strategy JSON extraction."""

    def _make_raw(self, segments):
        return json.dumps(segments)

    def test_direct_json_array(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        raw = json.dumps([
            {"start": 10.0, "end": 45.0, "score": 0.9,
             "clip_name": "Hook opener", "title": "T", "reason": "R"},
        ])
        result = parse_segment_response(raw, output_count=1, min_sec=15, max_sec=60, video_duration=300)
        assert result is not None
        assert len(result) == 1
        assert result[0].start == pytest.approx(10.0)
        assert result[0].end == pytest.approx(45.0)
        assert result[0].clip_name == 'Hook opener'

    def test_markdown_fence(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        raw = '```json\n[{"start":5,"end":40,"score":0.8,"clip_name":"Test","title":"T","reason":"R"}]\n```'
        result = parse_segment_response(raw, output_count=1, min_sec=15, max_sec=60, video_duration=300)
        assert result is not None
        assert result[0].clip_name == 'Test'

    def test_rejects_too_short(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        raw = json.dumps([
            {"start": 0, "end": 5, "score": 0.9, "clip_name": "X", "title": "T", "reason": "R"},
        ])
        result = parse_segment_response(raw, output_count=1, min_sec=15, max_sec=60, video_duration=300)
        assert result is None

    def test_rejects_too_long(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        raw = json.dumps([
            {"start": 0, "end": 200, "score": 0.9, "clip_name": "X", "title": "T", "reason": "R"},
        ])
        result = parse_segment_response(raw, output_count=1, min_sec=15, max_sec=60, video_duration=300)
        assert result is None

    def test_rejects_beyond_video_duration(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        raw = json.dumps([
            {"start": 290, "end": 320, "score": 0.9, "clip_name": "X", "title": "T", "reason": "R"},
        ])
        result = parse_segment_response(raw, output_count=1, min_sec=15, max_sec=60, video_duration=300)
        assert result is None

    def test_returns_none_on_invalid_json(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        result = parse_segment_response("not json at all", output_count=1, min_sec=15, max_sec=60, video_duration=300)
        assert result is None

    def test_sorts_by_score_desc(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        raw = json.dumps([
            {"start": 10, "end": 40, "score": 0.5, "clip_name": "Low", "title": "T", "reason": "R"},
            {"start": 50, "end": 90, "score": 0.9, "clip_name": "High", "title": "T", "reason": "R"},
        ])
        result = parse_segment_response(raw, output_count=2, min_sec=15, max_sec=90, video_duration=300)
        assert result is not None
        assert result[0].clip_name == 'High'

    def test_clips_to_output_count(self):
        from app.ai.analysis.groq.parser import parse_segment_response
        segs = [
            {"start": i * 40, "end": i * 40 + 30, "score": 0.8 - i * 0.05,
             "clip_name": f"Clip {i}", "title": "T", "reason": "R"}
            for i in range(5)
        ]
        raw = json.dumps(segs)
        result = parse_segment_response(raw, output_count=2, min_sec=15, max_sec=60, video_duration=600)
        assert result is not None
        assert len(result) == 2


# ── F2: PartContext round-trip ─────────────────────────────────────────────────

class TestPartContext:
    def test_from_dict_basic(self):
        from app.orchestration.context import PartContext
        d = {"start": 10.0, "end": 50.0, "duration": 40.0, "viral_score": 75.5}
        ctx = PartContext.from_dict(d)
        assert ctx.start == pytest.approx(10.0)
        assert ctx.viral_score == pytest.approx(75.5)

    def test_to_dict_round_trip(self):
        from app.orchestration.context import PartContext
        d = {
            "start": 5.0, "end": 35.0, "duration": 30.0,
            "viral_score": 80.0, "hook_score": 70.0, "motion_score": 60.0,
            "clip_name": "Bí quyết",
        }
        ctx = PartContext.from_dict(d)
        out = ctx.to_dict()
        assert out["start"] == pytest.approx(5.0)
        assert out["clip_name"] == "Bí quyết"

    def test_extra_keys_preserved(self):
        from app.orchestration.context import PartContext
        d = {"start": 0.0, "end": 30.0, "duration": 30.0, "custom_key": "hello"}
        ctx = PartContext.from_dict(d)
        out = ctx.to_dict()
        assert out["custom_key"] == "hello"

    def test_defaults_safe(self):
        from app.orchestration.context import PartContext
        ctx = PartContext()
        assert ctx.start == 0.0
        assert ctx.audio_energy == 50.0
        assert ctx.source == "local"

    def test_composite_uses_combined_score_first(self):
        from app.orchestration.context import PartContext
        ctx = PartContext(viral_score=60.0, combined_score=90.0)
        assert ctx.composite() == pytest.approx(90.0)

    def test_composite_fallback_viral(self):
        from app.orchestration.context import PartContext
        ctx = PartContext(viral_score=70.0, ai_blend_bonus=5.0)
        assert ctx.composite() == pytest.approx(75.0)

    def test_is_high_motion(self):
        from app.orchestration.context import PartContext
        assert PartContext(motion_score=61.0).is_high_motion() is True
        assert PartContext(motion_score=59.0).is_high_motion() is False

    def test_has_groq_data(self):
        from app.orchestration.context import PartContext
        ctx = PartContext(source="groq", groq_title="My title")
        assert ctx.has_groq_data() is True
        assert PartContext(source="local").has_groq_data() is False

    def test_bulk_helpers(self):
        from app.orchestration.context import parts_from_dicts, parts_to_dicts
        dicts = [{"start": float(i), "end": float(i + 30), "duration": 30.0} for i in range(3)]
        parts = parts_from_dicts(dicts)
        assert len(parts) == 3
        out = parts_to_dicts(parts)
        assert out[0]["start"] == pytest.approx(0.0)
        assert out[2]["start"] == pytest.approx(2.0)


# ── F3: groq_stage scored dict shape ──────────────────────────────────────────

class TestGroqStageToDictShape:
    """_to_scored_dict must produce all fields expected by pipeline consumers."""

    def _make_segment(self):
        from app.ai.analysis.groq.parser import GroqSegment
        return GroqSegment(
            start=10.0, end=55.0, score=0.85,
            clip_name="Khoảnh khắc viral",
            title="Viral moment", reason="High engagement",
        )

    def test_required_timing_fields(self):
        from app.orchestration.groq_stage import _to_scored_dict
        d = _to_scored_dict(self._make_segment())
        assert d["start"] == pytest.approx(10.0)
        assert d["end"] == pytest.approx(55.0)
        assert d["duration"] == pytest.approx(45.0)

    def test_score_fields_present(self):
        from app.orchestration.groq_stage import _to_scored_dict
        d = _to_scored_dict(self._make_segment())
        for field in ("viral_score", "hook_score", "motion_score",
                      "diversity_score", "retention_score", "audio_energy"):
            assert field in d, f"Missing field: {field}"

    def test_viral_score_scaled(self):
        from app.orchestration.groq_stage import _to_scored_dict
        d = _to_scored_dict(self._make_segment())
        assert d["viral_score"] == pytest.approx(85.0)

    def test_clip_name_preserved(self):
        from app.orchestration.groq_stage import _to_scored_dict
        d = _to_scored_dict(self._make_segment())
        assert d["clip_name"] == "Khoảnh khắc viral"

    def test_source_is_groq(self):
        from app.orchestration.groq_stage import _to_scored_dict
        d = _to_scored_dict(self._make_segment())
        assert d["source"] == "groq"

    def test_groq_metadata_present(self):
        from app.orchestration.groq_stage import _to_scored_dict
        d = _to_scored_dict(self._make_segment())
        assert d["groq_title"] == "Viral moment"
        assert d["groq_reason"] == "High engagement"


# ── F4: parallel_analysis module ──────────────────────────────────────────────

class TestParallelAnalysisResult:
    def test_default_result(self):
        from app.orchestration.parallel_analysis import ParallelAnalysisResult
        r = ParallelAnalysisResult()
        assert r.scenes == []
        assert r.full_srt_available is False
        assert r.scene_ok is True        # no error
        assert r.transcription_ok is False

    def test_scene_ok_false_when_error(self):
        from app.orchestration.parallel_analysis import ParallelAnalysisResult
        r = ParallelAnalysisResult(scene_error="failed")
        assert r.scene_ok is False

    def test_transcription_ok_true_when_available(self):
        from app.orchestration.parallel_analysis import ParallelAnalysisResult
        r = ParallelAnalysisResult(full_srt_available=True)
        assert r.transcription_ok is True


# ── F5: AI domain __init__.py public symbols ──────────────────────────────────

class TestAIDomainInterfaces:
    def test_analysis_domain_importable(self):
        import app.ai.analysis
        assert hasattr(app.ai.analysis, 'HybridAnalyzer')
        assert hasattr(app.ai.analysis, 'AnalysisSignals')

    def test_analysis_groq_symbols_in_all(self):
        import app.ai.analysis as m
        assert 'select_segments' in m.__all__
        assert 'GroqSegment' in m.__all__

    def test_director_domain_importable(self):
        import app.ai.director
        # Module must import without error even if optional deps absent

    def test_platform_domain_importable(self):
        import app.ai.platform

    def test_quality_domain_importable(self):
        import app.ai.quality

    def test_quality_gate_domain_importable(self):
        import app.ai.quality_gate


# ── F6: Whisper warmup graceful failure ───────────────────────────────────────

class TestWhisperWarmup:
    def test_returns_false_when_faster_whisper_absent(self, monkeypatch):
        """warmup_fw_model must return False (not raise) when faster_whisper not installed."""
        import app.services.subtitle_transcription_adapters as m
        monkeypatch.setattr(m, 'has_faster_whisper', lambda: False)
        result = m.warmup_fw_model("small")
        assert result is False

    def test_returns_false_on_model_load_error(self, monkeypatch):
        """warmup_fw_model must return False (not raise) on any load error."""
        import app.services.subtitle_transcription_adapters as m
        monkeypatch.setattr(m, 'has_faster_whisper', lambda: True)
        monkeypatch.setattr(m, '_detect_fw_device_compute', lambda: ("cpu", "int8"))
        monkeypatch.setattr(m, '_get_fw_model', lambda *a: (_ for _ in ()).throw(RuntimeError("no model")))
        result = m.warmup_fw_model("small")
        assert result is False
