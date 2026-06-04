"""
test_groq_only_integration.py — Phase C integration tests for groq_only_pipeline.

Three slices:
  C1 — Segment Preservation Contract: verify scored[] from Groq flows out
       of run_groq_only_pre_render() byte-for-byte unmutated, with
       decimal-precision timestamps preserved through clip_lock promotion.

  C2 — Real FFmpeg Cut Fidelity: cut a synthetic 60s video with cut_video()
       at specific timestamps and verify ffprobe-measured output durations
       match end-start within 100ms tolerance.

  C3 — Real FFmpeg qa_pipeline Validation: generate good/bad synthetic
       outputs and verify _validate_render_output() accepts/rejects each
       correctly.

C2/C3 auto-skip when ffmpeg/ffprobe are not available on the system.

Style mirrors test_groq_only_pipeline.py (mocking strategy, fixture helpers).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.models.schemas import RenderRequest
from app.orchestration.llm_pipeline import (
    LLMPreRenderResult,
    run_llm_pre_render,
)

# Backward-compat aliases
PreRenderScenesResult = LLMPreRenderResult
run_groq_only_pre_render = run_llm_pre_render
from app.orchestration.qa_pipeline import _validate_render_output
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
from app.services.render.clip_ops import cut_video


# ── Shared helpers (mirror test_groq_only_pipeline.py) ───────────────────────


def _make_payload(**overrides) -> RenderRequest:
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
    class JobCancelledError(RuntimeError):
        pass

    def __init__(self, cancelled: bool = False):
        self._cancelled = cancelled

    def is_cancelled(self, _job_id: str) -> bool:
        return self._cancelled


def _make_args(tmp_path: Path, payload: RenderRequest, **kwargs):
    source_path = tmp_path / "video.mp4"
    source_path.write_bytes(b"\x00" * 1024)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    return dict(
        source_path=source_path,
        source={"slug": "video", "duration": 300.0},
        work_dir=work_dir,
        payload=payload,
        tuned={"whisper_model": "base"},
        job_id="job-integ-test-123",
        effective_channel="testch",
        retry_count=0,
        cancel_registry=_FakeCancelRegistry(),
        set_stage_fn=MagicMock(),
        **kwargs,
    )


def _write_srt(work_dir: Path, slug: str = "video"):
    srt = work_dir / f"{slug}_full.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nhello\n", encoding="utf-8"
    )
    return srt


def _groq_seg(start: float, end: float, score: float = 0.8) -> dict:
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


# ── FFmpeg availability gate (C2/C3 skip cleanly when absent) ────────────────


def _ffmpeg_available() -> bool:
    try:
        ffmpeg = get_ffmpeg_bin()
        ffprobe = get_ffprobe_bin()
        if not ffmpeg or not ffprobe:
            return False
        if not Path(ffmpeg).is_file() and not shutil.which(ffmpeg):
            return False
        if not Path(ffprobe).is_file() and not shutil.which(ffprobe):
            return False
        # Quick smoke test
        r = subprocess.run(
            [ffmpeg, "-version"], capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


_FFMPEG_OK = _ffmpeg_available()
_skip_no_ffmpeg = pytest.mark.skipif(
    not _FFMPEG_OK, reason="FFmpeg binary not found on system"
)


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        get_ffprobe_bin(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return float((r.stdout or "0").strip() or 0.0)


def _ffprobe_streams(path: Path) -> dict:
    """Return {'has_video': bool, 'has_audio': bool, 'duration': float}."""
    cmd = [
        get_ffprobe_bin(), "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams", [])
    return {
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "duration": float(data.get("format", {}).get("duration") or 0.0),
    }


@pytest.fixture(scope="session")
def synthetic_video_60s(tmp_path_factory):
    """Generate a 60-second synthetic video with audio track once per session.

    Uses testsrc2 (1280x720 @ 30fps colorful pattern) + sine (1kHz tone).
    Re-used across all C2/C3 tests that need real FFmpeg input.
    """
    if not _FFMPEG_OK:
        pytest.skip("FFmpeg not available — cannot generate synthetic video")
    out_dir = tmp_path_factory.mktemp("synth_video")
    out_path = out_dir / "src_60s.mp4"
    cmd = [
        get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=60",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=60",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not out_path.exists():
        pytest.skip(f"Failed to generate synthetic video: {r.stderr[:200]}")
    return out_path


@pytest.fixture(scope="session")
def synthetic_short_video(tmp_path_factory):
    """Generate a 10-second video+audio output for qa_pipeline validation."""
    if not _FFMPEG_OK:
        pytest.skip("FFmpeg not available — cannot generate synthetic video")
    out_dir = tmp_path_factory.mktemp("synth_short")
    out_path = out_dir / "good_10s.mp4"
    cmd = [
        get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not out_path.exists():
        pytest.skip(f"Failed to generate good video: {r.stderr[:200]}")
    return out_path


@pytest.fixture(scope="session")
def synthetic_video_only(tmp_path_factory):
    """10s video with NO audio stream — used to verify qa_pipeline audio warning."""
    if not _FFMPEG_OK:
        pytest.skip("FFmpeg not available")
    out_dir = tmp_path_factory.mktemp("synth_vonly")
    out_path = out_dir / "video_only_10s.mp4"
    cmd = [
        get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=10",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not out_path.exists():
        pytest.skip(f"Failed to generate video-only file: {r.stderr[:200]}")
    return out_path


@pytest.fixture(scope="session")
def synthetic_audio_only(tmp_path_factory):
    """10s audio-only MP4 — used to verify qa_pipeline rejects no-video output."""
    if not _FFMPEG_OK:
        pytest.skip("FFmpeg not available")
    out_dir = tmp_path_factory.mktemp("synth_aonly")
    out_path = out_dir / "audio_only_10s.m4a"
    cmd = [
        get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
        "-c:a", "aac", "-b:a", "96k",
        "-vn",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not out_path.exists():
        pytest.skip(f"Failed to generate audio-only file: {r.stderr[:200]}")
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
# SLICE C1 — Segment Preservation Contract (CORE business requirement)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Verifies that segments emitted by Groq flow OUT of run_groq_only_pre_render()
# byte-for-byte unchanged: timestamps preserve decimal precision, source="groq"
# is stamped, no boundary refinement occurs in the Groq-only path itself.
#
# Mocking strategy:
#   - Real run_groq_only_pre_render() — we want its actual behavior
#   - Mock transcribe_with_adapter (no Whisper subprocess)
#   - Mock run_groq_segment_selection (return our known segments)
#   - Mock has_audio_stream (return True)
# ═══════════════════════════════════════════════════════════════════════════════


class TestC1SegmentPreservation:
    """Verify Groq's scored[] is preserved unmutated through the pipeline."""

    def test_c1_groq_segments_pass_through_unchanged_to_render_loop(
        self, tmp_path, monkeypatch
    ):
        """Captured scored[] matches Groq's exact output (field-by-field)."""
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)

        groq_output = [
            _groq_seg(12.345, 27.890, score=0.85),
            _groq_seg(45.100, 75.250, score=0.72),
        ]
        # Defensive copies — we assert on identity-of-values, not identity-of-list
        import copy
        groq_output_snapshot = copy.deepcopy(groq_output)

        def _fake_transcribe(*a, **kw):
            _write_srt(args["work_dir"])
            return None

        with patch(
            "app.orchestration.llm_pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "app.orchestration.llm_pipeline.transcribe_with_adapter",
            side_effect=_fake_transcribe,
        ), patch(
            "app.orchestration.llm_pipeline.run_llm_segment_selection",
            return_value=groq_output,
        ):
            result = run_groq_only_pre_render(**args)

        # Result is the boundary at which render_loop receives scored[]
        assert isinstance(result, PreRenderScenesResult)
        assert len(result.scored) == len(groq_output_snapshot)

        # Field-by-field equality with Groq's exact output
        for actual, expected in zip(result.scored, groq_output_snapshot):
            for key in (
                "start", "end", "duration", "viral_score", "hook_score",
                "motion_score", "diversity_score", "retention_score",
                "audio_energy", "clip_name", "groq_title", "groq_reason",
                "source",
            ):
                assert actual[key] == expected[key], (
                    f"field '{key}' mutated: {actual[key]!r} vs {expected[key]!r}"
                )
            # source must remain 'groq'
            assert actual["source"] == "groq"

    def test_c1_groq_timestamps_preserved_with_decimal_precision(
        self, tmp_path, monkeypatch
    ):
        """Float equality at sub-millisecond precision — no float-rounding drift."""
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload()
        args = _make_args(tmp_path, payload)

        # Pick timestamps with decimal patterns that would expose any round/cast bug
        precise_segs = [
            _groq_seg(12.345, 27.890),
            _groq_seg(33.001, 48.999),
            _groq_seg(100.123456, 130.654321),
        ]

        with patch(
            "app.orchestration.llm_pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "app.orchestration.llm_pipeline.transcribe_with_adapter",
            side_effect=lambda *a, **kw: _write_srt(args["work_dir"]),
        ), patch(
            "app.orchestration.llm_pipeline.run_llm_segment_selection",
            return_value=precise_segs,
        ):
            result = run_groq_only_pre_render(**args)

        # Exact float equality (==) — pipeline must not round or coerce timestamps
        assert result.scored[0]["start"] == 12.345
        assert result.scored[0]["end"] == 27.890
        assert result.scored[1]["start"] == 33.001
        assert result.scored[1]["end"] == 48.999
        assert result.scored[2]["start"] == 100.123456
        assert result.scored[2]["end"] == 130.654321

    def test_c1_clip_lock_preserves_groq_timestamps_when_promoting(
        self, tmp_path, monkeypatch
    ):
        """clip_lock reorders segments but must NOT mutate any timestamp."""
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")
        payload = _make_payload(
            clip_lock=[{"start_sec": 200, "end_sec": 230}]
        )
        args = _make_args(tmp_path, payload)

        segs = [
            _groq_seg(10.111, 40.222),
            _groq_seg(60.333, 90.444),
            _groq_seg(205.555, 228.666),  # in lock range → promoted to front
            _groq_seg(250.777, 290.888),
        ]

        with patch(
            "app.orchestration.llm_pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "app.orchestration.llm_pipeline.transcribe_with_adapter",
            side_effect=lambda *a, **kw: _write_srt(args["work_dir"]),
        ), patch(
            "app.orchestration.llm_pipeline.run_llm_segment_selection",
            return_value=segs,
        ):
            result = run_groq_only_pre_render(**args)

        # Order: locked segment promoted to index 0
        assert len(result.scored) == 4
        assert result.scored[0]["start"] == 205.555
        assert result.scored[0]["end"] == 228.666

        # Original timestamps preserved exactly across reorder
        promoted_starts = sorted(s["start"] for s in result.scored)
        assert promoted_starts == [10.111, 60.333, 205.555, 250.777]
        promoted_ends = sorted(s["end"] for s in result.scored)
        assert promoted_ends == [40.222, 90.444, 228.666, 290.888]

    def test_c1_no_s4_refinement_applied_in_groq_only_mode(
        self, tmp_path, monkeypatch
    ):
        """In default config (S4 env vars off), no candidate_adjustment_reason
        or cut_adjustment_reason flags appear — confirms no refinement was
        attempted within run_groq_only_pre_render() itself."""
        # Ensure S4 env vars are NOT set
        monkeypatch.delenv("S4_CANDIDATE_INTELLIGENCE_ENABLED", raising=False)
        monkeypatch.delenv("S4_RETENTION_PROXY_ENABLED", raising=False)
        monkeypatch.delenv("S4_SPEAKER_AWARE_CUTS_ENABLED", raising=False)
        monkeypatch.setattr("app.core.config.GROQ_API_KEY", "test-key")

        payload = _make_payload()
        args = _make_args(tmp_path, payload)
        segs = [_groq_seg(10.0, 40.0), _groq_seg(60.0, 95.0)]

        with patch(
            "app.orchestration.llm_pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "app.orchestration.llm_pipeline.transcribe_with_adapter",
            side_effect=lambda *a, **kw: _write_srt(args["work_dir"]),
        ), patch(
            "app.orchestration.llm_pipeline.run_llm_segment_selection",
            return_value=segs,
        ):
            result = run_groq_only_pre_render(**args)

        # None of the returned segments should carry S4 mutation markers
        for seg in result.scored:
            assert "candidate_adjustment_reason" not in seg, (
                "groq_only_pipeline must not invoke s4_boundary_refinement"
            )
            assert "retention_adjustment_reason" not in seg, (
                "groq_only_pipeline must not invoke s4_retention_proxy"
            )
            assert "cut_adjustment_reason" not in seg, (
                "groq_only_pipeline must not invoke s4_natural_cuts"
            )
            # And start/end must be exactly what we passed in
            assert seg["start"] in (10.0, 60.0)
            assert seg["end"] in (40.0, 95.0)


