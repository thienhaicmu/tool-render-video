"""Tests for the Content-mode deterministic duration-fit AI-optimization
(2026-07-04 architecture-review upgrade).

Covers:
  · ContentPlan.fit_to_target_duration — non-destructive reading_speed scaling
  · ContentPlan.estimated_total_sec — spoken + pause estimate
  · POST /api/content/estimate — preflight cost/provider (no render, no LLM)

The fit is deterministic (no LLM), never raises, and NEVER drops a scene —
content is narrative (every scene carries meaning), unlike a recap's redundant
coverage. It only nudges reading_speed within the domain clamp [0.5, 2.0].
"""
from __future__ import annotations

from app.domain.content_plan import ContentPlan, ContentScene


def _plan(n, chars, est, speed=1.0):
    return ContentPlan(scenes=[
        ContentScene(narration="x" * chars, reading_speed=speed, est_duration_sec=est)
        for _ in range(n)
    ])


def test_fit_over_length_speeds_up_to_hit_target():
    p = _plan(4, 450, 30.0)          # 120s of spoken content
    assert round(p.estimated_total_sec(), 1) == 120.0
    r = p.fit_to_target_duration(90.0)
    assert r["changed"] is True
    assert r["scaled_scenes"] == 4
    assert r["in_tolerance"] is True
    assert 88.0 <= p.estimated_total_sec() <= 92.0
    # speeds went UP (faster ⇒ shorter), still within clamp
    assert all(1.0 < s.reading_speed <= 2.0 for s in p.scenes)
    # persisted total refreshed
    assert 88.0 <= p.total_target_sec <= 92.0


def test_fit_near_target_is_noop():
    p = _plan(4, 150, 22.0)          # 88s ≈ 90s target (within 15%)
    r = p.fit_to_target_duration(90.0)
    assert r["changed"] is False
    assert r["in_tolerance"] is True
    assert all(s.reading_speed == 1.0 for s in p.scenes)


def test_fit_estimates_from_chars_when_est_missing():
    p = _plan(3, 300, est=0.0)       # 3 * (300/15) = 60s estimated
    assert round(p.estimated_total_sec(), 1) == 60.0
    r = p.fit_to_target_duration(30.0)
    assert r["changed"] is True
    # needs 2x speed → clamped at max 2.0
    assert all(s.reading_speed == 2.0 for s in p.scenes)


def test_fit_noop_on_unknown_target_or_empty():
    assert ContentPlan(scenes=[ContentScene(narration="a")]).fit_to_target_duration(0)["changed"] is False
    assert ContentPlan(scenes=[]).fit_to_target_duration(60)["changed"] is False


def test_fit_never_drops_scenes():
    p = _plan(5, 600, 40.0)          # 200s, target 30s (extreme)
    n_before = p.scene_count()
    p.fit_to_target_duration(30.0)
    assert p.scene_count() == n_before  # non-destructive — narrative preserved


def test_fit_never_raises_on_garbage():
    p = ContentPlan(scenes=[ContentScene(narration="a", reading_speed=0.0, est_duration_sec=-5.0)])
    # must not raise
    r = p.fit_to_target_duration(10.0)
    assert isinstance(r, dict)


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_estimate_endpoint_local_is_free():
    c = _client()
    plan = {"scenes": [
        {"narration": "x" * 300, "reading_speed": 1.0, "est_duration_sec": 20.0,
         "visual_prompt": "a cat", "asset_suggestion": "ai_image"},
    ]}
    r = c.post("/api/content/estimate", json={"plan": plan, "visual_provider": "local"})
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_cost"] == 0.0
    assert body["by_provider"] == {"local": 1}


def test_estimate_endpoint_budget_downgrades():
    c = _client()
    plan = {"scenes": [
        {"narration": "x" * 300, "est_duration_sec": 20.0,
         "visual_prompt": "a cat", "asset_suggestion": "ai_image"},
    ]}
    r = c.post("/api/content/estimate",
               json={"plan": plan, "visual_provider": "ai_image", "budget_cap": 0.01})
    assert r.status_code == 200
    # 0.04 ai_image cost exceeds 0.01 cap → downgrades (stock/local), never over cap
    assert r.json()["estimated_cost"] <= 0.01


def test_estimate_endpoint_requires_plan_or_script():
    c = _client()
    r = c.post("/api/content/estimate", json={"target_duration": 40})
    assert r.status_code == 422


# ── Narration audit ──────────────────────────────────────────────────────────

def test_narration_audit_flags_overloaded_and_sparse():
    p = ContentPlan(scenes=[
        ContentScene(narration="x" * 600, reading_speed=1.0, est_duration_sec=20.0),  # load 2.0
        ContentScene(narration="y" * 90, reading_speed=1.0, est_duration_sec=20.0),   # load 0.3
        ContentScene(narration="z" * 300, reading_speed=1.0, est_duration_sec=20.0),  # load 1.0
        ContentScene(narration="w" * 50),                                             # no estimate
    ])
    a = p.narration_audit()
    assert a["weak"] is True
    assert a["overloaded"] == 1
    assert a["sparse"] == 1
    assert a["rated"] == 3
    flags = [s["flag"] for s in a["scenes"]]
    assert flags == ["overloaded", "sparse", "ok", "no_estimate"]


def test_narration_audit_healthy_plan_not_weak():
    p = ContentPlan(scenes=[
        ContentScene(narration="x" * 300, reading_speed=1.0, est_duration_sec=20.0)
        for _ in range(3)
    ])
    a = p.narration_audit()
    assert a["weak"] is False
    assert a["overloaded"] == 0


def test_narration_audit_never_raises():
    p = ContentPlan(scenes=[ContentScene(narration="a", reading_speed=0.0, est_duration_sec=-1.0)])
    assert isinstance(p.narration_audit(), dict)
