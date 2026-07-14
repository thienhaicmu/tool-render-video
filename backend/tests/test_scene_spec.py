"""PASTE-JSON scene_spec — declarative background renderer + library banking (isolated).

Covers:
  · render_scene_spec — spec → SVG (all element types), defensive on junk
  · bank_scene_spec — render → PNG saved under background/{region}/{genre}/{slug}.png +
    upserted into story_assets (user-named slug), idempotent
  · SettingDef.scene_spec (de)serialises; absent → {} (old flow untouched)
"""
from __future__ import annotations

import json
from pathlib import Path

from app.domain.story_plan_v2 import StoryPlan, SettingDef
from app.features.render.engine.visual import svg_scene_spec as ss


FULL_SPEC = {
    "bg": {"top": "#39435c", "bottom": "#20283a"},
    "floor": {"y": 700, "color": "#454d5e", "edge": "#f2c94a"},
    "night": True,
    "elements": [
        {"type": "rect", "x": 120, "y": 470, "w": 1000, "h": 230, "rx": 20, "fill": "#6b7788"},
        {"type": "circle", "cx": 1250, "cy": 200, "r": 70, "fill": "#f3ead0"},
        {"type": "ellipse", "cx": 768, "cy": 150, "rx": 130, "ry": 36, "fill": "#f4dc90", "opacity": 0.85},
        {"type": "line", "x1": 60, "y1": 200, "x2": 20, "y2": 700, "stroke": "#aeb8cc", "opacity": 0.22},
        {"type": "path", "d": "M0 800 L280 420 L520 800 Z", "fill": "#6a5a78"},
        {"type": "polygon", "points": [[0, 800], [280, 420], [520, 800]], "fill": "#54465f"},
        {"type": "row", "of": {"type": "rect", "y": 600, "w": 120, "h": 80, "fill": "#39435c"}, "xs": [190, 400, 610]},
        {"type": "grid", "of": {"type": "rect", "w": 20, "h": 20, "fill": "#fff"}, "xs": [100, 200], "ys": [100, 200]},
        {"type": "group", "x": 50, "y": 50, "scale": 0.5, "children": [{"type": "rect", "x": 0, "y": 0, "w": 40, "h": 40, "fill": "#f00"}]},
    ],
}


def test_render_all_element_types():
    svg = ss.build_scene_spec_svg(FULL_SPEC)
    for tag in ("<rect", "<circle", "<ellipse", "<line", "<path", "<polygon", "<g transform", "linearGradient"):
        assert tag in svg, f"{tag} missing"
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_render_defensive_on_junk():
    assert ss.render_scene_spec("nope") == ""
    assert ss.render_scene_spec(None) == ""
    # empty spec → just a fallback gradient (never crashes, always a background)
    assert ss.render_scene_spec({}).startswith("<defs>")
    # a malformed element is skipped, others still render
    svg = ss.render_scene_spec({"bg": {"top": "#111", "bottom": "#222"},
                                "elements": [{"type": "rect"}, {"type": "bogus"}, 42,
                                             {"type": "circle", "cx": 10, "cy": 10, "r": 5, "fill": "#fff"}]})
    assert "<circle" in svg


def test_path_and_color_sanitised():
    # a path with an injection attempt has the illegal chars stripped; colour falls back.
    svg = ss.render_scene_spec({"bg": {"top": "#111", "bottom": "#222"},
                                "elements": [{"type": "path", "d": "M0 0\"/><script>x", "fill": "red;evil"}]})
    assert "<script" not in svg and "evil" not in svg


def test_setting_scene_spec_roundtrip():
    p = StoryPlan(settings=[SettingDef(id="s1", name="ga", scene_spec=FULL_SPEC)],
                  visuals=[], timeline=[])
    p2 = StoryPlan.from_json(p.to_json())
    assert p2 is not None
    assert p2.settings[0].scene_spec.get("floor", {}).get("y") == 700
    # a setting without the field → {} (old flow untouched)
    assert SettingDef(id="s2").scene_spec == {}


def test_from_json_ignores_bad_scene_spec():
    p = StoryPlan.from_json(json.dumps({
        "settings": [{"id": "s1", "scene_spec": "not-a-dict"}],
        "visuals": [{"id": "v1"}], "timeline": [{"id": "b1", "narration": "hi", "visual_id": "v1"}],
    }))
    assert p is not None and p.settings[0].scene_spec == {}


def test_bank_saves_to_library_and_upserts():
    from app.db.story_asset_repo import get_by_slug
    slug = "jp_hiendai_test_station_spec"
    got = ss.bank_scene_spec(FULL_SPEC, region="jp", genre="hiendai", slug=slug, name="test station")
    assert got == slug
    # file saved under background/{region}/{genre}/{slug}.png
    path = get_by_slug(slug, "background")
    assert path and Path(path).exists()
    assert Path(path).parts[-3:] == ("jp", "hiendai", f"{slug}.png")
    # idempotent — second call reuses, still returns the slug, file still there
    assert ss.bank_scene_spec(FULL_SPEC, region="jp", genre="hiendai", slug=slug) == slug
    assert Path(path).exists()


def test_bank_empty_slug_is_noop():
    assert ss.bank_scene_spec(FULL_SPEC, region="jp", genre="hiendai", slug="") == ""
    assert ss.bank_scene_spec({}, region="jp", genre="hiendai", slug="x") in ("", "x")  # empty spec → no crash
