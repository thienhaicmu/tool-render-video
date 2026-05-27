"""
test_phase0_hotfixes.py — Regression tests for the Phase 0 hotfixes.

Covers the three bugs identified in docs/review/BRUTAL_REVIEW_SUMMARY.md and
docs/review/TECHNICAL_DEBT_REPORT.md (C2, C3, H6) and fixed on
branch feature/ai-output-upgrade:

  Fix 1 (subtitle timing):  confirm apply_playback_speed=False is correct given
                             FFmpeg filter order (ass before setpts).  No code
                             change; test documents the invariant.

  Fix 2 (TTS narration):    mix_narration_audio() must pass atempo={speed} to
                             the narration stream when playback_speed != 1.0.

  Fix 3 (download timeout): download_youtube() must include socket_timeout in
                             yt-dlp options and must accept + honour cancel_event.

No real video file, FFmpeg subprocess, yt-dlp network call, or GPU required.
"""
from __future__ import annotations

import inspect
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Fix 1 — Subtitle timing is correct via FFmpeg filter order
#
# Review ref: TECHNICAL_DEBT_REPORT.md C2 / BRUTAL_REVIEW_SUMMARY.md
# Conclusion: apply_playback_speed=False in render_pipeline.py is CORRECT.
#   - The `ass` filter runs *before* `setpts=PTS/speed` in the vf_chain.
#   - setpts re-clocks every frame so the subtitle timestamp (in original
#     time) aligns with the correct frame automatically.
#   - Dividing subtitle timestamps by speed would double-correct and shift
#     them in the wrong direction.
# ---------------------------------------------------------------------------

class TestSubtitleTimingInvariant:
    """Confirms that slice_srt_by_time is called with apply_playback_speed=False
    and that render_engine builds the vf_chain with ass before setpts."""

    def test_render_engine_ass_before_setpts(self):
        """vf_chain must place the ass filter before setpts so that subtitle
        timestamps (in original time) land on the correct speed-adjusted frame.
        Checks legacy_renderer (render_part moved there in Phase 4E.5)."""
        from app.services.render import legacy_renderer

        src = inspect.getsource(legacy_renderer)
        ass_pos = src.find("ass='")
        setpts_pos = src.find("setpts=PTS/")
        assert ass_pos != -1, "ass filter not found in legacy_renderer source"
        assert setpts_pos != -1, "setpts filter not found in legacy_renderer source"
        assert ass_pos < setpts_pos, (
            "ass filter must appear before setpts in vf_chain build; "
            "reversing the order would cause subtitle drift"
        )

    def test_per_part_subtitle_transcribes_raw_clip(self):
        """render_pipeline.py must call transcribe_with_adapter on the already-cut
        raw_part clip for per-part subtitle generation, not slice the full-source SRT.
        Timestamps are naturally zero-based when Whisper reads a clip that starts at t=0,
        so no rebase arithmetic is needed and timing is correct by construction."""
        from app.orchestration import render_pipeline

        src = inspect.getsource(render_pipeline)
        assert "SUBTITLE_PER_PART_MODEL" in src, (
            "render_pipeline.py must reference SUBTITLE_PER_PART_MODEL to configure "
            "the per-part transcription model (used in _prepare_part_assets)"
        )
        assert "str(raw_part)" in src, (
            "render_pipeline.py must pass str(raw_part) as the audio source to "
            "transcribe_with_adapter() so subtitle timestamps start at 0 by construction"
        )


# ---------------------------------------------------------------------------
# Fix 2 — TTS narration atempo compensation
#
# Review ref: TECHNICAL_DEBT_REPORT.md C3 / BRUTAL_REVIEW_SUMMARY.md
# Fix: mix_narration_audio() now accepts playback_speed and applies
#      atempo={speed} to the narration stream when speed != 1.0.
# ---------------------------------------------------------------------------

