"""
test_clip_prompt_focused.py — guard for P1-4 (focused clip prompt).

Pins both modes of build_render_plan_prompt:
- default (fused): still asks for subtitle_policy / camera_strategy / audio_plan
  (byte-identical to prior behaviour);
- CLIP_PROMPT_FOCUSED=1: un-fused — a reasoning field + clips only, with the
  top-level sub-plans dropped (the parser defaults them). Format-safety holds in
  both modes.
"""
from __future__ import annotations

import json

from app.features.render.ai.llm.prompts import build_render_plan_prompt
from app.features.render.ai.llm.parser import parse_render_plan_response

_ARGS = dict(srt_content="1\n00:00:01,000 --> 00:00:03,000\nhello world\n",
             output_count=5, min_sec=20, max_sec=60, language="en")


def test_fused_is_default_and_keeps_subplans(monkeypatch):
    monkeypatch.delenv("CLIP_PROMPT_FOCUSED", raising=False)
    system, user = build_render_plan_prompt(**_ARGS)
    assert "subtitle_policy" in user        # top-level sub-plan requested
    assert "camera_strategy" in user
    assert "audio_plan" in user
    assert "SUBTITLE POLICY" in user        # STEP 2 header present
    assert '"reasoning"' not in user        # fused does not ask for reasoning


def test_focused_drops_subplans_and_adds_reasoning(monkeypatch):
    monkeypatch.setenv("CLIP_PROMPT_FOCUSED", "1")
    system, user = build_render_plan_prompt(**_ARGS)
    assert '"reasoning"' in user                     # reasoning field requested
    assert "CLIP SELECTION" in user                  # selection kept
    assert "reasoning" in system.lower()
    # Top-level sub-plans dropped:
    assert "subtitle_policy" not in user
    assert "camera_strategy" not in user
    assert "audio_plan" not in user
    assert "SUBTITLE POLICY" not in user
    # Per-clip fields are KEPT (they drive selection + downstream resolvers):
    assert "subtitle_style" in user
    assert "hook_type" in user


def test_focused_format_safe_with_braces_in_transcript(monkeypatch):
    monkeypatch.setenv("CLIP_PROMPT_FOCUSED", "1")
    args = {**_ARGS, "srt_content": "1\n00:00:01,000 --> 00:00:03,000\nuse {a: b} here\n"}
    # Must not raise KeyError/IndexError from str.format.
    _, user = build_render_plan_prompt(**args)
    assert "clips" in user


def test_focused_output_parses_to_clips_with_default_subplans(monkeypatch):
    # A focused-style response (reasoning + clips) must parse; reasoning is
    # ignored and the sub-plans fall back to their defaults.
    raw = json.dumps({
        "reasoning": "The strongest moment is the reveal at 44s.",
        "clips": [{"start": 40.0, "end": 75.0, "score": 0.9, "clip_name": "reveal"}],
    })
    plan = parse_render_plan_response(raw, output_count=5, min_sec=20, max_sec=60,
                                      video_duration=600)
    assert plan is not None and len(plan.clips) == 1
    assert plan.subtitle_policy.style == ""   # defaulted — backend resolver decides
    assert plan.camera_strategy.reframe_mode == ""
