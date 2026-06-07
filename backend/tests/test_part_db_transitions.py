"""Audit MT-4 phase B closure (Batch 10Q 2026-06-06).

``part_db.{mark_part_skipped_done,mark_part_waiting,mark_part_rendering}``
centralizes the 3 ``upsert_job_part`` calls that used to live inline in
``process_one_part``. Pin the Sacred Contract #5 transitions:

  QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE

These three facade calls cover exactly the WAITING, RENDERING, and
resume-skip → DONE transitions. CUTTING / TRANSCRIBING / per-part
terminal DONE remain owned by their respective stage helpers.

Tests assert the (stage, progress, output_file, message) tuple for
each transition by intercepting ``app.db.jobs_repo.upsert_job_part`` —
the contract is byte-identical to what process_one_part wrote inline
pre-extraction.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _build_ctx_paths_seg(tmp_path: Path):
    """Cheap PartRenderContext + PartPaths + seg shims. The facade only
    reads ctx.job_id and the seg score / time fields plus paths.part_name
    and paths.final_part — we don't need the full dataclasses."""
    from app.features.render.engine.stages.segment_metadata import PartPaths

    ctx = SimpleNamespace(job_id="job-mt4b")
    paths = PartPaths(
        raw_part=tmp_path / "x_raw.mp4",
        srt_part=tmp_path / "x.srt",
        ass_part=tmp_path / "x.ass",
        translated_srt_part=tmp_path / "x.en.srt",
        final_part=tmp_path / "story_part_001.mp4",
        part_name="story_part_001.mp4",
    )
    seg = {
        "start": 10.0, "end": 40.0, "duration": 30.0,
        "viral_score": 88, "motion_score": 72, "hook_score": 90,
    }
    return ctx, paths, seg


# ---------------------------------------------------------------------------
# Capture helper: intercept upsert_job_part so the assert is on the
# exact argument tuple the facade builds.
# ---------------------------------------------------------------------------


@pytest.fixture
def _capture_upsert(monkeypatch):
    captured: list[tuple] = []

    def _stub(*args, **kwargs):
        # The real upsert is positional; capture the tuple verbatim.
        captured.append((args, kwargs))
        return None

    monkeypatch.setattr(
        "app.features.render.engine.stages.part_db.upsert_job_part",
        _stub,
    )
    return captured


# ---------------------------------------------------------------------------
# 1. mark_part_skipped_done — resume-skip → DONE @ 100
# ---------------------------------------------------------------------------


def test_mark_part_skipped_done_writes_done_at_100(tmp_path, _capture_upsert):
    from app.core.stage import JobPartStage
    from app.features.render.engine.stages.part_db import mark_part_skipped_done

    ctx, paths, seg = _build_ctx_paths_seg(tmp_path)
    mark_part_skipped_done(ctx, idx=1, paths=paths, seg=seg)

    assert len(_capture_upsert) == 1
    args, _ = _capture_upsert[0]
    # Positional shape: job_id, idx, part_name, stage, progress,
    # start, end, duration, viral, motion, hook, output_file, message
    assert args[0] == "job-mt4b"
    assert args[1] == 1
    assert args[2] == "story_part_001.mp4"
    assert args[3] == JobPartStage.DONE, (
        "Sacred Contract #5 violation: resume-skip must emit JobPartStage.DONE "
        f"got {args[3]!r}"
    )
    assert args[4] == 100, "Resume-skip progress must be 100"
    assert args[5] == 10.0 and args[6] == 40.0 and args[7] == 30.0
    assert args[8] == 88 and args[9] == 72 and args[10] == 90
    assert args[11] == str(paths.final_part), (
        "Resume-skip output_file must point at the final_part on disk"
    )
    assert args[12] == "Skipped (already rendered)", (
        "User-visible message changed — check the FE doesn't substring-match it"
    )


# ---------------------------------------------------------------------------
# 2. mark_part_waiting — first DB write after the resume check
# ---------------------------------------------------------------------------


