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
    # R6: hint now carries an episode tag too (legacy acts → single episode).
    assert "Recap Ep 1/1" in s["editorial_hint"]
    assert "Act 1/1" in s["editorial_hint"]
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


# ── TTS never speaks timestamps/MS (bug fix) ─────────────────────────────────

def test_strip_time_artifacts():
    from app.features.render.engine.audio.timed_narration import _strip_time_artifacts as f
    assert f("[0.0 - 5.0] Anh ấy sốc") == "Anh ấy sốc"
    assert "00:00:05" not in f("Nói 00:00:05,000 rồi nghỉ")
    assert "ms" not in f("dừng 500ms thôi").lower()
    assert "-->" not in f("a --> b")
    assert f("12\n00:00:01 --> 00:00:04\nNội dung thật") == "Nội dung thật"
    # clean text untouched
    assert f("Một câu thuyết minh bình thường.") == "Một câu thuyết minh bình thường."


def test_grouping_strips_timestamp_from_spoken_text():
    from app.features.render.engine.audio.timed_narration import _group_voice_segments as g
    u = g([{"kind": "voice", "start": 0, "end": 5, "text": "[0.0 - 5.0] Mở đầu phim"}], 0.6)
    assert u[0]["text"] == "Mở đầu phim"   # no timestamp spoken


# ── Truncated recap JSON recovery (the "no JSON object found" failure) ────────

def test_recap_parser_salvages_truncated_json():
    """A long recap output can be cut off by the token limit → the parser must
    salvage the complete prefix instead of failing the whole render."""
    trunc = (
        '{"story_summary":"...","total_target_sec":120,"acts":[{"title":"A",'
        '"beat":"setup","scenes":[{"start":10,"end":40,"narration":"Mở đầu phim."},'
        '{"start":60,"end":90,"narration":"Cao trào bắt đầu khi'   # ← cut off mid-string
    )
    plan = parse_recap_response(trunc, 300.0)
    assert plan is not None
    assert plan.scene_count() >= 2
    assert plan.scenes()[0].narration == "Mở đầu phim."


# ── R6: episodes + per-scene audio_mode ──────────────────────────────────────

def test_recap_episodes_roundtrip_and_flatten():
    """New R6 shape: episodes → acts → scenes. acts/scenes flatten across eps."""
    raw = json.dumps({"total_target_sec": 300, "episodes": [
        {"title": "Tập 1", "acts": [{"title": "Setup", "beat": "setup", "scenes": [
            {"start": 0, "end": 30, "narration": "a", "audio_mode": "narrate"}]}]},
        {"title": "Tập 2", "acts": [{"title": "Climax", "beat": "climax", "scenes": [
            {"start": 40, "end": 70, "narration": "b"}]}]},
    ]})
    plan = RecapPlan.from_json(raw)
    assert plan.episode_count() == 2
    assert plan.scene_count() == 2
    assert len(plan.acts) == 2                       # flattened property
    # deterministic round-trip preserves the episode layer
    assert RecapPlan.from_json(plan.to_json()).episode_count() == 2


def test_recap_legacy_acts_wrap_into_single_episode():
    """A pre-R6 blob (top-level acts, no episodes) loads as one episode."""
    legacy = json.dumps({"total_target_sec": 50, "acts": [
        {"title": "A", "scenes": [{"start": 0, "end": 10, "narration": "x"}]}]})
    plan = RecapPlan.from_json(legacy)
    assert plan.episode_count() == 1
    assert plan.scene_count() == 1
    assert plan.scenes()[0].audio_mode == "narrate"   # conservative default


def test_recap_parser_audio_mode_original_drops_narration():
    """An 'original' scene must never carry narration — the source audio plays."""
    raw = json.dumps({"episodes": [{"title": "Tập 1", "acts": [{"scenes": [
        {"start": 0, "end": 12, "audio_mode": "narrate", "narration": "kể chuyện"},
        {"start": 14, "end": 22, "audio_mode": "original", "narration": "should drop"},
    ]}]}]})
    plan = parse_recap_response(raw, 200.0)
    assert plan is not None
    sc = plan.scenes()
    assert sc[0].audio_mode == "narrate" and sc[0].narration == "kể chuyện"
    assert sc[1].audio_mode == "original" and sc[1].narration == ""


def test_recap_episode_range_scales_with_duration():
    from app.features.render.ai.llm.recap_prompts import _episode_range
    assert _episode_range(30 * 60) == (1, 1)          # short → single
    assert _episode_range(94 * 60)[0] >= 2            # feature film → split
    lo, hi = _episode_range(130 * 60)
    assert hi <= 4 and lo >= 2                         # capped, multi-episode


def test_recap_prompt_requests_episodes_and_audio_mode():
    from app.features.render.ai.llm.recap_prompts import build_recap_prompt
    _, u = build_recap_prompt("[0-30] x", 94 * 60, "vi-VN")
    assert '"episodes"' in u and '"audio_mode"' in u
    assert "Tập" in u                                  # episode labelling guidance


def test_recap_scored_carries_episode_and_audio_mode():
    from app.features.render.engine.pipeline.recap_pipeline import _scored_from_recap_plan
    plan = RecapPlan.from_json(json.dumps({"episodes": [
        {"title": "Tập 1", "acts": [{"title": "S", "scenes": [
            {"start": 0, "end": 12, "narration": "a"},
            {"start": 14, "end": 22, "audio_mode": "original"}]}]},
        {"title": "Tập 2", "acts": [{"title": "C", "scenes": [
            {"start": 30, "end": 45, "narration": "b"}]}]},
    ]}))
    scored = _scored_from_recap_plan(plan)
    assert [s["episode_index"] for s in scored] == [0, 0, 1]
    assert scored[1]["audio_mode"] == "original" and scored[1]["narration_text"] == ""
    # distinct global act ids across episodes (→ separate title cards)
    assert scored[0]["act_index"] != scored[2]["act_index"]