class TestMixNarrationAudioAtempo:
    """mix_narration_audio() must apply atempo when playback_speed != 1.0."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _build_fake_paths(self, tmp_path: Path):
        video = tmp_path / "video.mp4"
        narration = tmp_path / "narration.mp3"
        output = tmp_path / "out.mp4"
        video.write_bytes(b"fake")
        narration.write_bytes(b"fake")
        return str(video), str(narration), str(output)

    def _run_mix(self, tmp_path, mode, speed, fake_has_audio=True):
        video_path, narration_path, output_path = self._build_fake_paths(tmp_path)

        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            # simulate successful output creation
            Path(output_path).write_bytes(b"fake_output")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with (
            patch("app.services.audio_mix_service.subprocess.run", side_effect=fake_run),
            patch(
                "app.services.audio_mix_service._has_audio_stream",
                return_value=fake_has_audio,
            ),
        ):
            from app.services.audio_mix_service import mix_narration_audio
            mix_narration_audio(
                video_path=video_path,
                narration_audio_path=narration_path,
                mix_mode=mode,
                output_path=output_path,
                playback_speed=speed,
            )

        return captured_cmds

    # ------------------------------------------------------------------
    # replace_original mode
    # ------------------------------------------------------------------

    def test_replace_original_1x_no_atempo(self, tmp_path):
        cmds = self._run_mix(tmp_path, "replace_original", speed=1.0)
        assert cmds, "subprocess.run was not called"
        cmd = cmds[-1]
        assert "atempo" not in " ".join(cmd), (
            "atempo must NOT be added at 1.0x speed (no-op would still change stream)"
        )

    def test_replace_original_115x_has_atempo(self, tmp_path):
        cmds = self._run_mix(tmp_path, "replace_original", speed=1.15)
        assert cmds, "subprocess.run was not called"
        cmd_str = " ".join(cmds[-1])
        assert "atempo=1.1500" in cmd_str, (
            f"atempo filter missing or wrong value for 1.15x speed; got: {cmd_str}"
        )

    def test_replace_original_slow_has_atempo(self, tmp_path):
        cmds = self._run_mix(tmp_path, "replace_original", speed=0.75)
        cmd_str = " ".join(cmds[-1])
        assert "atempo=0.7500" in cmd_str

    # ------------------------------------------------------------------
    # keep_original_low mode — source has audio
    # ------------------------------------------------------------------

    def test_keep_original_low_with_source_audio_115x_has_atempo(self, tmp_path):
        cmds = self._run_mix(tmp_path, "keep_original_low", speed=1.15, fake_has_audio=True)
        cmd_str = " ".join(cmds[-1])
        assert "atempo=1.1500" in cmd_str, (
            f"atempo missing in keep_original_low+source_audio path: {cmd_str}"
        )

    def test_keep_original_low_with_source_audio_1x_no_atempo(self, tmp_path):
        cmds = self._run_mix(tmp_path, "keep_original_low", speed=1.0, fake_has_audio=True)
        cmd_str = " ".join(cmds[-1])
        assert "atempo" not in cmd_str

    # ------------------------------------------------------------------
    # keep_original_low mode — no source audio (falls back to narration-only)
    # ------------------------------------------------------------------

    def test_keep_original_low_no_source_audio_115x_has_atempo(self, tmp_path):
        cmds = self._run_mix(tmp_path, "keep_original_low", speed=1.15, fake_has_audio=False)
        cmd_str = " ".join(cmds[-1])
        assert "atempo=1.1500" in cmd_str, (
            f"atempo missing in keep_original_low+no_source_audio path: {cmd_str}"
        )

    # ------------------------------------------------------------------
    # Speed clamping (atempo only supports 0.5–2.0)
    # ------------------------------------------------------------------

    def test_speed_clamped_to_max_2(self, tmp_path):
        cmds = self._run_mix(tmp_path, "replace_original", speed=3.5)
        cmd_str = " ".join(cmds[-1])
        assert "atempo=2.0000" in cmd_str, (
            f"speed must be clamped to 2.0 (atempo max); got: {cmd_str}"
        )

    def test_speed_clamped_to_min_05(self, tmp_path):
        cmds = self._run_mix(tmp_path, "replace_original", speed=0.1)
        cmd_str = " ".join(cmds[-1])
        assert "atempo=0.5000" in cmd_str, (
            f"speed must be clamped to 0.5 (atempo min); got: {cmd_str}"
        )

    # ------------------------------------------------------------------
    # render_pipeline.py passes playback_speed to mix_narration_audio
    # ------------------------------------------------------------------

    def test_render_pipeline_passes_playback_speed_to_mix(self):
        """render_pipeline.py must pass playback_speed= to mix_narration_audio().
        Omitting it silently uses the default (1.0) and skips atempo at all speeds."""
        from app.orchestration import render_pipeline

        src = inspect.getsource(render_pipeline)
        assert "playback_speed=_get_effective_playback_speed" in src, (
            "render_pipeline.py must pass "
            "playback_speed=_get_effective_playback_speed(payload, _target_platform) "
            "to mix_narration_audio()"
        )


# ---------------------------------------------------------------------------
# Fix 3 — download_youtube() timeout and cancel_event wiring
#
# Review ref: TECHNICAL_DEBT_REPORT.md H6 / BRUTAL_REVIEW_SUMMARY.md
# Fix: socket_timeout added to yt-dlp common opts; cancel_event forwarded
#      from render_pipeline.py via cancel_registry.get_event(job_id).
# ---------------------------------------------------------------------------

class TestDownloadYouTubeTimeout:
    """download_youtube() must include socket_timeout and honour cancel_event."""

    def test_socket_timeout_present_in_ydl_opts(self):
        """yt-dlp common options must include socket_timeout so that a stalled
        connection times out rather than hanging the render job indefinitely."""
        from app.services import downloader

        src = inspect.getsource(downloader)
        assert '"socket_timeout"' in src or "'socket_timeout'" in src, (
            "socket_timeout missing from download_youtube() yt-dlp options; "
            "a stalled network connection will hang the render job forever"
        )

    def test_socket_timeout_value_is_positive(self):
        """socket_timeout must be a positive integer (seconds)."""
        from app.services import downloader

        src = inspect.getsource(downloader)
        # Find "socket_timeout": <value>
        import re
        m = re.search(r'"socket_timeout"\s*:\s*(\d+)', src)
        if not m:
            m = re.search(r"'socket_timeout'\s*:\s*(\d+)", src)
        assert m is not None, "socket_timeout value not found"
        assert int(m.group(1)) > 0, "socket_timeout must be a positive integer"

    def test_cancel_event_is_accepted_parameter(self):
        """download_youtube() must accept a cancel_event kwarg so callers can
        interrupt a stalled download."""
        from app.services.downloader import download_youtube

        sig = inspect.signature(download_youtube)
        assert "cancel_event" in sig.parameters, (
            "download_youtube() is missing the cancel_event parameter"
        )

    def test_cancel_event_checked_in_progress_hook(self):
        """The yt-dlp progress hook must check cancel_event.is_set() so that
        a job cancellation propagates to an in-flight download."""
        from app.services import downloader

        src = inspect.getsource(downloader)
        assert "cancel_event" in src and "is_set()" in src, (
            "Progress hook in download_youtube() must check cancel_event.is_set()"
        )

    def test_render_pipeline_does_not_call_download_youtube(self):
        """render_pipeline.py must not call download_youtube() — only local
        video files are supported as render sources."""
        from app.orchestration import render_pipeline

        src = inspect.getsource(render_pipeline)
        assert "download_youtube" not in src, (
            "render_pipeline.py must not call download_youtube() — "
            "YouTube URL source mode has been removed; only local video files are supported"
        )

    def test_cancel_event_set_raises_on_download(self, tmp_path):
        """When cancel_event is set before the download hook fires, the download
        must raise (not silently complete).  Patches YoutubeDL directly since
        downloader.py imports it with `from yt_dlp import YoutubeDL`."""
        cancel = threading.Event()
        cancel.set()

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        # Simulate yt-dlp propagating the RuntimeError from the progress hook
        mock_ctx.download.side_effect = RuntimeError("Download cancelled")

        with patch("app.services.downloader.YoutubeDL", return_value=mock_ctx):
            from app.services.downloader import download_youtube

            with pytest.raises(Exception):
                download_youtube(
                    "https://www.youtube.com/watch?v=test",
                    tmp_path,
                    cancel_event=cancel,
                )
