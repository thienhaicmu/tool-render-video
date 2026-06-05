from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.audio.cleanup_adapters import AudioCleanupResult


def test_narration_cleanup_none_uses_original_path(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio

    original = tmp_path / "part_001.mp3"
    original.write_bytes(b"narration")
    payload = RenderRequest(audio_cleanup_engine="none")

    with patch("app.orchestration.audio_cleanup.cleanup_audio_with_adapter") as cleanup:
        result = _maybe_cleanup_narration_audio(
            str(original),
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
            source="subtitle",
        )

    cleanup.assert_not_called()
    assert result == str(original)
    assert original.read_bytes() == b"narration"


def test_narration_cleanup_placeholder_falls_back_to_original(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio

    original = tmp_path / "part_001.mp3"
    original.write_bytes(b"narration")
    payload = RenderRequest(audio_cleanup_engine="deepfilternet")

    with patch("app.orchestration.audio_cleanup._job_log") as job_log, \
         patch(
             "app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
             return_value=AudioCleanupResult(
                 input_path=str(original),
                 output_path=str(original),
                 engine="none",
                 applied=False,
                 warnings=["deepfilternet_adapter_not_implemented"],
             ),
         ):
        result = _maybe_cleanup_narration_audio(
            str(original),
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
            source="subtitle",
        )

    assert result == str(original)
    assert original.read_bytes() == b"narration"
    assert any("audio_cleanup_failed" in call.args[2] for call in job_log.call_args_list)


def test_narration_cleanup_success_uses_cleaned_path(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio

    original = tmp_path / "part_001.mp3"
    cleaned = tmp_path / "part_001.cleaned.mp3"
    original.write_bytes(b"narration")
    cleaned.write_bytes(b"cleaned")
    payload = RenderRequest(audio_cleanup_engine="deepfilternet")

    with patch("app.orchestration.audio_cleanup._job_log") as job_log, \
         patch(
             "app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
             return_value=AudioCleanupResult(
                 input_path=str(original),
                 output_path=str(cleaned),
                 engine="deepfilternet",
                 applied=True,
             ),
         ):
        result = _maybe_cleanup_narration_audio(
            str(original),
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
            source="subtitle",
        )

    assert result == str(cleaned)
    assert original.read_bytes() == b"narration"
    assert cleaned.read_bytes() == b"cleaned"
    assert any("audio_cleanup_applied" in call.args[2] for call in job_log.call_args_list)


def test_narration_cleanup_invalid_output_falls_back_to_original(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio

    original = tmp_path / "part_001.mp3"
    cleaned = tmp_path / "part_001.cleaned.mp3"
    original.write_bytes(b"narration")
    cleaned.write_bytes(b"")
    payload = RenderRequest(audio_cleanup_engine="deepfilternet")

    with patch(
        "app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
        return_value=AudioCleanupResult(
            input_path=str(original),
            output_path=str(cleaned),
            engine="deepfilternet",
            applied=True,
        ),
    ), patch("app.orchestration.audio_cleanup._job_log"):
        result = _maybe_cleanup_narration_audio(
            str(original),
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
            source="subtitle",
        )

    assert result == str(original)
    assert original.read_bytes() == b"narration"
    assert not cleaned.exists()


def test_narration_cleanup_exception_falls_back_to_original(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio

    original = tmp_path / "part_001.mp3"
    original.write_bytes(b"narration")
    payload = RenderRequest(audio_cleanup_engine="deepfilternet")

    with patch(
        "app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
        side_effect=RuntimeError("cleanup failed"),
    ), patch("app.orchestration.audio_cleanup._job_log") as job_log:
        result = _maybe_cleanup_narration_audio(
            str(original),
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
            source="subtitle",
        )

    assert result == str(original)
    assert original.read_bytes() == b"narration"
    assert any("audio_cleanup_failed" in call.args[2] for call in job_log.call_args_list)


@pytest.mark.parametrize("source", ["manual", "subtitle", "translated_subtitle"])
def test_narration_cleanup_preserves_supported_voice_sources(source, tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_cleanup_narration_audio

    original = tmp_path / f"{source}.mp3"
    original.write_bytes(b"narration")
    payload = RenderRequest(audio_cleanup_engine="deepfilternet")

    with patch("app.orchestration.audio_cleanup._job_log") as job_log, \
         patch(
             "app.orchestration.audio_cleanup.cleanup_audio_with_adapter",
             return_value=AudioCleanupResult(
                 input_path=str(original),
                 output_path=str(original),
                 engine="none",
                 applied=False,
                 warnings=["deepfilternet_adapter_not_implemented"],
             ),
         ):
        result = _maybe_cleanup_narration_audio(
            str(original),
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=None if source == "manual" else 1,
            source=source,
        )

    assert result == str(original)
    assert any(f"source={source}" in call.args[2] for call in job_log.call_args_list)
