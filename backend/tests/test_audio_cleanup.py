"""
test_audio_cleanup.py — Unit tests for Phase 4D audio-cleanup helper.

Coverage:
- Import from new module location works
- Backward-compat import from render_pipeline works (same object)
- _maybe_cleanup_narration_audio: engine=none returns original path
- _maybe_cleanup_narration_audio: cleanup raises → original path, warning logged
- _maybe_cleanup_narration_audio: cleanup succeeds → cleaned path returned
- _maybe_cleanup_narration_audio: cleanup produces empty/missing file → original path
- Does not call real DeepFilterNet or FFmpeg
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Section 1: Import correctness
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_audio_pipeline(self):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        assert callable(_maybe_cleanup_narration_audio)


class TestBackwardCompatImport:
    def test_re_exported_from_render_pipeline(self):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio as rp_fn
        assert rp_fn is _maybe_cleanup_narration_audio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(engine="none"):
    payload = MagicMock()
    payload.audio_cleanup_engine = engine
    return payload


def _make_cleanup_result(applied=True, output_path=None, warnings=None, elapsed_ms=50):
    r = MagicMock()
    r.applied = applied
    r.output_path = output_path
    r.warnings = warnings or []
    r.elapsed_ms = elapsed_ms
    return r


# ---------------------------------------------------------------------------
# Section 2: _maybe_cleanup_narration_audio behaviour
# ---------------------------------------------------------------------------

class TestMaybeCleanupNarrationAudio:
    def test_returns_original_when_engine_none(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        payload = _make_payload(engine="none")
        with patch.dict("os.environ", {"AUDIO_CLEANUP_AUTO": "0"}):
            result = _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1",
            )
        assert result == narration

    def test_auto_upgrade_skipped_when_env_off(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        payload = _make_payload(engine="none")
        with (
            patch.dict("os.environ", {"AUDIO_CLEANUP_AUTO": "0"}),
            patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter") as mock_cleanup,
        ):
            result = _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1",
            )
        mock_cleanup.assert_not_called()
        assert result == narration

    def test_returns_original_when_cleanup_raises(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        Path(narration).write_bytes(b"audio")
        payload = _make_payload(engine="deepfilternet")
        with (
            patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
                  side_effect=RuntimeError("deepfilternet crashed")),
            patch("app.orchestration.audio_cleanup._job_log") as mock_log,
            patch("app.orchestration.audio_cleanup._safe_unlink"),
        ):
            result = _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1",
            )
        assert result == narration
        warning_calls = [str(c) for c in mock_log.call_args_list if "warning" in str(c)]
        assert len(warning_calls) >= 1

    def test_returns_cleaned_path_on_success(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        cleaned = str(tmp_path / "narration.cleaned.mp3")
        Path(narration).write_bytes(b"audio")
        Path(cleaned).write_bytes(b"clean audio")
        payload = _make_payload(engine="deepfilternet")
        mock_result = _make_cleanup_result(applied=True, output_path=cleaned)
        with (
            patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
                  return_value=mock_result),
            patch("app.orchestration.audio_cleanup._job_log"),
        ):
            result = _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1",
            )
        assert result == cleaned

    def test_returns_original_when_cleaned_file_missing(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        cleaned = str(tmp_path / "narration.cleaned.mp3")
        Path(narration).write_bytes(b"audio")
        # cleaned file does NOT exist
        payload = _make_payload(engine="deepfilternet")
        mock_result = _make_cleanup_result(applied=True, output_path=cleaned)
        with (
            patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
                  return_value=mock_result),
            patch("app.orchestration.audio_cleanup._job_log"),
            patch("app.orchestration.audio_cleanup._safe_unlink"),
        ):
            result = _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1",
            )
        assert result == narration

    def test_returns_original_when_not_applied(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        Path(narration).write_bytes(b"audio")
        payload = _make_payload(engine="deepfilternet")
        mock_result = _make_cleanup_result(applied=False, output_path=None,
                                           warnings=["no noise detected"])
        with (
            patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
                  return_value=mock_result),
            patch("app.orchestration.audio_cleanup._job_log"),
            patch("app.orchestration.audio_cleanup._safe_unlink"),
        ):
            result = _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1",
            )
        assert result == narration

    def test_part_no_included_in_log_context(self, tmp_path):
        from app.orchestration.audio_cleanup import _maybe_cleanup_narration_audio
        narration = str(tmp_path / "narration.mp3")
        Path(narration).write_bytes(b"audio")
        payload = _make_payload(engine="deepfilternet")
        mock_result = _make_cleanup_result(applied=False)
        with (
            patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
                  return_value=mock_result),
            patch("app.orchestration.audio_cleanup._job_log") as mock_log,
            patch("app.orchestration.audio_cleanup._safe_unlink"),
        ):
            _maybe_cleanup_narration_audio(
                narration, payload,
                effective_channel="ch", job_id="job1", part_no=3,
            )
        all_log_msgs = " ".join(str(c) for c in mock_log.call_args_list)
        assert "part_no=3" in all_log_msgs
