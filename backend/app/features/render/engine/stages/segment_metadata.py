"""SegmentMetadata — per-part filesystem layout derived from ctx + seg.

Audit MT-4 phase A closure (Batch 10P, 2026-06-06). Closes the first
slice of FINDING-A20: ``process_one_part`` previously mixed path
derivation, DB writes, event emission, and stage orchestration into
one 272-LOC function. The path-derivation block (raw_part, srt_part,
ass_part, final_part, part_name, translated_srt_part) moved here as a
pure data helper.

Sacred Contracts touched: none. This module owns NO DB writes, NO
event emissions, NO state machine transitions. It only computes
filesystem paths from inputs.

The naming rules preserved byte-for-byte from the pre-extraction
``process_one_part`` body:

- When ``seg.variant_type`` is set (multi-variant render): output is
  ``{output_stem}_{variant}.mp4``.
- Else when ``seg.clip_name`` is set (LLM-provided natural filename):
  output is ``{clip_name}.mp4`` — with a ``_{idx:03d}`` suffix appended
  if a file with the same name already exists in ``output_dir`` (collision
  guard).
- Else (default): output is ``{output_stem}_part_{idx:03d}.mp4``.

The intermediate work files (raw / srt / ass / translated_srt) follow
the ``{source_slug}_part_{idx:03d}.<ext>`` pattern regardless of which
branch picks the final filename. They live under ``ctx.work_dir`` and
are cleaned up by the pipeline's finally block.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.features.render.engine.stages.part_render_context import PartRenderContext


@dataclass(frozen=True)
class PartPaths:
    """Frozen container for the six per-part filesystem paths.

    Field names mirror the original local-variable names used by
    ``process_one_part`` so the call-site adapter is a straight
    one-to-one mapping — no behavior change is possible.
    """
    raw_part:            Path  # work_dir/<slug>_part_<idx>_raw.mp4
    srt_part:            Path  # work_dir/<slug>_part_<idx>.srt
    ass_part:            Path  # work_dir/<slug>_part_<idx>.ass
    translated_srt_part: Path  # work_dir/<slug>_part_<idx>.<target_lang>.srt
    final_part:          Path  # output_dir/<final_filename>.mp4
    part_name:           str   # basename of final_part (used for DB rows)


def build_part_paths(ctx: PartRenderContext, idx: int, seg: dict) -> PartPaths:
    """Compute the six filesystem paths for a single part.

    The output filename selection mirrors the original three-branch
    logic in ``process_one_part`` lines 92-113 (pre-extraction). The
    work-file naming follows ``{source_slug}_part_{idx:03d}.*`` so
    multiple parts of the same source don't collide.

    Sacred Contract #2: the function reads ``ctx.payload.subtitle_target_language``
    via ``getattr(..., 'en')`` so a stored payload missing the field
    (pre-Sprint 4.x) still produces a valid translated_srt path. Never
    raises on a missing or empty seg key — defaults to '' and the
    default-output branch runs.
    """
    source_slug = ctx.source["slug"]
    work_stem   = f"{source_slug}_part_{idx:03d}"

    raw_part = ctx.work_dir / f"{work_stem}_raw.mp4"
    srt_part = ctx.work_dir / f"{work_stem}.srt"
    ass_part = ctx.work_dir / f"{work_stem}.ass"

    sub_target_lang     = getattr(ctx.payload, "subtitle_target_language", "en")
    translated_srt_part = ctx.work_dir / f"{work_stem}.{sub_target_lang}.srt"

    variant_type = str(seg.get("variant_type") or "")
    if variant_type:
        # Multi-variant render — one output per variant of the same segment.
        final_part = ctx.output_dir / f"{ctx.output_stem}_{variant_type}.mp4"
        part_name  = f"{ctx.output_stem}_{variant_type}.mp4"
    else:
        clip_name = str(seg.get("clip_name") or "").strip()
        if clip_name:
            # LLM-provided natural filename — already FS-safe (sanitized by
            # groq/parser.py / llm/parser.py before reaching this point).
            # Collision guard: if a file with the same name already exists
            # in the output dir (e.g. from a previous render of the same
            # source), append the part index to avoid silent overwrite.
            candidate = ctx.output_dir / f"{clip_name}.mp4"
            if candidate.exists():
                clip_name = f"{clip_name}_{idx:03d}"
            final_part = ctx.output_dir / f"{clip_name}.mp4"
            part_name  = f"{clip_name}.mp4"
        else:
            # Default output naming: predictable per-part filename.
            final_part = ctx.output_dir / f"{ctx.output_stem}_part_{idx:03d}.mp4"
            part_name  = f"{ctx.output_stem}_part_{idx:03d}.mp4"

    return PartPaths(
        raw_part=raw_part,
        srt_part=srt_part,
        ass_part=ass_part,
        translated_srt_part=translated_srt_part,
        final_part=final_part,
        part_name=part_name,
    )


__all__ = ["PartPaths", "build_part_paths"]
