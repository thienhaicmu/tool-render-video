"""Tests for app.core.ui_gate — STATIC_UI_VERSION activation gate.

Run with:
    python -m pytest tests/test_ui_gate.py -v
Or via the broader filter:
    python -m pytest -k "static_ui_version or static_v2 or ui_activation or ui_gate"
"""

import sys
from pathlib import Path

# Make sure backend/ is on sys.path so we can import app.core.ui_gate directly
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.core.ui_gate import resolve_static_directory, ENV_VAR, VERSION_V2, VERSION_LEGACY


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_backend(tmp_path):
    """Return a temp backend root with backend/static/ present."""
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "index.html").write_text("<html></html>")
    return tmp_path


@pytest.fixture()
def tmp_backend_with_v2(tmp_backend):
    """Same as tmp_backend but also has backend/static-v2/assets/."""
    v2 = tmp_backend / "static-v2"
    v2.mkdir()
    (v2 / "assets").mkdir()
    (v2 / "index.html").write_text("<html></html>")
    return tmp_backend


# ---------------------------------------------------------------------------
# 1. Missing env → legacy
# ---------------------------------------------------------------------------

def test_missing_env_returns_legacy(tmp_backend):
    static_dir, version = resolve_static_directory(tmp_backend, env_value=None.__class__.__name__)
    # env_value=None reads env var; pass an empty-string override to simulate unset
    static_dir, version = resolve_static_directory(tmp_backend, env_value="")
    assert version == VERSION_LEGACY
    assert static_dir == tmp_backend / "static"


def test_default_env_unset_returns_legacy(tmp_backend, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    static_dir, version = resolve_static_directory(tmp_backend)
    assert version == VERSION_LEGACY


# ---------------------------------------------------------------------------
# 2. STATIC_UI_VERSION=legacy → legacy
# ---------------------------------------------------------------------------

def test_explicit_legacy_returns_legacy(tmp_backend):
    static_dir, version = resolve_static_directory(tmp_backend, env_value="legacy")
    assert version == VERSION_LEGACY
    assert static_dir == tmp_backend / "static"


def test_explicit_legacy_uppercase(tmp_backend):
    static_dir, version = resolve_static_directory(tmp_backend, env_value="LEGACY")
    assert version == VERSION_LEGACY


# ---------------------------------------------------------------------------
# 3. STATIC_UI_VERSION=v2 with static-v2 present → v2
# ---------------------------------------------------------------------------

def test_v2_env_with_v2_dir_returns_v2(tmp_backend_with_v2):
    static_dir, version = resolve_static_directory(tmp_backend_with_v2, env_value="v2")
    assert version == VERSION_V2
    assert static_dir == tmp_backend_with_v2 / "static-v2"


def test_v2_env_uppercase(tmp_backend_with_v2):
    static_dir, version = resolve_static_directory(tmp_backend_with_v2, env_value="V2")
    assert version == VERSION_V2


# ---------------------------------------------------------------------------
# 4. Invalid env value → legacy fallback
# ---------------------------------------------------------------------------

def test_invalid_env_returns_legacy(tmp_backend):
    static_dir, version = resolve_static_directory(tmp_backend, env_value="nightly")
    assert version == VERSION_LEGACY
    assert static_dir == tmp_backend / "static"


def test_invalid_env_gibberish(tmp_backend):
    static_dir, version = resolve_static_directory(tmp_backend, env_value="__garbage__")
    assert version == VERSION_LEGACY


# ---------------------------------------------------------------------------
# 5. STATIC_UI_VERSION=v2 but static-v2 dir missing → legacy fallback
# ---------------------------------------------------------------------------

def test_v2_requested_but_dir_missing_falls_back_to_legacy(tmp_backend):
    # tmp_backend has static/ but NOT static-v2/
    assert not (tmp_backend / "static-v2").exists()
    static_dir, version = resolve_static_directory(tmp_backend, env_value="v2")
    assert version == VERSION_LEGACY
    assert static_dir == tmp_backend / "static"


# ---------------------------------------------------------------------------
# 6. Return type guarantees
# ---------------------------------------------------------------------------

def test_return_is_tuple_of_path_and_str(tmp_backend):
    result = resolve_static_directory(tmp_backend, env_value="legacy")
    assert isinstance(result, tuple)
    assert len(result) == 2
    static_dir, version = result
    assert isinstance(static_dir, Path)
    assert isinstance(version, str)


def test_never_raises_on_unusual_env(tmp_backend):
    for val in ["", "  ", "null", "None", "0", "true", "/tmp"]:
        static_dir, version = resolve_static_directory(tmp_backend, env_value=val)
        assert version in (VERSION_LEGACY, VERSION_V2)
