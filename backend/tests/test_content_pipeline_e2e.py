"""test_content_pipeline_e2e.py — Content Mode orchestrator E2E (Phase 3).

Runs run_content end-to-end with the AI Director and TTS MOCKED (so no network),
but with REAL FFmpeg for every scene compose + the final concat + the QA gate.
Asserts the full contract:

  1. A final .mp4 lands in the output dir with a valid video + audio stream.
  2. Job status in DB = "completed".
  3. result_json carries the Sacred Contract #1 keys on the output
     (output_rank_score / is_best_output / is_best_clip) + render_format="content".
  4. The ContentPlan blob is persisted (content_plan_json).

Skip guard: skipped when FFmpeg is unavailable.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


@pytest.fixture
def _content_sandbox(tmp_path, monkeypatch):
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
    # content_pipeline bound TEMP_DIR at import — repoint it at the sandbox.
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.content_pipeline.TEMP_DIR",
        temp_dir, raising=False,
    )

    # Keep these composition tests fast + deterministic: the sentence-SRT path,
    # not word-by-word (which would load Whisper on silent audio). CS-C's
    # word-by-word path has its own focused test in test_content_scene_render.py.
    monkeypatch.setattr(
        "app.features.render.engine.stages.content_scene_render._CONTENT_WORD_BY_WORD",
        False, raising=False,
    )

    from app.db.connection import init_db
    init_db()
    yield {"db_path": db_path, "output_dir": output_dir, "tmp_path": tmp_path}
    from app.db.connection import close_thread_conn
    close_thread_conn()


def _make_plan():
    from app.domain.content_plan import ContentPlan, ContentScene
    return ContentPlan(
        topic="Sao Hoa", tone="documentary", audience="general", language="vi-VN",
        total_target_sec=6.0, subtitle_style="capcut", bgm_mood="epic",
        scenes=[
            ContentScene(index=0, role="hook", narration="Xin chao cac ban.",
                         emotion="curious", reading_speed=1.0, pause_after=0.3),
            ContentScene(index=1, role="conclusion", narration="Va do la ket luan.",
                         emotion="epic", reading_speed=1.0),
        ],
    )


def _fake_synth_factory():
    """Return a synthesize_scene_narration stub that writes a real silent mp3."""
    from app.services.bin_paths import get_ffmpeg_bin

    def _fake(*, scene, job_id, out_path, **kwargs):
        dur = 2.0
        subprocess.run(
            [get_ffmpeg_bin(), "-y", "-f", "lavfi",
             "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", f"{dur}", "-c:a", "libmp3lame", out_path],
            capture_output=True, check=True, timeout=60,
        )
        return (out_path, dur)

    return _fake


def _probe_has(path: str, stream: str) -> bool:
    from app.services.bin_paths import get_ffprobe_bin
    r = subprocess.run(
        [get_ffprobe_bin(), "-v", "error", "-select_streams", stream,
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15,
    )
    return bool((r.stdout or "").strip())


@_NEEDS_FFMPEG
def test_run_content_end_to_end(_content_sandbox, monkeypatch):
    from app.models.schemas import RenderRequest
    import app.features.render.engine.pipeline.content_pipeline as cp

    job_id = str(uuid.uuid4())
    output_dir = _content_sandbox["output_dir"]

    # Mock the AI director + TTS (no network); FFmpeg stays real.
    monkeypatch.setattr(cp, "select_content_plan", lambda **k: _make_plan())
    monkeypatch.setattr(cp, "synthesize_scene_narration", _fake_synth_factory())

    payload = RenderRequest(
        channel_code="content-e2e",
        render_format="content",
        content_script="Hom nay chung ta tim hieu ve Sao Hoa. That thu vi.",
        content_background_kind="color",
        content_background_value="#101820",
        output_dir=str(output_dir / "content-e2e"),
        aspect_ratio="9:16",
        output_fps=30,
        add_subtitle=True,
        voice_enabled=False,
    )

    cp.run_content(
        job_id=job_id, payload=payload, resume_mode=False,
        load_session_fn=lambda sid: None, cleanup_session_fn=lambda sid: None,
    )

    # 1. A final .mp4 with valid video + audio.
    mp4s = list(output_dir.rglob("*.mp4"))
    assert mp4s, f"no .mp4 produced under {output_dir}"
    final = mp4s[0]
    assert _probe_has(str(final), "v:0"), "final output has no video stream"
    assert _probe_has(str(final), "a:0"), "final output has no audio stream"

    # 2. Job status = completed.
    from app.db.jobs_repo import get_job, get_content_plan
    row = get_job(job_id)
    assert row is not None and row["status"] == "completed", row and row["status"]

    # 3. result_json carries Sacred Contract #1 keys + render_format.
    result = json.loads(row.get("result_json") or "{}")
    assert result.get("render_format") == "content"
    outs = result.get("outputs") or []
    assert outs, "result_json.outputs empty"
    o = outs[0]
    for key in ("output_rank_score", "is_best_output", "is_best_clip"):
        assert key in o, f"Sacred Contract #1 key {key!r} missing from output"
    assert o["is_best_output"] is True and o["is_best_clip"] is True

    # 4. ContentPlan persisted.
    raw_plan = get_content_plan(job_id)
    assert raw_plan and "scenes" in raw_plan, "content_plan_json not persisted"


@_NEEDS_FFMPEG
def test_run_content_uses_approved_plan_override(_content_sandbox, monkeypatch):
    """CS-A: when content_plan_override is set, run_content renders FROM it and
    NEVER calls the AI Director."""
    from app.models.schemas import RenderRequest
    import app.features.render.engine.pipeline.content_pipeline as cp

    job_id = str(uuid.uuid4())
    output_dir = _content_sandbox["output_dir"]

    def _boom(**_k):
        raise AssertionError("select_content_plan must be skipped when a plan override is present")
    monkeypatch.setattr(cp, "select_content_plan", _boom)
    monkeypatch.setattr(cp, "synthesize_scene_narration", _fake_synth_factory())

    approved = _make_plan().to_json()
    payload = RenderRequest(
        channel_code="content-e2e",
        render_format="content",
        content_script="ignored because a plan override is supplied",
        content_plan_override=approved,
        content_background_kind="color",
        content_background_value="#000000",
        output_dir=str(output_dir / "content-override"),
        aspect_ratio="9:16", output_fps=30, add_subtitle=True, voice_enabled=False,
    )
    cp.run_content(
        job_id=job_id, payload=payload, resume_mode=False,
        load_session_fn=lambda sid: None, cleanup_session_fn=lambda sid: None,
    )
    from app.db.jobs_repo import get_job
    row = get_job(job_id)
    assert row is not None and row["status"] == "completed"
    assert list(output_dir.rglob("*.mp4")), "override render produced no output"


@_NEEDS_FFMPEG
def test_run_content_partial_success_status(_content_sandbox, monkeypatch):
    """MED-1: when a scene fails but ≥1 succeeds the job is completed_with_errors
    and result_json flags the partial success."""
    from app.models.schemas import RenderRequest
    import app.features.render.engine.pipeline.content_pipeline as cp
    from app.services.bin_paths import get_ffmpeg_bin

    job_id = str(uuid.uuid4())
    output_dir = _content_sandbox["output_dir"]
    monkeypatch.setattr(cp, "select_content_plan", lambda **k: _make_plan())

    def _synth_fail_first(*, scene, job_id, out_path, **kwargs):
        if getattr(scene, "index", 0) == 0:
            return None  # first scene's TTS fails
        # Surviving scene long enough that the concatenated output clears the QA
        # 10 KB floor (a 2 s static clip is below it).
        subprocess.run(
            [get_ffmpeg_bin(), "-y", "-f", "lavfi",
             "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", "6", "-c:a", "libmp3lame", out_path],
            capture_output=True, check=True, timeout=60,
        )
        return (out_path, 6.0)
    monkeypatch.setattr(cp, "synthesize_scene_narration", _synth_fail_first)

    payload = RenderRequest(
        channel_code="content-e2e", render_format="content",
        content_script="x", content_background_kind="color", content_background_value="#000000",
        output_dir=str(output_dir / "content-partial"), aspect_ratio="9:16",
        output_fps=30, add_subtitle=True, voice_enabled=False,
    )
    cp.run_content(job_id=job_id, payload=payload, resume_mode=False,
                   load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None)

    from app.db.jobs_repo import get_job
    row = get_job(job_id)
    assert row is not None and row["status"] == "completed_with_errors", row and row["status"]
    result = json.loads(row.get("result_json") or "{}")
    assert result.get("is_partial_success") is True
    assert result.get("failed_parts") == [1]  # scene index 0 → part_no 1


@_NEEDS_FFMPEG
def test_run_content_honors_cancel(_content_sandbox, monkeypatch):
    """MED-2: a cancelled job raises JobCancelledError and delivers no output."""
    from app.models.schemas import RenderRequest
    import app.features.render.engine.pipeline.content_pipeline as cp

    job_id = str(uuid.uuid4())
    output_dir = _content_sandbox["output_dir"]
    monkeypatch.setattr(cp, "select_content_plan", lambda **k: _make_plan())
    monkeypatch.setattr(cp, "synthesize_scene_narration", _fake_synth_factory())
    monkeypatch.setattr(cp.cancel_registry, "is_cancelled", lambda jid: True)

    payload = RenderRequest(
        channel_code="content-e2e", render_format="content", content_script="x",
        output_dir=str(output_dir / "content-cancel"), voice_enabled=False,
    )
    with pytest.raises(cp.cancel_registry.JobCancelledError):
        cp.run_content(job_id=job_id, payload=payload, resume_mode=False,
                       load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None)
    assert not list((output_dir / "content-cancel").rglob("*.mp4"))


def _make_av(path: str, dur: float = 3.0) -> None:
    # testsrc (animated) so even a short clip clears the QA 10 KB floor — a static
    # colour clip compresses below it.
    from app.services.bin_paths import get_ffmpeg_bin
    subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"testsrc=size=320x568:rate=30:duration={dur}",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
        capture_output=True, check=True, timeout=60,
    )


@_NEEDS_FFMPEG
def test_run_content_resumes_existing_scenes(_content_sandbox, monkeypatch):
    """CU-2: valid scene clips already on disk are reused — TTS is NOT re-run."""
    import app.features.render.engine.pipeline.content_pipeline as cp
    from app.models.schemas import RenderRequest

    job_id = str(uuid.uuid4())
    tmp_path = _content_sandbox["tmp_path"]
    output_dir = _content_sandbox["output_dir"]
    scenes_dir = tmp_path / "tmp" / job_id / "content_scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    _make_av(str(scenes_dir / "scene_001.mp4"))
    _make_av(str(scenes_dir / "scene_002.mp4"))

    monkeypatch.setattr(cp, "select_content_plan", lambda **k: _make_plan())

    def _boom_synth(**k):
        raise AssertionError("resume must skip TTS for already-rendered scenes")
    monkeypatch.setattr(cp, "synthesize_scene_narration", _boom_synth)

    payload = RenderRequest(
        channel_code="content-e2e", render_format="content", content_script="x",
        output_dir=str(output_dir / "content-resume"), aspect_ratio="9:16",
        output_fps=30, add_subtitle=False, voice_enabled=False,
    )
    cp.run_content(job_id=job_id, payload=payload, resume_mode=True,
                   load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None)

    from app.db.jobs_repo import get_job
    row = get_job(job_id)
    assert row is not None and row["status"] == "completed"
    assert list((output_dir / "content-resume").rglob("*.mp4"))


@_NEEDS_FFMPEG
def test_run_content_no_plan_fails_cleanly(_content_sandbox, monkeypatch):
    """AI returns None → run_content raises (process_render writes the failed
    row). Sacred Contract #3: no partial 'success' delivered."""
    from app.models.schemas import RenderRequest
    import app.features.render.engine.pipeline.content_pipeline as cp

    job_id = str(uuid.uuid4())
    output_dir = _content_sandbox["output_dir"]
    monkeypatch.setattr(cp, "select_content_plan", lambda **k: None)

    payload = RenderRequest(
        channel_code="content-e2e",
        render_format="content",
        content_script="something",
        output_dir=str(output_dir / "content-fail"),
        voice_enabled=False,
    )
    with pytest.raises(Exception):
        cp.run_content(
            job_id=job_id, payload=payload, resume_mode=False,
            load_session_fn=lambda sid: None, cleanup_session_fn=lambda sid: None,
        )
    # No .mp4 delivered.
    assert not list(output_dir.rglob("*.mp4"))
