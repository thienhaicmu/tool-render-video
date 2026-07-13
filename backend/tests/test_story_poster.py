"""Story poster/cover thumbnail (SVG hero visual + burned topic) — Lô C."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.features.render.engine.visual import svg_raster
from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS = pytest.mark.skipif(not (svg_raster.available() and _ffmpeg_ok()),
                            reason="needs resvg-py + FFmpeg")


def _plan() -> StoryPlan:
    return StoryPlan(
        topic="Kiếm Thế", region="cn", genre_key="wuxia",
        characters=[CharacterDef(id="han", name="Han", archetype="swordsman", gender="male")],
        settings=[SettingDef(id="s1", name="hall", scene_kind="palace")],
        visuals=[Visual(id="v1", setting_id="s1", character_ids=["han"]),
                 Visual(id="v2", setting_id="s1")],
        timeline=[Beat(id="b1", narration="x", visual_id="v1"),
                  Beat(id="b2", narration="y", visual_id="v2", hook=True, hook_text="H")])


def test_hero_visual_prefers_hook_beat():
    from app.features.render.engine.visual.story_poster import _hero_visual
    assert _hero_visual(_plan()).id == "v2"       # the hook beat's visual


def test_hero_visual_falls_back_to_first():
    from app.features.render.engine.visual.story_poster import _hero_visual
    p = StoryPlan(visuals=[Visual(id="v1"), Visual(id="v2")],
                  timeline=[Beat(id="b1", narration="x", visual_id="v1")])
    assert _hero_visual(p).id == "v1"


def test_hero_visual_none_without_visuals():
    from app.features.render.engine.visual.story_poster import _hero_visual
    assert _hero_visual(StoryPlan()) is None


@_NEEDS
def test_compose_poster_writes_jpg(tmp_path):
    from app.features.render.engine.visual.story_poster import compose_story_poster
    out = tmp_path / "cover.jpg"
    p = compose_story_poster(_plan(), str(out), 640, 360)
    assert p and Path(p).exists() and Path(p).stat().st_size > 0
    # the intermediate SVG raster is cleaned up
    assert not Path(str(out) + ".base.png").exists()


@_NEEDS
def test_compose_poster_none_without_visuals(tmp_path):
    from app.features.render.engine.visual.story_poster import compose_story_poster
    out = tmp_path / "cover.jpg"
    assert compose_story_poster(StoryPlan(topic="x"), str(out), 640, 360) is None
