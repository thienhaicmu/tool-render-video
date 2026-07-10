"""
G1 — cross-chapter series memory wired into Story v2 (offline).

Covers the READ seam (build_prior_context), the deterministic rolling summary, the
WRITE seam (persist_series_memory, incl. reference-sheet preservation), the prompt
injection, the director threading, and the /plan router wiring. All offline: DB via
story_repo, LLM via a fake call_fn.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.db.connection import init_db
from app.db import story_repo
from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat
from app.features.render.engine.pipeline.story_series_memory import (
    build_prior_context, rolling_summary_for, persist_series_memory,
)
from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_idea_prompt,
)
from app.features.render.ai.llm.story_director_v2 import run_super_plan
from app.features.story import router as story_router
from app.features.story.router import StoryPlanRequest, plan_storyboard


def setup_module(module):  # noqa: D401
    init_db()


def _sid() -> str:
    return "ser-" + uuid.uuid4().hex[:10]


def _super_json() -> str:
    return json.dumps({
        "topic": "t", "language": "vi",
        "characters": [{"id": "han", "name": "Han", "canonical_desc": "áo trắng"}],
        "visuals": [{"id": "v1", "prompt": "hall", "character_ids": ["han"], "tier": "medium"}],
        "timeline": [{"id": "b1", "narration": "đoạn 1", "visual_id": "v1", "focus": "center"}],
    })


# ── READ: build_prior_context ─────────────────────────────────────────────────

def test_build_prior_context_renders_chars_and_summary():
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(sid + "-han", series_id=sid, name="Hàn Phong",
                                    canonical_desc="áo trắng, kiếm bạc")
        story_repo.add_chapter_summary(sid, 1, "Hàn Phong phá cảnh.")
        ctx = build_prior_context(sid, before_chapter=2)
        assert "KNOWN CHARACTERS" in ctx and (sid + "-han") in ctx and "áo trắng" in ctx
        assert "STORY SO FAR" in ctx and "phá cảnh" in ctx
    finally:
        story_repo.delete_series(sid)


def test_build_prior_context_empty_series_is_blank():
    assert build_prior_context("") == ""
    assert build_prior_context("   ") == ""


def test_build_prior_context_disabled_env(monkeypatch):
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(sid + "-c", series_id=sid, name="C", canonical_desc="x")
        monkeypatch.setenv("STORY_SERIES_MEMORY", "0")
        assert build_prior_context(sid) == ""
    finally:
        story_repo.delete_series(sid)


def test_build_prior_context_before_chapter_excludes_current():
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.add_chapter_summary(sid, 1, "chương một")
        story_repo.add_chapter_summary(sid, 2, "chương hai")
        ctx = build_prior_context(sid, before_chapter=2)   # only ch1
        assert "chương một" in ctx and "chương hai" not in ctx
    finally:
        story_repo.delete_series(sid)


# ── rolling summary (pure) ────────────────────────────────────────────────────

def test_rolling_summary_is_topic_plus_narration_capped(monkeypatch):
    # Cap is a module constant (read at import) — patch the attribute, not the env.
    from app.features.render.engine.pipeline import story_series_memory as _sm
    monkeypatch.setattr(_sm, "_MAX_SUMMARY_CHARS", 20)
    plan = StoryPlan(topic="Chủ đề", timeline=[Beat(id="b1", narration="một hai ba bốn năm sáu")])
    s = _sm.rolling_summary_for(plan)
    assert s.startswith("Chủ đề")
    assert len(s) <= 20


# ── WRITE: persist_series_memory ──────────────────────────────────────────────

def test_persist_writes_characters_voice_and_summary():
    sid = _sid()
    cid = sid + "-han"
    try:
        plan = StoryPlan(
            language="vi", art_style="wuxia", topic="Test", chapter_no=5,
            characters=[CharacterDef(id=cid, name="Han", canonical_desc="áo trắng", voice_gender="male")],
            visuals=[Visual(id="v1", prompt="hall")],
            timeline=[Beat(id="b1", narration="Đêm lạnh.", visual_id="v1")],
        )
        plan.render.voices = {cid: ["gemini", "Puck"], "": ["gemini", "Kore"]}
        persist_series_memory(plan, sid, 5)
        row = story_repo.get_character(cid)
        assert row and row["canonical_desc"] == "áo trắng"
        assert row["voice_engine"] == "gemini" and row["voice_id"] == "Puck"
        assert row["gender"] == "male"
        sums = story_repo.list_chapter_summaries(sid)
        assert any("Test" in (s.get("rolling_summary") or "") for s in sums)
    finally:
        story_repo.delete_series(sid)


def test_persist_preserves_pinned_reference_sheet():
    sid = _sid()
    cid = sid + "-han"
    try:
        story_repo.upsert_series(sid, title="S")   # FK parent (as the pipeline now does)
        # A reference sheet pinned earlier in the render.
        story_repo.upsert_character(cid, series_id=sid, name="Han", canonical_desc="old",
                                    reference_image_path="/assets/ref.png")
        plan = StoryPlan(
            characters=[CharacterDef(id=cid, name="Han", canonical_desc="new")],
            visuals=[Visual(id="v1", prompt="hall")],
            timeline=[Beat(id="b1", narration="x", visual_id="v1")],
        )
        persist_series_memory(plan, sid, 1)
        row = story_repo.get_character(cid)
        assert row["reference_image_path"] == "/assets/ref.png"   # NOT wiped
        assert row["canonical_desc"] == "new"                     # updated
    finally:
        story_repo.delete_series(sid)


def test_build_prior_context_includes_settings():
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_environment(sid + "-hall", series_id=sid, name="Cloud Hall",
                                      canonical_desc="cold stone hall")
        ctx = build_prior_context(sid)
        assert "KNOWN SETTINGS" in ctx and (sid + "-hall") in ctx and "cold stone" in ctx
    finally:
        story_repo.delete_series(sid)


def test_persist_writes_settings_and_preserves_env_ref():
    sid = _sid()
    eid = sid + "-hall"
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_environment(eid, series_id=sid, name="Hall", canonical_desc="old",
                                      reference_image_path="/assets/env.png")
        plan = StoryPlan(
            series_id=sid, settings=[SettingDef(id=eid, name="Hall", canonical_desc="new")],
            visuals=[Visual(id="v1", prompt="p", setting_id=eid)],
            timeline=[Beat(id="b1", narration="n", visual_id="v1")],
        )
        persist_series_memory(plan, sid, 1)
        row = story_repo.get_environment(eid)
        assert row and row["canonical_desc"] == "new"
        assert row["reference_image_path"] == "/assets/env.png"   # preserved
    finally:
        story_repo.delete_series(sid)


def test_persist_noop_without_series():
    plan = StoryPlan(characters=[CharacterDef(id="x", name="X", canonical_desc="d")],
                     visuals=[Visual(id="v1", prompt="p")],
                     timeline=[Beat(id="b1", narration="n", visual_id="v1")])
    assert persist_series_memory(plan, "", 0) is None   # no raise, no write


# ── prompt injection ──────────────────────────────────────────────────────────

def test_prompt_injects_series_memory_when_present():
    _, user = build_super_story_prompt("Chương 2.", language="vi",
                                       prior_context="KNOWN CHARACTERS:\n- han (Han): áo trắng")
    assert "SERIES MEMORY" in user and "han (Han)" in user

    _, u_idea = build_super_idea_prompt("idea", duration_sec=60, language="vi",
                                        prior_context="STORY SO FAR:\n[Ch.1] x")
    assert "SERIES MEMORY" in u_idea


def test_prompt_no_memory_block_when_absent():
    _, user = build_super_story_prompt("Chương 1.", language="vi")
    assert "SERIES MEMORY" not in user


# ── director threading ────────────────────────────────────────────────────────

def test_run_super_plan_threads_prior_context():
    seen = {}

    def fake(system, user):
        seen["user"] = user
        return _super_json()
    p = run_super_plan(call_fn=fake, source="paste", chapter="Chương 2. " + ("x" * 40),
                       language="vi", prior_context="KNOWN CHARACTERS:\n- han (Han): áo trắng")
    assert p is not None
    assert "SERIES MEMORY" in seen["user"] and "han (Han)" in seen["user"]


# ── router wiring ─────────────────────────────────────────────────────────────

def test_plan_router_passes_prior_context_for_series(monkeypatch):
    sid = _sid()
    captured = {}

    def _fake(**kw):
        captured.update(kw)
        return StoryPlan(language="vi", topic="c2",
                         characters=[CharacterDef(id="han", name="Han")],
                         visuals=[Visual(id="v1", prompt="hall")],
                         timeline=[Beat(id="b1", narration="Đêm.", visual_id="v1")])
    monkeypatch.setattr(story_router, "generate_story_plan_v2", _fake)
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(sid + "-han", series_id=sid, name="Han", canonical_desc="áo trắng")
        story_repo.add_chapter_summary(sid, 1, "Chương 1 tóm tắt.")
        plan_storyboard(StoryPlanRequest(source="paste", chapter_text="Chương 2.",
                                         series_id=sid, chapter_no=2))
        assert captured["series_id"] == sid and captured["chapter_no"] == 2
        assert "STORY SO FAR" in captured["prior_context"]
        assert (sid + "-han") in captured["prior_context"]
    finally:
        story_repo.delete_series(sid)
