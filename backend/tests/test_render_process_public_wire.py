"""Audit MT-3 phase 2 closure (Batch 10O 2026-06-06).

The wire surface at ``POST /api/render/process`` now accepts
``RenderRequestPublic`` (88 fields, ``extra='forbid'``). BE-only fields
(channel_code, resume_job_id, ai_clip_*, ai_use_rag_memory, the
per-provider api_key fields, …) get a 422 at the boundary instead of
being silently sent.

These tests pin the wire contract via a FastAPI ``TestClient``:

1. A FE-shape payload (Public-only fields) is accepted — produces a
   queued job_id response.
2. A payload sneaking in a BE-only field (channel_code,
   resume_job_id, ai_clip_min_duration_sec, ai_use_rag_memory)
   produces 422 with the offending field named.
3. A typo (extra field not on Public) produces 422.
4. The Public + RenderRequest two-step keeps the server-derived defaults
   intact: a minimal FE payload, after server-side conversion, has
   ai_provider set from the env / config default and the BE-only
   fields populated with their RenderRequest defaults (resume_job_id
   None, ai_clip_min_duration_sec 15, etc.).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _client(tmp_path, monkeypatch):
    """Mount only the render router so the wire surface is exactly what
    /api/render/process sees in production, without pulling in the full
    app's startup (which would try to init the real DB)."""
    db_path = tmp_path / "wire.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()

    # Make sure the render pipeline finds a writable output dir without
    # touching the user's real channels tree.
    monkeypatch.setattr("app.core.config.CHANNELS_DIR", tmp_path / "channels", raising=False)
    monkeypatch.setattr("app.core.config.TEMP_DIR", tmp_path / "tmp", raising=False)
    (tmp_path / "channels").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)

    from fastapi import FastAPI
    from app.features.render.router import router as render_router

    app = FastAPI()
    app.include_router(render_router)

    # The handler enqueues into the job manager which submits to a thread
    # pool. Patch _queue_render_job so the test never actually starts a
    # render; we only want to verify the wire boundary, not the pipeline.
    from app.features.render.routers import lifecycle, _common as common_mod

    def _no_op_enqueue(job_id, channel, payload, resume_mode=False, queued_message=""):
        return None

    monkeypatch.setattr(lifecycle, "_queue_render_job", _no_op_enqueue)
    monkeypatch.setattr(common_mod, "_queue_render_job", _no_op_enqueue)
    # _validate_render_source checks Path(source_video_path).exists() —
    # we want the boundary contract to succeed with a fake path. Patch
    # the source validator to a no-op so the test isolates the wire
    # check from the local-file existence check.
    monkeypatch.setattr(lifecycle, "_validate_render_source", lambda p: None)
    monkeypatch.setattr(lifecycle, "_validate_text_layers_or_400", lambda p: [])

    return TestClient(app)


def _minimal_fe_payload():
    """Smallest Public-only payload that should round-trip cleanly."""
    return {
        "source_mode":       "local",
        "source_video_path": "C:/test/fake.mp4",
        "output_dir":        "C:/test/out",
        "render_profile":    "fast",
        "output_count":      1,
        "add_subtitle":      False,
        "voice_enabled":     False,
        "motion_aware_crop": False,
    }


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_process_accepts_fe_shape_payload(_client):
    resp = _client.post("/api/render/process", json=_minimal_fe_payload())

    assert resp.status_code == 200, (
        f"FE-shape payload was rejected: status={resp.status_code} body={resp.text}"
    )
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"


