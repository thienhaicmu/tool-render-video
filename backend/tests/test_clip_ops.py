"""
Tests for Phase 4E.2: services/render/clip_ops.py extraction.

Verifies:
- Import from new module works
- Backward-compat import from render_engine works
- Key moved names are identical objects between modules
- Behavior of clip ops is unchanged (no real FFmpeg calls)
"""

import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Import smoke tests — new module
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_clip_ops_package(self):
        from app.services.render import clip_ops
        assert clip_ops is not None

    def test_import_cut_video(self):
        from app.services.render.clip_ops import cut_video
        assert callable(cut_video)

    def test_import_detect_silence_trim_offset(self):
        from app.services.render.clip_ops import detect_silence_trim_offset
        assert callable(detect_silence_trim_offset)

    def test_import_detect_bad_first_frame(self):
        from app.services.render.clip_ops import detect_bad_first_frame
        assert callable(detect_bad_first_frame)

    def test_import_detect_silence_segments(self):
        from app.services.render.clip_ops import _detect_silence_segments
        assert callable(_detect_silence_segments)

    def test_import_apply_micro_pacing(self):
        from app.services.render.clip_ops import apply_micro_pacing
        assert callable(apply_micro_pacing)


# ---------------------------------------------------------------------------
# Backward-compat imports — render_engine namespace
# ---------------------------------------------------------------------------

class TestBackwardCompatImport:
    def test_cut_video_via_render_engine(self):
        from app.services.render_engine import cut_video
        assert callable(cut_video)

    def test_detect_silence_trim_offset_via_render_engine(self):
        from app.services.render_engine import detect_silence_trim_offset
        assert callable(detect_silence_trim_offset)

    def test_detect_bad_first_frame_via_render_engine(self):
        from app.services.render_engine import detect_bad_first_frame
        assert callable(detect_bad_first_frame)

    def test_detect_silence_segments_via_render_engine(self):
        from app.services.render_engine import _detect_silence_segments
        assert callable(_detect_silence_segments)

    def test_apply_micro_pacing_via_render_engine(self):
        from app.services.render_engine import apply_micro_pacing
        assert callable(apply_micro_pacing)


# ---------------------------------------------------------------------------
# Same-object identity — re-exports must be the same objects
# ---------------------------------------------------------------------------

class TestSameObjects:
    def test_cut_video_is_same_object(self):
        import app.services.render.clip_ops as co
        import app.services.render_engine as re_mod
        assert re_mod.cut_video is co.cut_video

    def test_detect_silence_trim_offset_is_same_object(self):
        import app.services.render.clip_ops as co
        import app.services.render_engine as re_mod
        assert re_mod.detect_silence_trim_offset is co.detect_silence_trim_offset

    def test_detect_bad_first_frame_is_same_object(self):
        import app.services.render.clip_ops as co
        import app.services.render_engine as re_mod
        assert re_mod.detect_bad_first_frame is co.detect_bad_first_frame

    def test_detect_silence_segments_is_same_object(self):
        import app.services.render.clip_ops as co
        import app.services.render_engine as re_mod
        assert re_mod._detect_silence_segments is co._detect_silence_segments

    def test_apply_micro_pacing_is_same_object(self):
        import app.services.render.clip_ops as co
        import app.services.render_engine as re_mod
        assert re_mod.apply_micro_pacing is co.apply_micro_pacing


# ---------------------------------------------------------------------------
# cut_video — command structure and stream-copy / re-encode paths
# ---------------------------------------------------------------------------

