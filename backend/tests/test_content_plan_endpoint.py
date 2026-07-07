"""GET /jobs/{id}/content-plan — polling / reattach fallback for the
``content.plan.ready`` WS event (item 7, 2026-07-07).

ContentMonitor builds its Director header + rich scene rows from the ``plan``
prop or the one-shot ``content.plan.ready`` WS event. Both are missing when a
running Content job is reattached from the topbar badge (plan prop null; the
plan event fired before the socket connected and is never replayed) and on a
WS→HTTP-polling downgrade. This endpoint returns the PERSISTED ContentPlan so
the FE can re-render the rich monitor in those cases.

Behavioral contract test (runs via TestClient). It pins:
  1. A persisted ContentPlan is returned as a plain dict carrying the rich
     fields the FE ContentPlan / ContentScene types read.
  2. Missing / malformed / plan-with-no-scenes → {available: False}, never 500.
  3. Unknown job → 404.

Mirrors test_recap_plan_endpoint.py.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _client(tmp_path, monkeypatch):
    db_path = tmp_path / "content_plan.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    from fastapi import FastAPI
    from app.routes import jobs as jobs_route
    app = FastAPI()
    app.include_router(jobs_route.router)
    return TestClient(app), db_path


def _seed_job(db_path, job_id: str, *, render_format: str = "content") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage,
                              progress_percent, message, payload_json, result_json,
                              created_at, updated_at)
            VALUES (?, 'render', 'test', 'running', 'rendering', 40, '', ?, '{}',
                    datetime('now'), datetime('now'))
            """,
            (job_id, json.dumps({"render_format": render_format})),
        )
        conn.commit()
    finally:
        conn.close()


def _valid_content_plan_json() -> str:
    from app.domain.content_plan import ContentPlan, ContentScene
    plan = ContentPlan(
        topic="Cách pha cà phê",
        tone="friendly",
        audience="người mới",
        language="vi-VN",
        total_target_sec=48.0,
        subtitle_style="capcut_box",
        bgm_mood="upbeat",
        scenes=[
            ContentScene(index=0, role="hook", narration="Bạn đã pha cà phê đúng chưa?",
                         emotion="curious", reading_speed=1.05, est_duration_sec=7.0,
                         visual_hint="tách cà phê bốc khói", transition_hint="fade",
                         emphasis=["đúng"]),
            ContentScene(index=1, role="body", narration="Đầu tiên, chọn hạt tươi.",
                         emotion="calm", est_duration_sec=9.0, transition_hint="slide"),
        ],
    )
    return plan.to_json()


def test_content_plan_returned_with_rich_fields(_client):
    """A persisted content plan → available True + a plain dict carrying the
    rich fields the FE ContentPlan/ContentScene types read."""
    from app.db.jobs_repo import update_content_plan
    client, db = _client
    _seed_job(db, "job-content")
    update_content_plan("job-content", _valid_content_plan_json())

    body = client.get("/api/jobs/job-content/content-plan").json()

    assert body["available"] is True
    plan = body["plan"]
    assert plan["topic"] == "Cách pha cà phê"
    assert plan["tone"] == "friendly"
    assert plan["subtitle_style"] == "capcut_box"
    assert plan["bgm_mood"] == "upbeat"
    assert plan["total_target_sec"] == 48.0
    assert len(plan["scenes"]) == 2
    s0 = plan["scenes"][0]
    # Rich per-scene fields survive the round-trip.
    assert s0["role"] == "hook"
    assert s0["narration"] == "Bạn đã pha cà phê đúng chưa?"
    assert s0["emotion"] == "curious"
    assert s0["reading_speed"] == 1.05
    assert s0["transition_hint"] == "fade"
    assert s0["emphasis"] == ["đúng"]


def test_no_content_plan_returns_unavailable(_client):
    """A content job whose plan hasn't been produced yet → available False."""
    client, db = _client
    _seed_job(db, "job-noplan")
    body = client.get("/api/jobs/job-noplan/content-plan").json()
    assert body["available"] is False
    assert body["plan"] is None


def test_empty_scenes_plan_returns_unavailable(_client):
    """A plan with no scenes is not useful to the monitor → available False."""
    from app.db.jobs_repo import update_content_plan
    from app.domain.content_plan import ContentPlan
    client, db = _client
    _seed_job(db, "job-emptyscenes")
    update_content_plan("job-emptyscenes", ContentPlan(topic="x").to_json())
    body = client.get("/api/jobs/job-emptyscenes/content-plan").json()
    assert body["available"] is False


def test_malformed_content_plan_does_not_500(_client):
    """Defensive: a corrupt content_plan_json must not 500 the polling path."""
    from app.db.jobs_repo import update_content_plan
    client, db = _client
    _seed_job(db, "job-badplan")
    update_content_plan("job-badplan", "{not valid json")
    resp = client.get("/api/jobs/job-badplan/content-plan")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_unknown_job_returns_404(_client):
    client, _ = _client
    resp = client.get("/api/jobs/does-not-exist/content-plan")
    assert resp.status_code == 404
