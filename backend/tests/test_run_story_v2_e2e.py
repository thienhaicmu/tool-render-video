"""test_run_story_v2_e2e.py — Story Mode v2 orchestrator E2E (B7).

Runs run_story_v2 end-to-end with the super plan / voice cast / image gen / TTS
MOCKED (no network), but with REAL FFmpeg for every cue's Ken Burns render + the
final xfade concat + the QA gate. Asserts the full contract:

  1. A final .mp4 with a valid video + audio stream lands in the output dir.
  2. Job status in DB = "completed".
  3. result_json carries the Sacred Contract #1 keys (output_rank_score /
     is_best_output / is_best_clip) + render_format="story".
  4. The StoryPlan v2 blob is persisted (story_plan_json, schema_version 2).
  5. Cancel raises JobCancelledError and delivers no output.
  6. AI returning None → run_story_v2 raises (Sacred #3, no fake success).

Skip guard: skipped when FFmpeg is unavailable.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

import app.features.render.engine.pipeline.story_pipeline_v2 as sp2
from app.domain.story_plan_v2 import (
    StoryPlan, CharacterDef, SettingDef, Visual, Beat, BeatAudio,
)


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


@pytest.fixture
def _story_sandbox(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "out"
    temp_dir = tmp_path / "tmp"
    for p in (data_dir, output_dir, temp_dir):
        p.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "app.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    monkeypatch.setattr("app.core.config.DATABASE_PATH", db_path, raising=False)
    monkeypatch.setattr("app.core.config.APP_DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr("app.core.config.TEMP_DIR", temp_dir, raising=False)
    monkeypatch.setattr("app.core.config.LOGS_DIR", data_dir / "logs", raising=False)
    monkeypatch.setattr(sp2, "TEMP_DIR", temp_dir, raising=False)
    monkeypatch.setattr(sp2, "CACHE_DIR", data_dir / "cache", raising=False)
    from app.db.connection import init_db
    init_db()
    yield {"output_dir": output_dir, "tmp_path": tmp_path}
    from app.db.connection import close_thread_conn
    close_thread_conn()


def _make_plan_v2() -> StoryPlan:
    return StoryPlan(
        language="vi", aspect_ratio="16:9", topic="Kiem The", seed=7,
        characters=[CharacterDef(id="han", name="Han Phong", voice_gender="male")],
        settings=[SettingDef(id="s1", name="Dai sanh")],
        visuals=[
            Visual(id="v1", setting_id="s1", prompt="a vast ancient hall", character_ids=["han"], tier="low"),
            Visual(id="v2", setting_id="s1", prompt="a quiet moonlit courtyard", tier="low"),
        ],
        timeline=[
            Beat(id="b1", narration="Dem lanh, gio rit qua khe cua.", speaker_id="",
                 visual_id="v1", focus="wide", motion="zoom_in", hook=True, hook_text="Bi mat"),
            Beat(id="b2", narration="Han Phong buoc vao dai sanh.", speaker_id="han",
                 visual_id="v1", focus="center", motion="pan_right"),
            Beat(id="b3", narration="San vang lang duoi anh trang.", speaker_id="",
                 visual_id="v2", focus="left", motion="static", transition_in="fade"),
        ],
    )


def _mock_cast(plan, language, narrator_gender="female"):
    plan.render.voices = {"": ["edge", ""], "han": ["edge", ""]}
    return plan.render.voices


def _mock_image(visual, refs, art_style, width, height, out_path, seed=0, provider="gpt_image"):
    from app.services.bin_paths import get_ffmpeg_bin
    subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"testsrc=size={width}x{height}",
         "-frames:v", "1", str(out_path)],
        capture_output=True, check=True, timeout=60,
    )
    return str(out_path)


def _mock_synth(plan, *, job_id, audio_dir, subtitle_mode="hook_only"):
    from app.services.bin_paths import get_ffmpeg_bin
    Path(audio_dir).mkdir(parents=True, exist_ok=True)
    for b in plan.timeline:
        p = Path(audio_dir) / f"a_{b.id}.mp3"
        subprocess.run(
            [get_ffmpeg_bin(), "-y", "-f", "lavfi",
             "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", "2.5", "-c:a", "libmp3lame", str(p)],
            capture_output=True, check=True, timeout=60,
        )
        plan.render.beat_audio[b.id] = BeatAudio(str(p), 2.5, [])


def _probe_has(path: str, stream: str) -> bool:
    from app.services.bin_paths import get_ffprobe_bin
    r = subprocess.run(
        [get_ffprobe_bin(), "-v", "error", "-select_streams", stream,
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15,
    )
    return bool((r.stdout or "").strip())


def _payload(output_dir, sub="story-e2e", **extra):
    from app.models.schemas import RenderRequest
    base = dict(
        channel_code="story-e2e", render_format="story",
        content_script="Chuong 1. Han Phong buoc vao dai sanh trong dem lanh.",
        output_dir=str(output_dir / sub), aspect_ratio="16:9", output_fps=30,
        add_subtitle=False, voice_enabled=False, voice_language="vi",
    )
    base.update(extra)
    return RenderRequest(**base)


def _wire_mocks(monkeypatch, plan_fn):
    monkeypatch.setattr(sp2, "generate_story_plan_v2", plan_fn)
    monkeypatch.setattr(sp2, "apply_voice_cast_v2", _mock_cast)
    monkeypatch.setattr(sp2, "generate_visual_image", _mock_image)
    monkeypatch.setattr(sp2, "synthesize_timeline", _mock_synth)


@_NEEDS_FFMPEG
def test_run_story_v2_end_to_end(_story_sandbox, monkeypatch):
    job_id = str(uuid.uuid4())
    output_dir = _story_sandbox["output_dir"]
    _wire_mocks(monkeypatch, lambda **k: _make_plan_v2())

    sp2.run_story_v2(
        job_id=job_id, payload=_payload(output_dir), resume_mode=False,
        load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None,
    )

    # 1. A final .mp4 with valid video + audio.
    mp4s = list(output_dir.rglob("*.mp4"))
    assert mp4s, f"no .mp4 produced under {output_dir}"
    final = mp4s[0]
    assert _probe_has(str(final), "v:0"), "final output has no video stream"
    assert _probe_has(str(final), "a:0"), "final output has no audio stream"

    # 2. Job completed.
    from app.db.jobs_repo import get_job, get_story_plan
    row = get_job(job_id)
    assert row is not None and row["status"] == "completed", row and row["status"]

    # 3. result_json — Sacred Contract #1 + render_format.
    result = json.loads(row.get("result_json") or "{}")
    assert result.get("render_format") == "story"
    outs = result.get("outputs") or []
    assert outs, "result_json.outputs empty"
    o = outs[0]
    for key in ("output_rank_score", "is_best_output", "is_best_clip"):
        assert key in o, f"Sacred Contract #1 key {key!r} missing"
    assert o["is_best_output"] is True and o["is_best_clip"] is True
    assert result.get("image_count") == 2 and result.get("beat_count") == 3

    # 4. StoryPlan v2 persisted.
    raw = get_story_plan(job_id)
    assert raw, "story_plan_json not persisted"
    persisted = StoryPlan.from_json(raw)
    assert persisted is not None and persisted.schema_version == 2
    assert len(persisted.render.cues) == 3   # cue sheet checkpointed


@_NEEDS_FFMPEG
def test_run_story_v2_uses_plan_override(_story_sandbox, monkeypatch):
    """When story_plan_override (v2) is set, run_story_v2 renders FROM it and never
    calls the super plan."""
    job_id = str(uuid.uuid4())
    output_dir = _story_sandbox["output_dir"]

    def _boom(**_k):
        raise AssertionError("super plan must be skipped when a v2 override is present")
    _wire_mocks(monkeypatch, _boom)

    approved = _make_plan_v2().to_json()
    sp2.run_story_v2(
        job_id=job_id, payload=_payload(output_dir, sub="story-override",
                                        story_plan_override=approved),
        resume_mode=False, load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None,
    )
    from app.db.jobs_repo import get_job
    row = get_job(job_id)
    assert row is not None and row["status"] == "completed"
    assert list((output_dir / "story-override").rglob("*.mp4"))


@_NEEDS_FFMPEG
def test_run_story_v2_honors_cancel(_story_sandbox, monkeypatch):
    job_id = str(uuid.uuid4())
    output_dir = _story_sandbox["output_dir"]
    _wire_mocks(monkeypatch, lambda **k: _make_plan_v2())
    monkeypatch.setattr(sp2.cancel_registry, "is_cancelled", lambda jid: True)

    with pytest.raises(sp2.cancel_registry.JobCancelledError):
        sp2.run_story_v2(
            job_id=job_id, payload=_payload(output_dir, sub="story-cancel"),
            resume_mode=False, load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None,
        )
    assert not list((output_dir / "story-cancel").rglob("*.mp4"))


@_NEEDS_FFMPEG
def test_run_story_v2_no_plan_fails_cleanly(_story_sandbox, monkeypatch):
    """Super plan returns None → run_story_v2 raises; no output delivered (Sacred #3)."""
    job_id = str(uuid.uuid4())
    output_dir = _story_sandbox["output_dir"]
    _wire_mocks(monkeypatch, lambda **k: None)

    with pytest.raises(Exception):
        sp2.run_story_v2(
            job_id=job_id, payload=_payload(output_dir, sub="story-fail"),
            resume_mode=False, load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None,
        )
    assert not list((output_dir / "story-fail").rglob("*.mp4"))
