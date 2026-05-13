from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest
from pydantic import ValidationError


def test_render_request_default_subtitle_transcription_engine():
    from app.models.schemas import RenderRequest

    payload = RenderRequest()

    assert payload.subtitle_transcription_engine == "default"


def test_render_request_accepts_whisperx_engine():
    from app.models.schemas import RenderRequest

    payload = RenderRequest(subtitle_transcription_engine="whisperx")

    assert payload.subtitle_transcription_engine == "whisperx"


def test_render_request_rejects_invalid_subtitle_transcription_engine():
    from app.models.schemas import RenderRequest

    with pytest.raises(ValidationError):
        RenderRequest(subtitle_transcription_engine="invalid")


def test_importing_adapters_does_not_import_whisperx():
    sys.modules.pop("whisperx", None)
    sys.modules.pop("app.services.subtitle_transcription_adapters", None)

    importlib.import_module("app.services.subtitle_transcription_adapters")

    assert "whisperx" not in sys.modules


def test_default_whisper_adapter_calls_transcribe_to_srt_with_same_args():
    from app.services.subtitle_transcription_adapters import DefaultWhisperAdapter

    with patch("app.services.subtitle_transcription_adapters.transcribe_to_srt") as transcribe:
        result = DefaultWhisperAdapter().transcribe(
            "input.mp4",
            "output.srt",
            model_name="small",
            retry_count=3,
            highlight_per_word=True,
        )

    transcribe.assert_called_once_with(
        "input.mp4",
        "output.srt",
        model_name="small",
        retry_count=3,
        highlight_per_word=True,
    )
    assert result.readable_srt_path == "output.srt"
    assert result.word_srt_path is None
    assert result.engine == "default"
    assert result.aligned is False
    assert result.warnings == []


def test_transcribe_with_adapter_default_uses_default_adapter():
    from app.services.subtitle_transcription_adapters import transcribe_with_adapter

    with patch("app.services.subtitle_transcription_adapters.transcribe_to_srt") as transcribe:
        result = transcribe_with_adapter(
            "input.mp4",
            "output.srt",
            engine="default",
            model_name="base",
            retry_count=2,
            highlight_per_word=False,
        )

    transcribe.assert_called_once_with(
        "input.mp4",
        "output.srt",
        model_name="base",
        retry_count=2,
        highlight_per_word=False,
    )
    assert result.engine == "default"
    assert result.word_srt_path is None
    assert result.warnings == []


def test_transcribe_with_adapter_whisperx_unavailable_falls_back_to_default(monkeypatch):
    import app.services.subtitle_transcription_adapters as adapters

    monkeypatch.setattr(adapters, "has_whisperx", lambda: False)

    with patch("app.services.subtitle_transcription_adapters.transcribe_to_srt") as transcribe:
        result = adapters.transcribe_with_adapter(
            "input.mp4",
            "output.srt",
            engine="whisperx",
            model_name="base",
            retry_count=2,
            highlight_per_word=True,
        )

    transcribe.assert_called_once_with(
        "input.mp4",
        "output.srt",
        model_name="base",
        retry_count=2,
        highlight_per_word=True,
    )
    assert result.engine == "default"
    assert result.word_srt_path is None
    assert "whisperx_unavailable" in result.warnings


def test_transcribe_with_adapter_whisperx_placeholder_falls_back_to_default(monkeypatch):
    import app.services.subtitle_transcription_adapters as adapters

    monkeypatch.setattr(adapters, "has_whisperx", lambda: True)

    with patch("app.services.subtitle_transcription_adapters.transcribe_to_srt") as transcribe:
        result = adapters.transcribe_with_adapter(
            "input.mp4",
            "output.srt",
            engine="whisperx",
            model_name="base",
            retry_count=2,
            highlight_per_word=False,
        )

    transcribe.assert_called_once()
    assert result.engine == "default"
    assert result.word_srt_path is None
    assert "whisperx_adapter_not_implemented" in result.warnings
