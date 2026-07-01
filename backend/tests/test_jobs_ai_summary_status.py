"""Audit FINDING-BR11 closure (Batch 10C 2026-06-06).

``GET /api/jobs/{id}/ai-summary`` previously returned ``{available: false}``
when result_json was missing, or a payload with empty fields when the LLM
failed mid-render. The FE renders the AI Analysis card on truthy response
and showed an empty card with no explanation either way.

The endpoint now classifies its response into four explicit ``ai_status``
states plus a human ``status_message`` so the FE can hide the card or
display the message:

- "ok"          — full ranking + best_clip present (default)
- "no_ranking"  — pipeline ran but produced no output_ranking
- "degraded"    — best_clip present but story / director hint missing
- "no_result"   — result_json itself absent (job still running / errored
                  before persisting AI artefacts)

This test file pins the contract by hitting the route through a FastAPI
TestClient with seeded jobs so a future refactor of the classification
logic doesn't silently regress.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _client(tmp_path, monkeypatch):
    """Fresh DB + FastAPI app — exposes a TestClient bound to the same DB."""
    db_path = tmp_path / "ai_summary.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    # Build a minimal FastAPI app with just the jobs router so we don't
    # trigger the full main.py startup (which would re-init the DB at a
    # different path).
    from fastapi import FastAPI
    from app.routes import jobs as jobs_route
    app = FastAPI()
    # jobs_route.router already declares prefix="/api/jobs" — don't double it.
    app.include_router(jobs_route.router)
    return TestClient(app), db_path


def _seed_job(db_path, job_id: str, *, result: dict | None) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage,
                              progress_percent, message, payload_json, result_json,
                              created_at, updated_at)
            VALUES (?, 'render', 'test', 'completed', 'done', 100, '', '{}', ?,
                    datetime('now'), datetime('now'))
            """,
            (job_id, json.dumps(result) if result is not None else None),
        )
        conn.commit()
    finally:
        conn.close()


