"""T1.1 closure regression guard — Audit 2026-06-08 (Batch A V9-C1/C2/D2).

The CRITICAL false-success path was: when the LLM dispatcher returned
None AND ``run_llm_pre_render`` returned ``scored=[]`` under the
``LLM_EMIT_RENDER_PLAN=1`` default, the render loop iterated an empty
list and both ``outputs`` and ``failed_parts`` ended empty. The
pre-T1.1 finalize block read:

    if failed_parts and not outputs:
        raise RuntimeError(...)
    if failed_parts:
        _job_log(...)
    # ... falls through to status="completed" + 0 outputs

i.e. it gated the only failure-raise on ``failed_parts`` being
truthy. With 0 parts attempted, ``failed_parts=[]`` so no raise → the
pipeline marched on to ``run_render_finalize`` which wrote
``status="completed"`` with ``outputs=[]``. FE then auto-advanced to
Results and fired a success toast for a job that produced zero clips.

T1.1 (commit 48a5173) added an EARLIER guard:

    if not outputs and not failed_parts:
        raise RuntimeError(
            f"ai_emission_empty: 0 outputs produced and 0 parts ..."
        )

This test pins that guard by mocking the same boundary functions as
test_render_pipeline_integration.py (the 6-mock recipe) and
configuring the LLM mocks to produce the empty-emission scenario.
The assertion is on the RAISE itself — the outer ``process_render``
handler that translates the raise into ``status="failed"`` is a
separate concern (already covered by test_render_pipeline_contract.
test_process_render_cancel_path_marks_cancelled and the cancel-path
contract). What this test guards is the orchestrator's REFUSAL to
write a success status when nothing was produced.

If a future refactor removes the guard, this test fires before any
user can encounter the false-success path again.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Sandbox fixture (inline copy of the MT-5 integration fixture pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def _t1_1_sandbox(tmp_path, monkeypatch):
    """Isolate the pipeline from the real data/app.db + data/channels tree."""
    data_dir = tmp_path / "data"
    channels_dir = tmp_path / "channels"
    output_dir = tmp_path / "out"
    temp_dir = tmp_path / "tmp"
    for p in (data_dir, channels_dir, output_dir, temp_dir):
        p.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "app.db"

    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    monkeypatch.setattr("app.core.config.DATABASE_PATH", db_path, raising=False)
    monkeypatch.setattr("app.core.config.CHANNELS_DIR", channels_dir, raising=False)
    monkeypatch.setattr("app.core.config.APP_DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr("app.core.config.TEMP_DIR", temp_dir, raising=False)
    monkeypatch.setattr("app.core.config.LOGS_DIR", data_dir / "logs", raising=False)
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.render_pipeline.TEMP_DIR",
        temp_dir,
        raising=False,
    )

    from app.db.connection import init_db
    init_db()

    yield {
        "db_path":      db_path,
        "output_dir":   output_dir,
        "channels_dir": channels_dir,
        "tmp_path":     tmp_path,
    }

    from app.db.connection import close_thread_conn
    close_thread_conn()


def _build_payload(output_dir: Path):
    """Minimal RenderRequest — same shape as MT-5 fixture."""
    from app.models.schemas import RenderRequest

    return RenderRequest(
        channel_code="t1-1-guard",
        source_mode="local",
        source_video_path=str(Path(__file__).parent / "_NONEXISTENT_BECAUSE_MOCKED.mp4"),
        output_dir=str(output_dir / "t1-1-guard" / "video_out"),
        render_profile="fast",
        output_count=2,
        add_subtitle=False,
        voice_enabled=False,
        motion_aware_crop=False,
        llm_enabled=False,
        hook_apply_enabled=False,
        hook_overlay_enabled=False,
        ai_director_enabled=False,
    )


def _empty_llm_pre(full_srt: Path):
    """LLMPreRenderResult with NO scored segments → empty emission scenario."""
    from app.features.render.engine.pipeline.llm_pipeline import LLMPreRenderResult

    full_srt.parent.mkdir(parents=True, exist_ok=True)
    full_srt.write_text("", encoding="utf-8")
    return LLMPreRenderResult(
        full_srt=full_srt,
        full_srt_available=False,
        early_transcription_done=False,
        scored=[],            # ← The bug-trigger: zero scored segments
        total_parts=0,        # ← matches scored
        target_platform="tiktok",
        dna_clean_visual=False,
        seg_min_sec=15,
        seg_max_sec=60,
    )


def _make_source_prep(output_stem: str, source_path: Path):
    from app.features.render.engine.pipeline.pipeline_source_prep import SourcePrepResult
    return SourcePrepResult(
        source={
            "slug": "t1_1_guard",
            "title": "T1.1 guard source",
            "duration": 90.0,
            "channel_code": "t1-1-guard",
        },
        source_path=source_path,
        edit_session_id="",
        detected_source_mode="local",
        output_stem=output_stem,
    )


def _empty_render_loop_result():
    """RenderLoopResult with no outputs and no failed parts —
    matches what the loop produces when total_parts=0."""
    from app.features.render.engine.pipeline.pipeline_render_loop import RenderLoopResult
    return RenderLoopResult(outputs=[], rows=[], failed_parts=[])


# ---------------------------------------------------------------------------
# The guard test
# ---------------------------------------------------------------------------


def test_pipeline_marks_job_failed_when_ai_emission_produces_zero_outputs(_t1_1_sandbox):
    """T1.1 guard: empty AI emission → orchestrator marks job FAILED
    rather than writing status="completed".

    The internal ``RuntimeError("ai_emission_empty: ...")`` raised by
    the T1.1 guard at render_pipeline.py:1080+ is caught by the
    orchestrator's outer try/except (lines 1322-1385), which writes
    status="failed", stage=JobStage.FAILED to the DB. We verify that
    DB state — and verify that finalize was NEVER called.

    Pre-T1.1 the orchestrator skipped the raise and called finalize,
    which wrote status="completed" with outputs=[]. Post-T1.1 finalize
    must not be called and the DB row must end FAILED.
    """
    job_id = str(uuid.uuid4())
    output_dir = _t1_1_sandbox["output_dir"] / "t1-1-guard" / "video_out"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_payload(_t1_1_sandbox["output_dir"])

    rp = "app.features.render.engine.pipeline.render_pipeline"
    fake_source = _make_source_prep(
        output_stem="t11smoke",
        source_path=Path(payload.source_video_path),
    )
    fake_llm_pre = _empty_llm_pre(
        full_srt=_t1_1_sandbox["tmp_path"] / "tmp" / job_id / "full.srt",
    )

    with patch(f"{rp}.prepare_render_source", return_value=fake_source), \
         patch(f"{rp}.run_manual_voice_tts", return_value=(None, False)), \
         patch(f"{rp}.run_llm_pre_render", return_value=fake_llm_pre), \
         patch(f"{rp}._llm_select_render_plan", return_value=None), \
         patch(f"{rp}.run_render_loop", return_value=_empty_render_loop_result()), \
         patch(f"{rp}.run_render_finalize", return_value="completed") as m_fin:

        from app.features.render.engine.pipeline.render_pipeline import (
            run_render_pipeline,
        )

        # The outer except in render_pipeline catches the ai_emission_empty
        # raise and translates it into a DB-level FAILED status — the
        # function returns normally.
        run_render_pipeline(
            job_id=job_id,
            payload=payload,
            resume_mode=False,
            load_session_fn=lambda sid: None,
            cleanup_session_fn=lambda sid: None,
        )

    # CRITICAL: finalize must NOT have been called. Pre-T1.1 it was.
    assert m_fin.call_count == 0, (
        f"T1.1 guard breached — run_render_finalize was called "
        f"{m_fin.call_count} time(s) despite outputs=[] and "
        f"failed_parts=[]. The orchestrator regressed into the "
        f"false-success path; finalize would have written "
        f"status='completed' with 0 outputs."
    )

    # Verify the DB row was marked FAILED with the expected stage.
    from app.db.jobs_repo import get_job
    row = get_job(job_id)
    assert row is not None, "job row was not persisted"
    assert row["status"] == "failed", (
        f"T1.1 guard breached — job status should be 'failed' (the outer "
        f"except handler translates the ai_emission_empty raise), got "
        f"status={row['status']!r}. Pre-T1.1 this would have been "
        f"'completed' with 0 outputs."
    )
    assert row["stage"] == "failed", (
        f"Expected stage='failed' (JobStage.FAILED.value), got {row['stage']!r}"
    )


def test_pipeline_still_marks_failed_on_all_parts_failed(_t1_1_sandbox):
    """Defence-in-depth: the EXISTING 'All parts failed' raise must
    still fire when failed_parts is non-empty. T1.1 added a NEW guard
    BEFORE this one; this test verifies the new guard didn't shadow
    the old one — both raises end up at the same outer except handler
    which marks the job FAILED.
    """
    job_id = str(uuid.uuid4())
    output_dir = _t1_1_sandbox["output_dir"] / "t1-1-guard" / "video_out"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_payload(_t1_1_sandbox["output_dir"])

    rp = "app.features.render.engine.pipeline.render_pipeline"
    fake_source = _make_source_prep(
        output_stem="t11smoke",
        source_path=Path(payload.source_video_path),
    )
    # 1 scored segment, simulating a "the AI picked something but every
    # part failed in render" scenario.
    scored = [{
        "start": 0.0, "end": 30.0, "duration": 30.0,
        "viral_score": 80.0, "hook_score": 70.0, "motion_score": 60.0,
        "retention_score": 65.0, "market_score": 60.0,
        "duration_fit_score": 70.0, "speech_density_score": 65.0,
        "ranking_components": {},
        "variant_type": "",
        "content_type_hint": "viral",
    }]
    from app.features.render.engine.pipeline.llm_pipeline import LLMPreRenderResult
    full_srt = _t1_1_sandbox["tmp_path"] / "tmp" / job_id / "full.srt"
    full_srt.parent.mkdir(parents=True, exist_ok=True)
    full_srt.write_text("", encoding="utf-8")
    fake_llm_pre = LLMPreRenderResult(
        full_srt=full_srt, full_srt_available=False,
        early_transcription_done=False,
        scored=scored, total_parts=1,
        target_platform="tiktok", dna_clean_visual=False,
        seg_min_sec=15, seg_max_sec=60,
    )

    # RenderLoop reports 1 failed part, 0 outputs (the "all failed" case).
    from app.features.render.engine.pipeline.pipeline_render_loop import RenderLoopResult
    all_failed_result = RenderLoopResult(
        outputs=[],
        rows=[],
        failed_parts=[{"part_no": 1, "reason": "synthetic test failure"}],
    )

    with patch(f"{rp}.prepare_render_source", return_value=fake_source), \
         patch(f"{rp}.run_manual_voice_tts", return_value=(None, False)), \
         patch(f"{rp}.run_llm_pre_render", return_value=fake_llm_pre), \
         patch(f"{rp}._llm_select_render_plan", return_value=None), \
         patch(f"{rp}.run_render_loop", return_value=all_failed_result), \
         patch(f"{rp}.run_render_finalize", return_value="completed") as m_fin:

        from app.features.render.engine.pipeline.render_pipeline import (
            run_render_pipeline,
        )

        # Inner raise is caught and translated to FAILED in DB.
        run_render_pipeline(
            job_id=job_id,
            payload=payload,
            resume_mode=False,
            load_session_fn=lambda sid: None,
            cleanup_session_fn=lambda sid: None,
        )

    # Finalize must not have been called for the all-failed case.
    assert m_fin.call_count == 0, (
        f"run_render_finalize was called {m_fin.call_count} time(s) "
        f"despite outputs=[] — regression."
    )

    # Job must be FAILED in DB.
    from app.db.jobs_repo import get_job
    row = get_job(job_id)
    assert row is not None
    assert row["status"] == "failed", (
        f"Expected status='failed' for all-parts-failed case, got "
        f"{row['status']!r}"
    )
