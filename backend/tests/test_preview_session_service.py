"""Tests for services/preview/session_service.py (Phase 4H.2)."""

import json
import time
from pathlib import Path
from unittest import mock

import pytest

import app.services.preview.session_service as svc
import app.routes.render as render_mod


@pytest.fixture(autouse=True)
def clear_sessions():
    """Ensure _PREVIEW_SESSIONS is empty before and after each test."""
    svc._PREVIEW_SESSIONS.clear()
    yield
    svc._PREVIEW_SESSIONS.clear()


# ── Singleton identity ──────────────────────────────────────────────────────────

def test_sessions_dict_is_same_object_in_routes_and_service():
    """routes/render._PREVIEW_SESSIONS must be the same object as session_service._PREVIEW_SESSIONS."""
    assert render_mod._PREVIEW_SESSIONS is svc._PREVIEW_SESSIONS


def test_evict_stale_preview_sessions_is_same_object_in_routes_and_service():
    """routes/render.evict_stale_preview_sessions must be the session_service function."""
    assert render_mod.evict_stale_preview_sessions is svc.evict_stale_preview_sessions


# ── _save_session ───────────────────────────────────────────────────────────────

def test_save_session_writes_to_memory(tmp_path):
    svc._save_session("abc", {"video_path": "/v.mp4", "work_dir": str(tmp_path)})
    assert "abc" in svc._PREVIEW_SESSIONS
    assert svc._PREVIEW_SESSIONS["abc"]["video_path"] == "/v.mp4"


def test_save_session_adds_created_at_if_missing(tmp_path):
    before = time.time()
    svc._save_session("abc", {"work_dir": str(tmp_path)})
    after = time.time()
    ts = svc._PREVIEW_SESSIONS["abc"]["created_at"]
    assert before <= ts <= after


def test_save_session_does_not_overwrite_existing_created_at(tmp_path):
    svc._save_session("abc", {"work_dir": str(tmp_path), "created_at": 1000.0})
    assert svc._PREVIEW_SESSIONS["abc"]["created_at"] == 1000.0


def test_save_session_writes_json_file(tmp_path):
    svc._save_session("abc", {"video_path": "/v.mp4", "work_dir": str(tmp_path)})
    meta = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    assert meta["video_path"] == "/v.mp4"


def test_save_session_evicts_oldest_when_at_capacity(tmp_path):
    original_max = svc._MAX_PREVIEW_SESSIONS
    svc._MAX_PREVIEW_SESSIONS = 2
    try:
        svc._save_session("old", {"work_dir": str(tmp_path), "created_at": 1.0})
        svc._save_session("new1", {"work_dir": str(tmp_path), "created_at": 2.0})
        # At capacity — adding a third should evict "old" (lowest created_at)
        svc._save_session("new2", {"work_dir": str(tmp_path), "created_at": 3.0})
        assert "old" not in svc._PREVIEW_SESSIONS
        assert "new1" in svc._PREVIEW_SESSIONS
        assert "new2" in svc._PREVIEW_SESSIONS
    finally:
        svc._MAX_PREVIEW_SESSIONS = original_max


# ── _load_session ───────────────────────────────────────────────────────────────

def test_load_session_returns_from_memory(tmp_path):
    svc._PREVIEW_SESSIONS["abc"] = {"video_path": "/v.mp4", "work_dir": str(tmp_path)}
    result = svc._load_session("abc")
    assert result is not None
    assert result["video_path"] == "/v.mp4"


def test_load_session_returns_none_for_unknown():
    result = svc._load_session("does-not-exist")
    assert result is None


def test_load_session_falls_back_to_disk(tmp_path):
    session_dir = tmp_path / "sess1"
    session_dir.mkdir()
    video_file = tmp_path / "v.mp4"
    video_file.touch()
    data = {"video_path": str(video_file), "work_dir": str(session_dir)}
    (session_dir / "session.json").write_text(json.dumps(data), encoding="utf-8")

    with mock.patch.object(svc, "_PREVIEW_DIR", tmp_path):
        result = svc._load_session("sess1")

    assert result is not None
    assert result["video_path"] == str(video_file)
    # Should be cached in memory after disk load
    assert "sess1" in svc._PREVIEW_SESSIONS


def test_load_session_disk_fallback_ignores_missing_video(tmp_path):
    session_dir = tmp_path / "sess2"
    session_dir.mkdir()
    data = {"video_path": str(tmp_path / "gone.mp4"), "work_dir": str(session_dir)}
    (session_dir / "session.json").write_text(json.dumps(data), encoding="utf-8")

    with mock.patch.object(svc, "_PREVIEW_DIR", tmp_path):
        result = svc._load_session("sess2")

    assert result is None


# ── _cleanup_preview_session ────────────────────────────────────────────────────

def test_cleanup_removes_from_memory(tmp_path):
    svc._PREVIEW_SESSIONS["abc"] = {"work_dir": str(tmp_path)}
    svc._cleanup_preview_session("abc")
    assert "abc" not in svc._PREVIEW_SESSIONS


def test_cleanup_removes_disk_dir(tmp_path):
    session_dir = tmp_path / "abc"
    session_dir.mkdir()
    svc._PREVIEW_SESSIONS["abc"] = {"work_dir": str(tmp_path)}
    with mock.patch.object(svc, "_PREVIEW_DIR", tmp_path):
        svc._cleanup_preview_session("abc")
    assert not session_dir.exists()


def test_cleanup_is_idempotent_for_unknown_session():
    svc._cleanup_preview_session("does-not-exist")  # must not raise


# ── evict_stale_preview_sessions ────────────────────────────────────────────────

def test_evict_removes_old_sessions(tmp_path):
    now = time.time()
    svc._PREVIEW_SESSIONS["stale"] = {"work_dir": str(tmp_path), "created_at": now - 7 * 3600}
    svc._PREVIEW_SESSIONS["fresh"] = {"work_dir": str(tmp_path), "created_at": now - 1 * 3600}

    original_ttl = svc._SESSION_TTL_HOURS
    svc._SESSION_TTL_HOURS = 6
    try:
        evicted = svc.evict_stale_preview_sessions()
    finally:
        svc._SESSION_TTL_HOURS = original_ttl

    assert evicted == 1
    assert "stale" not in svc._PREVIEW_SESSIONS
    assert "fresh" in svc._PREVIEW_SESSIONS


def test_evict_returns_zero_when_nothing_stale(tmp_path):
    now = time.time()
    svc._PREVIEW_SESSIONS["fresh"] = {"work_dir": str(tmp_path), "created_at": now - 1}
    original_ttl = svc._SESSION_TTL_HOURS
    svc._SESSION_TTL_HOURS = 6
    try:
        evicted = svc.evict_stale_preview_sessions()
    finally:
        svc._SESSION_TTL_HOURS = original_ttl
    assert evicted == 0


def test_evict_returns_zero_on_empty_sessions():
    original_ttl = svc._SESSION_TTL_HOURS
    svc._SESSION_TTL_HOURS = 6
    try:
        evicted = svc.evict_stale_preview_sessions()
    finally:
        svc._SESSION_TTL_HOURS = original_ttl
    assert evicted == 0