class TestCutVideo:
    def _make_ffmpeg_ok(self):
        """Patch _run_ffmpeg_with_retry to succeed silently."""
        return patch("app.services.render.clip_ops._run_ffmpeg_with_retry")

    def _make_probe(self, duration):
        return patch("app.services.render.clip_ops._probe_duration", return_value=duration)

    def test_stream_copy_path_used_when_duration_ok(self):
        """Stream-copy cmd is tried first; on success with good duration, function returns."""
        with self._make_ffmpeg_ok() as mock_run, \
             self._make_probe(10.0):
            from app.services.render.clip_ops import cut_video
            cut_video("in.mp4", "out.mp4", start_time=0.0, end_time=10.0)

        # Only one FFmpeg call — the stream-copy attempt
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "-c" in cmd
        copy_idx = cmd.index("-c")
        assert cmd[copy_idx + 1] == "copy"

    def test_accurate_cut_used_when_force_accurate_cut_true(self):
        """force_accurate_cut=True skips stream-copy and goes straight to re-encode."""
        with self._make_ffmpeg_ok() as mock_run, \
             self._make_probe(10.0):
            from app.services.render.clip_ops import cut_video
            cut_video("in.mp4", "out.mp4", start_time=0.0, end_time=10.0,
                      force_accurate_cut=True)

        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "libx264" in cmd

    def test_fallback_to_reencode_on_duration_mismatch(self):
        """When stream-copy duration is wrong, a second re-encode call is made."""
        # probe returns bad duration (0.0) — mismatch triggers re-encode
        with self._make_ffmpeg_ok() as mock_run, \
             self._make_probe(0.0):
            from app.services.render.clip_ops import cut_video
            cut_video("in.mp4", "out.mp4", start_time=0.0, end_time=10.0)

        assert mock_run.call_count == 2
        # Second call uses libx264 re-encode
        second_cmd = mock_run.call_args_list[1][0][0]
        assert "libx264" in second_cmd

    def test_output_path_in_command(self):
        with self._make_ffmpeg_ok(), self._make_probe(5.0):
            from app.services.render.clip_ops import cut_video
            with patch("app.services.render.clip_ops._run_ffmpeg_with_retry") as mock_run:
                patch("app.services.render.clip_ops._probe_duration", return_value=5.0).start()
                cut_video("source.mp4", "cut_output.mp4", 0.0, 5.0)
                patch.stopall()
                if mock_run.call_args:
                    cmd = mock_run.call_args[0][0]
                    assert "cut_output.mp4" in cmd

    def test_keyframe_drift_triggers_reencode(self):
        """When stream-copy output is >0.1s over intended, re-encode is triggered."""
        # intended=10s, probe returns 10.5s → drift=0.5s > 0.1 → re-encode
        with self._make_ffmpeg_ok() as mock_run, \
             self._make_probe(10.5):
            from app.services.render.clip_ops import cut_video
            cut_video("in.mp4", "out.mp4", start_time=0.0, end_time=10.0)

        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# detect_silence_trim_offset — returns float in [min_trim, max_trim]
# ---------------------------------------------------------------------------

