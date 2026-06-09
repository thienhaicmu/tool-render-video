"""test_e2e_ffmpeg_render.py — True E2E FFmpeg render verification.

What this test does that the MT-5 integration test (test_render_pipeline_integration.py)
does NOT:

  - run_render_loop runs for REAL → FFmpeg actually cuts and encodes a clip.
  - run_render_finalize runs for REAL → qa_pipeline validates the output,
    result_json is written to the DB, job status is set to "completed".

Assertions:
  1. At least one .mp4 output file exists on disk.
  2. The output file has a valid video stream (ffprobe check).
  3. Job status in DB is "completed" or "completed_with_errors".
  4. result_json["output_ranking"] entries carry the three Sacred Contract #1
     keys: output_rank_score, is_best_output, is_best_clip.

Still mocked (require unavailable external services):
  - prepare_render_source   → SourcePrepResult pointing to the synthetic video
  - run_llm_pre_render      → LLMPreRenderResult with 1 fake segment (2–17 s)
  - _llm_select_render_plan → None (legacy path)
  - run_manual_voice_tts    → (None, False) — voice disabled anyway

Skip guard: the test is skipped when FFmpeg cannot generate the synthetic
source video (e.g. CI without FFmpeg on PATH).
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Skip guard ───────────────────────────────────────────────────────────────

def _ffmpeg_ok() -> bool:
    try:
        from app.features.render.engine.encoder.ffmpeg_helpers import get_ffmpeg_bin
        r = subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


# ── Sandbox fixture ──────────────────────────────────────────────────────────

@pytest.fixture
def _e2e_sandbox(tmp_path, monkeypatch):
    """Isolated DB + directories + a 20-second synthetic source MP4."""
    data_dir     = tmp_path / "data"
    channels_dir = tmp_path / "channels"
    output_dir   = tmp_path / "out"
    temp_dir     = tmp_path / "tmp"
    for p in (data_dir, channels_dir, output_dir, temp_dir):
        p.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "app.db"

    monkeypatch.setattr("app.db.connection.DATABASE_PATH",   db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    monkeypatch.setattr("app.core.config.DATABASE_PATH",     db_path,            raising=False)
    monkeypatch.setattr("app.core.config.CHANNELS_DIR",      channels_dir,       raising=False)
    monkeypatch.setattr("app.core.config.APP_DATA_DIR",      data_dir,           raising=False)
    monkeypatch.setattr("app.core.config.TEMP_DIR",          temp_dir,           raising=False)
    monkeypatch.setattr("app.core.config.LOGS_DIR",          data_dir / "logs",  raising=False)
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.render_pipeline.TEMP_DIR",
        temp_dir, raising=False,
    )

    from app.db.connection import init_db
    init_db()

    # Generate a 20-second black video with silent audio (256×144, 25 fps)
    from app.features.render.engine.encoder.ffmpeg_helpers import get_ffmpeg_bin
    source_video = tmp_path / "e2e_source.mp4"
    gen = subprocess.run(
        [
            get_ffmpeg_bin(),
            "-f", "lavfi", "-i", "color=c=black:size=256x144:rate=25",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            "-t", "20",
            "-y", str(source_video),
        ],
        capture_output=True, timeout=30,
    )
    if gen.returncode != 0 or not source_video.exists():
        pytest.skip("FFmpeg failed to generate synthetic source video — skipping E2E test")

    yield {
        "db_path":      db_path,
        "source_video": source_video,
        "output_dir":   output_dir,
        "tmp_path":     tmp_path,
    }

    from app.db.connection import close_thread_conn
    close_thread_conn()


# ── Mock factories ────────────────────────────────────────────────────────────

def _fake_source(source_video: Path):
    from app.features.render.engine.pipeline.pipeline_source_prep import SourcePrepResult
    return SourcePrepResult(
        source={
            "slug":         "e2e_test",
            "title":        "E2E synthetic source",
            "duration":     20.0,
            "channel_code": "e2e-ffmpeg",
        },
        source_path=source_video,
        edit_session_id="",
        detected_source_mode="local",
        output_stem="e2e_test",
    )


def _fake_llm_pre(full_srt: Path):
    from app.features.render.engine.pipeline.llm_pipeline import LLMPreRenderResult
    full_srt.parent.mkdir(parents=True, exist_ok=True)
    full_srt.write_text("", encoding="utf-8")
    return LLMPreRenderResult(
        full_srt=full_srt,
        full_srt_available=False,
        early_transcription_done=False,
        scored=[{
            "start": 2.0,  "end": 17.0,  "duration": 15.0,
            "viral_score":        80.0,
            "hook_score":         75.0,
            "motion_score":       60.0,
            "retention_score":    70.0,
            "market_score":       65.0,
            "duration_fit_score": 85.0,
            "speech_density_score": 50.0,
            "ranking_components": {},
            "variant_type":       "",
            "content_type_hint":  "interview",
        }],
        total_parts=1,
        target_platform="tiktok",
        dna_clean_visual=False,
        seg_min_sec=10,
        seg_max_sec=30,
    )


def _has_video_stream(path: str) -> bool:
    try:
        from app.features.render.engine.encoder.ffmpeg_helpers import get_ffprobe_bin
        r = subprocess.run(
            [
                get_ffprobe_bin(), "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0", path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return "video" in r.stdout
    except Exception:
        return False


# ── The test ─────────────────────────────────────────────────────────────────

@_NEEDS_FFMPEG
def test_real_ffmpeg_render_produces_valid_output(_e2e_sandbox):
    """FFmpeg cuts + encodes a real clip from a synthetic source.

    run_render_loop and run_render_finalize run without mocking so that:
      - FFmpeg actually executes (catching encode regressions)
      - qa_pipeline actually validates the output (catching QA regressions)
      - result_json is actually written to the DB (catching finalize regressions)
    """
    from app.models.schemas import RenderRequest

    job_id       = str(uuid.uuid4())
    source_video = _e2e_sandbox["source_video"]
    output_dir   = _e2e_sandbox["output_dir"]

    payload = RenderRequest(
        channel_code="e2e-ffmpeg",
        source_mode="local",
        source_video_path=str(source_video),
        output_dir=str(output_dir / "e2e-ffmpeg" / "video_out"),
        render_profile="fast",
        output_count=1,
        add_subtitle=False,
        voice_enabled=False,
        motion_aware_crop=False,
        llm_enabled=False,
        hook_apply_enabled=False,
        hook_overlay_enabled=False,
        ai_director_enabled=False,
        ai_clip_min_duration_sec=10,
        ai_clip_max_duration_sec=30,
    )

    rp = "app.features.render.engine.pipeline.render_pipeline"
    with patch(f"{rp}.prepare_render_source",   return_value=_fake_source(source_video)), \
         patch(f"{rp}.run_manual_voice_tts",    return_value=(None, False)), \
         patch(f"{rp}.run_llm_pre_render",
               return_value=_fake_llm_pre(
                   _e2e_sandbox["tmp_path"] / "tmp" / job_id / "full.srt"
               )), \
         patch(f"{rp}._llm_select_render_plan", return_value=None):

        from app.features.render.engine.pipeline.render_pipeline import run_render_pipeline
        run_render_pipeline(
            job_id=job_id,
            payload=payload,
            resume_mode=False,
            load_session_fn=lambda sid: None,
            cleanup_session_fn=lambda sid: None,
        )

    # ── 1. At least one .mp4 output on disk ──────────────────────────────
    mp4_files = list(output_dir.rglob("*.mp4"))
    assert mp4_files, (
        f"No .mp4 output found under {output_dir}. "
        "run_render_loop or run_render_finalize failed to produce any output."
    )

    # ── 2. Output has a valid video stream ───────────────────────────────
    for mp4 in mp4_files:
        assert _has_video_stream(str(mp4)), (
            f"Output file has no valid video stream (corrupt or empty): {mp4}"
        )

    # ── 3. Job status in DB = completed or completed_with_errors ─────────
    from app.db.jobs_repo import get_job
    job_row = get_job(job_id)
    assert job_row is not None, f"Job {job_id} not found in DB after pipeline run"
    assert job_row["status"] in ("completed", "completed_with_errors"), (
        f"Expected completed/completed_with_errors, got: {job_row['status']!r}"
    )

    # ── 4. result_json carries Sacred Contract #1 keys ───────────────────
    raw_result = job_row.get("result_json") or "{}"
    try:
        result = json.loads(raw_result)
    except json.JSONDecodeError:
        pytest.fail(f"result_json is not valid JSON: {raw_result[:300]}")

    ranking = result.get("output_ranking") or []
    assert ranking, (
        "result_json.output_ranking is empty — pipeline produced no ranked output. "
        f"result keys: {list(result.keys())}"
    )
    for entry in ranking:
        for key in ("output_rank_score", "is_best_output", "is_best_clip"):
            assert key in entry, (
                f"Sacred Contract #1 violation: output_ranking entry missing '{key}'. "
                f"Entry keys: {list(entry.keys())}"
            )
