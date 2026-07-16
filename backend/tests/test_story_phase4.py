"""
Phase 4 — structure-by-code + quality/cost modes (2026-07-16 review).

Pins:
  * story_script_structurer builds a StoryPlan deterministically from the
    Writer's script: settings per [SCENE:], one visual per setting, NARR →
    narrator beat, a dialogue run → one lines[] beat (or per-line beats when
    multiline is off), known speakers fuzzy-matched to Understanding ids,
    unknown speakers added, first beat hooked — wording verbatim (coverage ≈1).
  * STORY_STRUCTURE_BY_CODE: "1"/economy → the structure LLM is never called;
    "fallback" (default) → replaces the legacy re-buy when the LLM structure
    attempt + bounded retry fail; "0" → pre-Phase-4 behaviour.
  * Quality modes: economy rides mini for ALL roles, premium disables mini —
    resolved in generate_story_plan_v2 (request field > STORY_QUALITY_MODE env).
  * estimate_super_plan_cost prices modes distinctly (economy < balanced < premium).

Offline: every call_fn is a local fake — no network.
"""
from __future__ import annotations

import json

import pytest

import app.features.render.ai.llm as L
from app.features.render.ai.llm.story_director_v2 import (
    end_plan_run, estimate_super_plan_cost, run_super_plan,
)
from app.features.render.ai.llm.story_script_structurer import structure_script_by_code
from app.features.render.ai.llm.story_understanding import (
    parse_understanding, validate_plan_coverage,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("STORY_QUALITY_MODE", "STORY_STRUCTURE_BY_CODE", "STORY_MINI_ROUTING",
                "STORY_MINI_MODEL", "STORY_SUPER_MODEL", "STORY_PROVIDER_FALLBACK",
                "STORY_MULTILINE_BEATS", "STORY_MAX_LLM_CALLS_PER_PLAN",
                "STORY_STRUCTURE_MODEL", "STORY_WRITER_MODEL", "STORY_UNDERSTANDING_MODEL"):
        monkeypatch.delenv(var, raising=False)
    end_plan_run()
    yield
    end_plan_run()


_CHAPTER = (
    "Han Phong entered the great hall with cold eyes and a steady breath. "
    "The elder raised his sword and the wind screamed across the courtyard stones. "
    "In the end Han Phong walked away from the ruined sect gate forever."
)
_UND_JSON = json.dumps({
    "topic": "the fall of a sect", "genre": "wuxia", "tone": "grim",
    "characters": [{"id": "han_phong", "name": "Han Phong", "role": "protagonist",
                    "gender": "male", "desc": "cold eyes"}],
    "locations": [{"id": "great_hall", "name": "great hall", "desc": ""}],
    "relationships": [], "goals_conflicts": [],
    "events": [
        {"id": "e1", "summary": "Han Phong enters the great hall",
         "characters": ["han_phong"], "location": "great_hall", "time": "",
         "quote": "entered the great hall with cold eyes", "importance": "major"},
        {"id": "e2", "summary": "Han Phong leaves forever",
         "characters": ["han_phong"], "location": "", "time": "",
         "quote": "walked away from the ruined sect gate forever", "importance": "major"},
    ],
})
_NARR_1 = "Han Phong entered the great hall with cold eyes."
_NARR_2 = "The elder raised his sword against the silence."
_NARR_3 = "Han Phong walked away from the ruined sect gate forever."
_SCRIPT = f"[SCENE: great_hall]\nNARR: {_NARR_1}\nNARR: {_NARR_2}\nNARR: {_NARR_3}\n"

_SCRIPT_DIALOGUE = (
    "[SCENE: great_hall]\n"
    f"NARR: {_NARR_1}\n"
    'Han Phong (angry): "You will regret this."\n'
    'Elder Mo: "Kneel."\n'
    "[SCENE: sect_gate]\n"
    f"NARR: {_NARR_3}\n"
)


def _plan_json(narrations, hook_first=True):
    return json.dumps({
        "topic": "test", "language": "en",
        "characters": [{"id": "han_phong", "name": "Han Phong"}],
        "settings": [{"id": "great_hall", "name": "great hall"}],
        "visuals": [{"id": "v1", "setting_id": "great_hall"}],
        "timeline": [
            {"id": f"b{i}", "visual_id": "v1", "narration": t,
             **({"hook": True} if (i == 1 and hook_first) else {})}
            for i, t in enumerate(narrations, start=1)
        ],
    })


# ── structurer unit ───────────────────────────────────────────────────────────

def test_structurer_builds_plan_verbatim():
    u = parse_understanding(_UND_JSON)
    plan = structure_script_by_code(_SCRIPT_DIALOGUE, u, language="en",
                                    ceiling=10, multiline=True)
    assert plan is not None
    assert len(plan.settings) == 2 and len(plan.visuals) == 2
    assert plan.timeline[0].hook is True
    # dialogue run → ONE beat with two lines; speakers resolved.
    dlg = next(b for b in plan.timeline if b.effective_lines() and
               any(ln.speaker_id for ln in b.effective_lines()))
    speakers = [ln.speaker_id for ln in dlg.effective_lines()]
    assert "han_phong" in speakers                      # fuzzy-matched to canon id
    assert any(s and s != "han_phong" for s in speakers)  # Elder Mo added as new
    emotions = [ln.emotion for ln in dlg.effective_lines()]
    assert "angry" in emotions
    cov = validate_plan_coverage(_SCRIPT_DIALOGUE, plan)
    assert cov["coverage"] >= 0.9 and cov["order_coverage"] >= 0.9


def test_structurer_multiline_off_per_line_beats():
    u = parse_understanding(_UND_JSON)
    plan = structure_script_by_code(_SCRIPT_DIALOGUE, u, language="en",
                                    ceiling=10, multiline=False)
    assert plan is not None
    spoken = [b for b in plan.timeline if (b.speaker_id or "")]
    assert len(spoken) == 2                             # one beat per dialogue line
    assert spoken[0].narration == "You will regret this."


def test_structurer_rejects_empty():
    assert structure_script_by_code("", None) is None
    assert structure_script_by_code("   \n  ", None) is None


# ── director integration ──────────────────────────────────────────────────────

def _run(structure_responses, monkeypatch=None, quality_mode="", env=None):
    if monkeypatch is not None:
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
    log = {"structure": 0, "events": []}

    def structure_fn(sys, usr):
        log["structure"] += 1
        return structure_responses[min(log["structure"] - 1, len(structure_responses) - 1)]

    plan = run_super_plan(
        call_fn=structure_fn, writer_call_fn=lambda s, u: _SCRIPT,
        json_call_fn=lambda s, u: _UND_JSON, source="paste", chapter=_CHAPTER,
        language="en", ceiling=5, provider_label="test",
        quality_mode=quality_mode, observer=log["events"].append)
    return plan, log


def test_structure_by_code_always_skips_llm(monkeypatch):
    plan, log = _run([_plan_json([_NARR_1])], monkeypatch,
                     env={"STORY_STRUCTURE_BY_CODE": "1", "STORY_COMPILER": "1"})
    assert plan is not None
    assert log["structure"] == 0                        # structure LLM never called
    assert any(e.get("event") == "validation" and e.get("stage") == "structure_code"
               and e.get("passed") for e in log["events"])


def test_economy_mode_forces_code_structure(monkeypatch):
    plan, log = _run([_plan_json([_NARR_1])], monkeypatch,
                     env={"STORY_COMPILER": "1"}, quality_mode="economy")
    assert plan is not None
    assert log["structure"] == 0


def test_fallback_replaces_legacy_rebuy(monkeypatch):
    bad = _plan_json(["totally unrelated banana rocket cheese words"], hook_first=False)
    plan, log = _run([bad], monkeypatch, env={"STORY_COMPILER": "1"})  # default: fallback
    assert plan is not None
    assert log["structure"] == 2                        # attempt + bounded retry
    kinds = [e.get("event") for e in log["events"]]
    assert "compiler_fallback" not in kinds             # legacy re-buy is gone
    assert any(e.get("event") == "validation" and e.get("stage") == "structure_code"
               for e in log["events"])


def test_code_fallback_kill_switch_restores_legacy(monkeypatch):
    bad = _plan_json(["totally unrelated banana rocket cheese words"], hook_first=False)
    plan, log = _run([bad], monkeypatch,
                     env={"STORY_COMPILER": "1", "STORY_STRUCTURE_BY_CODE": "0"})
    kinds = [e.get("event") for e in log["events"]]
    assert "compiler_fallback" in kinds                 # pre-Phase-4 behaviour


# ── quality-mode routing ──────────────────────────────────────────────────────

def _routes(monkeypatch, *, quality_mode="", env=None):
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(L, "_get_story_call_fn", lambda p, k, m: None)
    events = []
    out = L.generate_story_plan_v2(
        provider="openai", source="paste", chapter="text", api_key="k",
        resolve_key=lambda _p: "k", observer=events.append, quality_mode=quality_mode)
    assert out is None
    return [e for e in events if e.get("event") == "provider_attempt"][0]["role_routes"]


def test_economy_routes_everything_mini(monkeypatch):
    routes = _routes(monkeypatch, quality_mode="economy")
    assert routes["understanding"]["model"] == "gpt-4o-mini"
    assert routes["structure"]["model"] == "gpt-4o-mini"
    assert routes["writer"]["model"] == "gpt-4o-mini"


def test_premium_routes_everything_super(monkeypatch):
    routes = _routes(monkeypatch, quality_mode="premium")
    assert routes["understanding"]["model"] == "gpt-4o"
    assert routes["structure"]["model"] == "gpt-4o"
    assert routes["writer"]["model"] == "gpt-4o"


def test_quality_mode_env_fallback(monkeypatch):
    routes = _routes(monkeypatch, env={"STORY_QUALITY_MODE": "premium"})
    assert routes["structure"]["model"] == "gpt-4o"


# ── estimator + request surface ───────────────────────────────────────────────

def test_estimate_mode_ordering(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    eco = estimate_super_plan_cost(source_chars=15000, ceiling=10,
                                   source="paste", quality_mode="economy")
    bal = estimate_super_plan_cost(source_chars=15000, ceiling=10,
                                   source="paste", quality_mode="balanced")
    pre = estimate_super_plan_cost(source_chars=15000, ceiling=10,
                                   source="paste", quality_mode="premium")
    assert eco["cost_usd"] < bal["cost_usd"] < pre["cost_usd"]
    assert eco["llm_calls"] == 2                        # understanding + writer
    idea = estimate_super_plan_cost(source_chars=800, ceiling=10,
                                    source="idea", quality_mode="economy")
    assert idea["llm_calls"] == 1                       # writer only


def test_plan_request_accepts_quality_mode():
    from app.features.story.router import StoryPlanRequest
    req = StoryPlanRequest(source="idea", idea="x", quality_mode="economy")
    assert req.quality_mode == "economy"
    assert StoryPlanRequest(source="idea", idea="x").quality_mode == ""
