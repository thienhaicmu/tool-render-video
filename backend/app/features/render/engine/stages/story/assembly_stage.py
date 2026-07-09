"""
assembly_stage.py — join Story shot clips → one video (P5).

Reuses Content's ``concat_with_transitions`` (xfade/acrossfade per boundary, driven
by the 2-tier transition list: cut within a scene, fade between scenes) and falls
back to a plain concat (recap_assembler.concat_clips) on any xfade failure — so a
render is never lost to a filtergraph edge case. A single shot is copied straight
through. Never raises; returns ``{ok, method, expected_duration}``.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core.stage import JobStage

logger = logging.getLogger("app.render.story")


def assemble_shots(ctx, plan, payload, *, output_dir, output_stem, shot_clips, transitions, set_stage):
    """Assemble ``shot_clips`` (ordered) → final_out with 2-tier transitions.
    Returns (final_out: Path, result: dict)."""
    final_out = output_dir / f"{output_stem}.mp4"
    set_stage(JobStage.WRITING_REPORT, 88, f"Assembling {len(shot_clips)} shot(s)")

    # Single shot → copy straight through (nothing to concat).
    if len(shot_clips) == 1:
        try:
            shutil.copyfile(shot_clips[0], str(final_out))
        except Exception as exc:
            logger.warning("story: single-shot copy failed: %s", exc)
            return final_out, {"ok": False, "method": "copy_failed", "expected_duration": 0.0}
        return final_out, {"ok": True, "method": "single", "expected_duration": 0.0}

    from app.features.render.engine.stages.content_assembler import concat_with_transitions
    res = concat_with_transitions(
        shot_clips, str(final_out), transitions=transitions,
        width=ctx.width, height=ctx.height, fps=ctx.fps,
    )
    if res.get("ok") and final_out.exists() and final_out.stat().st_size > 0:
        return final_out, res

    # Fallback: plain concat (re-encode) — never lose a render to an xfade edge case.
    logger.info("story: xfade assembly failed (%s) — plain concat fallback", res.get("method"))
    from app.features.render.engine.stages.recap_assembler import concat_clips
    res2 = concat_clips(shot_clips, str(final_out), width=ctx.width, height=ctx.height, fps=ctx.fps)
    return final_out, res2


__all__ = ["assemble_shots"]
