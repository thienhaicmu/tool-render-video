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
    assert result.warnings == ["deepfilternet_unavailable"]
    assert input_path.read_bytes() == b"original-audio"
    assert not output_path.exists()


def test_cleanup_audio_deepfilternet_import_failure_falls_back_to_noop(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: True)
    monkeypatch.setattr(adapters, "_load_deepfilternet_api", lambda: (_ for _ in ()).throw(ImportError("boom")))
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
    assert result.warnings == ["deepfilternet_import_failed"]
    assert input_path.read_bytes() == b"original-audio"
    assert not output_path.exists()


def test_cleanup_audio_deepfilternet_runtime_failure_falls_back_to_noop(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: True)
    monkeypatch.setattr(adapters, "_load_deepfilternet_api", lambda: {"init_df": lambda: ("model", object(), None)})
    monkeypatch.setattr(adapters, "_probe_audio_duration", lambda path: 1.0)
    monkeypatch.setattr(adapters, "_convert_audio_to_wav", lambda input_path, wav_path: (_ for _ in ()).throw(RuntimeError("boom")))
    input_path = tmp_path / "input.mp3"
    output_path = tmp_path / "clean.mp3"
    input_path.write_bytes(b"original-audio")

    result = adapters.cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="deepfilternet",
    )

    assert result.engine == "none"
    assert result.applied is False
    assert result.output_path == str(input_path)
    assert result.warnings == ["deepfilternet_runtime_failed"]
    assert input_path.read_bytes() == b"original-audio"
    assert not output_path.with_suffix(".wav").exists()


def test_cleanup_audio_deepfilternet_success_returns_cleaned_wav(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    class FakeState:
        def sr(self):
            return 48000

    input_path = tmp_path / "input.mp3"
    output_path = tmp_path / "clean.mp3"
    cleaned_wav = output_path.with_suffix(".wav")
    input_path.write_bytes(b"original-audio")

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: True)
    monkeypatch.setattr(adapters, "_probe_audio_duration", lambda path: 1.0)

    def fake_convert(_input_path, wav_path):
        assert _input_path == str(input_path)
        PathLike = type(input_path)
        PathLike(wav_path).write_bytes(b"wav")

    def fake_save_audio(path, audio, sample_rate):
        assert audio == "enhanced"
        assert sample_rate == 48000
        type(input_path)(path).write_bytes(b"cleaned")

    monkeypatch.setattr(adapters, "_convert_audio_to_wav", fake_convert)
    monkeypatch.setattr(
        adapters,
        "_load_deepfilternet_api",
        lambda: {
            "init_df": lambda: ("model", FakeState(), None),
            "load_audio": lambda path, sr: ("audio", sr),
            "enhance": lambda model, state, audio: "enhanced",
            "save_audio": fake_save_audio,
        },
    )

    result = adapters.cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="deepfilternet",
    )

    assert result.engine == "deepfilternet"
    assert result.applied is True
    assert result.output_path == str(cleaned_wav)
    assert cleaned_wav.read_bytes() == b"cleaned"
    assert input_path.read_bytes() == b"original-audio"
    assert not (tmp_path / "input.deepfilternet.input.wav").exists()


def test_cleanup_audio_deepfilternet_missing_output_falls_back(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    input_path = tmp_path / "input.mp3"
    output_path = tmp_path / "clean.mp3"
    input_path.write_bytes(b"original-audio")

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: True)
    monkeypatch.setattr(adapters, "_probe_audio_duration", lambda path: 1.0)
    monkeypatch.setattr(adapters, "_convert_audio_to_wav", lambda input_path, wav_path: type(output_path)(wav_path).write_bytes(b"wav"))
    monkeypatch.setattr(
        adapters,
        "_load_deepfilternet_api",
        lambda: {
            "init_df": lambda: ("model", object(), None),
            "load_audio": lambda path, sr: ("audio", sr),
            "enhance": lambda model, state, audio: "enhanced",
            "save_audio": lambda path, audio, sample_rate: None,
        },
    )

    result = adapters.cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="deepfilternet",
    )

    assert result.engine == "none"
    assert result.applied is False
    assert result.warnings == ["deepfilternet_output_invalid"]


def test_cleanup_audio_deepfilternet_duration_mismatch_falls_back(monkeypatch, tmp_path):
    import app.services.audio_cleanup_adapters as adapters

    input_path = tmp_path / "input.mp3"
    output_path = tmp_path / "clean.mp3"
    cleaned_wav = output_path.with_suffix(".wav")
    input_path.write_bytes(b"original-audio")

    monkeypatch.setattr(adapters, "has_deepfilternet", lambda: True)
    durations = iter([1.0, 1.5])
    monkeypatch.setattr(adapters, "_probe_audio_duration", lambda path: next(durations))
    monkeypatch.setattr(adapters, "_convert_audio_to_wav", lambda input_path, wav_path: type(output_path)(wav_path).write_bytes(b"wav"))
    monkeypatch.setattr(
        adapters,
        "_load_deepfilternet_api",
        lambda: {
            "init_df": lambda: ("model", object(), None),
            "load_audio": lambda path, sr: ("audio", sr),
            "enhance": lambda model, state, audio: "enhanced",
            "save_audio": lambda path, audio, sample_rate: type(output_path)(path).write_bytes(b"cleaned"),
        },
    )

    result = adapters.cleanup_audio_with_adapter(
        str(input_path),
        str(output_path),
        engine="deepfilternet",
    )

    assert result.engine == "none"
    assert result.applied is False
    assert result.warnings == ["deepfilternet_duration_mismatch"]
    assert not cleaned_wav.exists()


def test_duration_within_tolerance():
    from app.services.audio_cleanup_adapters import _duration_within_tolerance

    assert _duration_within_tolerance(10.0, 10.15) is True
    assert _duration_within_tolerance(10.0, 10.25) is False
    assert _duration_within_tolerance(1.0, 1.14) is True
    assert _duration_within_tolerance(1.0, 1.20) is False
