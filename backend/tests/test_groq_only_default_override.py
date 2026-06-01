"""Phase D tests — GROQ_ONLY_DEFAULT server-wide override on NEW jobs.

Verifies Sacred Contract 2 is preserved:
- Stored job replays (resume/retry) never silently flip groq_only_mode.
- Only NEW API requests can receive the default override.
- Explicit field value in request always wins over the env default.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.schemas import RenderRequest
from app.routes import render as render_route


def _minimal_payload(**overrides) -> RenderRequest:
    """RenderRequest with the smallest viable fields for create_render_job()."""
    base = dict(
        source_mode="local",
        source_video_path=r"C:\fake\source.mp4",
        channel_code="T1",
        output_dir=r"C:\fake\out",
    )
    base.update(overrides)
    return RenderRequest(**base)


class TestGroqOnlyDefaultOverride:
    def test_override_off_keeps_field_false_when_not_set(self):
        """GROQ_ONLY_DEFAULT=False, request omits field → payload stays False."""
        payload = _minimal_payload()
        assert "groq_only_mode" not in payload.model_fields_set
        assert payload.groq_only_mode is False

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", False), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_validate_text_layers_or_400"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.create_render_job(payload)

        mock_queue.assert_called_once()
        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is False

    def test_override_on_flips_field_when_not_set(self):
        """GROQ_ONLY_DEFAULT=True, request omits field → payload flips to True
        AND groq_analysis_enabled also auto-enabled to avoid hard-fail."""
        payload = _minimal_payload()
        assert "groq_only_mode" not in payload.model_fields_set
        assert "groq_analysis_enabled" not in payload.model_fields_set

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", True), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_validate_text_layers_or_400"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.create_render_job(payload)

        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is True
        assert forwarded.groq_analysis_enabled is True

    def test_override_on_respects_explicit_groq_analysis_disabled(self):
        """GROQ_ONLY_DEFAULT=True but request explicitly sets groq_analysis_enabled=False
        → respect explicit value (user will hit hard-fail in pipeline, as intended)."""
        payload = _minimal_payload(groq_analysis_enabled=False)

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", True), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_validate_text_layers_or_400"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.create_render_job(payload)

        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is True
        assert forwarded.groq_analysis_enabled is False

    def test_explicit_false_wins_over_env_default(self):
        """GROQ_ONLY_DEFAULT=True but request explicitly sets False → False wins."""
        payload = _minimal_payload(groq_only_mode=False)
        assert "groq_only_mode" in payload.model_fields_set

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", True), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_validate_text_layers_or_400"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.create_render_job(payload)

        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is False

    def test_explicit_true_is_preserved_when_env_off(self):
        """GROQ_ONLY_DEFAULT=False but request explicitly sets True → True stays."""
        payload = _minimal_payload(groq_only_mode=True)
        assert "groq_only_mode" in payload.model_fields_set

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", False), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_validate_text_layers_or_400"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.create_render_job(payload)

        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is True


class TestResumeRetryDoNotApplyOverride:
    """Sacred Contract 2 — stored job replays must never silently flip the field."""

    def test_resume_render_job_does_not_apply_default_override(self):
        """Resume path reconstructs RenderRequest from stored payload_json; override must NOT fire."""
        import json

        stored_payload = {
            "source_mode": "local",
            "source_video_path": r"C:\fake\source.mp4",
            "channel_code": "T1",
            "output_dir": r"C:\fake\out",
        }
        fake_row = {
            "job_id": "fake-job",
            "payload_json": json.dumps(stored_payload),
        }

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", True), \
             patch.object(render_route, "get_job", return_value=fake_row), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.resume_render_job("fake-job")

        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is False, (
            "Sacred Contract 2 violated: resume path silently flipped groq_only_mode"
        )

    def test_retry_failed_parts_does_not_apply_default_override(self):
        """Retry path reconstructs RenderRequest from stored payload_json; override must NOT fire."""
        import json

        stored_payload = {
            "source_mode": "local",
            "source_video_path": r"C:\fake\source.mp4",
            "channel_code": "T1",
            "output_dir": r"C:\fake\out",
        }
        fake_row = {
            "job_id": "fake-job",
            "status": "failed",
            "payload_json": json.dumps(stored_payload),
        }
        failed_part = {"status": "failed", "part_no": 1}

        with patch.object(render_route._cfg, "GROQ_ONLY_DEFAULT", True), \
             patch.object(render_route, "get_job", return_value=fake_row), \
             patch.object(render_route, "list_job_parts", return_value=[failed_part]), \
             patch.object(render_route, "_queue_render_job") as mock_queue, \
             patch.object(render_route, "_validate_render_source"), \
             patch.object(render_route, "_coerce_legacy_channel_payload"):
            render_route.retry_failed_parts("fake-job")

        forwarded = mock_queue.call_args.args[2]
        assert forwarded.groq_only_mode is False, (
            "Sacred Contract 2 violated: retry path silently flipped groq_only_mode"
        )