def test_recap_parser_caps_episode_count():
    """More episodes than the cap fold into the last kept episode (no scene loss)."""
    import app.features.render.ai.llm.recap_parser as rp
    eps = [{"title": f"Tập {i}", "acts": [{"scenes": [
        {"start": i * 20, "end": i * 20 + 12, "narration": f"n{i}"}]}]} for i in range(7)]
    plan = parse_recap_response(json.dumps({"episodes": eps}), 1000.0)
    assert plan is not None
    assert plan.episode_count() <= rp._RECAP_MAX_EPISODES
    assert plan.scene_count() == 7                     # every scene survives


# ── R6 fix: recap delivers EPISODES (not per-scene parts) via /api/outputs ────

def test_recap_outputs_returns_episodes_not_parts():
    """A recap job's /api/outputs must surface the assembled EPISODES from
    result_json, not the 26 internal per-scene job_parts."""
    from app.routes.outputs import _recap_episode_items
    job = {
        "payload_json": json.dumps({"render_format": "recap"}),
        "result_json": json.dumps({"render_format": "recap", "outputs": [
            {"part_no": 1, "episode_no": 1, "title": "Tập 1", "duration": 90.0,
             "output_file": "/no/such/ep1.mp4", "output_rank_score": 100.0,
             "is_best_output": True},
            {"part_no": 2, "episode_no": 2, "title": "Tập 2", "duration": 88.0,
             "output_file": "/no/such/ep2.mp4", "output_rank_score": 99.0,
             "is_best_output": False},
        ]}),
    }
    items = _recap_episode_items(job)
    assert items is not None and len(items) == 2
    assert items[0]["episode_no"] == 1 and items[0]["is_best_output"] is True
    assert items[0]["part_name"] == "Tập 1"
    # a clips job → None (falls back to job_parts path, unchanged)
    clip_job = {"payload_json": json.dumps({"render_format": "clips"}), "result_json": "{}"}
    assert _recap_episode_items(clip_job) is None
    # recap with no outputs yet → None
    empty = {"payload_json": json.dumps({"render_format": "recap"}), "result_json": "{}"}
    assert _recap_episode_items(empty) is None


# ── R6 fix: "MS" bug — TTS must never speak SSML <break> tags ─────────────────

def test_sanitize_plain_tts_strips_ssml_break_and_ms():
    """edge-tts reads SSML as plain text → <break time='500ms'/> was spoken as
    'ms'. The sanitizer must remove break tags, residual markup and stray Nms."""
    from app.features.render.engine.audio.tts import _sanitize_plain_tts as f
    assert "ms" not in f("a <break time='500ms'/> b").lower()
    assert "<break" not in f("x <break time='300ms'/> y")
    assert "500ms" not in f("dừng 500ms rồi đi")
    assert "<" not in f("a <emphasis>b</emphasis> c")     # any residual markup
    # clean narration is untouched (no false positives)
    assert f("Nam tưởng mọi chuyện đã yên.") == "Nam tưởng mọi chuyện đã yên."


# ── R6 fix: episode files named by AI chapter title, not "_recap_ep01" ────────

def test_recap_episode_filename_is_fs_safe():
    """Episode output filenames use the AI chapter title and must be filesystem
    safe (no Windows-illegal chars, no trailing dot, length-capped)."""
    from app.features.render.engine.pipeline.recap_pipeline import _safe_filename as f
    out = f('Hidden Weapons - Tập 1: Mở màn án mạng')
    assert ":" not in out and "/" not in out and "\\" not in out
    assert "Tập 1" in out and "Mở màn" in out          # title preserved (minus ':')
    assert f("a/b\\c:d") and "/" not in f("a/b\\c:d")  # illegal chars stripped
    assert f("trailing dots...") == "trailing dots"     # Windows trailing-dot trim
    assert f("") == "" and f("::::") == ""              # nothing usable → empty
    assert len(f("x" * 500)) <= 120                     # length cap


# ── R6 fix: recap thumbnails resolve to the EPISODE mp4, not a scene part ─────

def test_recap_thumbnail_resolves_to_episode_file():
    """The thumbnail routes must map a recap part_no to its EPISODE mp4
    (result_json.outputs), since per-scene parts live in a cleaned-up temp dir."""
    from app.routes.outputs import recap_output_file_for_part as g
    job = {
        "payload_json": json.dumps({"render_format": "recap"}),
        "result_json": json.dumps({"render_format": "recap", "outputs": [
            {"part_no": 1, "episode_no": 1, "output_file": "/x/Tập 1.mp4"},
            {"part_no": 2, "episode_no": 2, "output_file": "/x/Tập 2.mp4"},
        ]}),
    }
    assert g(job, 1) == "/x/Tập 1.mp4"
    assert g(job, 2) == "/x/Tập 2.mp4"
    assert g(job, 99) is None
    # clips job → None (routes fall back to job_parts, unchanged)
    clip = {"payload_json": json.dumps({"render_format": "clips"}), "result_json": "{}"}
    assert g(clip, 1) is None
