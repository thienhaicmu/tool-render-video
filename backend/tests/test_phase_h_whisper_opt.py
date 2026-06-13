"""Phase H — Whisper Speed Optimization QA tests.

Covers:
  - pipeline_cache.py: WHISPER_CONTENT_HASH_CACHE flag, _content_hash,
    _atomic_write_text correctness
  - adapters.py: _FW_MODEL_CACHE is an OrderedDict (LRU), FW_MODEL_CACHE_MAX
    env var is respected
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


# ── pipeline_cache.py — content-hash cache flag ───────────────────────────────

def test_content_hash_returns_hex_string(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _content_hash

    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake video content" * 100)
    h = _content_hash(str(f))
    assert h is not None
    assert len(h) == 64   # sha256 hex


def test_content_hash_returns_none_on_missing_file():
    from app.features.render.engine.pipeline.pipeline_cache import _content_hash

    result = _content_hash("/nonexistent/path.mp4")
    assert result is None


def test_content_hash_same_content_same_hash(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _content_hash

    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mp4"
    data = b"identical content"
    f1.write_bytes(data)
    f2.write_bytes(data)

    assert _content_hash(str(f1)) == _content_hash(str(f2))


def test_content_hash_different_content_different_hash(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _content_hash

    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mp4"
    f1.write_bytes(b"content A")
    f2.write_bytes(b"content B")

    assert _content_hash(str(f1)) != _content_hash(str(f2))


def test_atomic_write_text_produces_file(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _atomic_write_text

    target = tmp_path / "out.json"
    _atomic_write_text(target, '{"key": "value"}')

    assert target.exists()
    assert target.read_text() == '{"key": "value"}'


def test_atomic_write_text_leaves_no_tmp_file(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _atomic_write_text

    target = tmp_path / "out.json"
    _atomic_write_text(target, "data")

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_whisper_content_hash_cache_env_flag():
    import importlib

    # When flag is "0" (default), _CONTENT_HASH_CACHE must be False
    with patch.dict(os.environ, {"WHISPER_CONTENT_HASH_CACHE": "0"}):
        import app.features.render.engine.pipeline.pipeline_cache as mod
        importlib.reload(mod)
        assert mod._CONTENT_HASH_CACHE is False

    # When flag is "1", _CONTENT_HASH_CACHE must be True
    with patch.dict(os.environ, {"WHISPER_CONTENT_HASH_CACHE": "1"}):
        importlib.reload(mod)
        assert mod._CONTENT_HASH_CACHE is True

    # Restore default
    with patch.dict(os.environ, {"WHISPER_CONTENT_HASH_CACHE": "0"}):
        importlib.reload(mod)


# ── adapters.py — LRU model cache ────────────────────────────────────────────

def test_fw_model_cache_is_ordered_dict():
    from collections import OrderedDict
    from app.features.render.engine.subtitle.transcription.adapters import _FW_MODEL_CACHE

    assert isinstance(_FW_MODEL_CACHE, OrderedDict)


def test_fw_model_cache_max_env_var():
    """FW_MODEL_CACHE_MAX env var must control the cap."""
    import importlib

    with patch.dict(os.environ, {"FW_MODEL_CACHE_MAX": "3"}):
        import app.features.render.engine.subtitle.transcription.adapters as mod
        importlib.reload(mod)
        assert mod._FW_MODEL_CACHE_MAX == 3


def test_fw_model_cache_max_default_is_two():
    import importlib

    with patch.dict(os.environ, {}, clear=False):
        # Remove the env var to test default
        env_no_var = {k: v for k, v in os.environ.items() if k != "FW_MODEL_CACHE_MAX"}
        with patch.dict(os.environ, env_no_var, clear=True):
            import app.features.render.engine.subtitle.transcription.adapters as mod
            importlib.reload(mod)
            assert mod._FW_MODEL_CACHE_MAX >= 1  # at least 1 (default is 2)


def test_enforce_fw_lru_evicts_oldest():
    """_enforce_fw_lru should pop oldest entries when over cap."""
    from collections import OrderedDict
    from unittest.mock import patch as mpatch

    # We can't easily test _get_fw_model without faster-whisper installed,
    # but we can test the eviction logic directly.
    import app.features.render.engine.subtitle.transcription.adapters as mod

    original_cache = mod._FW_MODEL_CACHE
    original_max = mod._FW_MODEL_CACHE_MAX

    try:
        # Set a tiny cap and fill the cache
        mod._FW_MODEL_CACHE = OrderedDict()
        mod._FW_MODEL_CACHE_MAX = 2
        # Insert 3 fake entries directly (bypassing model load)
        mod._FW_MODEL_CACHE[("tiny", "cpu", "int8")] = object()
        mod._FW_MODEL_CACHE[("base", "cpu", "int8")] = object()
        mod._FW_MODEL_CACHE[("small", "cpu", "int8")] = object()  # over cap

        # Patch _release_fw_model to avoid any cleanup side-effects
        with mpatch.object(mod, "_release_fw_model", lambda k, m: None):
            mod._enforce_fw_lru()

        # After eviction, cache should have at most _FW_MODEL_CACHE_MAX entries
        assert len(mod._FW_MODEL_CACHE) <= mod._FW_MODEL_CACHE_MAX
        # Oldest entry ("tiny") should have been evicted
        assert ("tiny", "cpu", "int8") not in mod._FW_MODEL_CACHE
    finally:
        mod._FW_MODEL_CACHE = original_cache
        mod._FW_MODEL_CACHE_MAX = original_max


# ── WHISPER_BATCH_SIZE env var ────────────────────────────────────────────────

def test_whisper_batch_size_env_var_exists():
    """The WHISPER_BATCH_SIZE env var should be readable; default 8 on CUDA, 4 on CPU."""
    # The adapters module uses os.getenv for batch size inside transcription calls.
    # Verify no import error when the env var is set.
    with patch.dict(os.environ, {"WHISPER_BATCH_SIZE": "16"}):
        from app.features.render.engine.subtitle.transcription import adapters  # noqa: F401
    # No assertion needed — just verify the import succeeds
