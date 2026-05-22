"""
test_asset_pipeline.py — Unit tests for Phase 4B extraction.

Coverage:
- Import from new module location works
- Backward-compat import from render_pipeline works (same object)
- _maybe_prepend_remotion_hook_intro: returns 0.0 when flag off, no generate_hook_intro call
- _maybe_prepend_asset_intro: returns None when no asset_intro_path configured
- _maybe_append_asset_outro: returns None when no asset_outro_path configured
- _maybe_apply_asset_logo: returns None when no asset_logo_path configured
- render_events shared helpers: _safe_unlink, _job_log, _emit_render_event import correctly
- _JOB_LOG_DIRS is the same dict object in both render_events and render_pipeline
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Section 1: Import correctness
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_asset_pipeline(self):
        from app.orchestration.asset_pipeline import (
            _maybe_append_asset_outro,
            _maybe_apply_asset_logo,
            _maybe_prepend_asset_intro,
            _maybe_prepend_remotion_hook_intro,
        )
        assert callable(_maybe_prepend_remotion_hook_intro)
        assert callable(_maybe_prepend_asset_intro)
        assert callable(_maybe_append_asset_outro)
        assert callable(_maybe_apply_asset_logo)

    def test_import_render_events(self):
        from app.orchestration.render_events import (
            _JOB_LOG_DIRS,
            _append_json_line,
            _emit_render_event,
            _job_log,
            _render_error_code,
            _safe_unlink,
        )
        assert isinstance(_JOB_LOG_DIRS, dict)
        assert callable(_safe_unlink)
        assert callable(_job_log)
        assert callable(_emit_render_event)
        assert callable(_append_json_line)
        assert callable(_render_error_code)


class TestBackwardCompatImport:
    def test_asset_functions_re_exported_from_render_pipeline(self):
        from app.orchestration.asset_pipeline import (
            _maybe_append_asset_outro,
            _maybe_apply_asset_logo,
            _maybe_prepend_asset_intro,
            _maybe_prepend_remotion_hook_intro,
        )
        from app.orchestration.render_pipeline import (
            _maybe_append_asset_outro as rp_outro,
            _maybe_apply_asset_logo as rp_logo,
            _maybe_prepend_asset_intro as rp_intro,
            _maybe_prepend_remotion_hook_intro as rp_hook,
        )
        assert rp_hook is _maybe_prepend_remotion_hook_intro
        assert rp_intro is _maybe_prepend_asset_intro
        assert rp_outro is _maybe_append_asset_outro
        assert rp_logo is _maybe_apply_asset_logo

    def test_render_events_helpers_re_exported_from_render_pipeline(self):
        from app.orchestration.render_events import (
            _emit_render_event,
            _job_log,
            _safe_unlink,
        )
        from app.orchestration.render_pipeline import (
            _emit_render_event as rp_emit,
            _job_log as rp_log,
            _safe_unlink as rp_unlink,
        )
        assert rp_log is _job_log
        assert rp_emit is _emit_render_event
        assert rp_unlink is _safe_unlink

    def test_job_log_dirs_is_same_object(self):
        from app.orchestration.render_events import _JOB_LOG_DIRS as ev_dirs
        from app.orchestration.render_pipeline import _JOB_LOG_DIRS as rp_dirs
        assert ev_dirs is rp_dirs, "_JOB_LOG_DIRS must be the same dict object in both modules"


# ---------------------------------------------------------------------------
# Section 2: _maybe_prepend_remotion_hook_intro behaviour
# ---------------------------------------------------------------------------

def _make_payload(**kwargs):
    payload = MagicMock()
    defaults = {
        "remotion_hook_intro": False,
        "intro_preset": "",
        "aspect_ratio": "3:4",
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(payload, k, v)
    payload.__class__.__name__ = "RenderRequest"

    def _getattr_side(name, default=None):
        return getattr(payload, name, default)

    return payload


class TestMaybePrependRemotionHookIntro:
    def test_returns_0_when_flag_off(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_remotion_hook_intro
        payload = _make_payload(remotion_hook_intro=False)
        result = _maybe_prepend_remotion_hook_intro(
            tmp_path / "part_001.mp4",
            payload,
            effective_channel="ch",
            job_id="job123",
            part_no=1,
        )
        assert result == 0.0

    def test_does_not_call_generate_hook_intro_when_disabled(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_remotion_hook_intro
        payload = _make_payload(remotion_hook_intro=False)
        with patch("app.orchestration.asset_pipeline.generate_hook_intro") as mock_gen:
            _maybe_prepend_remotion_hook_intro(
                tmp_path / "part_001.mp4",
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
            mock_gen.assert_not_called()

    def test_returns_0_when_generate_hook_intro_returns_none(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_remotion_hook_intro
        payload = _make_payload(remotion_hook_intro=True)
        with (
            patch("app.orchestration.asset_pipeline.generate_hook_intro", return_value=None),
            patch("app.orchestration.asset_pipeline.resolve_intro_preset", return_value="viral_pop"),
            patch("app.orchestration.asset_pipeline._job_log"),
            patch("app.orchestration.asset_pipeline._safe_unlink"),
        ):
            result = _maybe_prepend_remotion_hook_intro(
                tmp_path / "part_001.mp4",
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert result == 0.0

    def test_returns_duration_on_success(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_remotion_hook_intro
        payload = _make_payload(remotion_hook_intro=True)
        final_part = tmp_path / "part_001.mp4"
        final_part.write_bytes(b"fake")
        concat_out = str(tmp_path / "part_001.with_intro.mp4")

        with (
            patch("app.orchestration.asset_pipeline.generate_hook_intro", return_value="/fake/intro.mp4"),
            patch("app.orchestration.asset_pipeline.prepend_intro_clip", return_value=concat_out),
            patch("app.orchestration.asset_pipeline.resolve_intro_preset", return_value="viral_pop"),
            patch("app.orchestration.asset_pipeline._job_log"),
            patch("app.orchestration.asset_pipeline._safe_unlink"),
            patch("os.replace"),
        ):
            result = _maybe_prepend_remotion_hook_intro(
                final_part,
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert result == 1.0  # viral_pop preset → 1.0s


# ---------------------------------------------------------------------------
# Section 3: _maybe_prepend_asset_intro behaviour
# ---------------------------------------------------------------------------

class TestMaybePrependAssetIntro:
    def test_returns_none_when_no_path_configured(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_asset_intro
        payload = MagicMock()
        payload.asset_intro_path = ""
        result = _maybe_prepend_asset_intro(
            tmp_path / "part_001.mp4",
            payload,
            effective_channel="ch",
            job_id="job123",
            part_no=1,
        )
        assert result is None

    def test_returns_none_when_path_attribute_absent(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_asset_intro
        payload = MagicMock(spec=[])  # no attributes
        result = _maybe_prepend_asset_intro(
            tmp_path / "part_001.mp4",
            payload,
            effective_channel="ch",
            job_id="job123",
            part_no=1,
        )
        assert result is None

    def test_logs_warning_when_file_missing(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_asset_intro
        payload = MagicMock()
        payload.asset_intro_path = "/nonexistent/intro.mp4"
        with (
            patch("app.orchestration.asset_pipeline._job_log") as mock_log,
            patch("app.orchestration.asset_pipeline._emit_render_event"),
        ):
            _maybe_prepend_asset_intro(
                tmp_path / "part_001.mp4",
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert any("asset_missing_skip" in str(call) for call in mock_log.call_args_list)

    def test_applies_intro_when_file_exists(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_prepend_asset_intro
        intro_file = tmp_path / "intro.mp4"
        intro_file.write_bytes(b"fake")
        final_part = tmp_path / "part_001.mp4"
        final_part.write_bytes(b"fake")
        concat_out = str(tmp_path / "part_001.with_asset_intro.mp4")
        payload = MagicMock()
        payload.asset_intro_path = str(intro_file)
        with (
            patch("app.orchestration.asset_pipeline.prepend_intro_clip", return_value=concat_out),
            patch("app.orchestration.asset_pipeline._job_log") as mock_log,
            patch("app.orchestration.asset_pipeline._emit_render_event"),
            patch("app.orchestration.asset_pipeline._safe_unlink"),
            patch("os.replace"),
        ):
            _maybe_prepend_asset_intro(
                final_part,
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert any("asset_applied" in str(call) for call in mock_log.call_args_list)


# ---------------------------------------------------------------------------
# Section 4: _maybe_append_asset_outro behaviour
# ---------------------------------------------------------------------------

class TestMaybeAppendAssetOutro:
    def test_returns_none_when_no_path_configured(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_append_asset_outro
        payload = MagicMock()
        payload.asset_outro_path = ""
        result = _maybe_append_asset_outro(
            tmp_path / "part_001.mp4",
            payload,
            effective_channel="ch",
            job_id="job123",
            part_no=1,
        )
        assert result is None

    def test_logs_warning_when_file_missing(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_append_asset_outro
        payload = MagicMock()
        payload.asset_outro_path = "/nonexistent/outro.mp4"
        with (
            patch("app.orchestration.asset_pipeline._job_log") as mock_log,
            patch("app.orchestration.asset_pipeline._emit_render_event"),
        ):
            _maybe_append_asset_outro(
                tmp_path / "part_001.mp4",
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert any("asset_missing_skip" in str(call) for call in mock_log.call_args_list)


# ---------------------------------------------------------------------------
# Section 5: _maybe_apply_asset_logo behaviour
# ---------------------------------------------------------------------------

class TestMaybeApplyAssetLogo:
    def test_returns_none_when_no_path_configured(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_apply_asset_logo
        payload = MagicMock()
        payload.asset_logo_path = ""
        result = _maybe_apply_asset_logo(
            tmp_path / "part_001.mp4",
            payload,
            effective_channel="ch",
            job_id="job123",
            part_no=1,
        )
        assert result is None

    def test_logs_warning_when_file_missing(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_apply_asset_logo
        payload = MagicMock()
        payload.asset_logo_path = "/nonexistent/logo.png"
        with (
            patch("app.orchestration.asset_pipeline._job_log") as mock_log,
            patch("app.orchestration.asset_pipeline._emit_render_event"),
        ):
            _maybe_apply_asset_logo(
                tmp_path / "part_001.mp4",
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert any("asset_missing_skip" in str(call) for call in mock_log.call_args_list)

    def test_applies_logo_when_file_exists(self, tmp_path):
        from app.orchestration.asset_pipeline import _maybe_apply_asset_logo
        logo_file = tmp_path / "logo.png"
        logo_file.write_bytes(b"fake")
        final_part = tmp_path / "part_001.mp4"
        final_part.write_bytes(b"fake")
        watermarked_out = str(tmp_path / "part_001.with_logo.mp4")
        payload = MagicMock()
        payload.asset_logo_path = str(logo_file)
        with (
            patch("app.orchestration.asset_pipeline.apply_logo_watermark", return_value=watermarked_out),
            patch("app.orchestration.asset_pipeline._job_log") as mock_log,
            patch("app.orchestration.asset_pipeline._emit_render_event"),
            patch("app.orchestration.asset_pipeline._safe_unlink"),
            patch("os.replace"),
        ):
            _maybe_apply_asset_logo(
                final_part,
                payload,
                effective_channel="ch",
                job_id="job123",
                part_no=1,
            )
        assert any("asset_applied" in str(call) for call in mock_log.call_args_list)


# ---------------------------------------------------------------------------
# Section 6: render_events helpers
# ---------------------------------------------------------------------------

class TestRenderEventsHelpers:
    def test_safe_unlink_suppresses_error(self, tmp_path):
        from app.orchestration.render_events import _safe_unlink
        nonexistent = tmp_path / "ghost.mp4"
        _safe_unlink(nonexistent)  # must not raise

    def test_safe_unlink_removes_existing_file(self, tmp_path):
        from app.orchestration.render_events import _safe_unlink
        f = tmp_path / "to_delete.mp4"
        f.write_bytes(b"x")
        _safe_unlink(f)
        assert not f.exists()

    def test_render_error_code_ffmpeg(self):
        from app.orchestration.render_events import _render_error_code
        assert _render_error_code("encode", "ffmpeg failed") == "RN004"

    def test_render_error_code_not_found(self):
        from app.orchestration.render_events import _render_error_code
        assert _render_error_code("cut", "file not found") == "RN002"

    def test_render_error_code_default(self):
        from app.orchestration.render_events import _render_error_code
        assert _render_error_code("unknown", "some error") == "RN001"
