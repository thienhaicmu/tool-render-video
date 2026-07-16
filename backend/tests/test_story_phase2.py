"""
Phase 2 — targeted retry / checkpoint / cancel / budget (2026-07-16 review).

Pins:
  * Understanding quote-repair: ONE bounded round fixes rejected verbatim quotes
    instead of discarding the whole compiler run.
  * Structure retry: a coverage-gate rejection re-runs ONLY the structure call,
    with the rejection reasons in the prompt — the approved script is reused.
  * Chunk-local fallback: a failed chunk falls back to single-pass for THAT
    chunk only; paid sibling chunks are kept.
  * Shot-grammar code-fix: broken AI-authored grammar is re-derived by code
    instead of voiding the paid plan.
  * Per-job cancel token + logical-call budget enforced at _observed_call.
  * POST /api/story/plan/async/{id}/cancel sets the job's cancel Event.

Offline: every call_fn is a local fake — no network.
"""
from __future__ import annotations

import json
import threading

import pytest

import app.features.render.ai.llm as L
import app.features.render.ai.llm.story_director_v2 as director
from app.domain.story_plan_v2 import StoryPlan
from app.features.render.ai.llm.story_director_v2 import (
    _observed_call, _rederive_shot_grammar, begin_plan_run, end_plan_run,
    run_super_plan, shot_grammar_gate,
)
from app.features.render.ai.llm.story_understanding import apply_quote_fixes, parse_understanding


@pytest.fixture(autouse=True)
def _reset_run_state(monkeypatch):
    """Run state is thread-local and pytest reuses the thread — DISARM before and
    after each test so an armed budget/cancel never leaks into other tests."""
    monkeypatch.delenv("STORY_MAX_LLM_CALLS_PER_PLAN", raising=False)
    end_plan_run()
    yield
    end_plan_run()


# ── shared scenario (English to keep verbatim-quote matching simple) ──────────

_CHAPTER = (
    "Han Phong entered the great hall with cold eyes and a steady breath. "
    "The elder raised his sword and the wind screamed across the courtyard stones. "
    "In the end Han Phong walked away from the ruined sect gate forever."
)
_GOOD_QUOTE_1 = "entered the great hall with cold eyes"
_BAD_QUOTE_2 = "walked off from the destroyed gate"          # paraphrased → unverifiable
_FIXED_QUOTE_2 = "walked away from the ruined sect gate forever"

_NARR_1 = "Han Phong entered the great hall with cold eyes."
_NARR_2 = "The elder raised his sword against the silence."
_NARR_3 = "Han Phong walked away from the ruined sect gate forever."
_SCRIPT = f"[SCENE: great_hall]\nNARR: {_NARR_1}\nNARR: {_NARR_2}\nNARR: {_NARR_3}\n"


def _understanding_json(quote2: str) -> str:
    return json.dumps({
        "topic": "test", "genre": "drama", "tone": "grim",
        "characters": [{"id": "han_phong", "name": "Han Phong", "role": "protagonist",
                        "gender": "male", "desc": "cold eyes"}],
        "locations": [{"id": "great_hall", "name": "great hall", "desc": ""}],
        "relationships": [], "goals_conflicts": [],
        "events": [
            {"id": "e1", "summary": "Han Phong enters the great hall",
             "characters": ["han_phong"], "location": "great_hall", "time": "",
             "quote": _GOOD_QUOTE_1, "importance": "major"},
            {"id": "e2", "summary": "Han Phong leaves the sect forever",
             "characters": ["han_phong"], "location": "", "time": "",
             "quote": quote2, "importance": "major"},
        ],
    })


def _plan_json(narrations: "list[str]", hook_first: bool = True) -> str:
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


def _run(json_responses, writer_responses, structure_responses, events=None):
    """Drive run_super_plan with scripted per-stage fakes; returns (plan, log)."""
    log = {"json": 0, "writer": 0, "structure": 0, "structure_prompts": [],
           "events": events if events is not None else []}

    def json_fn(sys, usr):
        log["json"] += 1
        return json_responses[min(log["json"] - 1, len(json_responses) - 1)]

    def writer_fn(sys, usr):
        log["writer"] += 1
        return writer_responses[min(log["writer"] - 1, len(writer_responses) - 1)]

    def structure_fn(sys, usr):
        log["structure"] += 1
        log["structure_prompts"].append(usr)
        return structure_responses[min(log["structure"] - 1, len(structure_responses) - 1)]

    plan = run_super_plan(
        call_fn=structure_fn, writer_call_fn=writer_fn, json_call_fn=json_fn,
        source="paste", chapter=_CHAPTER, language="en", ceiling=5,
        provider_label="test", observer=log["events"].append)
    return plan, log


