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


# ── A2: base-video layer ──────────────────────────────────────────────────────

def _capture(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"\x00" * 256)
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(br.subprocess, "run", fake_run)
    return captured


def test_video_base_uses_segment_not_kenburns(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    # The base video "exists"; the written output file also passes the real check.
    monkeypatch.setattr(br, "_ok_file", lambda p: p == "/base.mp4" or bool(p) and Path(p).exists())
    ctx = SimpleNamespace(width=1280, height=720, fps=30.0, shots_dir=str(tmp_path),
                          bg_value="#101820", ffmpeg_threads=0,
                          base_video_path="/base.mp4", base_video_dur=10.0)
    cue = SimpleNamespace(start_sec=13.0, end_sec=15.0, crop_from=(0.0, 0.0, 1.0, 1.0),
                          crop_to=(0.0, 0.0, 1.0, 1.0), visual_id="v1", audio_path="",
                          hook=False, hook_text="", text_anchor="auto")
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}))
    r = br.render_one_cue(ctx, plan, 1, cue)
    assert r["clip"] and r["fallback"] is False       # a real base was used

    cmd = captured["cmd"]
    assert "-stream_loop" in cmd and cmd[cmd.index("-stream_loop") + 1] == "-1"
    assert "/base.mp4" in cmd
    # start_sec 13 % base_dur 10 = 3.0 → seeked into the looped video
    assert cmd[cmd.index("-ss") + 1] == "3.000"
    assert "-loop" not in cmd                          # NOT the image path
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "force_original_aspect_ratio=increase" in fc and "crop=1280:720" in fc
    assert "zoompan" not in fc                         # no Ken Burns on video


def _video_ctx(tmp_path, extra=None):
    return SimpleNamespace(width=720, height=1280, fps=30.0, shots_dir=str(tmp_path),
                           bg_value="#101820", ffmpeg_threads=0,
                           base_video_path="/base.mp4", base_video_dur=4.0, **(extra or {}))


def _overlay_cue(anchor="right", scale="large", motion="fade"):
    return SimpleNamespace(start_sec=0.0, end_sec=2.0, crop_from=(0, 0, 1, 1), crop_to=(0, 0, 1, 1),
                           visual_id="v1", audio_path="", hook=False, hook_text="", text_anchor="auto",
                           speaker_id="han", char_anchor=anchor, char_scale=scale, char_motion=motion)


def test_char_overlay_composites_master(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p in ("/base.mp4", "/m.png") or bool(p) and Path(p).exists())
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}, masters={"han": "/m.png"}))
    br.render_one_cue(_video_ctx(tmp_path), plan, 1, _overlay_cue(scale="large", motion="fade"))
    cmd = captured["cmd"]
    assert "/m.png" in cmd                            # master added as an input
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[2:v]" in fc and "overlay=x=" in fc       # composited from input [2]
    assert f"scale=-1:{int(1280 * 0.90)}" in fc       # large → 0.90 of canvas height
    assert "fade=t=in" in fc and "alpha=1" in fc      # fade motion on the fg


def test_char_overlay_slide_uses_time_expr(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p in ("/base.mp4", "/m.png") or bool(p) and Path(p).exists())
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}, masters={"han": "/m.png"}))
    br.render_one_cue(_video_ctx(tmp_path), plan, 1, _overlay_cue(anchor="left", motion="slide"))
    fc = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "if(lt(t," in fc                            # slide animates x over time


def test_no_overlay_when_char_anchor_none(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p == "/base.mp4" or bool(p) and Path(p).exists())
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}, masters={"han": "/m.png"}))
    br.render_one_cue(_video_ctx(tmp_path), plan, 1, _overlay_cue(anchor="none"))
    cmd = captured["cmd"]
    assert "/m.png" not in cmd                         # no overlay input
    assert "overlay=x=" not in cmd[cmd.index("-filter_complex") + 1]


def test_no_overlay_without_base_video(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p == "/img.png" or bool(p) and Path(p).exists())
    # image-based (no base video) → overlay never engages even if char_anchor is set.
    ctx = SimpleNamespace(width=720, height=1280, fps=30.0, shots_dir=str(tmp_path),
                          bg_value="#101820", ffmpeg_threads=0)
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={"v1": "/img.png"}, masters={"han": "/m.png"}))
    br.render_one_cue(ctx, plan, 1, _overlay_cue())
    assert "/m.png" not in captured["cmd"]


def test_no_base_video_keeps_image_kenburns_path(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p == "/img.png")
    # ctx has NO base_video_path → image path unchanged (byte-identical to pre-A2).
    ctx = SimpleNamespace(width=1280, height=720, fps=30.0, shots_dir=str(tmp_path),
                          bg_value="#101820", ffmpeg_threads=0)
    cue = SimpleNamespace(start_sec=0.0, end_sec=2.0, crop_from=(0.0, 0.0, 1.0, 1.0),
                          crop_to=(0.0, 0.0, 1.0, 1.0), visual_id="v1", audio_path="",
                          hook=False, hook_text="", text_anchor="auto")
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={"v1": "/img.png"}))
    br.render_one_cue(ctx, plan, 1, cue)
    cmd = captured["cmd"]
    assert "-stream_loop" not in cmd
    assert "-loop" in cmd and "/img.png" in cmd
    assert "zoompan" in cmd[cmd.index("-filter_complex") + 1]
