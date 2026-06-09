"""Sprint E-1 — output_dir auto-populate from saved setting.

_validate_output_dir() behaviour:
  1. Non-empty output_dir  → DB never queried, payload unchanged.
  2. Empty output_dir + saved setting exists → payload.output_dir updated.
  3. Empty output_dir + no saved setting → 400 with Settings hint in detail.
  4. Empty output_dir + DB raises → graceful 400 (no crash).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from unittest.mock import patch


def _make_payload(output_dir: str = ""):
    from app.models.schemas import RenderRequest
    return RenderRequest(output_dir=output_dir, source_mode="local", source_video_path="/tmp/v.mp4")


def test_non_empty_output_dir_skips_lookup():
    from app.features.render.routers._common import _validate_output_dir

    payload = _make_payload(output_dir="/some/dir")
    with patch("app.db.creator_repo.get_default_output_dir") as mock_get:
        _validate_output_dir(payload)
        mock_get.assert_not_called()
    assert payload.output_dir == "/some/dir"


def test_empty_output_dir_uses_saved_setting():
    from app.features.render.routers._common import _validate_output_dir

    payload = _make_payload(output_dir="")
    with patch("app.db.creator_repo.get_default_output_dir", return_value="/saved/out"):
        _validate_output_dir(payload)
    assert payload.output_dir == "/saved/out"


def test_empty_output_dir_no_saved_raises_400_with_settings_hint():
    from app.features.render.routers._common import _validate_output_dir

    payload = _make_payload(output_dir="")
    with patch("app.db.creator_repo.get_default_output_dir", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            _validate_output_dir(payload)
    assert exc_info.value.status_code == 400
    assert "Settings" in str(exc_info.value.detail)


def test_empty_output_dir_db_error_raises_400():
    from app.features.render.routers._common import _validate_output_dir

    payload = _make_payload(output_dir="")
    with patch("app.db.creator_repo.get_default_output_dir", side_effect=RuntimeError("DB boom")):
        with pytest.raises(HTTPException) as exc_info:
            _validate_output_dir(payload)
    assert exc_info.value.status_code == 400
