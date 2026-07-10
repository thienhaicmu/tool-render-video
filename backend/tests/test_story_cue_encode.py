"""Story v2 — Q4: cue clips are a near-lossless INTERMEDIATE.

render_one_cue must encode each cue with the configurable STORY_CUE_CRF /
STORY_CUE_PRESET (near-lossless + fast) so the assembler's mandatory xfade
re-encode is the only quality-defining pass — no double-encode quality loss.
Captures the ffmpeg argv (no real encode) and asserts the wiring.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app.features.render.engine.stages.story.beat_render as br


def _ctx(tmp_path):
    return SimpleNamespace(width=1280, height=720, fps=30.0, shots_dir=str(tmp_path),
                           bg_value="#101820", ffmpeg_threads=0)


def _cue():
    return SimpleNamespace(start_sec=0.0, end_sec=2.0, crop_from=(0.0, 0.0, 1.0, 1.0),
                           crop_to=(0.0, 0.0, 1.0, 1.0), visual_id="v1", audio_path="",
                           hook=False, hook_text="", subtitle="")


def test_defaults_are_near_lossless():
    # The shipped defaults: near-lossless crf + a fast preset (intermediate, re-encoded).
    assert br._CUE_CRF == "15"
    assert br._CUE_PRESET == "veryfast"


def test_render_one_cue_uses_configurable_intermediate(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"\x00" * 256)   # out path is the last arg
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(br.subprocess, "run", fake_run)
    # Prove the encode reads the (env-driven) module constants rather than hardcoding.
    monkeypatch.setattr(br, "_CUE_CRF", "13")
    monkeypatch.setattr(br, "_CUE_PRESET", "faster")

    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}))
    r = br.render_one_cue(_ctx(tmp_path), plan, 1, _cue())
    assert r["clip"], r

    cmd = captured["cmd"]
    assert "libx264" in cmd
    assert cmd[cmd.index("-crf") + 1] == "13"
    assert cmd[cmd.index("-preset") + 1] == "faster"
    # still a single delivered stream pair + faststart (intermediate stays mp4)
    assert "+faststart" in cmd