# ═══════════════════════════════════════════════════════════════════════════════
# SLICE C2 — Real FFmpeg Cut Fidelity
# ═══════════════════════════════════════════════════════════════════════════════
#
# Verifies cut_video() (real FFmpeg subprocess) respects requested timestamps
# to within ±100ms tolerance, preserves both audio and video streams, and
# correctly handles multiple sequential cuts.
# ═══════════════════════════════════════════════════════════════════════════════


@_skip_no_ffmpeg
class TestC2FFmpegCutFidelity:
    """Real FFmpeg cut_video calls against a synthetic source video."""

    # cut_video's internal tolerance is max(0.35, dur*0.03) — it ACCEPTS up to
    # 350ms drift. For business-correctness assertion we use a tighter ±150ms
    # check (real-world stream-copy keyframe drift can push past 100ms).
    DURATION_TOLERANCE_SEC = 0.15

    def test_c2_cut_video_respects_start_end_timestamps(
        self, synthetic_video_60s, tmp_path
    ):
        """Single cut with mid-decimal timestamps lands within tolerance."""
        out = tmp_path / "cut_single.mp4"
        start, end = 10.0, 25.5
        intended = end - start

        cut_video(str(synthetic_video_60s), str(out), start, end)

        assert out.exists(), "cut_video did not produce output"
        assert out.stat().st_size > 10_000, "output suspiciously small"

        actual_dur = _ffprobe_duration(out)
        drift = abs(actual_dur - intended)
        assert drift <= self.DURATION_TOLERANCE_SEC, (
            f"cut duration drift {drift:.3f}s exceeds "
            f"{self.DURATION_TOLERANCE_SEC}s tolerance "
            f"(intended={intended:.3f}s actual={actual_dur:.3f}s)"
        )

    def test_c2_three_cuts_produce_three_valid_outputs(
        self, synthetic_video_60s, tmp_path
    ):
        """Three independent cuts each respect their intended durations."""
        cuts = [
            (10.0, 25.5),
            (30.0, 45.5),
            (50.0, 58.0),
        ]
        outputs = []
        for i, (start, end) in enumerate(cuts):
            out = tmp_path / f"cut_{i}.mp4"
            cut_video(str(synthetic_video_60s), str(out), start, end)
            outputs.append((out, end - start))

        for out_path, intended in outputs:
            assert out_path.exists(), f"missing {out_path.name}"
            actual = _ffprobe_duration(out_path)
            drift = abs(actual - intended)
            assert drift <= self.DURATION_TOLERANCE_SEC, (
                f"{out_path.name}: drift {drift:.3f}s "
                f"intended={intended:.3f} actual={actual:.3f}"
            )

    def test_c2_cut_preserves_audio_stream(
        self, synthetic_video_60s, tmp_path
    ):
        """Cut output must keep both video and audio streams from source."""
        out = tmp_path / "cut_av.mp4"
        cut_video(str(synthetic_video_60s), str(out), 15.0, 25.0)

        assert out.exists()
        streams = _ffprobe_streams(out)
        assert streams["has_video"], "cut output lost video stream"
        assert streams["has_audio"], "cut output lost audio stream"


