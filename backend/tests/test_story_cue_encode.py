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
    # No visual asset on purpose (tests the encode wiring on the legacy solid-bg
    # path) — V3-only mode would refuse to render a blank cue.
    monkeypatch.setenv("STORY_V3_ONLY", "0")
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
    # GĐ4a portrait reflow: 720×1280 is PORTRAIT → large (0.90) × PORTRAIT_SCALE_MULT
    # so two figures fit the narrow frame; right-anchored masters mirror (hflip)
    # to face the scene centre.
    from app.features.render.engine.visual.composition import PORTRAIT_SCALE_MULT
    assert f"scale=-1:{int(1280 * 0.90 * PORTRAIT_SCALE_MULT)}" in fc
    assert "hflip" in fc                              # right anchor faces inward
    assert "fade=t=in" in fc and "alpha=1" in fc      # fade motion on the fg


def test_char_overlay_slide_uses_time_expr(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p in ("/base.mp4", "/m.png") or bool(p) and Path(p).exists())
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}, masters={"han": "/m.png"}))
    br.render_one_cue(_video_ctx(tmp_path), plan, 1, _overlay_cue(anchor="left", motion="slide"))
    fc = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "if(lt(t," in fc                            # slide animates x over time


def test_char_overlay_switches_per_line(monkeypatch, tmp_path):
    # P3 — a dialogue cue with line_overlays chains one TIME-GATED overlay per line so
    # the on-screen character switches with the speaker (image path, no base video).
    from app.domain.story_plan_v2 import LineSpan
    captured = _capture(monkeypatch)
    monkeypatch.setenv("STORY_V3_ONLY", "0")   # legacy solid-bg path (no visual asset)
    monkeypatch.setattr(br, "_ok_file", lambda p: p in ("/mA.png", "/mB.png") or (bool(p) and Path(p).exists()))
    plan = SimpleNamespace(render=SimpleNamespace(
        visual_assets={}, masters={"a:angry:point": "/mA.png", "b:sad:stand": "/mB.png"}))
    ctx = SimpleNamespace(width=1280, height=720, fps=30.0, shots_dir=str(tmp_path),
                          bg_value="#101820", ffmpeg_threads=0)
    cue = SimpleNamespace(start_sec=0.0, end_sec=4.0, crop_from=(0, 0, 1, 1), crop_to=(0, 0, 1, 1),
                          visual_id="v1", audio_path="", hook=False, hook_text="", text_anchor="auto",
                          speaker_id="", char_anchor="none", char_scale="medium", char_motion="fade",
                          emotion="normal", pose="stand", source_audio="mute",
                          line_overlays=[LineSpan(0.0, 2.0, "a", "angry", "point", "center"),
                                         LineSpan(2.0, 4.0, "b", "sad", "stand", "left")])
    br.render_one_cue(ctx, plan, 1, cue)
    cmd = captured["cmd"]
    assert "/mA.png" in cmd and "/mB.png" in cmd          # both line masters added as inputs
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[2:v]" in fc and "[3:v]" in fc                # two overlay inputs
    assert "enable='between(t,0.000,2.000)'" in fc        # line A window
    assert "enable='between(t,2.000,4.000)'" in fc        # line B window


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


# ── Composition-QA: overlay pushes the hook to the top ────────────────────────

def test_overlay_forces_hook_to_top(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p in ("/base.mp4", "/m.png") or bool(p) and Path(p).exists())
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}, masters={"han": "/m.png"}))
    cue = _overlay_cue(anchor="right")
    cue.hook = True; cue.hook_text = "Hook"; cue.text_anchor = "bottom"   # would collide
    br.render_one_cue(_video_ctx(tmp_path), plan, 1, cue)
    fc = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "y=h*0.08" in fc and "y=h*0.82" not in fc     # hook pushed to top, not bottom
    assert "overlay=x=" in fc


def test_no_overlay_hook_keeps_its_anchor(monkeypatch, tmp_path):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p == "/img.png" or bool(p) and Path(p).exists())
    ctx = SimpleNamespace(width=720, height=1280, fps=30.0, shots_dir=str(tmp_path),
                          bg_value="#101820", ffmpeg_threads=0)
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={"v1": "/img.png"}, masters={}))
    cue = _overlay_cue(anchor="none")
    cue.hook = True; cue.hook_text = "Hook"; cue.text_anchor = "bottom"
    br.render_one_cue(ctx, plan, 1, cue)
    fc = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "y=h*0.82" in fc                               # bottom respected (no overlay)


# ── A4: base-video audio (source_audio mute/keep/duck) ────────────────────────

def _audio_cue(source_audio="keep"):
    return SimpleNamespace(start_sec=0.0, end_sec=2.0, crop_from=(0, 0, 1, 1), crop_to=(0, 0, 1, 1),
                           visual_id="v1", audio_path="", hook=False, hook_text="", text_anchor="auto",
                           speaker_id="", char_anchor="none", char_scale="medium", char_motion="fade",
                           source_audio=source_audio)


def _fc_for(monkeypatch, tmp_path, source_audio, has_audio=True):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(br, "_ok_file", lambda p: p == "/base.mp4" or bool(p) and Path(p).exists())
    ctx = _video_ctx(tmp_path, {"base_video_has_audio": has_audio})
    plan = SimpleNamespace(render=SimpleNamespace(visual_assets={}, masters={}))
    br.render_one_cue(ctx, plan, 1, _audio_cue(source_audio))
    cmd = captured["cmd"]
    return cmd[cmd.index("-filter_complex") + 1]


def test_source_audio_keep_mixes_original(monkeypatch, tmp_path):
    fc = _fc_for(monkeypatch, tmp_path, "keep")
    assert "[0:a]" in fc and "amix=inputs=2" in fc and "sidechaincompress" not in fc


def test_source_audio_duck_sidechains_original(monkeypatch, tmp_path):
    fc = _fc_for(monkeypatch, tmp_path, "duck")
    assert "sidechaincompress" in fc and "asplit=2" in fc and "amix=inputs=2" in fc


def test_source_audio_mute_is_narration_only(monkeypatch, tmp_path):
    fc = _fc_for(monkeypatch, tmp_path, "mute")
    assert "[0:a]" not in fc and "amix" not in fc      # narration only (byte-identical to A2/A3)


def test_source_audio_ignored_without_base_audio(monkeypatch, tmp_path):
    # keep requested but the base video has no audio → narration-only, no crash.
    fc = _fc_for(monkeypatch, tmp_path, "keep", has_audio=False)
    assert "[0:a]" not in fc and "amix" not in fc


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
