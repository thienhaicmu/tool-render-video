"""PartDB — centralized DB-write facade for per-part stage transitions.

Audit MT-4 phase B closure (Batch 10Q, 2026-06-06). Closes the second
slice of FINDING-A20: ``process_one_part`` previously called
``upsert_job_part`` inline at three different stage transitions with
the same 9 invariant arguments and only the stage / progress /
output_file / message varying. The facade pulls those three calls
into named functions so:

  1. Sacred Contract #5 (frozen per-part stage transition names) has a
     single grep-able surface — every ``upsert_job_part`` call from
     ``process_one_part`` now lives in one ~60-LOC file.
  2. A test can pin the (stage, progress, output_file, message) tuple
     for each transition without spinning up the pipeline.
  3. A future observability addition (e.g. counter per transition,
     structured log line) plugs in here in 3 places instead of 3 inline
     sites scattered across part_renderer.py.

Sacred Contracts touched by this module:

- #5 (frozen per-part stage names): every emit uses a ``JobPartStage``
  enum value, never a raw string. The stage strings themselves are
  unchanged from the pre-extraction inline calls.
- #7 (DB sole authority): all writes go through ``app.db.jobs_repo.
  upsert_job_part`` — never a raw ``sqlite3.connect`` call here.

Sacred Contracts NOT touched: #1 (result_json keys — finalize/ranking
own those), #6 (_emit_render_event shape — pure DB facade, no WS), #8
(qa_pipeline gate).

Why module-level functions instead of a class: there is no per-instance
state worth holding. The 3 transitions read from PartRenderContext +
PartPaths + seg dict and write through the shared ``upsert_job_part``
import. A class would be ornamental — straight functions match the
project's existing module-helper style (see ``part_done.run_part_done``).
"""
from __future__ import annotations

from app.core.stage import JobPartStage
from app.db.jobs_repo import upsert_job_part
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.features.render.engine.stages.segment_metadata import PartPaths


def mark_part_skipped_done(
    ctx: PartRenderContext, idx: int, paths: PartPaths, seg: dict
) -> None:
    """Resume-skip terminal write — Sacred Contract #5: directly into DONE.

    Fired by ``process_one_part`` when ``resume_from_last=True`` and the
    final output file already exists and validates via ffprobe (see
    BR12 invariant in ``part_renderer.py`` and the resume comment block
    there). Skips every intermediate WAITING / CUTTING / TRANSCRIBING /
    RENDERING transition — the file is already on disk.

    Stage = JobPartStage.DONE, progress = 100, output_file = final_part,
    message = "Skipped (already rendered)".
    """
    upsert_job_part(
        ctx.job_id, idx, paths.part_name, JobPartStage.DONE, 100,
        seg["start"], seg["end"], seg["duration"],
        seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0),
        str(paths.final_part), "Skipped (already rendered)",
    )


def mark_part_waiting(
    ctx: PartRenderContext, idx: int, paths: PartPaths, seg: dict
) -> None:
    """First DB write after the resume-skip check passes — Sacred
    Contract #5 WAITING.

    Output file is empty because the encode hasn't started yet — we
    don't know the final path won't be renamed by collision guard in
    a future variant. Progress at 5% mirrors the FE's "starting" bar.
    """
    upsert_job_part(
        ctx.job_id, idx, paths.part_name, JobPartStage.WAITING, 5,
        seg["start"], seg["end"], seg["duration"],
        seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0),
        "", "Waiting for worker",
    )


def mark_part_rendering(
    ctx: PartRenderContext, idx: int, paths: PartPaths, seg: dict
) -> None:
    """Asset prep done, FFmpeg encoding begins — Sacred Contract #5
    RENDERING.

    Output_file is committed at this point (final_part) — the encode
    target is fixed and qa_pipeline will validate the file at this
    exact path during finalize.
    """
    upsert_job_part(
        ctx.job_id, idx, paths.part_name, JobPartStage.RENDERING, 70,
        seg["start"], seg["end"], seg["duration"],
        seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0),
        str(paths.final_part), "Rendering final video",
    )


__all__ = [
    "mark_part_skipped_done",
    "mark_part_waiting",
    "mark_part_rendering",
]
