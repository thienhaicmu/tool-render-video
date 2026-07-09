"""Story-to-Video P1 — /api/story/analyze router logic + dispatch guard tests.

Router functions are called directly (no full-app TestClient boot) with
analyze_story monkeypatched, so these run offline. Also asserts the dispatcher's
no-key short-circuit (Sacred Contract #3).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.db.connection import init_db
from app.db import story_repo
from app.features.render.ai.llm import analyze_story
from app.domain.story_plan import StoryBible, StoryCharacter, StoryEnvironment
from app.features.story import router as story_router
from app.features.story.router import StoryAnalyzeRequest, analyze_chapter


def setup_module(module):  # noqa: D401
    init_db()


def test_dispatch_no_key_returns_none():
    # No api_key + no resolve_key → every provider skipped → None (no network).
    assert analyze_story(chapter_text="Một chương truyện dài.", api_key="") is None


def test_endpoint_422_on_empty_text():
    with pytest.raises(HTTPException) as ei:
        analyze_chapter(StoryAnalyzeRequest(chapter_text="   "))
    assert ei.value.status_code == 422


def test_endpoint_502_when_ai_returns_none(monkeypatch):
    monkeypatch.setattr(story_router, "analyze_story", lambda **kw: None)
    with pytest.raises(HTTPException) as ei:
        analyze_chapter(StoryAnalyzeRequest(chapter_text="Nội dung chương."))
    assert ei.value.status_code == 502


def test_endpoint_returns_bible_without_series(monkeypatch):
    bible = StoryBible(
        setting="Tu tiên giới", hook="trỗi dậy",
        characters=[StoryCharacter(id="han_phong", name="Hàn Phong", description="áo trắng")],
    )
    monkeypatch.setattr(story_router, "analyze_story",
                        lambda **kw: {"bible": bible, "meta": {"topic": "tiên hiệp"}})
    out = analyze_chapter(StoryAnalyzeRequest(chapter_text="Nội dung."))
    assert out["meta"]["topic"] == "tiên hiệp"
    assert out["bible"]["characters"][0]["id"] == "han_phong"


def test_endpoint_persists_bible_when_series_given(monkeypatch):
    sid = "test-story-" + uuid.uuid4().hex[:8]
    bible = StoryBible(
        characters=[StoryCharacter(id=sid + "-c", name="Hàn Phong", description="áo trắng",
                                   voice_engine="gemini", voice_id="vi-A")],
        environments=[StoryEnvironment(id=sid + "-e", name="Vạn Kiếm Tông", description="trên mây")],
    )
    monkeypatch.setattr(story_router, "analyze_story",
                        lambda **kw: {"bible": bible, "meta": {"rolling_summary": "toàn chương"}})
    try:
        out = analyze_chapter(StoryAnalyzeRequest(
            chapter_text="Nội dung.", series_id=sid, chapter_no=1,
        ))
        assert out["bible"]["characters"][0]["name"] == "Hàn Phong"
        # Persisted to the cross-chapter Character DB.
        chars = story_repo.list_characters(sid)
        assert len(chars) == 1 and chars[0]["voice_engine"] == "gemini"
        envs = story_repo.list_environments(sid)
        assert len(envs) == 1 and envs[0]["name"] == "Vạn Kiếm Tông"
        summaries = story_repo.list_chapter_summaries(sid)
        assert summaries and summaries[0]["rolling_summary"] == "toàn chương"
    finally:
        story_repo.delete_series(sid)