def test_no_result_returns_explicit_status(_client):
    """result_json missing → ai_status=no_result, available=false, message present."""
    client, db = _client
    _seed_job(db, "job-noresult", result=None)

    resp = client.get("/api/jobs/job-noresult/ai-summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["ai_status"] == "no_result"
    assert body["status_message"]  # non-empty string
    assert "not available" in body["status_message"].lower()


def test_no_ranking_returns_explicit_status(_client):
    """result_json present but output_ranking empty + best_clip None →
    ai_status=no_ranking. This is the common LLM-Call-2-failed case."""
    client, db = _client
    # Empty result_json (parses to {}, but `result` is falsy so we hit
    # no_result). Use a non-empty result_json that still has no ranking.
    _seed_job(db, "job-noranking", result={"segments": [{"start": 0, "end": 5}]})

    resp = client.get("/api/jobs/job-noranking/ai-summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["ai_status"] == "no_ranking"
    assert "ranked" in body["status_message"].lower()
    assert body["output_count"] == 0
    assert body["best_part_no"] is None


def test_degraded_returns_explicit_status(_client):
    """best_clip present + story missing + ai_director not enabled →
    ai_status=degraded. The card should show a partial-data warning, not
    a full analysis."""
    client, db = _client
    _seed_job(db, "job-degraded", result={
        "output_ranking": [
            {"part_no": 1, "output_rank": 1, "output_rank_score": 75.0,
             "ranking_reason": "high hook", "confidence_tier": "strong"}
        ],
        "best_clip": {
            "part_no": 1, "output_rank_score": 75.0, "ranking_reason": "high hook",
            "confidence_tier": "strong",
        },
        # No "story", no "ai_director.enabled".
    })

    resp = client.get("/api/jobs/job-degraded/ai-summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["ai_status"] == "degraded"
    assert body["status_message"]
    assert body["best_part_no"] == 1


def test_ok_status_with_story_and_director(_client):
    """Full happy path: ranking + best_clip + story + director enabled →
    ai_status=ok and status_message is empty (the FE renders the normal
    analysis card)."""
    client, db = _client
    _seed_job(db, "job-ok", result={
        "output_ranking": [
            {"part_no": 1, "output_rank": 1, "output_rank_score": 80.0,
             "ranking_reason": "best hook", "confidence_tier": "strong",
             "is_best_clip": True},
            {"part_no": 2, "output_rank": 2, "output_rank_score": 60.0,
             "ranking_reason": "second", "confidence_tier": "worth_testing"},
        ],
        "best_clip": {"part_no": 1, "output_rank_score": 80.0, "ranking_reason": "best hook"},
        "story": {"description": "A story about a thing"},
        "ai_director": {"enabled": True},
        "segments": [{"start": 0, "end": 5}, {"start": 5, "end": 10}],
    })

    resp = client.get("/api/jobs/job-ok/ai-summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["ai_status"] == "ok"
    assert body["status_message"] == ""
    assert body["output_count"] == 2
    assert body["best_part_no"] == 1


def test_ok_when_best_clip_present_with_story_only(_client):
    """Edge case: best_clip + story present, director not enabled — should
    still classify as ok (story is the load-bearing signal for the card)."""
    client, db = _client
    _seed_job(db, "job-ok-story", result={
        "output_ranking": [{"part_no": 1, "output_rank": 1, "output_rank_score": 70.0}],
        "best_clip": {"part_no": 1, "output_rank_score": 70.0},
        "story": {"description": "Has a story"},
        # ai_director omitted.
    })

    resp = client.get("/api/jobs/job-ok-story/ai-summary")

    body = resp.json()
    assert body["ai_status"] == "ok"


def test_story_model_present_when_column_set(_client):
    """R3 (architecture-review, 2026-06-30): a job that ran with
    ``use_story_intelligence`` persists ``story_model_json``; ai-summary
    surfaces it under the additive ``story_model`` key — distinct from the
    legacy result_json ``story`` field, which stays independent."""
    from app.db.jobs_repo import update_story_model
    client, db = _client
    _seed_job(db, "job-sm", result={
        "output_ranking": [{"part_no": 1, "output_rank": 1, "output_rank_score": 80.0,
                            "is_best_clip": True}],
        "best_clip": {"part_no": 1, "output_rank_score": 80.0},
        "story": {"description": "legacy story"},
        "ai_director": {"enabled": True},
    })
    update_story_model("job-sm", json.dumps({
        "schema_version": 3, "summary": "Whole-film synopsis", "theme": "redemption",
        "characters": [{"name": "A", "role": "hero", "want": "peace"}],
    }))

    body = client.get("/api/jobs/job-sm/ai-summary").json()
    assert body["story_model"] is not None
    assert body["story_model"]["summary"] == "Whole-film synopsis"
    assert body["story_model"]["theme"] == "redemption"
    # Legacy `story` stays independent and unchanged.
    assert body["story"] == {"description": "legacy story"}


def test_story_model_none_when_column_absent(_client):
    """Legacy job (never ran Story Intelligence) → story_model is None so the FE
    can hide the StoryModel card. The rest of the payload is unaffected."""
    client, db = _client
    _seed_job(db, "job-nosm", result={
        "output_ranking": [{"part_no": 1, "output_rank": 1, "output_rank_score": 70.0}],
        "best_clip": {"part_no": 1, "output_rank_score": 70.0},
        "story": {"description": "s"},
        "ai_director": {"enabled": True},
    })
    body = client.get("/api/jobs/job-nosm/ai-summary").json()
    assert body["story_model"] is None


def test_story_model_none_on_malformed_json(_client):
    """Defensive: a corrupt story_model_json must not 500 — _parse_json returns
    {} which the endpoint surfaces as None."""
    from app.db.jobs_repo import update_story_model
    client, db = _client
    _seed_job(db, "job-badsm", result={
        "output_ranking": [{"part_no": 1, "output_rank": 1, "output_rank_score": 70.0}],
        "best_clip": {"part_no": 1, "output_rank_score": 70.0},
        "story": {"description": "s"},
        "ai_director": {"enabled": True},
    })
    update_story_model("job-badsm", "{not valid json")
    resp = client.get("/api/jobs/job-badsm/ai-summary")
    assert resp.status_code == 200
    assert resp.json()["story_model"] is None


def test_unknown_job_returns_404(_client):
    """Audit FINDING-BR11 only touches the available-but-empty cases.
    Unknown-job behaviour must remain a 404 — we pin it here so a future
    refactor of the classification block doesn't accidentally swallow
    the lookup miss into a 200."""
    client, _ = _client
    resp = client.get("/api/jobs/does-not-exist/ai-summary")
    assert resp.status_code == 404