class TestDetectSilenceTrimOffset:
    _STDERR_WITH_SILENCE = (
        "... silence_start: 0\n"
        "... silence_end: 0.65 | silence_duration: 0.65\n"
    )
    _STDERR_NO_SILENCE = "no silence here\n"

    def _run_result(self, stderr):
        m = MagicMock()
        m.stderr = stderr
        m.returncode = 0
        return m

    def test_returns_silence_end_within_bounds(self):
        from app.services.render.clip_ops import detect_silence_trim_offset
        with patch("subprocess.run", return_value=self._run_result(self._STDERR_WITH_SILENCE)):
            result = detect_silence_trim_offset("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.65)

    def test_returns_zero_when_no_silence(self):
        from app.services.render.clip_ops import detect_silence_trim_offset
        with patch("subprocess.run", return_value=self._run_result(self._STDERR_NO_SILENCE)):
            result = detect_silence_trim_offset("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.0)

    def test_clamped_to_max_trim(self):
        # silence_end=2.0 but max_trim=1.5 → clamped to 1.5
        stderr = "silence_end: 2.0 | silence_duration: 2.0\n"
        from app.services.render.clip_ops import detect_silence_trim_offset
        with patch("subprocess.run", return_value=self._run_result(stderr)):
            result = detect_silence_trim_offset("v.mp4", 0.0, 10.0, max_trim=1.5)
        assert result == pytest.approx(1.5)

    def test_returns_zero_when_below_min_trim(self):
        # silence_end=0.05, min_trim default=0.2 → below min → 0.0
        stderr = "silence_end: 0.05 | silence_duration: 0.05\n"
        from app.services.render.clip_ops import detect_silence_trim_offset
        with patch("subprocess.run", return_value=self._run_result(stderr)):
            result = detect_silence_trim_offset("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.0)

    def test_zero_on_subprocess_exception(self):
        from app.services.render.clip_ops import detect_silence_trim_offset
        with patch("subprocess.run", side_effect=OSError("no ffmpeg")):
            result = detect_silence_trim_offset("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# detect_bad_first_frame — black frame skip
# ---------------------------------------------------------------------------

class TestDetectBadFirstFrame:
    def _run_result(self, stderr):
        m = MagicMock()
        m.stderr = stderr
        m.returncode = 0
        return m

    def test_returns_shift_for_leading_black_frame(self):
        # black_start at 0 (≤0.08), black_end=0.5
        stderr = "[blackdetect @ 0x0] black_start:0 black_end:0.5 black_duration:0.5\n"
        from app.services.render.clip_ops import detect_bad_first_frame
        with patch("subprocess.run", return_value=self._run_result(stderr)):
            result = detect_bad_first_frame("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.5)

    def test_returns_zero_when_black_starts_late(self):
        # black_start=1.0 — not at the beginning
        stderr = "[blackdetect @ 0x0] black_start:1.0 black_end:1.5 black_duration:0.5\n"
        from app.services.render.clip_ops import detect_bad_first_frame
        with patch("subprocess.run", return_value=self._run_result(stderr)):
            result = detect_bad_first_frame("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.0)

    def test_returns_zero_when_no_black_frames(self):
        from app.services.render.clip_ops import detect_bad_first_frame
        with patch("subprocess.run", return_value=self._run_result("")):
            result = detect_bad_first_frame("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.0)

    def test_shift_clamped_to_max_shift_sec(self):
        # black_end=2.0 but max_shift_sec=1.0 → clamped to 1.0
        stderr = "[blackdetect @ 0x0] black_start:0 black_end:2.0 black_duration:2.0\n"
        from app.services.render.clip_ops import detect_bad_first_frame
        with patch("subprocess.run", return_value=self._run_result(stderr)):
            result = detect_bad_first_frame("v.mp4", 0.0, 10.0, max_shift_sec=1.0)
        assert result == pytest.approx(1.0)

    def test_returns_zero_on_subprocess_exception(self):
        from app.services.render.clip_ops import detect_bad_first_frame
        with patch("subprocess.run", side_effect=OSError("no ffmpeg")):
            result = detect_bad_first_frame("v.mp4", 0.0, 10.0)
        assert result == pytest.approx(0.0)

    def test_returns_zero_when_clip_too_short_to_scan(self):
        # clip_dur=0.5 → scan_dur=0.5-0.5=0.0 < 0.08 → returns 0.0 immediately
        from app.services.render.clip_ops import detect_bad_first_frame
        result = detect_bad_first_frame("v.mp4", 0.0, 0.5)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _detect_silence_segments — (start, end) pairs
# ---------------------------------------------------------------------------

class TestDetectSilenceSegments:
    _STDERR = (
        "silence_start: 1.0\n"
        "silence_end: 1.8 | silence_duration: 0.8\n"
        "silence_start: 3.5\n"
        "silence_end: 4.0 | silence_duration: 0.5\n"
    )

    def _run_result(self, stderr):
        m = MagicMock()
        m.stderr = stderr
        m.returncode = 0
        return m

    def test_parses_two_segments(self):
        from app.services.render.clip_ops import _detect_silence_segments
        with patch("subprocess.run", return_value=self._run_result(self._STDERR)):
            result = _detect_silence_segments("v.mp4")
        assert len(result) == 2
        assert result[0] == pytest.approx((1.0, 1.8))
        assert result[1] == pytest.approx((3.5, 4.0))

    def test_returns_empty_on_no_silence(self):
        from app.services.render.clip_ops import _detect_silence_segments
        with patch("subprocess.run", return_value=self._run_result("no silence\n")):
            result = _detect_silence_segments("v.mp4")
        assert result == []

    def test_returns_empty_on_exception(self):
        from app.services.render.clip_ops import _detect_silence_segments
        with patch("subprocess.run", side_effect=OSError("timeout")):
            result = _detect_silence_segments("v.mp4")
        assert result == []

    def test_cancel_event_short_circuits(self):
        """When _tls.cancel_event is set, returns [] without running subprocess."""
        from app.services.render.clip_ops import _detect_silence_segments
        import app.services.render.clip_ops as co_mod
        cancel_mock = MagicMock()
        cancel_mock.is_set.return_value = True
        with patch.object(co_mod._tls, "cancel_event", cancel_mock, create=True):
            with patch("subprocess.run") as mock_run:
                result = _detect_silence_segments("v.mp4")
        assert result == []
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# apply_micro_pacing — disabled/no-op and enabled paths
# ---------------------------------------------------------------------------

class TestApplyMicroPacing:
    _NO_OP = {"applied": False, "segments_trimmed": 0, "total_trim_ms": 0, "method": "audio"}

    def test_no_op_when_clip_too_short(self):
        from app.services.render.clip_ops import apply_micro_pacing
        with patch("app.services.render.clip_ops._probe_duration", return_value=3.0):
            result = apply_micro_pacing("in.mp4", "out.mp4", min_clip_dur=5.0)
        assert result == self._NO_OP

    def test_no_op_when_probe_returns_none(self):
        from app.services.render.clip_ops import apply_micro_pacing
        with patch("app.services.render.clip_ops._probe_duration", return_value=None):
            result = apply_micro_pacing("in.mp4", "out.mp4")
        assert result == self._NO_OP

    def test_no_op_when_no_silences(self):
        from app.services.render.clip_ops import apply_micro_pacing
        with patch("app.services.render.clip_ops._probe_duration", return_value=30.0), \
             patch("app.services.render.clip_ops._detect_silence_segments", return_value=[]):
            result = apply_micro_pacing("in.mp4", "out.mp4")
        assert result == self._NO_OP

    def test_applied_true_when_silences_trimmed(self):
        """With a 30s clip and a silence segment in the middle, applied=True."""
        from app.services.render.clip_ops import apply_micro_pacing
        silences = [(2.0, 2.8)]  # 0.8s silence → trim > 0.1s → qualifies
        with patch("app.services.render.clip_ops._probe_duration", return_value=30.0), \
             patch("app.services.render.clip_ops._detect_silence_segments", return_value=silences), \
             patch("app.services.render.clip_ops._has_audio_stream", return_value=True), \
             patch("app.services.render.clip_ops._run_ffmpeg_with_retry"):
            result = apply_micro_pacing("in.mp4", "out.mp4")
        assert result["applied"] is True
        assert result["segments_trimmed"] >= 1
        assert result["total_trim_ms"] > 0
        assert result["method"] == "audio"

    def test_filter_complex_contains_concat(self):
        """The filter_complex passed to FFmpeg must use concat."""
        from app.services.render.clip_ops import apply_micro_pacing
        silences = [(2.0, 2.8)]
        with patch("app.services.render.clip_ops._probe_duration", return_value=30.0), \
             patch("app.services.render.clip_ops._detect_silence_segments", return_value=silences), \
             patch("app.services.render.clip_ops._has_audio_stream", return_value=False), \
             patch("app.services.render.clip_ops._run_ffmpeg_with_retry") as mock_run:
            apply_micro_pacing("in.mp4", "out.mp4")
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        fc_idx = cmd.index("-filter_complex")
        fc_str = cmd[fc_idx + 1]
        assert "concat" in fc_str

    def test_no_audio_args_when_no_audio_stream(self):
        """When video-only source, no -c:a in output command."""
        from app.services.render.clip_ops import apply_micro_pacing
        silences = [(2.0, 2.8)]
        with patch("app.services.render.clip_ops._probe_duration", return_value=30.0), \
             patch("app.services.render.clip_ops._detect_silence_segments", return_value=silences), \
             patch("app.services.render.clip_ops._has_audio_stream", return_value=False), \
             patch("app.services.render.clip_ops._run_ffmpeg_with_retry") as mock_run:
            apply_micro_pacing("in.mp4", "out.mp4")
        cmd = mock_run.call_args[0][0]
        assert "-c:a" not in cmd

    def test_audio_args_present_when_has_audio(self):
        """When source has audio, -c:a aac is included."""
        from app.services.render.clip_ops import apply_micro_pacing
        silences = [(2.0, 2.8)]
        with patch("app.services.render.clip_ops._probe_duration", return_value=30.0), \
             patch("app.services.render.clip_ops._detect_silence_segments", return_value=silences), \
             patch("app.services.render.clip_ops._has_audio_stream", return_value=True), \
             patch("app.services.render.clip_ops._run_ffmpeg_with_retry") as mock_run:
            apply_micro_pacing("in.mp4", "out.mp4")
        cmd = mock_run.call_args[0][0]
        assert "-c:a" in cmd
        assert "aac" in cmd
