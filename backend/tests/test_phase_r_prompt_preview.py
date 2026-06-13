"""
tests/test_phase_r_prompt_preview.py — Phase R: LLM Prompt Preview.

POST /api/render/preview-prompt
  - Returns {system_prompt, user_prompt, editorial_hint, srt_chars, truncated}
  - No render job created, no LLM call made
  - srt_chars=0 when no SRT provided
  - srt_chars=len(srt_content) when SRT provided
  - editorial_hint field always present
  - truncated field always present (bool)
  - Cache lookup attempted when source_video_path provided
  - Prompt build gracefully handles errors
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


_SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:05,000
Hello and welcome to this video.

2
00:00:05,000 --> 00:00:10,000
Today we'll be talking about Python.
"""

_PREVIEW_URL = "/api/render/preview-prompt"


def test_preview_prompt_returns_required_keys(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value="editorial hint"),
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("sys", "usr")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": False}),
    ):
        resp = client.post(_PREVIEW_URL, json={"srt_content": _SAMPLE_SRT})
    assert resp.status_code == 200
    data = resp.json()
    assert "system_prompt" in data
    assert "user_prompt" in data
    assert "editorial_hint" in data
    assert "srt_chars" in data
    assert "truncated" in data


def test_preview_prompt_srt_chars_zero_when_no_srt(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value=""),
    ):
        resp = client.post(_PREVIEW_URL, json={})
    assert resp.status_code == 200
    assert resp.json()["srt_chars"] == 0


def test_preview_prompt_srt_chars_equals_content_length(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value=""),
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("sys", "usr")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": False}),
    ):
        resp = client.post(_PREVIEW_URL, json={"srt_content": _SAMPLE_SRT})
    assert resp.status_code == 200
    assert resp.json()["srt_chars"] == len(_SAMPLE_SRT.strip())


def test_preview_prompt_system_and_user_prompt_returned(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value=""),
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("SYSTEM_CONTENT", "USER_CONTENT")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": False}),
    ):
        resp = client.post(_PREVIEW_URL, json={"srt_content": _SAMPLE_SRT})
    data = resp.json()
    assert data["system_prompt"] == "SYSTEM_CONTENT"
    assert data["user_prompt"] == "USER_CONTENT"


def test_preview_prompt_editorial_hint_returned(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value="strong_hook_focus"),
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("s", "u")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": False}),
    ):
        resp = client.post(_PREVIEW_URL, json={"srt_content": _SAMPLE_SRT})
    assert resp.json()["editorial_hint"] == "strong_hook_focus"


def test_preview_prompt_truncated_flag_from_check(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value=""),
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("s", "u")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": True}),
    ):
        resp = client.post(_PREVIEW_URL, json={"srt_content": _SAMPLE_SRT})
    assert resp.json()["truncated"] is True


def test_preview_prompt_no_srt_returns_empty_prompts(client):
    with patch("app.routes.prompt_preview._build_editorial_hint", return_value=""):
        resp = client.post(_PREVIEW_URL, json={})
    data = resp.json()
    assert data["system_prompt"] == ""
    assert data["user_prompt"] == ""
    assert data["truncated"] is False


def test_preview_prompt_cache_lookup_attempted_when_path_provided(client):
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value=""),
        patch(
            "app.features.render.engine.pipeline.pipeline_cache._transcription_cache_get",
            return_value=_SAMPLE_SRT,
        ),
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("s", "u")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": False}),
    ):
        resp = client.post(_PREVIEW_URL, json={"source_video_path": "/videos/test.mp4"})
    assert resp.status_code == 200
    # srt_chars > 0 means cache hit was used
    assert resp.json()["srt_chars"] > 0


def test_preview_prompt_raw_srt_overrides_cache(client):
    """When srt_content is provided directly, cache is not consulted."""
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value=""),
        patch(
            "app.features.render.engine.pipeline.pipeline_cache._transcription_cache_get",
            return_value="CACHED_SRT",
        ) as mock_cache,
        patch("app.routes.prompt_preview.build_render_plan_prompt", return_value=("s", "u")),
        patch("app.routes.prompt_preview.check_srt_truncation", return_value={"truncated": False}),
    ):
        resp = client.post(
            _PREVIEW_URL,
            json={"srt_content": _SAMPLE_SRT, "source_video_path": "/videos/test.mp4"},
        )
    assert resp.status_code == 200
    mock_cache.assert_not_called()


def test_preview_prompt_editorial_hint_error_graceful(client):
    """If _build_editorial_hint raises, response still returns 200 with empty hint."""
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", side_effect=RuntimeError("oops")),
    ):
        resp = client.post(_PREVIEW_URL, json={})
    assert resp.status_code == 200
    assert resp.json()["editorial_hint"] == ""


def test_preview_prompt_defaults_used_when_not_provided(client):
    """Defaults: output_count=3, hook_strength=balanced, video_type=auto."""
    with (
        patch("app.routes.prompt_preview._build_editorial_hint", return_value="") as mock_hint,
    ):
        resp = client.post(_PREVIEW_URL, json={})
    assert resp.status_code == 200
    # Verify request body parsed with defaults (check mock call args)
    call_args = mock_hint.call_args[0][0]
    assert call_args.output_count == 3
    assert call_args.hook_strength == "balanced"
    assert call_args.video_type == "auto"


def test_preview_prompt_output_count_override(client):
    with patch("app.routes.prompt_preview._build_editorial_hint", return_value="") as mock_hint:
        client.post(_PREVIEW_URL, json={"output_count": 5})
    call_args = mock_hint.call_args[0][0]
    assert call_args.output_count == 5


def test_preview_prompt_output_count_out_of_range_422(client):
    resp = client.post(_PREVIEW_URL, json={"output_count": 25})
    assert resp.status_code == 422
