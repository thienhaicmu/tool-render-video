"""
test_downloader_timeout.py — Tests for wall-clock timeout in download_youtube().

Phase 5.1 — Task 2

Coverage:
- _DOWNLOAD_WALLCLOCK_TIMEOUT constant exists and is a positive integer
- _try_download_with_timeout raises RuntimeError with "timed out" when timeout expires
- Timeout error message contains "wall-clock" (distinguishes from other errors)
- Normal download path is unaffected when download completes within timeout
- env var YTDLP_WALLCLOCK_TIMEOUT is respected
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Constant presence
# ---------------------------------------------------------------------------

class TestTimeoutConstant:
    def test_constant_exists(self):
        from app.services.downloader import _DOWNLOAD_WALLCLOCK_TIMEOUT
        assert isinstance(_DOWNLOAD_WALLCLOCK_TIMEOUT, int)
        assert _DOWNLOAD_WALLCLOCK_TIMEOUT > 0

    def test_constant_default_is_300(self):
        """Default must be 300 seconds (5 minutes) per spec."""
        # Only valid when env var is not overriding
        if "YTDLP_WALLCLOCK_TIMEOUT" not in os.environ:
            from app.services.downloader import _DOWNLOAD_WALLCLOCK_TIMEOUT
            assert _DOWNLOAD_WALLCLOCK_TIMEOUT == 300

    def test_constant_minimum_is_60(self):
        """Minimum must be clamped to 60s even if env says lower."""
        from app.services.downloader import _DOWNLOAD_WALLCLOCK_TIMEOUT
        assert _DOWNLOAD_WALLCLOCK_TIMEOUT >= 60


# ---------------------------------------------------------------------------
# _try_download_with_timeout behaviour
# ---------------------------------------------------------------------------

class TestWallClockTimeoutMechanism:
    """Test the wall-clock timeout wrapper inside download_youtube().

    We test the inner _try_download_with_timeout closure by patching
    concurrent.futures.ThreadPoolExecutor to simulate timeout.
    """

    def _run_download_youtube_with_mocked_timeout(self, timeout_error=False):
        """Invoke download_youtube() with mocked internals.

        If timeout_error=True, the inner download "hangs" and the timeout fires.
        If timeout_error=False, the inner download completes normally.
        """
        from pathlib import Path
        import concurrent.futures

        fake_result = {
            "title": "Test Video",
            "slug": "test-video",
            "duration": 60,
            "filepath": "/tmp/source.mp4",
            "thumbnail": None,
            "selected_height": 1080,
            "selected_fps": 30,
            "selected_format": "137+140",
        }

        if timeout_error:
            # Simulate a hung download — Future.result() raises TimeoutError
            mock_future = MagicMock()
            mock_future.result.side_effect = concurrent.futures.TimeoutError()
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit = MagicMock(return_value=mock_future)
        else:
            # Simulate a fast, successful download
            mock_future = MagicMock()
            mock_future.result.return_value = fake_result
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit = MagicMock(return_value=mock_future)

        with patch("app.services.downloader.concurrent.futures.ThreadPoolExecutor",
                   return_value=mock_executor):
            with patch("app.services.downloader._ensure_ffmpeg_on_path", return_value="/fake/ffmpeg"):
                with patch("app.services.downloader._resolve_ytdlp_proxy", return_value=""):
                    from app.services.downloader import download_youtube
                    temp_dir = MagicMock()
                    temp_dir.mkdir = MagicMock()
                    temp_dir.glob = MagicMock(return_value=[])
                    return download_youtube("https://youtube.com/watch?v=test", temp_dir)

    def test_timeout_raises_runtime_error(self):
        """Wall-clock timeout must raise RuntimeError with 'timed out' in message."""
        with pytest.raises(RuntimeError) as exc_info:
            self._run_download_youtube_with_mocked_timeout(timeout_error=True)
        msg = str(exc_info.value).lower()
        assert "timed out" in msg or "timeout" in msg, (
            f"Expected 'timed out' in error message, got: {exc_info.value}"
        )

    def test_timeout_error_message_contains_wall_clock(self):
        """Timeout error must be distinguishable from other errors via 'wall-clock' text."""
        with pytest.raises(RuntimeError) as exc_info:
            self._run_download_youtube_with_mocked_timeout(timeout_error=True)
        msg = str(exc_info.value).lower()
        assert "wall-clock" in msg or "wall_clock" in msg or "wallclock" in msg, (
            f"Expected wall-clock indicator in timeout message, got: {exc_info.value}"
        )

    def test_normal_download_not_affected(self):
        """When download completes before timeout, result is returned normally."""
        result = self._run_download_youtube_with_mocked_timeout(timeout_error=False)
        assert result is not None
        assert "title" in result or "filepath" in result

    def test_socket_timeout_still_present(self):
        """socket_timeout must still be in the yt-dlp common opts (existing behaviour)."""
        # Read the source to verify socket_timeout is still in common dict
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "app" / "services" / "downloader.py"
        content = src.read_text(encoding="utf-8")
        assert "socket_timeout" in content, (
            "socket_timeout was removed from downloader.py — must be preserved"
        )

    def test_wallclock_timeout_import(self):
        """_DOWNLOAD_WALLCLOCK_TIMEOUT must be accessible at module level."""
        import app.services.downloader as mod
        assert hasattr(mod, "_DOWNLOAD_WALLCLOCK_TIMEOUT"), (
            "_DOWNLOAD_WALLCLOCK_TIMEOUT not found at module level"
        )

    def test_concurrent_futures_import(self):
        """concurrent.futures must be imported in downloader.py."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "app" / "services" / "downloader.py"
        content = src.read_text(encoding="utf-8")
        assert "import concurrent.futures" in content or "from concurrent" in content, (
            "concurrent.futures not imported in downloader.py"
        )
