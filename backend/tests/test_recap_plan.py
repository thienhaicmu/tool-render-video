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


def test_scored_from_recap_plan_shape():
    from app.features.render.engine.pipeline.recap_pipeline import _scored_from_recap_plan
    plan = RecapPlan.from_json(json.dumps({
        "acts": [
            {"title": "A", "beat": "setup", "scenes": [
                {"start": 0, "end": 30}, {"start": 40, "end": 70, "is_climax": True},
            ]},
            {"title": "B", "beat": "climax", "scenes": [{"start": 100, "end": 130}]},
        ],
    }))
    scored = _scored_from_recap_plan(plan)
    assert len(scored) == 3
    # chronological + act grouping preserved
    assert [s["start"] for s in scored] == [0.0, 40.0, 100.0]
    assert scored[0]["act_index"] == 0 and scored[2]["act_index"] == 1
    assert scored[1]["is_climax"] is True
    # every entry has the keys the render loop / part_renderer reads
    for s in scored:
        assert {"start", "end", "duration", "viral_score", "clip_name", "source"} <= set(s)
        assert s["source"] == "recap"


def test_recap_scene_carries_editorial_hint():
    """R3 — each recap scene composes a DIRECTOR'S INTENT (act context +
    narration_intent) that steers the per-scene narration."""
    from app.features.render.engine.pipeline.recap_pipeline import _scored_from_recap_plan
    plan = RecapPlan.from_json(json.dumps({
        "acts": [{"title": "Mo dau", "beat": "setup", "scenes": [
            {"start": 0, "end": 30, "narration_intent": "introduce the hero"},
        ]}],
    }))
    s = _scored_from_recap_plan(plan)[0]
    assert "Recap Act 1/1" in s["editorial_hint"]
    assert "introduce the hero" in s["editorial_hint"]
    assert s["narration_intent"] == "introduce the hero"


def test_editorial_hint_in_rewrite_prompt():
    """R3 — editorial_hint surfaces a DIRECTOR'S INTENT line; empty = no line."""
    from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt
    _, u = build_rewrite_prompt("[0-5] a", 5.0, "vi-VN", editorial_hint="[Recap Act 1/3] he buys a car")
    assert "DIRECTOR'S INTENT" in u and "buys a car" in u
    _, u2 = build_rewrite_prompt("[0-5] a", 5.0, "vi-VN")
    assert "DIRECTOR'S INTENT" not in u2


def test_narration_srt_voice_only_and_speed_mapped(tmp_path):
    """R3b — narration SRT: voice segments only (skip 'original'), timestamps
    mapped to the final timeline (source/speed)."""
    from app.features.render.engine.stages.recap_narration_subtitle import build_narration_srt
    segs = [
        {"kind": "voice", "start": 0, "end": 4, "text": "opening"},
        {"kind": "original", "start": 4, "end": 7},          # skipped (no caption)
        {"kind": "voice", "start": 6, "end": 9, "text": "climax"},
    ]
    out = tmp_path / "n.srt"
    assert build_narration_srt(segs, speed=2.0, out_path=str(out)) is True
    body = out.read_text(encoding="utf-8")
    assert "opening" in body and "climax" in body
    # speed=2 → source 0-4s maps to final 0-2s
    assert "00:00:00,000 --> 00:00:02,000" in body
    # 'original' window produced no caption → only 2 cue indices
    assert body.count(" --> ") == 2


def test_narration_srt_empty_when_no_voice():
    from app.features.render.engine.stages.recap_narration_subtitle import build_narration_srt
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".srt"); os.close(fd)
    try:
        assert build_narration_srt([{"kind": "original", "start": 0, "end": 5}], 1.0, p) is False
    finally:
        os.unlink(p)


