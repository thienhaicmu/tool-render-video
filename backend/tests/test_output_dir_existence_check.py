"""Sprint G-1 — output_dir existence check in _validate_output_dir.

1. Non-existent path → accepted (pipeline will create it via mkdir).
2. Existing directory → accepted.
3. Path exists but is a file → 400.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def _make_payload(output_dir: str):
    from app.models.schemas import RenderRequest
    return RenderRequest(output_dir=output_dir, source_mode="local", source_video_path="/tmp/v.mp4")


def test_nonexistent_path_accepted(tmp_path):
    from app.features.render.routers._common import _validate_output_dir
    missing = str(tmp_path / "does_not_exist" / "subdir")
    payload = _make_payload(missing)
    _validate_output_dir(payload)  # must not raise


def test_existing_directory_accepted(tmp_path):
    from app.features.render.routers._common import _validate_output_dir
    payload = _make_payload(str(tmp_path))
    _validate_output_dir(payload)  # must not raise


def test_path_is_file_raises_400(tmp_path):
    from app.features.render.routers._common import _validate_output_dir
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake")
    payload = _make_payload(str(f))
    with pytest.raises(HTTPException) as exc_info:
        _validate_output_dir(payload)
    assert exc_info.value.status_code == 400
    assert "not a directory" in exc_info.value.detail
