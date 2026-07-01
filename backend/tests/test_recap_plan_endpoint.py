"""Phase 5 / R4 (architecture-review, 2026-06-30) — GET /jobs/{id}/recap-plan.

Polling fallback for the recap.plan.ready WS event. When WebSocket is blocked
(offline-first / corporate proxy), RecapLiveView fetches this endpoint instead
so its timeline still renders.

This is a BEHAVIORAL contract test (the endpoint runs via TestClient, unlike
the WS emit which needs a full render context). It pins:

  1. A persisted RecapPlan is re-projected into the {episodes, scenes[...]}
     shape with the EXACT scene-block key set the FE RecapSceneBlock reads.
  2. story_model rides along (StoryModelCard over polling).
  3. Missing / malformed / non-recap plans return {available: False}, never 500.
  4. Unknown job → 404.

The scene-block key set mirrors ``test_recap_plan_ready_ws_shape.py`` and the
FE ``RecapSceneBlock`` interface — keep all three in lockstep.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

# Must match test_recap_plan_ready_ws_shape.py::_EXPECTED_SCENE_KEYS and the FE
# RecapSceneBlock interface in frontend/src/websocket/events.ts.
_EXPECTED_SCENE_KEYS = {"n", "ep", "act", "start", "end", "dur", "title", "mode", "climax"}


@pytest.fixture
def _client(tmp_path, monkeypatch):
    db_path = tmp_path / "recap_plan.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    from fastapi import FastAPI
    from app.routes import jobs as jobs_route
    app = FastAPI()
    app.include_router(jobs_route.router)
    return TestClient(app), db_path


def _seed_job(db_path, job_id: str, *, render_format: str = "recap") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage,
                              progress_percent, message, payload_json, result_json,
                              created_at, updated_at)
            VALUES (?, 'render', 'test', 'completed', 'done', 100, '', ?, '{}',
                    datetime('now'), datetime('now'))
            """,
            (job_id, json.dumps({"render_format": render_format})),
        )
        conn.commit()
    finally:
        conn.close()


def _valid_recap_plan_json() -> str:
    from app.domain.recap_plan import RecapPlan, Episode, Act, RecapScene, StoryModel
    plan = RecapPlan(
        total_target_sec=90.0,
        story=StoryModel(summary="A whole-film synopsis.", theme="hope"),
        episodes=[Episode(title="Tập 1", acts=[
            Act(title="Setup", beat="setup", scenes=[
                RecapScene(start=0.0, end=30.0, title="Scene A", is_climax=False),
                RecapScene(start=30.0, end=60.0, title="Scene B", is_climax=True),
            ]),
        ])],
    )
    return plan.to_json()


def test_recap_plan_projected_with_fe_scene_keys(_client):
    """A persisted recap plan → {episodes, scenes[...]} with EXACTLY the FE
    RecapSceneBlock key set, plus story_model for the StoryModelCard."""
    from app.db.jobs_repo import update_recap_plan
    client, db = _client
    _seed_job(db, "job-recap", render_format="recap")
    update_recap_plan("job-recap", _valid_recap_plan_json())

    body = client.get("/api/jobs/job-recap/recap-plan").json()

    assert body["available"] is True
    assert len(body["scenes"]) == 2
    assert set(body["scenes"][0].keys()) == _EXPECTED_SCENE_KEYS, (
        "recap-plan endpoint scene-block keys drifted from the FE "
        "RecapSceneBlock interface / the WS recap.plan.ready shape."
    )
    # Part order + climax flag survive the projection.
    assert body["scenes"][0]["n"] == 1
    assert body["scenes"][1]["climax"] is True
    # Episode shape mirrors FE RecapEpisodeInfo.
    assert body["episodes"][0] == {"title": "Tập 1", "acts": 1, "scenes": 2}
    # StoryModel rides along for StoryModelCard over polling.
    assert body["story_model"]["theme"] == "hope"
    assert body["story_model"]["summary"] == "A whole-film synopsis."


def test_no_recap_plan_returns_unavailable(_client):
    """A recap job whose plan hasn't been produced yet → available False (not
    an error) so the FE keeps polling / hides the view."""
    client, db = _client
    _seed_job(db, "job-noplan", render_format="recap")
    body = client.get("/api/jobs/job-noplan/recap-plan").json()
    assert body["available"] is False
    assert body["scenes"] == []


def test_malformed_recap_plan_does_not_500(_client):
    """Defensive: a corrupt recap_plan_json must not 500 the polling path."""
    from app.db.jobs_repo import update_recap_plan
    client, db = _client
    _seed_job(db, "job-badplan", render_format="recap")
    update_recap_plan("job-badplan", "{not valid json")
    resp = client.get("/api/jobs/job-badplan/recap-plan")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_unknown_job_returns_404(_client):
    client, _ = _client
    resp = client.get("/api/jobs/does-not-exist/recap-plan")
    assert resp.status_code == 404
