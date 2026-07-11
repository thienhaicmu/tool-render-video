"""Story Mode v2 — B7.1 cue overlay builder (_overlay_suffix): hook-title drawtext
(hook-only, no full subtitle; no ffmpeg — filtergraph string only)."""
from __future__ import annotations

from app.domain.story_plan_v2 import Cue
from app.features.render.engine.stages.story import beat_render as br


def test_no_overlay_when_plain_cue():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3)
    assert br._overlay_suffix(c, 1920, 1080) == ""


def test_hook_burns_upper_drawtext():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, hook=True, hook_text="Bí mật ngàn năm")
    s = br._overlay_suffix(c, 1920, 1080)
    assert s.startswith(",drawtext=")
    assert "textfile=" in s and "y=h*0.10" in s
    # Vietnamese text goes through a textfile — never inline.
    assert "Bí mật" not in s


def test_hook_ignored_when_no_text():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, hook=True, hook_text="  ")
    assert br._overlay_suffix(c, 1920, 1080) == ""


def test_no_full_subtitle_burn():
    # There is no full-video subtitle anymore — only hooks burn on screen.
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3)
    assert br._overlay_suffix(c, 1920, 1080) == ""


def test_writes_textfile(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "get_text_overlay_temp_dir", lambda: tmp_path)
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, hook=True, hook_text="Đêm lạnh")
    br._overlay_suffix(c, 1920, 1080)
    files = list(tmp_path.glob("story_cue_*.txt"))
    assert files and "Đêm lạnh" in files[0].read_text(encoding="utf-8")


# ── s4: text_anchor placement ─────────────────────────────────────────────────

def test_text_anchor_default_auto_is_upper_third():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, hook=True, hook_text="Hook")
    s = br._overlay_suffix(c, 1920, 1080)         # default text_anchor="auto"
    assert "y=h*0.10" in s and "x=(w-text_w)/2" in s


def test_text_anchor_bottom_and_side():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, hook=True,
            hook_text="Hook", text_anchor="bottom")
    assert "y=h*0.82" in br._overlay_suffix(c, 1920, 1080)
    c2 = Cue(beat_id="b2", visual_id="v1", start_sec=0, end_sec=3, hook=True,
             hook_text="Hook", text_anchor="left")
    assert "x=w*0.06" in br._overlay_suffix(c2, 1920, 1080)


def test_anchor_xy_helper():
    assert br._anchor_xy("auto") == ("(w-text_w)/2", "h*0.10")
    assert br._anchor_xy("top")[1] == "h*0.08"
    assert br._anchor_xy("right")[0] == "w-text_w-w*0.06"
