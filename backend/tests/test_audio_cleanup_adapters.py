from __future__ import annotations

import importlib
import sys

import pytest
from pydantic import ValidationError


def test_render_request_default_audio_cleanup_engine_none():
    from app.models.schemas import RenderRequest

    payload = RenderRequest()

    assert payload.audio_cleanup_engine == "none"


def test_render_request_accepts_deepfilternet_engine():
    from app.models.schemas import RenderRequest

    payload = RenderRequest(audio_cleanup_engine="deepfilternet")

    assert payload.audio_cleanup_engine == "deepfilternet"


def test_render_request_rejects_invalid_audio_cleanup_engine():
    from app.models.schemas import RenderRequest

    with pytest.raises(ValidationError):
        RenderRequest(audio_cleanup_engine="invalid")


def test_importing_audio_cleanup_adapters_does_not_import_ml_packages():
    for name in (
        "deepfilternet",
        "torch",
        "torchaudio",
        "app.services.audio_cleanup_adapters",
    ):
        sys.modules.pop(name, None)

    importlib.import_module("app.services.audio_cleanup_adapters")

    assert "deepfilternet" not in sys.modules
    assert "torch" not in sys.modules
    assert "torchaudio" not in sys.modules


def test_cleanup_audio_none_returns_noop_result(tmp_path):
    from app.services.audio_cleanup_adapters import cleanup_audio_with_adapter

    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "clean.wav"
    input_path.write_bytes(b"original-audio")

    result = cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="none",
    )

    assert result.input_path == str(input_path)
    assert result.output_path == str(input_path)
    assert result.engine == "none"
    assert result.applied is False
    assert result.warnings == []
    assert input_path.read_bytes() == b"original-audio"
    assert not output_path.exists()


def test_cleanup_audio_deepfilternet_unavailable_falls_back_to_noop(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: False)
    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "clean.wav"
    input_path.write_bytes(b"original-audio")

    result = adapters.cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="deepfilternet",
    )

    assert result.input_path == str(input_path)
    assert result.output_path == str(input_path)
    assert result.engine == "none"
    assert result.applied is False
    assert result.warnings == [
        "deepfilternet_unavailable",
        "deepfilternet_adapter_not_implemented",
    ]
    assert input_path.read_bytes() == b"original-audio"
    assert not output_path.exists()


def test_cleanup_audio_deepfilternet_available_placeholder_is_noop(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: True)
    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "clean.wav"
    input_path.write_bytes(b"original-audio")

    result = adapters.cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="deepfilternet",
    )

    assert result.engine == "none"
    assert result.applied is False
    assert result.warnings == ["deepfilternet_adapter_not_implemented"]
    assert input_path.read_bytes() == b"original-audio"
    assert not output_path.exists()
