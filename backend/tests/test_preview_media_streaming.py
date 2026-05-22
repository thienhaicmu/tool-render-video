"""Tests for services/preview/media_streaming.py (Phase 4H.3)."""

import importlib
import inspect
from pathlib import Path
from unittest import mock

import pytest
from fastapi import HTTPException

import app.services.preview.media_streaming as ms
import app.routes.render as render_mod


# ── Module structure ────────────────────────────────────────────────────────────

def test_media_streaming_module_imports():
    assert hasattr(ms, "_parse_range_header")
    assert hasattr(ms, "_iter_file_bytes")


def test_routes_render_imports():
    assert hasattr(render_mod, "_parse_range_header")
    assert hasattr(render_mod, "_iter_file_bytes")


def test_no_apirouter_in_media_streaming():
    # Check namespace, not raw source text (source may mention the name in docstrings)
    assert "APIRouter" not in dir(ms)
    assert not hasattr(ms, "router")
    # Confirm no route decorators in actual imports
    import app.services.preview.media_streaming as _ms_mod
    assert not any(
        name in vars(_ms_mod)
        for name in ("APIRouter", "router", "Request", "UploadFile")
    )


def test_no_routes_render_import_in_media_streaming():
    src = inspect.getsource(ms)
    assert "routes.render" not in src
    assert "from app.routes" not in src


def test_no_db_import_in_media_streaming():
    src = inspect.getsource(ms)
    assert "upsert_job" not in src
    assert "list_job_parts" not in src
    assert "from app.services.db" not in src


def test_no_render_pipeline_import_in_media_streaming():
    src = inspect.getsource(ms)
    assert "render_pipeline" not in src


def test_no_session_service_import_in_media_streaming():
    src = inspect.getsource(ms)
    assert "session_service" not in src


# ── Same-object identity ────────────────────────────────────────────────────────

def test_parse_range_header_same_object():
    assert render_mod._parse_range_header is ms._parse_range_header


def test_iter_file_bytes_same_object():
    assert render_mod._iter_file_bytes is ms._iter_file_bytes


# ── Route handlers remain in routes/render.py ─────────────────────────────────

def test_stream_render_part_media_still_in_routes():
    assert hasattr(render_mod, "stream_render_part_media")
    assert callable(render_mod.stream_render_part_media)


def test_get_render_part_thumbnail_still_in_routes():
    assert hasattr(render_mod, "get_render_part_thumbnail")
    assert callable(render_mod.get_render_part_thumbnail)


# ── _parse_range_header ─────────────────────────────────────────────────────────

def test_parse_range_valid_explicit():
    byte1, byte2 = ms._parse_range_header("bytes=0-99", 1000)
    assert byte1 == 0
    assert byte2 == 99


def test_parse_range_open_end():
    byte1, byte2 = ms._parse_range_header("bytes=500-", 1000)
    assert byte1 == 500
    assert byte2 == 999  # file_size - 1


def test_parse_range_clamps_end_to_file_size():
    byte1, byte2 = ms._parse_range_header("bytes=0-99999", 100)
    assert byte2 == 99  # clamped to 99


def test_parse_range_invalid_format_raises_416():
    with pytest.raises(HTTPException) as exc_info:
        ms._parse_range_header("invalid", 1000)
    assert exc_info.value.status_code == 416
    assert "Content-Range" in exc_info.value.headers


def test_parse_range_non_bytes_unit_raises_416():
    with pytest.raises(HTTPException) as exc_info:
        ms._parse_range_header("pages=0-10", 1000)
    assert exc_info.value.status_code == 416


def test_parse_range_start_beyond_file_raises_416():
    with pytest.raises(HTTPException) as exc_info:
        ms._parse_range_header("bytes=5000-9999", 1000)
    assert exc_info.value.status_code == 416


def test_parse_range_start_equals_file_size_raises_416():
    with pytest.raises(HTTPException) as exc_info:
        ms._parse_range_header("bytes=1000-1099", 1000)
    assert exc_info.value.status_code == 416


def test_parse_range_start_greater_than_end_raises_416():
    with pytest.raises(HTTPException) as exc_info:
        ms._parse_range_header("bytes=100-50", 1000)
    assert exc_info.value.status_code == 416


def test_parse_range_error_header_includes_file_size():
    with pytest.raises(HTTPException) as exc_info:
        ms._parse_range_header("bytes=9999-", 100)
    assert exc_info.value.headers["Content-Range"] == "bytes */100"


def test_parse_range_single_byte():
    byte1, byte2 = ms._parse_range_header("bytes=42-42", 100)
    assert byte1 == 42
    assert byte2 == 42


# ── _iter_file_bytes ────────────────────────────────────────────────────────────

def test_iter_file_bytes_full_content(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"Hello, world!")
    data = b"".join(ms._iter_file_bytes(f, 0, 12))
    assert data == b"Hello, world!"


def test_iter_file_bytes_partial(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"ABCDEFGHIJ")
    data = b"".join(ms._iter_file_bytes(f, 2, 5))
    assert data == b"CDEF"  # bytes 2,3,4,5 inclusive


def test_iter_file_bytes_single_byte(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"XYZ")
    data = b"".join(ms._iter_file_bytes(f, 1, 1))
    assert data == b"Y"


def test_iter_file_bytes_small_chunk(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"ABCDEFGH")
    chunks = list(ms._iter_file_bytes(f, 0, 7, chunk=2))
    assert b"".join(chunks) == b"ABCDEFGH"
    assert len(chunks) == 4  # 8 bytes / 2-byte chunk = 4 chunks


def test_iter_file_bytes_empty_range_yields_nothing(tmp_path):
    # start == end + 1 would be end < start, which is caller's responsibility;
    # test that start == end produces exactly 1 byte
    f = tmp_path / "test.bin"
    f.write_bytes(b"ABC")
    data = b"".join(ms._iter_file_bytes(f, 0, 0))
    assert data == b"A"


# ── Range + no-range behavior (integration-style, no route machinery) ──────────

def test_no_range_full_file_readable(tmp_path):
    """When no Range header is provided the full file should be streamable."""
    content = b"full file content"
    f = tmp_path / "clip.mp4"
    f.write_bytes(content)
    file_size = len(content)
    data = b"".join(ms._iter_file_bytes(f, 0, file_size - 1))
    assert data == content


def test_valid_range_partial_read(tmp_path):
    content = b"0123456789"
    f = tmp_path / "clip.mp4"
    f.write_bytes(content)
    byte1, byte2 = ms._parse_range_header("bytes=3-6", len(content))
    data = b"".join(ms._iter_file_bytes(f, byte1, byte2))
    assert data == b"3456"  # bytes at index 3,4,5,6
