"""Paste-JSON → render feature (2026-07-14).

Covers the backend surface that lets a user paste a StoryPlan JSON and render it
verbatim (no AI):
  · StoryPlan.normalize_for_render — scrub dangling refs + drop stale render state
  · story_source validator accepts "paste_json" (Contract #2: additive)
  · POST /api/story/validate — preflight errors/warnings/estimate
  · _resolve_story_plan_v2 strict mode — paste_json never falls back to an AI call
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domain.story_plan_v2 import (
    StoryPlan, CharacterDef, SettingDef, Visual, Beat, Line, BeatAudio,
)
from app.models.render import RenderRequest
from app.features.render.engine.pipeline import story_pipeline_v2 as sp


def _client():
    return TestClient(app)


VALID_PLAN = {
    "schema_version": 2, "language": "vi", "aspect_ratio": "9:16",
    "characters": [{"id": "a", "name": "A", "canonical_desc": "x"}],
    "settings": [{"id": "s1", "name": "S"}],
    "visuals": [{"id": "v1", "setting_id": "s1", "character_ids": ["a"]}],
    "timeline": [{"id": "b1", "visual_id": "v1", "focus": "center",
                  "lines": [{"speaker_id": "a", "text": "Xin chào các bạn", "emotion": "happy"}]}],
    "render": {},
}


# ── B1: normalize_for_render ──────────────────────────────────────────────────

def test_normalize_scrubs_refs_and_resets_render():
    p = StoryPlan(
        language="vi",
        characters=[CharacterDef(id="a")],
        settings=[SettingDef(id="s1")],
        visuals=[Visual(id="v1", setting_id="s1", character_ids=["a", "ghost"])],
        timeline=[Beat(id="b1", visual_id="v1", lines=[Line("a", "hi"), Line("ghost", "bad")])],
    )
    p.render.beat_audio["b1"] = BeatAudio("stale.mp3", 5.0, [], [])   # DERIVED — cleared
    # Review picks live in render state — MUST survive normalize (the Bug-2 fix).
    p.render.voices["a"] = ["elevenlabs", "VOICE1"]
    p.render.masters["a"] = "/lib/a.png"
    p.render.visual_assets["v1"] = "/lib/bg.png"
    p.normalize_for_render(15)
    # derived state cleared (regenerated every render)
    assert p.render.beat_audio == {} and p.render.cues == []
    # user picks PRESERVED
    assert p.render.voices["a"] == ["elevenlabs", "VOICE1"]
    assert p.render.masters["a"] == "/lib/a.png"
    assert p.render.visual_assets["v1"] == "/lib/bg.png"
    # dangling refs still scrubbed
    assert "ghost" not in (p.visuals[0].character_ids or [])
    assert p.timeline[0].lines[1].speaker_id == ""   # unknown speaker → narrator


# ── B4: story_source validator (Contract #2 additive) ─────────────────────────

def test_story_source_validator_accepts_paste_json():
    assert RenderRequest(story_source="paste_json").story_source == "paste_json"
    assert RenderRequest(story_source="PASTE_JSON").story_source == "paste_json"
    assert RenderRequest(story_source="weird").story_source == ""      # coerced (Contract #2)
    assert RenderRequest().story_source == ""                          # default unchanged


# ── B3: /api/story/validate ───────────────────────────────────────────────────

def test_validate_ok():
    b = _client().post("/api/story/validate", json={"plan": VALID_PLAN}).json()
    assert b["ok"] is True and b["errors"] == []
    assert b["beat_count"] == 1 and b["image_count"] == 1 and b["character_count"] == 1
    assert b["plan_normalized"] is not None
    assert b["estimated_total_sec"] > 0


def test_validate_accepts_json_string():
    b = _client().post("/api/story/validate", json={"plan": json.dumps(VALID_PLAN)}).json()
    assert b["ok"] is True


def test_validate_parse_fail_is_clean_200():
    r = _client().post("/api/story/validate", json={"plan": "not json {"})
    assert r.status_code == 200 and r.json()["ok"] is False
    assert r.json()["errors"]


def test_validate_empty_timeline_and_no_visual_are_errors():
    b = _client().post("/api/story/validate",
                       json={"plan": {"schema_version": 2, "visuals": [], "timeline": []}}).json()
    assert b["ok"] is False
    assert any("visual" in e for e in b["errors"])
    assert any("timeline" in e or "beat" in e for e in b["errors"])


def test_validate_dangling_ref_is_warning_not_error():
    plan = json.loads(json.dumps(VALID_PLAN))
    plan["timeline"][0]["lines"][0]["speaker_id"] = "nobody"
    b = _client().post("/api/story/validate", json={"plan": plan}).json()
    assert b["ok"] is True                                   # scrubbed, not blocked
    assert any("nobody" in w for w in b["warnings"])


def test_validate_template2_without_video_warns():
    plan = json.loads(json.dumps(VALID_PLAN))
    plan["timeline"][0]["source_audio"] = "duck"
    b = _client().post("/api/story/validate",
                       json={"plan": plan, "has_base_video": False}).json()
    assert any("video" in w.lower() for w in b["warnings"])


# ── B4: strict — paste_json never falls back to AI ────────────────────────────

def _resolve(source, override):
    payload = SimpleNamespace(story_plan_override=override, story_series_id="",
                              story_chapter_no=0, ai_provider="")
    return sp._resolve_story_plan_v2(
        payload, job_id="j", resume_mode=False, source=source, chapter="", idea="",
        duration_sec=0, genre="", language="vi", art_style="", aspect="9:16",
        subtitle_mode="hook_only")


def test_strict_paste_json_valid_override_renders_verbatim():
    plan, meta = _resolve("paste_json", json.dumps(VALID_PLAN))
    assert isinstance(plan, StoryPlan) and meta["plan_source"] == "override"


def test_strict_paste_json_invalid_override_raises_not_ai():
    # invalid (empty timeline/visuals) + strict → RuntimeError BEFORE any AI call
    with pytest.raises(RuntimeError):
        _resolve("paste_json", '{"schema_version": 2}')


def test_strict_paste_json_empty_override_raises():
    with pytest.raises(RuntimeError):
        _resolve("paste_json", "")


# ── run_story_v2 GUARD — paste_json must not be rejected for empty content_script ──
# (regression for the 2026-07-14 bug: the guard raised "empty content_script" and the
#  render failed at 0% because paste_json carries no chapter — it renders from override.)

def _patch_preamble(monkeypatch, sp, tmp_path):
    from types import SimpleNamespace as NS
    monkeypatch.setattr(sp, "setup_render_pipeline",
                        lambda payload: NS(effective_channel="story-verify", output_dir=tmp_path))
    monkeypatch.setattr(sp, "prepare_output_dir", lambda *a, **k: None)
    monkeypatch.setattr(sp, "register_job_log_dir", lambda *a, **k: None)
    monkeypatch.setattr(sp, "upsert_job", lambda *a, **k: None)
    monkeypatch.setattr(sp, "_job_log", lambda *a, **k: None)


def test_run_story_v2_guard_allows_paste_json(monkeypatch, tmp_path):
    _patch_preamble(monkeypatch, sp, tmp_path)

    class _Reached(Exception):
        pass

    def _boom(*a, **k):
        raise _Reached()      # reached plan-resolve → the guard let paste_json through
    monkeypatch.setattr(sp, "_resolve_story_plan_v2", _boom)

    payload = RenderRequest(render_format="story", story_source="paste_json",
                            story_plan_override=json.dumps(VALID_PLAN), output_dir=str(tmp_path))
    with pytest.raises(_Reached):
        sp.run_story_v2("jtest_pj", payload, load_session_fn=lambda *a, **k: None,
                        cleanup_session_fn=lambda *a, **k: None)


def test_run_story_v2_guard_still_blocks_empty_paste(monkeypatch, tmp_path):
    # source=paste with empty content_script MUST still fail — the guard stays intact.
    _patch_preamble(monkeypatch, sp, tmp_path)
    payload = RenderRequest(render_format="story", story_source="paste",
                            content_script="", output_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="content_script"):
        sp.run_story_v2("jtest_paste", payload, load_session_fn=lambda *a, **k: None,
                        cleanup_session_fn=lambda *a, **k: None)
