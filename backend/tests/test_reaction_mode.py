"""Reaction narration mode (narration_mode="reaction") — schema + freeze plan.

Covers Phase A (segment schema: kind / freeze_after / freeze_text in the
rewrite parser + prompt persona) and Phase B (freeze-point planning with the
per-point and per-clip caps + source→final time mapping). Pure logic — no
FFmpeg/LLM calls.
"""
import pytest

from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt
from app.features.render.engine.stages.part_reaction_freeze import plan_freeze_points


# ── Parser: reaction schema ──────────────────────────────────────────────────

def test_parser_keeps_voice_and_original_segments():
    raw = (
        '{"segments":['
        '{"kind":"voice","start":3,"end":6,"text":"lead in","freeze_after":1.5,"freeze_text":"wait"},'
        '{"kind":"original","start":7,"end":11}'
        ']}'
    )
    out = parse_rewrite_response(raw, 12.0, 50)
    assert out is not None and len(out) == 2
    voice, original = out
    assert voice["kind"] == "voice" and voice["text"] == "lead in"
    assert voice["freeze_after"] == 1.5 and voice["freeze_text"] == "wait"
    assert original["kind"] == "original" and original["text"] == ""


def test_parser_drops_voice_without_text_keeps_original_without_text():
    raw = (
        '{"segments":['
        '{"kind":"voice","start":0,"end":3,"text":""},'      # dropped (voice needs text)
        '{"kind":"original","start":4,"end":7}'              # kept (no text expected)
        ']}'
    )
    out = parse_rewrite_response(raw, 10.0, 50)
    assert out is not None and len(out) == 1
    assert out[0]["kind"] == "original"


def test_parser_clamps_freeze_after_to_ceiling():
    raw = '{"segments":[{"kind":"voice","start":0,"end":3,"text":"x","freeze_after":99}]}'
    out = parse_rewrite_response(raw, 10.0, 50)
    assert out is not None
    assert out[0]["freeze_after"] <= 3.0  # _FREEZE_MAX_PER_POINT_SEC ceiling


def test_parser_default_kind_is_voice_backcompat():
    # Faithful-rewrite shape (no kind) → defaults to voice, no freeze.
    raw = '{"segments":[{"start":0,"end":4,"text":"hello"}]}'
    out = parse_rewrite_response(raw, 4.0, 50)
    assert out is not None and out[0]["kind"] == "voice"
    assert out[0]["freeze_after"] == 0.0 and out[0]["freeze_text"] == ""


# ── Prompt: reaction persona ─────────────────────────────────────────────────

def test_reaction_prompt_injects_section_and_no_brace_leak():
    _, user = build_rewrite_prompt("[0-5] a", 5.0, "vi-VN", narration_mode="reaction")
    assert "REACTION MODE" in user
    assert "{{" not in user and "}}" not in user  # no format-brace leak


def test_default_prompt_has_no_reaction_section():
    _, user = build_rewrite_prompt("[0-5] a", 5.0, "vi-VN")
    assert "REACTION MODE" not in user


# ── Freeze planning: caps + time mapping ─────────────────────────────────────

def test_plan_clamps_per_point():
    segs = [{"kind": "voice", "start": 0, "end": 6, "text": "x", "freeze_after": 5.0}]
    pts = plan_freeze_points(segs, render_speed=1.0, clip_final_duration=20.0)
    assert len(pts) == 1 and pts[0]["hold"] <= 2.0  # default per-point cap


def test_plan_enforces_total_cap():
    segs = [
        {"kind": "voice", "start": i * 4, "end": i * 4 + 3, "text": "x", "freeze_after": 2.0}
        for i in range(5)
    ]
    pts = plan_freeze_points(segs, render_speed=1.0, clip_final_duration=60.0)
    assert sum(p["hold"] for p in pts) <= 6.0 + 1e-6  # default total cap


def test_plan_maps_source_time_by_speed():
    # voice ends at source t=6s; at 2x speed the freeze lands near final t=3s.
    segs = [{"kind": "voice", "start": 0, "end": 6, "text": "x", "freeze_after": 1.0}]
    pts = plan_freeze_points(segs, render_speed=2.0, clip_final_duration=10.0)
    assert len(pts) == 1
    assert pts[0]["at"] == pytest.approx(3.0, abs=0.05)


def test_plan_skips_original_segments_and_zero_freeze():
    segs = [
        {"kind": "original", "start": 0, "end": 5},
        {"kind": "voice", "start": 5, "end": 8, "text": "x", "freeze_after": 0},
    ]
    assert plan_freeze_points(segs, render_speed=1.0, clip_final_duration=10.0) == []


def test_plan_empty_when_no_segments():
    assert plan_freeze_points([], render_speed=1.0, clip_final_duration=10.0) == []