def test_understanding_quote_repair_recovers(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    monkeypatch.setenv("STORY_UNDERSTANDING_REPAIR", "1")
    repair_fix = json.dumps({"events": [{"id": "e2", "quote": _FIXED_QUOTE_2}]})
    plan, log = _run(
        json_responses=[_understanding_json(_BAD_QUOTE_2), repair_fix],
        writer_responses=[_SCRIPT],
        structure_responses=[_plan_json([_NARR_1, _NARR_2, _NARR_3])])
    assert plan is not None
    assert log["json"] == 2             # understanding + ONE quote-repair round
    assert log["structure"] == 1
    stages = [e.get("stage") for e in log["events"] if e.get("event") == "call_started"]
    assert "understanding_repair" in stages


def test_understanding_repair_disabled_falls_back(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    monkeypatch.setenv("STORY_UNDERSTANDING_REPAIR", "0")
    plan, log = _run(
        json_responses=[_understanding_json(_BAD_QUOTE_2)],
        writer_responses=[_SCRIPT],
        # compiler gate fails → the legacy single-pass gets this plan instead
        structure_responses=[_plan_json([_NARR_1, _NARR_2, _NARR_3])])
    assert log["json"] == 1             # no repair round when disabled
    kinds = [e.get("event") for e in log["events"]]
    assert "compiler_fallback" in kinds


def test_structure_retry_with_reasons(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    monkeypatch.setenv("STORY_STRUCTURE_RETRY", "1")
    bad = _plan_json(["totally unrelated banana rocket cheese words"], hook_first=False)
    good = _plan_json([_NARR_1, _NARR_2, _NARR_3])
    plan, log = _run(
        json_responses=[_understanding_json(_FIXED_QUOTE_2)],
        writer_responses=[_SCRIPT],
        structure_responses=[bad, good])
    assert plan is not None
    assert log["structure"] == 2        # ONE bounded structure-only retry
    assert "PREVIOUS ATTEMPT REJECTED" in log["structure_prompts"][1]
    assert "PREVIOUS ATTEMPT REJECTED" not in log["structure_prompts"][0]


def test_structure_retry_disabled_fails_to_legacy(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    monkeypatch.setenv("STORY_STRUCTURE_RETRY", "0")
    # Phase 4: the default structure failure path is now the CODE structurer —
    # pin the PRE-Phase-4 legacy fallback explicitly for this kill-switch test.
    monkeypatch.setenv("STORY_STRUCTURE_BY_CODE", "0")
    bad = _plan_json(["totally unrelated banana rocket cheese words"], hook_first=False)
    plan, log = _run(
        json_responses=[_understanding_json(_FIXED_QUOTE_2)],
        writer_responses=[_SCRIPT],
        structure_responses=[bad])
    # kill-switch: no retry; compiler falls back to legacy (which reuses the
    # same structure fake and its plan then fails/succeeds independently).
    kinds = [e.get("event") for e in log["events"]]
    assert "compiler_fallback" in kinds


def test_apply_quote_fixes_merges_only_named_events():
    u = parse_understanding(_understanding_json(_BAD_QUOTE_2))
    n = apply_quote_fixes(u, json.dumps({"events": [
        {"id": "e2", "quote": _FIXED_QUOTE_2},
        {"id": "ghost", "quote": "not an event"},
    ]}))
    assert n == 1
    assert u.events[1].quote == _FIXED_QUOTE_2
    assert u.events[0].quote == _GOOD_QUOTE_1          # untouched
    assert apply_quote_fixes(u, "not json") == 0


# ── shot-grammar code-fix ─────────────────────────────────────────────────────

def test_rederive_fixes_broken_authored_grammar():
    beats = [{"id": f"b{i}", "visual_id": "v1", "narration": f"beat {i}",
              "shot_id": f"sh{i}"} for i in range(1, 7)]
    plan = StoryPlan._from_dict({
        "topic": "t", "language": "en",
        "characters": [], "settings": [{"id": "s1", "name": "s1"}],
        "visuals": [{"id": "v1", "setting_id": "s1"}],
        "timeline": beats,
        "scenes": [{"id": "sc1", "setting_id": "s1",
                    "beat_ids": [b["id"] for b in beats],
                    "shot_ids": [b["shot_id"] for b in beats]}],
        # authored grammar: SAME setup on all six shots → repetition + no
        # establishing + no size variety → the gate must fail.
        "shots": [{"id": f"sh{i}", "scene_id": "sc1", "beat_ids": [f"b{i}"],
                   "visual_id": "v1", "shot_size": "medium", "angle": "eye_level",
                   "motion_intent": "static"} for i in range(1, 7)],
    })
    assert shot_grammar_gate(plan)                     # broken as authored
    fixed = _rederive_shot_grammar(plan)
    assert shot_grammar_gate(fixed) == []              # code grammar passes


# ── cancel + budget at the single enforcement point ───────────────────────────

def test_budget_blocks_further_calls(monkeypatch):
    monkeypatch.setenv("STORY_MAX_LLM_CALLS_PER_PLAN", "2")
    begin_plan_run(None)
    calls = {"n": 0}
    events = []

    def _fn(sys, usr):
        calls["n"] += 1
        return "ok"

    assert _observed_call(_fn, "s", "u", stage="a", observer=events.append) == "ok"
    assert _observed_call(_fn, "s", "u", stage="b", observer=events.append) == "ok"
    assert _observed_call(_fn, "s", "u", stage="c", observer=events.append) is None
    assert calls["n"] == 2
    blocked = [e for e in events if e.get("event") == "call_blocked"]
    assert blocked and blocked[0]["reason"] == "budget_exhausted"


def test_cancel_blocks_calls():
    ev = threading.Event()
    ev.set()
    begin_plan_run(ev)
    calls = {"n": 0}
    events = []
    out = _observed_call(lambda s, u: calls.__setitem__("n", 1) or "x",
                         "s", "u", stage="a", observer=events.append)
    assert out is None and calls["n"] == 0
    assert [e for e in events if e.get("event") == "call_blocked"][0]["reason"] == "cancelled"


def test_generate_story_plan_cancel_short_circuits(monkeypatch):
    attempted = []
    monkeypatch.setattr(L, "_get_story_call_fn",
                        lambda p, k, m: (attempted.append(p) or None))
    ev = threading.Event()
    ev.set()
    out = L.generate_story_plan_v2(provider="openai", source="paste",
                                   chapter="text", api_key="k",
                                   resolve_key=lambda _p: "k", cancel_event=ev)
    assert out is None
    assert attempted == []              # no provider attempt after cancel


# ── router cancel endpoint ────────────────────────────────────────────────────

def test_plan_async_cancel_endpoint():
    import app.features.story.router as story_router
    job_id = "a" * 32
    ev = threading.Event()
    with story_router._PLAN_JOBS_LOCK:
        story_router._PLAN_JOBS[job_id] = {
            "status": "running", "created": 0.0, "cancel": ev, "progress": {}}
    try:
        out = story_router.plan_storyboard_async_cancel(job_id)
        assert ev.is_set()
        assert out["status"] == "cancelling"
        status = story_router.plan_storyboard_async_status(job_id)
        assert status["status"] == "cancelling"
    finally:
        with story_router._PLAN_JOBS_LOCK:
            story_router._PLAN_JOBS.pop(job_id, None)


def test_plan_async_cancel_unknown_404():
    from fastapi import HTTPException
    import app.features.story.router as story_router
    with pytest.raises(HTTPException):
        story_router.plan_storyboard_async_cancel("f" * 32)


# ── chunk-local fallback ──────────────────────────────────────────────────────

def test_chunk_local_fallback_keeps_siblings(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    monkeypatch.setenv("STORY_CHUNK_LOCAL_FALLBACK", "1")
    long_chapter = ("Han Phong walked the long road. " * 4200).strip()  # > 60k chars
    compiler_calls = {"n": 0}

    def _fake_compiler(**kwargs):
        compiler_calls["n"] += 1
        if compiler_calls["n"] == 1:
            return None                                    # first chunk fails
        return StoryPlan.from_json(_plan_json([_NARR_1, _NARR_2, _NARR_3]))

    fallback_stages = []

    def _fake_call_and_parse(call_fn, sysm, user, ceiling, **kw):
        fallback_stages.append(kw.get("stage", ""))
        return StoryPlan.from_json(_plan_json([_NARR_1, _NARR_2, _NARR_3]))

    monkeypatch.setattr(director, "_run_compiler", _fake_compiler)
    monkeypatch.setattr(director, "_call_and_parse", _fake_call_and_parse)
    plan = run_super_plan(
        call_fn=lambda s, u: None, writer_call_fn=lambda s, u: None,
        json_call_fn=lambda s, u: None, source="paste", chapter=long_chapter,
        language="en", ceiling=6, provider_label="test")
    assert plan is not None
    assert compiler_calls["n"] >= 2                       # siblings still compiled
    assert any(s.startswith("chunk_") and s.endswith("_single_pass")
               for s in fallback_stages)                  # only chunk 1 fell back
    assert len([s for s in fallback_stages if s.endswith("_single_pass")]) == 1
