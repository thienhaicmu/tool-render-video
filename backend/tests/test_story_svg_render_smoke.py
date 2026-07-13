"""
test_story_svg_render_smoke.py — REAL SVG rasterisation smoke test (Lô 0).

The story e2e test (test_run_story_v2_e2e) MOCKS generate_visual_image, so the actual
SVG compose → resvg raster path is never exercised there. Now that SVG is the sole art
engine, that path is load-bearing: this test drives it for real (no mock) so a broken /
missing resvg-py surfaces in CI instead of degrading to a blank video at runtime.

Also pins the pipeline foundation guard: when the SVG path is active but the rasteriser
is unavailable, run_story_v2 must FAIL FAST with a clear message rather than deliver a
solid-background video as success.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.features.render.engine.visual import svg_raster
from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual


_resvg = pytest.mark.skipif(not svg_raster.available(),
                            reason="resvg-py not installed (SVG raster unavailable)")


def _plan() -> StoryPlan:
    return StoryPlan(
        seed=1, language="vi", art_style="wuxia", aspect_ratio="16:9",
        region="cn", genre_key="wuxia",
        characters=[CharacterDef(id="c1", name="Han Feng", archetype="swordsman", gender="male")],
        settings=[SettingDef(id="s1", name="pavilion", scene_kind="palace")],
        visuals=[Visual(id="v1", setting_id="s1", prompt="a lone hero at night",
                        character_ids=["c1"])],
    )


def _is_png(p: str) -> bool:
    b = Path(p).read_bytes()
    return len(b) >= 8 and b[:8] == b"\x89PNG\r\n\x1a\n"


@_resvg
def test_compose_visual_with_characters_rasters_to_png(tmp_path):
    """chars=True: background + placed characters → a real, valid PNG."""
    from app.features.render.engine.visual.svg_compose import compose_visual
    plan = _plan()
    svg = compose_visual(plan, plan.visuals[0], 1536, 1024, chars=True)
    assert svg and svg.lstrip().startswith("<svg")
    out = tmp_path / "v1.png"
    p = svg_raster.save_svg_png(svg, str(out), 1536, 1024, opaque_bg="#101820")
    assert p and Path(p).exists() and Path(p).stat().st_size > 0
    assert _is_png(p)


@_resvg
def test_compose_visual_background_only_rasters_to_png(tmp_path):
    """chars=False: the actual render key-visual mode (characters overlaid per-beat)."""
    from app.features.render.engine.visual.svg_compose import compose_visual
    plan = _plan()
    svg = compose_visual(plan, plan.visuals[0], 1536, 1024, chars=False)
    assert svg and svg.lstrip().startswith("<svg")
    out = tmp_path / "v1_bg.png"
    p = svg_raster.save_svg_png(svg, str(out), 1536, 1024, opaque_bg="#101820")
    assert p and _is_png(p)


@_resvg
def test_character_master_rasters_to_transparent_png(tmp_path):
    """The per-beat overlay master: an SVG chibi → a transparent PNG (no opaque_bg)."""
    from app.features.render.engine.visual.svg_char import build_char, emotion_expr
    from app.features.render.engine.visual.svg_presets import preset
    opts = preset("swordsman", "cn", "wuxia", "male")
    opts["expr"] = emotion_expr("angry")
    opts["pose"] = "point"
    out = tmp_path / "master.png"
    p = svg_raster.save_svg_png(build_char(opts), str(out), 1024, 1536)
    assert p and _is_png(p)
