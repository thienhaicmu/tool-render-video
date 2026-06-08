"""Audit MT-4 phase A closure (Batch 10P 2026-06-06).

``build_part_paths`` extracted from ``process_one_part`` (lines 92-113
pre-extraction). It owns the six per-part filesystem path derivations:

- ``raw_part / srt_part / ass_part / translated_srt_part`` —
  intermediate work files under ``ctx.work_dir``.
- ``final_part`` — the output mp4 path under ``ctx.output_dir``.
- ``part_name`` — basename string used for DB rows.

The output filename selection has three branches that must be preserved
byte-for-byte (the rest of the pipeline reads ``part_name`` and writes
files at ``final_part``):

1. ``seg.variant_type`` set → ``{output_stem}_{variant}.mp4``
2. ``seg.clip_name`` set + path does NOT exist → ``{clip_name}.mp4``
3. ``seg.clip_name`` set + path EXISTS → ``{clip_name}_{idx:03d}.mp4``
   (collision guard)
4. Default → ``{output_stem}_part_{idx:03d}.mp4``

This file pins all four paths + the four intermediate work files.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _build_ctx(tmp_path: Path, *, source_slug: str = "myvideo",
               output_stem: str = "stem", subtitle_target_language: str = "en"):
    """Cheap PartRenderContext stand-in — we don't need the full dataclass.
    ``build_part_paths`` only touches ctx.work_dir, ctx.output_dir,
    ctx.source["slug"], ctx.output_stem, and ctx.payload.subtitle_target_language."""
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "out"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        work_dir=work_dir,
        output_dir=output_dir,
        source={"slug": source_slug},
        output_stem=output_stem,
        payload=SimpleNamespace(subtitle_target_language=subtitle_target_language),
    )


# ---------------------------------------------------------------------------
# 1. Default branch — no variant, no clip_name
# ---------------------------------------------------------------------------


def test_default_branch_predictable_per_part_filename(tmp_path):
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    paths = build_part_paths(ctx, idx=1, seg={})

    assert paths.raw_part            == tmp_path / "work" / "src_part_001_raw.mp4"
    assert paths.srt_part            == tmp_path / "work" / "src_part_001.srt"
    assert paths.ass_part            == tmp_path / "work" / "src_part_001.ass"
    assert paths.translated_srt_part == tmp_path / "work" / "src_part_001.en.srt"
    assert paths.final_part          == tmp_path / "out" / "story_part_001.mp4"
    assert paths.part_name           == "story_part_001.mp4"


def test_default_branch_with_larger_idx_pads_three_digits(tmp_path):
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    paths = build_part_paths(ctx, idx=42, seg={})

    assert paths.raw_part.name   == "src_part_042_raw.mp4"
    assert paths.final_part.name == "story_part_042.mp4"
    assert paths.part_name       == "story_part_042.mp4"


# ---------------------------------------------------------------------------
# 2. Variant branch — multi-variant render
# ---------------------------------------------------------------------------


def test_variant_branch_uses_variant_suffix(tmp_path):
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    seg = {"variant_type": "aggressive"}
    paths = build_part_paths(ctx, idx=1, seg=seg)

    assert paths.final_part.name == "story_aggressive.mp4"
    assert paths.part_name       == "story_aggressive.mp4"
    # Intermediate work files still use the part-index pattern.
    assert paths.raw_part.name == "src_part_001_raw.mp4"


def test_variant_branch_ignores_clip_name(tmp_path):
    """When variant_type is set, clip_name MUST be ignored — variant
    output naming wins. Pin so a future refactor that swaps branch
    precedence breaks loudly."""
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    seg = {"variant_type": "balanced", "clip_name": "should_be_ignored"}
    paths = build_part_paths(ctx, idx=2, seg=seg)

    assert paths.part_name == "story_balanced.mp4"
    assert "should_be_ignored" not in paths.part_name


# ---------------------------------------------------------------------------
# 3. clip_name branch — LLM-provided natural filename
# ---------------------------------------------------------------------------


def test_clip_name_branch_uses_natural_name(tmp_path):
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    seg = {"clip_name": "People losing it over cameras"}
    paths = build_part_paths(ctx, idx=1, seg=seg)

    assert paths.final_part.name == "People losing it over cameras.mp4"
    assert paths.part_name       == "People losing it over cameras.mp4"


def test_clip_name_collision_appends_idx(tmp_path):
    """If a file with the chosen name already exists in output_dir,
    append the part index. This prevents silent overwrite when a
    follow-up render reuses an LLM-suggested name from a prior job."""
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    # Pre-create the file that would collide.
    collision_target = ctx.output_dir / "great clip.mp4"
    collision_target.write_bytes(b"\x00")

    seg = {"clip_name": "great clip"}
    paths = build_part_paths(ctx, idx=7, seg=seg)

    assert paths.final_part.name == "great clip_007.mp4"
    assert paths.part_name       == "great clip_007.mp4"


def test_empty_clip_name_falls_through_to_default(tmp_path):
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, source_slug="src", output_stem="story")
    seg = {"clip_name": "   "}  # whitespace-only
    paths = build_part_paths(ctx, idx=1, seg=seg)

    # Empty/whitespace clip_name does NOT win the branch — default path.
    assert paths.final_part.name == "story_part_001.mp4"


# ---------------------------------------------------------------------------
# 4. translated_srt_part respects payload.subtitle_target_language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang,expected_suffix", [
    ("en", "en.srt"),
    ("ja", "ja.srt"),
    ("vi", "vi.srt"),
])
def test_translated_srt_part_honors_target_language(tmp_path, lang, expected_suffix):
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path, subtitle_target_language=lang)
    paths = build_part_paths(ctx, idx=1, seg={})
    assert paths.translated_srt_part.name.endswith(expected_suffix)


def test_translated_srt_defaults_to_en_when_payload_missing_attribute(tmp_path):
    """Sacred Contract #2 spirit: a stored payload from a pre-Sprint-4
    job lacks subtitle_target_language entirely. The getattr default
    keeps the path computation working."""
    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path)
    # Strip the attribute to simulate a pre-Sprint-4 payload replay.
    del ctx.payload.subtitle_target_language
    paths = build_part_paths(ctx, idx=1, seg={})
    assert paths.translated_srt_part.name.endswith(".en.srt")


# ---------------------------------------------------------------------------
# 5. PartPaths is frozen — accidental mutation fails loudly
# ---------------------------------------------------------------------------


def test_part_paths_dataclass_is_frozen(tmp_path):
    from dataclasses import FrozenInstanceError

    from app.features.render.engine.stages.segment_metadata import build_part_paths

    ctx = _build_ctx(tmp_path)
    paths = build_part_paths(ctx, idx=1, seg={})
    with pytest.raises(FrozenInstanceError):
        paths.part_name = "rewritten.mp4"  # type: ignore[misc]
