"""Story Mode v2 — B7.1 cue overlay builder (_overlay_suffix): hook title + full
subtitle drawtext (no ffmpeg — filtergraph string only)."""
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


def test_full_subtitle_burns_lower_drawtext():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, subtitle="Hàn Phong bước vào đại sảnh.")
    s = br._overlay_suffix(c, 1920, 1080)
    assert "drawtext=" in s and "y=h-text_h-h*0.07" in s


def test_hook_and_subtitle_two_drawtext():
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3,
            hook=True, hook_text="Mở đầu", subtitle="Một câu phụ đề.")
    s = br._overlay_suffix(c, 1920, 1080)
    assert s.count("drawtext=") == 2


def test_writes_textfile(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "get_text_overlay_temp_dir", lambda: tmp_path)
    c = Cue(beat_id="b1", visual_id="v1", start_sec=0, end_sec=3, hook=True, hook_text="Đêm lạnh")
    br._overlay_suffix(c, 1920, 1080)
    files = list(tmp_path.glob("story_cue_*.txt"))
    assert files and "Đêm lạnh" in files[0].read_text(encoding="utf-8")
