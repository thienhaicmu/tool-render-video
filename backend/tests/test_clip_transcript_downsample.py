"""
test_clip_transcript_downsample.py — guard for 0D (clip transcript downsampling).

Pins two properties of build_render_plan_prompt's transcript fitting:
  1. Short sources (<= cap) pass through unchanged — byte-identical to the old
     head-slice behaviour (no regression for the common short-form case).
  2. Long sources are DOWNSAMPLED across the whole runtime, not head-sliced, so
     lines from the BACK HALF survive (the bug: clips after ~30 min were invisible).
Also checks format-safety (a transcript containing braces must not break .format()).
"""
from __future__ import annotations

from app.features.render.ai.llm.prompts import (
    _fit_seconds_transcript,
    build_render_plan_prompt,
)


def test_short_transcript_passthrough_unchanged():
    text = "[0.0 - 2.0] hello\n[2.0 - 4.0] world"
    assert _fit_seconds_transcript(text, 10_000) == text  # under cap → identical


def test_long_transcript_downsampled_covers_start_and_end():
    # Build a long seconds-format transcript with unique start/end markers.
    lines = [f"[{i}.0 - {i}.9] line number {i}" for i in range(4000)]
    text = "\n".join(lines)
    cap = 5000
    out = _fit_seconds_transcript(text, cap)
    # Downsample marker present, budget respected (+ short marker line).
    assert "downsampled to fit" in out
    assert len(out) <= cap + 80
    # Crucially: content from BOTH the opening AND the final stretch survives —
    # a head-slice would contain only early line numbers.
    assert "line number 0" in out or "line number 1 " in out
    assert any(f"line number {n}" in out for n in range(3900, 4000)), \
        "back half of a long transcript must survive downsampling (0D fix)"


def test_downsample_never_raises_on_junk():
    assert _fit_seconds_transcript("", 100) == ""
    assert isinstance(_fit_seconds_transcript("x" * 500, 100), str)


def test_build_prompt_format_safe_with_braces_in_transcript():
    # Transcript text containing { } must not break str.format() in the builder.
    srt = "1\n00:00:01,000 --> 00:00:03,000\nuse a dict like {key: value} here\n"
    system, user = build_render_plan_prompt(
        srt_content=srt, output_count=3, min_sec=20, max_sec=60, language="en",
    )
    assert "RenderPlan" in system
    assert "{key: value}" in user or "(key: value)" in user or "key" in user
