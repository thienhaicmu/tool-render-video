"""Story Mode v2 — Phase 4 (Q3): auto character reference sheets for consistency.

Covers: the reference-sheet generator accepts a v2 CharacterDef (canonical_desc) and
is content-addressed (generate once, then cache-hit); the pipeline fills
plan.render.refs ONLY for provider='gpt_image', skips Pollinations, and honours the
STORY_REFERENCE_SHEETS kill-switch. All gpt-image-1 calls are mocked (no cost).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app.features.render.engine.pipeline.story_pipeline_v2 as sp2
from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Visual
from app.features.render.engine.visual import story_reference_sheet as rs


# ── generator: v2 CharacterDef + cache ───────────────────────────────────────

def test_refsheet_reads_canonical_desc_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "_ASSETS_DIR", tmp_path)
    calls = {"n": 0}

    def fake_bytes(prompt, w, h, quality="medium", **kw):
        calls["n"] += 1
        assert "ao trang" in prompt          # subject came from canonical_desc
        assert quality == "high"
        return b"\x89PNG" + b"0" * 2048

    monkeypatch.setattr(rs, "generate_image_bytes", fake_bytes)
    c = SimpleNamespace(id="han", name="Han", canonical_desc="ao trang, kiem bac")
    p1 = rs.generate_character_reference_sheet(c, art_style="wuxia")
    assert p1 and Path(p1).exists()
    p2 = rs.generate_character_reference_sheet(c, art_style="wuxia")   # identical → cache hit
    assert p2 == p1
    assert calls["n"] == 1                    # generated once, second served from disk


def test_refsheet_none_without_subject(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "_ASSETS_DIR", tmp_path)
    monkeypatch.setattr(rs, "generate_image_bytes", lambda *a, **k: b"x" * 4096)
    assert rs.generate_character_reference_sheet(SimpleNamespace(id="", name="", canonical_desc="")) is None


# ── pipeline: gpt_image only, env kill-switch ────────────────────────────────

def _plan() -> StoryPlan:
    return StoryPlan(
        characters=[CharacterDef(id="han", name="Han", canonical_desc="x")],
        visuals=[Visual(id="v1", prompt="p", character_ids=["han"]),
                 Visual(id="v2", prompt="q")],  # v2 has no character → not requested
    )


def _mute_pipeline(monkeypatch):
    monkeypatch.setattr(sp2, "update_story_plan", lambda *a, **k: None)
    monkeypatch.setattr(sp2, "_emit_render_event", lambda *a, **k: None)


def test_pipeline_fills_refs_for_gpt_image(monkeypatch):
    _mute_pipeline(monkeypatch)
    monkeypatch.setattr(rs, "generate_character_reference_sheet", lambda c, art_style="": "/tmp/ref_han.png")
    plan = _plan()
    sp2._generate_reference_sheets(plan, "wuxia", job_id="j", effective_channel="c", provider="gpt_image")
    assert plan.render.refs == {"han": "/tmp/ref_han.png"}


def test_pipeline_skips_pollinations(monkeypatch):
    _mute_pipeline(monkeypatch)
    monkeypatch.setattr(rs, "generate_character_reference_sheet",
                        lambda c, art_style="": (_ for _ in ()).throw(AssertionError("must not gen for free")))
    plan = _plan()
    sp2._generate_reference_sheets(plan, "", job_id="j", effective_channel="c", provider="pollinations")
    assert plan.render.refs == {}


def test_pipeline_env_kill_switch(monkeypatch):
    _mute_pipeline(monkeypatch)
    monkeypatch.setenv("STORY_REFERENCE_SHEETS", "0")
    monkeypatch.setattr(rs, "generate_character_reference_sheet",
                        lambda c, art_style="": (_ for _ in ()).throw(AssertionError("kill-switch failed")))
    plan = _plan()
    sp2._generate_reference_sheets(plan, "", job_id="j", effective_channel="c", provider="gpt_image")
    assert plan.render.refs == {}


def test_pipeline_no_double_gen_when_ref_present(monkeypatch):
    _mute_pipeline(monkeypatch)
    calls = {"n": 0}

    def _gen(c, art_style=""):
        calls["n"] += 1
        return "/tmp/ref.png"

    monkeypatch.setattr(rs, "generate_character_reference_sheet", _gen)
    plan = _plan()
    plan.render.refs["han"] = "/already/pinned.png"      # already have one
    sp2._generate_reference_sheets(plan, "", job_id="j", effective_channel="c", provider="gpt_image")
    assert plan.render.refs["han"] == "/already/pinned.png"
    assert calls["n"] == 0                                # skipped — no regen