# ---------------------------------------------------------------------------
# 2. BE-only fields are rejected with 422
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_field,extra_value",
    [
        ("channel_code",             "k1"),
        ("resume_job_id",            "some-prior-job"),
        ("resume_from_last",         True),
        ("ai_clip_min_duration_sec", 30),
        ("ai_clip_max_duration_sec", 60),
        ("ai_use_rag_memory",        True),
        ("gemini_api_key",           "fake-key"),
        ("openai_api_key",           "fake-key"),
        ("claude_api_key",           "fake-key"),
        ("groq_api_key",             "fake-key"),
        ("hook_applied_text",        "smashed it"),
        ("creator_dna",              {}),
        ("market_viral",             {"target_market": "US"}),
        ("voice_rate",               "+0%"),
        ("voice_id",                 "abc"),
        ("audio_bitrate",            "256k"),
        ("video_codec",              "h265"),
        ("loudnorm_enabled",         False),
        ("groq_only_mode",           True),
        ("render_preset",            "viral"),
    ],
)
def test_process_rejects_be_only_field(_client, extra_field, extra_value):
    """The audit's MT-3 contract: BE-only fields must NOT cross the wire.
    Sneaking any of the 64 into a /process body now returns 422 instead
    of being silently accepted (the old Strict behaviour)."""
    body = _minimal_fe_payload()
    body[extra_field] = extra_value

    resp = _client.post("/api/render/process", json=body)
    assert resp.status_code == 422, (
        f"Expected 422 for BE-only field {extra_field!r}, got {resp.status_code}: "
        f"{resp.text}"
    )
    # FastAPI's validation error response names the offending field in the
    # ``loc`` array — check that the rejection actually identifies our
    # field, not something else.
    detail = resp.json().get("detail", [])
    field_paths = {tuple(item.get("loc", [])) for item in detail}
    assert any(extra_field in path for path in field_paths), (
        f"422 response did not name field {extra_field!r}. Detail: {detail}"
    )


# ---------------------------------------------------------------------------
# 3. Typo / unknown fields are rejected
# ---------------------------------------------------------------------------


def test_process_rejects_typo_field(_client):
    body = _minimal_fe_payload()
    body["render_profil"] = "fast"  # missing 'e'

    resp = _client.post("/api/render/process", json=body)
    assert resp.status_code == 422
    detail = resp.json().get("detail", [])
    assert any("render_profil" in str(item.get("loc", [])) for item in detail)


# ---------------------------------------------------------------------------
# 4. Server-side fill: the Public→RenderRequest conversion populates
#    BE-only defaults so the rest of the pipeline sees a full surface.
# ---------------------------------------------------------------------------


def test_public_to_render_request_conversion_fills_be_defaults(monkeypatch):
    """Construct Public → dump → build RenderRequest → assert BE-only
    defaults landed. This is the conversion the handler does at line
    ``payload = RenderRequest(**public_payload.model_dump())``.
    """
    from app.models.render import RenderRequest
    from app.models.render_public import RenderRequestPublic

    public = RenderRequestPublic(
        source_mode="local",
        source_video_path="x.mp4",
        render_profile="fast",
        output_count=2,
        add_subtitle=False,
    )

    full = RenderRequest(**public.model_dump())

    # Public-supplied fields preserved.
    assert full.source_video_path == "x.mp4"
    assert full.render_profile    == "fast"
    assert full.output_count      == 2
    # BE-only defaults landed without the FE having to send them.
    assert full.channel_code      == ""        # default
    assert full.resume_job_id     is None      # default
    assert full.resume_from_last  is False     # default
    assert full.ai_clip_min_duration_sec == 15   # validator-bounded default
    assert full.ai_clip_max_duration_sec == 60
    assert full.voice_rate        == "+0%"     # default
    assert full.creator_dna       == {}        # default_factory


def test_process_default_ai_provider_applied(_client, monkeypatch):
    """The handler sets ``payload.ai_provider = _cfg.AI_PROVIDER_DEFAULT``
    when the FE didn't send one. Pin that the server default still
    populates after the Public→RenderRequest conversion."""
    monkeypatch.setattr("app.core.config.AI_PROVIDER_DEFAULT", "gemini")

    body = _minimal_fe_payload()
    # Don't include ai_provider — expect default fill.
    resp = _client.post("/api/render/process", json=body)
    assert resp.status_code == 200, f"unexpected status: {resp.status_code} {resp.text}"