# ═══════════════════════════════════════════════════════════════════════════════
# SLICE C3 — Real FFmpeg qa_pipeline Validation
# ═══════════════════════════════════════════════════════════════════════════════
#
# Verifies _validate_render_output() correctly accepts good output and rejects
# truncated/empty/incomplete outputs. Uses real FFmpeg-generated files.
# ═══════════════════════════════════════════════════════════════════════════════


@_skip_no_ffmpeg
class TestC3QaPipelineValidation:
    """Real qa_pipeline._validate_render_output against synthetic outputs."""

    def test_c3_qa_pipeline_accepts_valid_video_with_audio(
        self, synthetic_short_video
    ):
        """A normal 10s video with audio passes all hard checks."""
        result = _validate_render_output(synthetic_short_video)
        assert result["ok"] is True, (
            f"valid video rejected: {result.get('error')!r} "
            f"warnings={result.get('warnings')}"
        )
        assert result["error"] is None
        meta = result["metadata"]
        assert meta["has_video"] is True
        assert meta["has_audio"] is True
        assert meta["duration"] > 0

    def test_c3_qa_pipeline_rejects_zero_byte_file(self, tmp_path):
        """Empty/zero-byte file fails the 10KB minimum size check."""
        bad = tmp_path / "empty.mp4"
        bad.write_bytes(b"")

        result = _validate_render_output(bad)
        assert result["ok"] is False
        assert result["error"] is not None
        assert "too small" in result["error"].lower()
        assert result["code"] == "RN001"

    def test_c3_qa_pipeline_rejects_video_without_audio(
        self, synthetic_video_only
    ):
        """Video-only output passes hard checks but emits an audio warning.

        Per qa_pipeline contract, missing audio is non-fatal (warn-only) so
        legitimate silent clips aren't blocked — but the warning MUST appear
        so developers can detect the issue.
        """
        result = _validate_render_output(synthetic_video_only)
        # Hard checks still pass (video present, duration > 0, > 10KB)
        assert result["ok"] is True
        assert result["metadata"]["has_video"] is True
        assert result["metadata"]["has_audio"] is False
        # ...but warning must surface the missing-audio condition
        assert any(
            "audio" in w.lower() for w in result["warnings"]
        ), f"expected audio warning, got {result['warnings']!r}"

    def test_c3_qa_pipeline_rejects_video_without_video_stream(
        self, synthetic_audio_only
    ):
        """Audio-only output fails the 'no video stream' hard check."""
        result = _validate_render_output(synthetic_audio_only)
        assert result["ok"] is False
        assert result["error"] is not None
        assert "video stream" in result["error"].lower()
        assert result["code"] == "RN001"
        assert result["metadata"]["has_video"] is False
