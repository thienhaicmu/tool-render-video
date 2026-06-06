"""Tests for app.features.render.engine.subtitle.transcription.whisper."""
import threading
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Module-level constants and caches
# ---------------------------------------------------------------------------

from app.features.render.engine.subtitle.transcription.whisper import (
    _MODEL_CACHE,
    _MODEL_TRANSCRIBE_LOCKS,
    get_whisper_model,
    has_audio_stream,
)


def test_model_cache_is_dict():
    assert isinstance(_MODEL_CACHE, dict)


def test_model_transcribe_locks_is_dict():
    assert isinstance(_MODEL_TRANSCRIBE_LOCKS, dict)


# ---------------------------------------------------------------------------
# has_audio_stream — delegates to ffmpeg_helpers._has_audio_stream
# ---------------------------------------------------------------------------

def test_has_audio_stream_delegates_to_helpers():
    with patch(
        "app.features.render.engine.encoder.ffmpeg_helpers._has_audio_stream",
        return_value=True,
    ) as mock_fn:
        result = has_audio_stream("/fake/video.mp4")
    assert result is True
    mock_fn.assert_called_once_with("/fake/video.mp4")


def test_has_audio_stream_false_path():
    with patch(
        "app.features.render.engine.encoder.ffmpeg_helpers._has_audio_stream",
        return_value=False,
    ):
        assert has_audio_stream("/fake/video.mp4") is False


# ---------------------------------------------------------------------------
# get_whisper_model — lazy loader with cache
# ---------------------------------------------------------------------------

def test_get_whisper_model_caches_result():
    """Second call should return cached model, not re-load it."""
    mock_model = MagicMock()
    # Patch whisper.load_model so we don't touch real model files
    with patch("whisper.load_model", return_value=mock_model) as mock_load:
        # Clear cache for test isolation
        _MODEL_CACHE.clear()

        m1 = get_whisper_model("base")
        m2 = get_whisper_model("base")

        # load_model should only be called once (second is from cache)
        assert mock_load.call_count == 1
        assert m1 is m2


def test_get_whisper_model_different_names_load_separately():
    mock_base = MagicMock(name="base_model")
    mock_tiny = MagicMock(name="tiny_model")

    def _fake_load(name, **kwargs):
        return mock_base if name == "base" else mock_tiny

    with patch("whisper.load_model", side_effect=_fake_load):
        _MODEL_CACHE.clear()
        m_base = get_whisper_model("base")
        m_tiny = get_whisper_model("tiny")

    assert m_base is not m_tiny


def test_get_whisper_model_thread_safe_lock_acquired():
    """get_whisper_model uses _MODEL_CACHE_LOCK so parallel calls don't double-load."""
    mock_model = MagicMock()
    load_count = {"n": 0}

    def _slow_load(name, **kwargs):
        load_count["n"] += 1
        return mock_model

    with patch("whisper.load_model", side_effect=_slow_load):
        _MODEL_CACHE.clear()
        results = []

        def _call():
            results.append(get_whisper_model("base"))

        threads = [threading.Thread(target=_call) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # Should have loaded exactly once despite 5 concurrent calls
    assert load_count["n"] == 1
    assert all(r is mock_model for r in results)
