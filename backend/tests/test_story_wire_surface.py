"""Story-to-Video P6 — wire surface (RenderRequestPublic) + story-plan job read."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.db.connection import init_db
from app.db.jobs_repo import upsert_job, update_story_plan
from app.domain.story_plan import StoryPlan, StoryScene, Shot
from app.models.render_public import RenderRequestPublic, FE_FACING_FIELDS
from app.routes.jobs import api_get_job_story_plan


def setup_module(module):  # noqa: D401
    init_db()


# ── wire surface ──────────────────────────────────────────────────────────────

def test_story_fields_in_public_model():
    for f in ("story_series_id", "story_chapter_no", "story_art_style",
              "story_reading_pace", "story_plan_override"):
        assert f in RenderRequestPublic.model_fields
        assert f in FE_FACING_FIELDS


def test_public_accepts_story_render_payload():
    # /api/render/process receives RenderRequestPublic (extra="forbid").
    p = RenderRequestPublic(
        render_format="story", content_script="Chương 1...",
        story_series_id="tienhiep-1", story_chapter_no=186, story_art_style="wuxia",
        story_reading_pace="fast", story_plan_override="",
    )
    assert p.render_format == "story"
    assert p.story_chapter_no == 186
    assert p.story_art_style == "wuxia"


def test_public_forbids_unknown_field():
    with pytest.raises(Exception):
        RenderRequestPublic(story_bogus_field="nope")


def test_story_fields_default_inert_in_public():
    p = RenderRequestPublic()
    assert p.story_series_id == ""
    assert p.story_chapter_no == 0
    assert p.story_reading_pace == "normal"
    assert p.story_plan_override == ""


# ── story-plan job read (reattach / polling fallback) ────────────────────────

def _job() -> str:
    jid = "test-story-job-" + uuid.uuid4().hex[:8]
    upsert_job(jid, "render", "vn", "running", {}, {})
    return jid


def test_story_plan_404_for_missing_job():
    with pytest.raises(HTTPException) as ei:
        api_get_job_story_plan("no-such-job-" + uuid.uuid4().hex)
    assert ei.value.status_code == 404


def test_story_plan_available_false_when_no_plan():
    jid = _job()
    out = api_get_job_story_plan(jid)
    assert out["available"] is False and out["plan"] is None


def test_story_plan_returns_persisted_plan():
    jid = _job()
    plan = StoryPlan(language="vi", topic="tiên hiệp", scenes=[
        StoryScene(index=0, shots=[Shot(index=0, sid="a", narration="Đêm lạnh.", visual_prompt="peak")]),
    ])
    update_story_plan(jid, plan.to_json())
    out = api_get_job_story_plan(jid)
    assert out["available"] is True
    assert out["plan"]["topic"] == "tiên hiệp"
    assert out["plan"]["scenes"][0]["shots"][0]["narration"] == "Đêm lạnh."