def test_mark_part_waiting_writes_waiting_at_5_with_empty_output(tmp_path, _capture_upsert):
    from app.core.stage import JobPartStage
    from app.features.render.engine.stages.part_db import mark_part_waiting

    ctx, paths, seg = _build_ctx_paths_seg(tmp_path)
    mark_part_waiting(ctx, idx=2, paths=paths, seg=seg)

    args, _ = _capture_upsert[0]
    assert args[1] == 2
    assert args[3] == JobPartStage.WAITING, (
        "Sacred Contract #5 violation: first post-resume transition must be WAITING"
    )
    assert args[4] == 5, "WAITING progress is intentionally low — pin"
    assert args[11] == "", (
        "WAITING transition output_file must be empty — encode hasn't started"
    )
    assert args[12] == "Waiting for worker"


# ---------------------------------------------------------------------------
# 3. mark_part_rendering — asset prep done, encoding begins
# ---------------------------------------------------------------------------


def test_mark_part_rendering_writes_rendering_at_70_with_final_path(tmp_path, _capture_upsert):
    from app.core.stage import JobPartStage
    from app.features.render.engine.stages.part_db import mark_part_rendering

    ctx, paths, seg = _build_ctx_paths_seg(tmp_path)
    mark_part_rendering(ctx, idx=3, paths=paths, seg=seg)

    args, _ = _capture_upsert[0]
    assert args[1] == 3
    assert args[3] == JobPartStage.RENDERING
    assert args[4] == 70, (
        "RENDERING progress is the 'we're at encode' marker — pin so a future "
        "tweak doesn't desync the FE's progress bar."
    )
    assert args[11] == str(paths.final_part)
    assert args[12] == "Rendering final video"


# ---------------------------------------------------------------------------
# 4. Sacred Contract #5: every facade emits an enum, never a raw string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("facade_name", [
    "mark_part_skipped_done",
    "mark_part_waiting",
    "mark_part_rendering",
])
def test_facade_emits_jobpartstage_enum_not_raw_string(tmp_path, _capture_upsert, facade_name):
    """Sacred Contract #5: stage strings are frozen and the safest way
    to enforce that is to use the JobPartStage enum. A regression that
    swaps an enum for a raw 'done' string here would silently corrupt
    the FE's status mapping."""
    from app.core.stage import JobPartStage
    from app.features.render.engine.stages import part_db as part_db_mod

    ctx, paths, seg = _build_ctx_paths_seg(tmp_path)
    getattr(part_db_mod, facade_name)(ctx, idx=1, paths=paths, seg=seg)

    args, _ = _capture_upsert[0]
    assert isinstance(args[3], JobPartStage), (
        f"{facade_name} emitted a non-enum stage: {args[3]!r} ({type(args[3]).__name__}). "
        "Sacred Contract #5 demands JobPartStage enum members."
    )


# ---------------------------------------------------------------------------
# 5. Defensive: seg.get() defaults to 0 when scores missing
# ---------------------------------------------------------------------------


def test_facade_tolerates_missing_score_keys(tmp_path, _capture_upsert):
    """The pre-extraction inline code used ``seg.get("viral_score", 0)``
    — a stored payload missing the score keys still produced a valid
    DB row. Pin so the facade preserves the same defaulting."""
    from app.features.render.engine.stages.part_db import mark_part_waiting

    ctx = SimpleNamespace(job_id="job-mt4b")
    from app.features.render.engine.stages.segment_metadata import PartPaths
    paths = PartPaths(
        raw_part=tmp_path / "x_raw.mp4",
        srt_part=tmp_path / "x.srt",
        ass_part=tmp_path / "x.ass",
        translated_srt_part=tmp_path / "x.en.srt",
        final_part=tmp_path / "f.mp4",
        part_name="f.mp4",
    )
    # Only the required start/end/duration keys present — scores missing.
    seg = {"start": 0.0, "end": 5.0, "duration": 5.0}

    mark_part_waiting(ctx, idx=1, paths=paths, seg=seg)

    args, _ = _capture_upsert[0]
    assert args[8] == 0 and args[9] == 0 and args[10] == 0
