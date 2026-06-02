"""
test_groq_only_pipeline.py — Phase B unit tests for groq_only_pipeline.

Covers all 9 hard-fail conditions plus happy-path return shape, clip
exclude/lock behaviour, resume-skip-Whisper, and event sequencing.

Mocking strategy:
  - patch app.orchestration.groq_only_pipeline.transcribe_with_adapter
  - patch app.orchestration.groq_only_pipeline.run_groq_segment_selection
  - patch app.orchestration.groq_only_pipeline.has_audio_stream
  - monkeypatch app.core.config.GROQ_API_KEY
  - real RenderRequest (not Mock) so payload attributes behave correctly
  - tmp_path for work_dir/full_srt; stub set_stage_fn + cancel_registry
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# conftest.py adds repo root to sys.path; this lets tests import backend.app.*
from app.models.schemas import RenderRequest
from app.orchestration.groq_only_pipeline import (
    GroqOnlyPipelineError,
    PreRenderScenesResult,
    run_groq_only_pre_render,
)


# ── Test fixtures / helpers ──────────────────────────────────────────────────

def _make_payload(**overrides) -> RenderRequest:
    """Construct minimal RenderRequest with groq_only_mode preconditions enabled."""
    defaults = dict(
        groq_only_mode=True,
        groq_analysis_enabled=True,
        multi_variant=False,
        min_part_sec=15,
        max_part_sec=60,
        target_platform="youtube_shorts",
        groq_min_quality_score=0.6,
        resume_from_last=False,
        clip_exclude=None,
        clip_lock=None,
        highlight_per_word=False,
        subtitle_transcription_engine="default",
    )
    defaults.update(overrides)
    return RenderRequest(**defaults)


class _FakeCancelRegistry:
    """Stub cancel_registry; never cancels unless instructed."""

    class JobCancelledError(RuntimeError):
        pass

    def __init__(self, cancelled: bool = False):
        self._cancelled = cancelled

    def is_cancelled(self, _job_id: str) -> bool:
        return self._cancelled


def _make_args(tmp_path: Path, payload: RenderRequest, **kwargs):
    """Build the full keyword-arg dict for run_groq_only_pre_render."""
    source_path = tmp_path / "video.mp4"
    source_path.write_bytes(b"\x00" * 1024)  # non-empty placeholder
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    return dict(
        source_path=source_path,
        source={"slug": "video", "duration": 300.0},
        work_dir=work_dir,
        payload=payload,
        tuned={"whisper_model": "base"},
        job_id="job-test-1234567890",
        effective_channel="testch",
        retry_count=0,
        cancel_registry=_FakeCancelRegistry(),
        set_stage_fn=MagicMock(),
        **kwargs,
    )


def _write_srt(work_dir: Path, slug: str = "video", content: str = "1\n00:00:00,000 --> 00:00:05,000\nhello\n"):
    """Write a non-empty SRT to the expected location."""
    srt = work_dir / f"{slug}_full.srt"
    srt.write_text(content, encoding="utf-8")
    return srt


def _groq_seg(start: float, end: float, score: float = 0.8) -> dict:
    """Construct a Groq-shaped scored dict (mirrors _to_scored_dict)."""
    return {
        "start": start,
        "end": end,
        "duration": end - start,
        "viral_score": score * 100,
        "hook_score": score * 100,
        "motion_score": 50.0,
        "diversity_score": 50.0,
        "retention_score": score * 100,
        "audio_energy": 50.0,
        "clip_name": "clip",
        "groq_title": "title",
        "groq_reason": "reason",
        "source": "groq",
    }


# ── Tests ────────────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_groq_only_returns_pre_render_result_with_correct_shape(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)

        def _fake_transcribe(*a, **kw):
            _write_srt(args["work_dir"])
            return None

        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter", side_effect=_fake_transcribe), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection",
                   return_value=[_groq_seg(10, 40), _groq_seg(60, 95)]):
            result = run_groq_only_pre_render(**args)

        assert isinstance(result, PreRenderScenesResult)
        assert result.full_srt_available is True
        assert result.early_transcription_done is True
        assert result.total_parts == 2
        assert len(result.scored) == 2
        assert result.content_analysis is None
        assert result.target_platform == "youtube_shorts"
        assert result.dna_clean_visual is False
        assert result.early_retrieved_knowledge == []
        assert result.seg_min_sec == 15
        assert result.seg_max_sec == 60
        assert result.full_srt.exists()


class TestHardFailPreflight:
    def test_groq_only_hard_fails_when_no_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             pytest.raises(GroqOnlyPipelineError, match="GROQ_API_KEY"):
            run_groq_only_pre_render(**args)

    def test_groq_only_warns_and_continues_when_groq_analysis_not_enabled(self, tmp_path, monkeypatch, caplog):
        # Phase F1: guard downgraded from hard-fail to warning — pipeline must not raise.
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload(groq_analysis_enabled=False)
        args = _make_args(tmp_path, payload)

        def _fake_transcribe(*a, **kw):
            _write_srt(args["work_dir"])
            return None

        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter", side_effect=_fake_transcribe), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection",
                   return_value=[_groq_seg(10, 40)]), \
             caplog.at_level(logging.WARNING, logger="app.render.groq_only"):
            result = run_groq_only_pre_render(**args)  # must NOT raise

        assert result.total_parts == 1
        assert any("groq_analysis_enabled=False" in r.message for r in caplog.records)

    def test_groq_only_warns_and_continues_when_multi_variant_enabled(self, tmp_path, monkeypatch, caplog):
        # multi_variant guard downgraded from hard-fail to graceful degradation.
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload(multi_variant=True)
        args = _make_args(tmp_path, payload)

        def _fake_transcribe(*a, **kw):
            _write_srt(args["work_dir"])
            return None

        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter", side_effect=_fake_transcribe), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection",
                   return_value=[_groq_seg(10, 40)]), \
             patch("app.orchestration.groq_only_pipeline._emit_render_event") as mock_emit:
            result = run_groq_only_pre_render(**args)  # must NOT raise

        assert result.total_parts == 1
        emitted = [kw.get("event") for _a, kw in mock_emit.call_args_list]
        assert "groq_only.multi_variant_degraded" in emitted

    def test_groq_only_hard_fails_when_source_has_no_audio(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=False), \
             pytest.raises(GroqOnlyPipelineError, match="audio stream"):
            run_groq_only_pre_render(**args)


class TestHardFailWhisper:
    def test_groq_only_hard_fails_when_whisper_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)

        # Pre-create a stub SRT so we can verify _safe_unlink removes it on failure.
        srt_path = args["work_dir"] / "video_full.srt"
        srt_path.write_text("placeholder", encoding="utf-8")

        def _raise_oserror(*a, **kw):
            raise OSError("whisper disk failure")

        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter", side_effect=_raise_oserror), \
             patch("app.orchestration.groq_only_pipeline._transcription_cache_get", return_value=None):
            with pytest.raises(GroqOnlyPipelineError, match="Whisper transcription failed") as exc_info:
                run_groq_only_pre_render(**args)
            # Confirm chained exception preserved
            assert exc_info.value.__cause__ is not None
            assert isinstance(exc_info.value.__cause__, OSError)

        assert not srt_path.exists(), "SRT must be unlinked on Whisper failure"

    def test_groq_only_hard_fails_when_whisper_produces_empty_srt(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)

        def _produce_empty(*a, **kw):
            (args["work_dir"] / "video_full.srt").write_bytes(b"")  # 0-byte
            return None

        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter", side_effect=_produce_empty), \
             patch("app.orchestration.groq_only_pipeline._transcription_cache_get", return_value=None), \
             pytest.raises(GroqOnlyPipelineError, match="SRT empty"):
            run_groq_only_pre_render(**args)


class TestHardFailGroq:
    def _setup_transcribe(self, args):
        def _fake_transcribe(*a, **kw):
            _write_srt(args["work_dir"])
            return None
        return _fake_transcribe

    def test_groq_only_hard_fails_when_groq_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter",
                   side_effect=self._setup_transcribe(args)), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection", return_value=None), \
             pytest.raises(GroqOnlyPipelineError, match="min_quality_score"):
            run_groq_only_pre_render(**args)

    def test_groq_only_hard_fails_when_groq_returns_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter",
                   side_effect=self._setup_transcribe(args)), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection", return_value=[]), \
             pytest.raises(GroqOnlyPipelineError, match="empty"):
            run_groq_only_pre_render(**args)


class TestSegmentBoundsAndSteering:
    def _fake_transcribe(self, args):
        def _t(*a, **kw):
            _write_srt(args["work_dir"])
            return None
        return _t

    def test_groq_only_hard_fails_on_segments_outside_duration(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)
        args["source"] = {"slug": "video", "duration": 120.0}

        bad_seg = _groq_seg(10, 999)  # end far past duration
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter",
                   side_effect=self._fake_transcribe(args)), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection", return_value=[bad_seg]), \
             pytest.raises(GroqOnlyPipelineError, match="outside video duration"):
            run_groq_only_pre_render(**args)

    def test_groq_only_hard_fails_when_clip_exclude_wipes_pool(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload(clip_exclude=[{"start_sec": 0, "end_sec": 300}])
        args = _make_args(tmp_path, payload)

        segs = [_groq_seg(10, 40), _groq_seg(60, 90)]
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter",
                   side_effect=self._fake_transcribe(args)), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection", return_value=segs), \
             pytest.raises(GroqOnlyPipelineError, match="clip_exclude removed all"):
            run_groq_only_pre_render(**args)

    def test_groq_only_applies_clip_lock_promotion(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        # Lock the seg at start=200..230 — should move from index 2 to index 0.
        payload = _make_payload(clip_lock=[{"start_sec": 200, "end_sec": 230}])
        args = _make_args(tmp_path, payload)

        segs = [
            _groq_seg(10, 40),
            _groq_seg(60, 90),
            _groq_seg(200, 230),  # locked target
            _groq_seg(250, 290),
        ]
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter",
                   side_effect=self._fake_transcribe(args)), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection", return_value=segs):
            result = run_groq_only_pre_render(**args)

        assert len(result.scored) == 4, "clip_lock must not drop any segs"
        assert result.scored[0]["start"] == 200, "locked seg must be at front"


class TestResume:
    def test_groq_only_skips_whisper_on_resume_with_existing_srt(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload(resume_from_last=True)
        args = _make_args(tmp_path, payload)

        # Pre-write a non-empty SRT so the resume branch fires.
        _write_srt(args["work_dir"])

        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter") as mock_trans, \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection",
                   return_value=[_groq_seg(10, 40)]):
            result = run_groq_only_pre_render(**args)

        mock_trans.assert_not_called()
        assert result.total_parts == 1


class TestEventSequence:
    def test_groq_only_emits_correct_event_sequence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload(
            clip_exclude=[{"start_sec": 200, "end_sec": 210}],
            clip_lock=[{"start_sec": 60, "end_sec": 70}],
        )
        args = _make_args(tmp_path, payload)

        segs = [_groq_seg(10, 40), _groq_seg(60, 90)]
        with patch("app.orchestration.groq_only_pipeline.has_audio_stream", return_value=True), \
             patch("app.orchestration.groq_only_pipeline.transcribe_with_adapter",
                   side_effect=lambda *a, **kw: _write_srt(args["work_dir"]) and None), \
             patch("app.orchestration.groq_only_pipeline.run_groq_segment_selection", return_value=segs), \
             patch("app.orchestration.groq_only_pipeline._emit_render_event") as mock_emit:
            run_groq_only_pre_render(**args)

        emitted_events = [kw["event"] for _a, kw in mock_emit.call_args_list]
        # Verify required events fire in order
        assert "groq_only.transcription_started" in emitted_events
        assert "groq_only.selection_started" in emitted_events
        assert "clip_excluded" in emitted_events
        assert "clip_locked" in emitted_events
        assert "groq_only.selection_complete" in emitted_events

        # Ordering: transcription_started < selection_started < selection_complete
        idx_trans = emitted_events.index("groq_only.transcription_started")
        idx_sel_start = emitted_events.index("groq_only.selection_started")
        idx_sel_done = emitted_events.index("groq_only.selection_complete")
        assert idx_trans < idx_sel_start < idx_sel_done
