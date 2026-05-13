from __future__ import annotations

import importlib
import sys
import types
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


def test_transcribe_with_adapter_whisperx_runtime_failure_falls_back_to_default(monkeypatch, tmp_path):
    import app.services.subtitle_transcription_adapters as adapters

    monkeypatch.setattr(adapters, "has_whisperx", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        types.SimpleNamespace(
            load_model=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        ),
    )

    output_srt = tmp_path / "output.srt"

    def fake_default_transcribe(video_path, readable_srt_path, **kwargs):
        assert readable_srt_path == str(output_srt)
        output_srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nfallback\n\n",
            encoding="utf-8",
        )

    with patch("app.services.subtitle_transcription_adapters.transcribe_to_srt") as transcribe:
        transcribe.side_effect = fake_default_transcribe
        result = adapters.transcribe_with_adapter(
            "input.mp4",
            str(output_srt),
            engine="whisperx",
            model_name="base",
            retry_count=2,
            highlight_per_word=False,
        )

    transcribe.assert_called_once()
    assert result.engine == "default"
    assert result.word_srt_path is None
    assert "whisperx_runtime_error:RuntimeError" in result.warnings
    assert output_srt.exists()
    assert "fallback" in output_srt.read_text(encoding="utf-8")


def test_transcribe_with_adapter_whisperx_success_writes_word_level_srt(monkeypatch, tmp_path):
    import app.services.subtitle_transcription_adapters as adapters
    from app.services.subtitle_engine import parse_srt_blocks

    class FakeWhisperXModel:
        def transcribe(self, audio, batch_size):
            return {
                "language": "en",
                "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
            }

    def fake_align(segments, model_a, metadata, audio, device, return_char_alignments):
        return {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello world",
                    "words": [
                        {"word": "hello", "start": 0.1, "end": 0.4},
                        {"word": "world", "start": 0.5, "end": 0.9},
                    ],
                }
            ]
        }

    monkeypatch.setattr(adapters, "has_whisperx", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        types.SimpleNamespace(
            load_model=lambda *args, **kwargs: FakeWhisperXModel(),
            load_audio=lambda video_path: "audio",
            load_align_model=lambda language_code, device: (
                "align-model",
                {"language": language_code},
            ),
            align=fake_align,
        ),
    )

    output_srt = tmp_path / "output.srt"
    with patch("app.services.subtitle_transcription_adapters.transcribe_to_srt") as transcribe:
        result = adapters.transcribe_with_adapter(
            "input.mp4",
            str(output_srt),
            engine="whisperx",
            model_name="base",
            retry_count=2,
            highlight_per_word=True,
        )

    transcribe.assert_not_called()
    assert result.engine == "whisperx"
    assert result.aligned is True
    assert result.word_srt_path is None
    assert output_srt.exists()

    blocks = parse_srt_blocks(str(output_srt))
    assert [block["text"] for block in blocks] == ["hello", "world"]
    assert blocks[0]["start"] == pytest.approx(0.1)
    assert blocks[1]["end"] == pytest.approx(0.9)


def test_whisperx_word_timing_normalizes_ultra_short_duration(tmp_path):
    from app.services.subtitle_engine import parse_srt_blocks
    from app.services.subtitle_transcription_adapters import _write_whisperx_srt

    output_srt = tmp_path / "output.srt"
    _write_whisperx_srt(
        {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "a test",
                    "words": [
                        {"word": "a", "start": 0.10, "end": 0.12},
                        {"word": "test", "start": 0.30, "end": 0.60},
                    ],
                }
            ]
        },
        str(output_srt),
        word_level=True,
    )

    blocks = parse_srt_blocks(str(output_srt))
    assert blocks[0]["text"] == "a"
    assert blocks[0]["end"] - blocks[0]["start"] >= 0.099


def test_whisperx_word_timing_repairs_overlapping_words(tmp_path):
    from app.services.subtitle_engine import parse_srt_blocks
    from app.services.subtitle_transcription_adapters import _write_whisperx_srt

    output_srt = tmp_path / "output.srt"
    _write_whisperx_srt(
        {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello world",
                    "words": [
                        {"word": "hello", "start": 0.10, "end": 0.35},
                        {"word": "world", "start": 0.20, "end": 0.50},
                    ],
                }
            ]
        },
        str(output_srt),
        word_level=True,
    )

    blocks = parse_srt_blocks(str(output_srt))
    assert [block["text"] for block in blocks] == ["hello", "world"]
    assert blocks[1]["start"] >= blocks[0]["end"] + 0.009


def test_whisperx_word_timing_drops_punctuation_only_fragments(tmp_path):
    from app.services.subtitle_engine import parse_srt_blocks
    from app.services.subtitle_transcription_adapters import _write_whisperx_srt

    output_srt = tmp_path / "output.srt"
    _write_whisperx_srt(
        {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "wait",
                    "words": [
                        {"word": "!!!", "start": 0.10, "end": 0.20},
                        {"word": "wait", "start": 0.30, "end": 0.60},
                    ],
                }
            ]
        },
        str(output_srt),
        word_level=True,
    )

    blocks = parse_srt_blocks(str(output_srt))
    assert [block["text"] for block in blocks] == ["wait"]


def test_whisperx_invalid_word_timing_falls_back_to_segment_level(tmp_path):
    from app.services.subtitle_engine import parse_srt_blocks
    from app.services.subtitle_transcription_adapters import _write_whisperx_srt

    output_srt = tmp_path / "output.srt"
    _write_whisperx_srt(
        {
            "segments": [
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "segment fallback",
                    "words": [
                        {"word": "bad", "start": 1.20, "end": 1.10},
                        {"word": "also bad", "start": None, "end": 1.80},
                    ],
                }
            ]
        },
        str(output_srt),
        word_level=True,
    )

    blocks = parse_srt_blocks(str(output_srt))
    assert len(blocks) == 1
    assert blocks[0]["text"] == "segment fallback"
    assert blocks[0]["start"] == pytest.approx(1.0)
    assert blocks[0]["end"] == pytest.approx(2.0)
