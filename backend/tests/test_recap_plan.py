"""Recap/Review Film mode — R1 foundation (RecapPlan, parser, prompt, persistence).

Pure logic + an isolated-DB persistence round-trip. No live LLM/FFmpeg.
See docs/RECAP_REVIEW_SPEC.md.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.domain.recap_plan import RecapPlan
from app.features.render.ai.llm.recap_parser import parse_recap_response
from app.features.render.ai.llm.recap_prompts import build_recap_prompt


# ── Domain ───────────────────────────────────────────────────────────────────

def test_recapplan_roundtrip_and_flatten():
    raw = json.dumps({
        "total_target_sec": 600,
        "acts": [
            {"title": "Setup", "beat": "setup", "scenes": [
                {"start": 10, "end": 40, "narration_intent": "intro", "is_climax": False},
                {"start": 120, "end": 150, "is_climax": True},
            ]},
            {"title": "Climax", "beat": "climax", "scenes": [
                {"start": 3000, "end": 3060, "is_climax": True},
            ]},
        ],
    })
    p = RecapPlan.from_json(raw)
    assert p is not None
    assert len(p.acts) == 2 and p.scene_count() == 3
    assert len(p.scenes()) == 3
    assert sum(1 for s in p.scenes() if s.is_climax) == 2
    # deterministic round-trip
    assert RecapPlan.from_json(p.to_json()).to_json() == p.to_json()


def test_recapplan_defensive():
    assert RecapPlan.from_json(None) is None
    assert RecapPlan.from_json("not json {") is None
    assert RecapPlan.from_json("[1,2,3]") is None       # non-dict
    assert RecapPlan.from_json("{}") is not None          # empty but valid → no acts


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parser_clamps_scene_to_duration():
    raw = '{"total_target_sec":600,"acts":[{"title":"A","beat":"setup","scenes":[{"start":10,"end":9999}]}]}'
    plan = parse_recap_response(raw, video_duration=300.0)
    assert plan is not None
    assert plan.scenes()[0].end == 300.0          # clamped to film duration


def test_parser_drops_invalid_scenes_and_empty_acts():
    raw = (
        '{"acts":[{"title":"A","scenes":[{"start":5,"end":5},{"start":6,"end":6.1}]},'  # both invalid → act dropped
        '{"title":"B","scenes":[{"start":10,"end":40}]}]}'
    )
    plan = parse_recap_response(raw, video_duration=300.0)
    assert plan is not None
    assert len(plan.acts) == 1 and plan.acts[0].title == "B"


def test_parser_total_clamped_to_duration_and_fallback():
    raw = '{"total_target_sec":99999,"acts":[{"scenes":[{"start":0,"end":30}]}]}'
    plan = parse_recap_response(raw, video_duration=300.0)
    assert plan is not None and 0 < plan.total_target_sec <= 300.0


def test_parser_none_safe():
    assert parse_recap_response("", 300.0) is None
    assert parse_recap_response("no json here", 300.0) is None
    assert parse_recap_response('{"acts":[]}', 300.0) is None    # no usable acts


def test_parser_strips_code_fence():
    raw = '```json\n{"acts":[{"scenes":[{"start":0,"end":30}]}]}\n```'
    assert parse_recap_response(raw, 300.0) is not None


# ── Prompt ───────────────────────────────────────────────────────────────────

def test_recap_prompt_shape():
    system, user = build_recap_prompt("[0-30] scene one\n[30-60] scene two", 1800.0, "vi-VN", tone="cinematic")
    assert "recap" in system.lower()
    assert "1800" in user                       # film duration injected
    assert '"acts"' in user                     # output schema present
    assert "{{" not in user and "}}" not in user  # no format-brace leak


# ── Persistence (isolated DB) ────────────────────────────────────────────────

@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "recap.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    return db_path


def _insert_job(db_path, job_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status) VALUES (?, 'render', 'test', 'running')",
            (job_id,),
        )
        conn.commit()
    finally:
        conn.close()


def test_recap_plan_persistence_roundtrip(_isolated_db):
    from app.db.jobs_repo import get_recap_plan, update_recap_plan
    _insert_job(_isolated_db, "job_recap_1")
    assert get_recap_plan("job_recap_1") is None      # NULL initially
    blob = RecapPlan.from_json('{"total_target_sec":120,"acts":[{"scenes":[{"start":0,"end":30}]}]}').to_json()
    update_recap_plan("job_recap_1", blob)
    assert get_recap_plan("job_recap_1") == blob
    update_recap_plan("job_recap_1", None)            # clear
    assert get_recap_plan("job_recap_1") is None
    assert get_recap_plan("missing_job") is None      # defensive


def test_recap_plan_column_exists_after_migration(_isolated_db):
    conn = sqlite3.connect(str(_isolated_db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    finally:
        conn.close()
    assert "recap_plan_json" in cols