def test_recap_plan_column_exists_after_migration(_isolated_db):
    conn = sqlite3.connect(str(_isolated_db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    finally:
        conn.close()
    assert "recap_plan_json" in cols


# ── N5: recap continuity + coverage ──────────────────────────────────────────

def test_recap_continuity_carries_previous_intent():
    from app.features.render.engine.pipeline.recap_pipeline import _scored_from_recap_plan
    plan = RecapPlan.from_json(json.dumps({"acts": [{"title": "A", "beat": "setup", "scenes": [
        {"start": 10, "end": 40, "narration_intent": "hero introduced"},
        {"start": 60, "end": 90, "narration_intent": "first conflict"},
    ]}]}))
    s = _scored_from_recap_plan(plan)
    assert "Previously: hero introduced" in s[1]["editorial_hint"]
    assert "Now: first conflict" in s[1]["editorial_hint"]
    # first scene has no "Previously"
    assert "Previously:" not in s[0]["editorial_hint"]


def test_recap_coverage_flags_clustered_plan():
    from app.features.render.engine.pipeline.recap_pipeline import _check_recap_coverage
    # all scenes in the first ~3% of a 3600s film → weak
    plan = RecapPlan.from_json(json.dumps({"acts": [{"scenes": [
        {"start": 5, "end": 35}, {"start": 40, "end": 70}, {"start": 75, "end": 100},
    ]}]}))
    cov = _check_recap_coverage(plan, 3600.0)
    assert cov["weak"] is True and cov["span_pct"] < 50.0


def test_recap_coverage_ok_when_well_spread():
    from app.features.render.engine.pipeline.recap_pipeline import _check_recap_coverage
    # scenes spread across a 300s film with small gaps → not weak
    plan = RecapPlan.from_json(json.dumps({"acts": [{"scenes": [
        {"start": 10, "end": 50}, {"start": 70, "end": 120}, {"start": 140, "end": 190},
        {"start": 210, "end": 260}, {"start": 270, "end": 295},
    ]}]}))
    cov = _check_recap_coverage(plan, 300.0)
    assert cov["weak"] is False


# ── N3: prosody grouping ─────────────────────────────────────────────────────

def test_group_voice_segments_merges_adjacent():
    from app.features.render.engine.audio.timed_narration import _group_voice_segments as g
    segs = [
        {"kind": "voice", "start": 0, "end": 3, "text": "a"},
        {"kind": "voice", "start": 3.3, "end": 6, "text": "b"},
        {"kind": "voice", "start": 6.2, "end": 9, "text": "c"},
    ]
    r = g(segs, 0.6)
    assert len(r) == 1 and r[0]["text"] == "a b c" and r[0]["start"] == 0.0 and r[0]["end"] == 9.0


def test_group_voice_segments_keeps_large_gaps_separate():
    from app.features.render.engine.audio.timed_narration import _group_voice_segments as g
    segs = [
        {"kind": "voice", "start": 0, "end": 3, "text": "a"},
        {"kind": "voice", "start": 8, "end": 10, "text": "b"},
    ]
    assert len(g(segs, 0.6)) == 2


def test_group_voice_segments_skips_original_and_respects_disable():
    from app.features.render.engine.audio.timed_narration import _group_voice_segments as g
    segs = [
        {"kind": "voice", "start": 0, "end": 3, "text": "a"},
        {"kind": "original", "start": 3, "end": 7},
        {"kind": "voice", "start": 7, "end": 9, "text": "b"},
    ]
    assert len(g(segs, 0.6)) == 2          # original window splits the groups
    # max_gap=0 → no merging
    close = [
        {"kind": "voice", "start": 0, "end": 3, "text": "a"},
        {"kind": "voice", "start": 3.1, "end": 6, "text": "b"},
    ]
    assert len(g(close, 0.0)) == 2


# ── Recap scene quality: min duration + whole-film coverage ──────────────────

def test_recap_parser_merges_tiny_scenes():
    """2–5s subtitle-line fragments must be merged into >=6s coherent scenes."""
    raw = json.dumps({"acts": [{"title": "A", "scenes": [
        {"start": 0, "end": 3}, {"start": 3, "end": 6}, {"start": 6, "end": 9},
        {"start": 20, "end": 24}, {"start": 24, "end": 28},
    ]}]})
    plan = parse_recap_response(raw, 300.0)
    assert plan is not None
    assert all((s.end - s.start) >= 6.0 for s in plan.scenes()), \
        f"tiny scenes survived: {[(s.start, s.end) for s in plan.scenes()]}"


def test_recap_transcript_downsampled_spans_whole_film():
    """A long transcript is downsampled (not head-truncated) so the AI sees the
    whole runtime — fixes the 'recap covers only the opening 6%' bug."""
    from app.features.render.ai.llm.recap_prompts import _fit_transcript
    big = "\n".join(f"[{i}.0 - {i+1}.0] line {i}" for i in range(20000))
    fit = _fit_transcript(big, 5000)
    assert len(fit) <= 5200
    # contains an early AND a late line (spans the film, not just the head)
    assert "line 0" in fit
    assert any(f"line {i}" in fit for i in range(19000, 20000))


# ── Content-strategy: AI-authored recap narration ────────────────────────────

def test_recap_scene_narration_roundtrips_and_flows_to_scored():
    from app.features.render.engine.pipeline.recap_pipeline import _scored_from_recap_plan
    plan = RecapPlan.from_json(json.dumps({"acts": [{"title": "A", "scenes": [
        {"start": 10, "end": 40, "narration": "Mở đầu: nhân vật chính xuất hiện."},
    ]}]}))
    assert plan.scenes()[0].narration.startswith("Mở đầu")
    assert RecapPlan.from_json(plan.to_json()).scenes()[0].narration == plan.scenes()[0].narration
    scored = _scored_from_recap_plan(plan)
    assert scored[0]["narration_text"] == "Mở đầu: nhân vật chính xuất hiện."


def test_recap_prompt_requests_authored_narration_and_full_transcript():
    from app.features.render.ai.llm.recap_prompts import build_recap_prompt, MAX_RECAP_SRT_CHARS
    _, u = build_recap_prompt("[0-30] x", 1800.0, "vi-VN")
    assert '"narration"' in u                 # schema asks for actual narration text
    assert MAX_RECAP_SRT_CHARS >= 500000       # whole-film transcript (no head-truncate)
