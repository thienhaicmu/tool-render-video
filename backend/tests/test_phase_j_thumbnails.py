"""Phase J — Output Thumbnail API QA tests.

Covers:
  - routes/thumbnails.py: _cache_key, _cache_get, _cache_put,
    GET /api/jobs/{id}/outputs/{part_no}/thumbnail
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── helper functions ──────────────────────────────────────────────────────────

def test_cache_key_is_md5_of_path_and_mtime():
    from app.routes.thumbnails import _cache_key

    key = _cache_key("/some/file.mp4", 1234567.89)
    expected = hashlib.md5("/some/file.mp4|1234567.89".encode()).hexdigest()
    assert key == expected


def test_cache_key_different_mtime_different_key():
    from app.routes.thumbnails import _cache_key

    k1 = _cache_key("/file.mp4", 1000.0)
    k2 = _cache_key("/file.mp4", 2000.0)
    assert k1 != k2


def test_cache_key_different_path_different_key():
    from app.routes.thumbnails import _cache_key

    k1 = _cache_key("/a.mp4", 1000.0)
    k2 = _cache_key("/b.mp4", 1000.0)
    assert k1 != k2


def test_cache_get_returns_none_for_missing_key(tmp_path):
    from app.routes.thumbnails import _cache_get
    import app.routes.thumbnails as mod

    original_dir = mod._THUMBNAIL_DIR
    try:
        mod._THUMBNAIL_DIR = tmp_path
        result = _cache_get("nonexistent_key")
        assert result is None
    finally:
        mod._THUMBNAIL_DIR = original_dir


def test_cache_get_returns_bytes_for_fresh_entry(tmp_path):
    from app.routes.thumbnails import _cache_get
    import app.routes.thumbnails as mod

    original_dir = mod._THUMBNAIL_DIR
    try:
        mod._THUMBNAIL_DIR = tmp_path
        key = "testkey"
        (tmp_path / f"{key}.jpg").write_bytes(b"JPEG_DATA")
        result = _cache_get(key)
        assert result == b"JPEG_DATA"
    finally:
        mod._THUMBNAIL_DIR = original_dir


def test_cache_get_returns_none_for_expired_entry(tmp_path):
    from app.routes.thumbnails import _cache_get
    import app.routes.thumbnails as mod

    original_dir = mod._THUMBNAIL_DIR
    try:
        mod._THUMBNAIL_DIR = tmp_path
        key = "expiredkey"
        cache_file = tmp_path / f"{key}.jpg"
        cache_file.write_bytes(b"OLD_JPEG")
        # Make the file appear very old
        old_time = time.time() - (mod._THUMBNAIL_CACHE_TTL_SEC + 100)
        import os
        os.utime(cache_file, (old_time, old_time))
        result = _cache_get(key)
        assert result is None
        # Expired file should be deleted
        assert not cache_file.exists()
    finally:
        mod._THUMBNAIL_DIR = original_dir


def test_cache_put_writes_atomically(tmp_path):
    from app.routes.thumbnails import _cache_put
    import app.routes.thumbnails as mod

    original_dir = mod._THUMBNAIL_DIR
    try:
        mod._THUMBNAIL_DIR = tmp_path
        _cache_put("mykey", b"JPEG_BYTES")
        result_file = tmp_path / "mykey.jpg"
        assert result_file.exists()
        assert result_file.read_bytes() == b"JPEG_BYTES"
        # No .tmp file left behind
        assert not (tmp_path / "mykey.jpg.tmp").exists()
    finally:
        mod._THUMBNAIL_DIR = original_dir


def test_cache_put_silent_on_error():
    from app.routes.thumbnails import _cache_put
    import app.routes.thumbnails as mod

    # Point to a directory that can't be created (invalid path)
    original_dir = mod._THUMBNAIL_DIR
    try:
        mod._THUMBNAIL_DIR = Path("/invalid/\x00/path")
        # Must not raise
        _cache_put("k", b"data")
    finally:
        mod._THUMBNAIL_DIR = original_dir


# ── FastAPI route tests ───────────────────────────────────────────────────────

def _client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_thumbnail_404_when_job_missing():
    with patch("app.routes.thumbnails.get_job", return_value=None):
        resp = _client().get("/api/jobs/j1/outputs/1/thumbnail")
    assert resp.status_code == 404


def test_thumbnail_404_when_part_missing():
    with patch("app.routes.thumbnails.get_job", return_value={"job_id": "j1"}), \
         patch("app.routes.thumbnails.list_job_parts", return_value=[]):
        resp = _client().get("/api/jobs/j1/outputs/1/thumbnail")
    assert resp.status_code == 404


def test_thumbnail_404_when_no_output_file():
    with patch("app.routes.thumbnails.get_job", return_value={"job_id": "j1"}), \
         patch("app.routes.thumbnails.list_job_parts", return_value=[
             {"part_no": 1, "output_file": ""}
         ]):
        resp = _client().get("/api/jobs/j1/outputs/1/thumbnail")
    assert resp.status_code == 404


def test_thumbnail_404_when_file_not_on_disk():
    with patch("app.routes.thumbnails.get_job", return_value={"job_id": "j1"}), \
         patch("app.routes.thumbnails.list_job_parts", return_value=[
             {"part_no": 1, "output_file": "/nonexistent/file.mp4"}
         ]):
        resp = _client().get("/api/jobs/j1/outputs/1/thumbnail")
    assert resp.status_code == 404


def test_thumbnail_served_from_cache(tmp_path):
    import app.routes.thumbnails as mod

    output_file = tmp_path / "clip.mp4"
    output_file.write_bytes(b"fake")
    mtime = output_file.stat().st_mtime
    key = mod._cache_key(str(output_file), mtime)

    # Pre-populate cache
    original_dir = mod._THUMBNAIL_DIR
    mod._THUMBNAIL_DIR = tmp_path
    (tmp_path / f"{key}.jpg").write_bytes(b"\xff\xd8\xff" + b"fake_jpeg")

    try:
        with patch("app.routes.thumbnails.get_job", return_value={"job_id": "j1"}), \
             patch("app.routes.thumbnails.list_job_parts", return_value=[
                 {"part_no": 1, "output_file": str(output_file)}
             ]):
            resp = _client().get("/api/jobs/j1/outputs/1/thumbnail")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
    finally:
        mod._THUMBNAIL_DIR = original_dir


def test_thumbnail_503_when_extraction_fails(tmp_path):
    output_file = tmp_path / "clip.mp4"
    output_file.write_bytes(b"fake")

    with patch("app.routes.thumbnails.get_job", return_value={"job_id": "j1"}), \
         patch("app.routes.thumbnails.list_job_parts", return_value=[
             {"part_no": 1, "output_file": str(output_file)}
         ]), \
         patch("app.routes.thumbnails.probe_video_metadata",
               return_value={"duration": 10.0}), \
         patch("app.routes.thumbnails.extract_thumbnail_frame",
               return_value=None):   # extraction failure
        resp = _client().get("/api/jobs/j1/outputs/1/thumbnail")

    assert resp.status_code == 503


def test_thumbnail_width_query_param_validated():
    """width < 64 should return 422 (FastAPI query validation)."""
    with patch("app.routes.thumbnails.get_job", return_value={"job_id": "j1"}), \
         patch("app.routes.thumbnails.list_job_parts", return_value=[]):
        resp = _client().get("/api/jobs/j1/outputs/1/thumbnail?width=10")
    assert resp.status_code == 422
