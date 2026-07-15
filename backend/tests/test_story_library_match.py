"""Phase A — offline library-first auto-match in visuals_stage (gated, best-effort)."""
from __future__ import annotations

from pathlib import Path

from app.domain.story_plan_v2 import StoryPlan, SettingDef, Visual
import app.features.render.engine.stages.story.visuals_stage as vs


def _plan(**vis):
    return StoryPlan(
        region="cn", genre_key="wuxia",
        settings=[SettingDef(id="hall", name="Đại điện", scene_kind="throne_room"),
                  SettingDef(id="bare", name="Nowhere")],
        visuals=list(vis.get("visuals", [])),
    )


# ── helper _match_library_background ─────────────────────────────────────────

def test_match_skips_visual_with_characters(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("app.db.story_asset_repo.match_asset",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "x.png")
    p = _plan()
    v = Visual(id="v1", setting_id="hall", character_ids=["han"])  # has a character → keep AI
    assert vs._match_library_background(p, v) is None
    assert called["n"] == 0                                        # match_asset never called


def test_match_uses_scene_kind_and_scope(monkeypatch):
    seen = {}
    def fake(kind, name="", region="", genre="", **k):
        seen.update(kind=kind, name=name, region=region, genre=genre); return "/lib/bg.png"
    monkeypatch.setattr("app.db.story_asset_repo.match_asset", fake)
    p = _plan()
    v = Visual(id="v1", setting_id="hall", character_ids=[])       # char-less establishing
    assert vs._match_library_background(p, v) == "/lib/bg.png"
    assert seen == {"kind": "background", "name": "throne_room", "region": "cn", "genre": "wuxia"}


def test_match_falls_back_to_setting_name(monkeypatch):
    got = {}
    monkeypatch.setattr("app.db.story_asset_repo.match_asset",
                        lambda kind, name="", **k: got.update(name=name) or None)
    p = _plan()
    vs._match_library_background(p, Visual(id="v1", setting_id="bare", character_ids=[]))
    assert got["name"] == "Nowhere"                               # no scene_kind → setting name


def test_match_honors_ai_chosen_setting_asset(monkeypatch):
    # T2 debt — Phase A now honors the AI's library-pick (setting.asset) BEFORE fuzzy match,
    # same precedence as svg_compose (single policy).
    # style-aware: get_by_slug now also receives the active library ``style`` kwarg.
    monkeypatch.setattr("app.db.story_asset_repo.get_by_slug",
                        lambda slug, kind="", **k: "/lib/pick.png" if slug == "cn_bg_x" else None)
    fuzzy = []
    monkeypatch.setattr("app.db.story_asset_repo.match_asset",
                        lambda *a, **k: fuzzy.append(1) or "/fuzzy.png")
    p = StoryPlan(region="cn", genre_key="wuxia",
                  settings=[SettingDef(id="s", name="X", scene_kind="throne_room", asset="cn_bg_x")])
    assert vs._match_library_background(p, Visual(id="v1", setting_id="s", character_ids=[])) == "/lib/pick.png"
    assert fuzzy == []                                            # fuzzy not consulted when asset resolves


def test_match_none_when_no_setting_or_name(monkeypatch):
    monkeypatch.setattr("app.db.story_asset_repo.match_asset", lambda *a, **k: "should_not_be_used")
    p = _plan()
    assert vs._match_library_background(p, Visual(id="v1", setting_id="", character_ids=[])) is None


# ── _generate_images gate integration ────────────────────────────────────────

def _patch_io(monkeypatch):
    monkeypatch.setattr(vs, "update_story_plan", lambda *a, **k: None)
    monkeypatch.setattr(vs, "_emit_render_event", lambda *a, **k: None)


def test_gate_on_matches_and_skips_compose(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.setenv("STORY_LIBRARY_FIRST", "1")
    # v1 matches library, v2 does not.
    monkeypatch.setattr(vs, "_match_library_background",
                        lambda plan, v: "/lib/v1.png" if v.id == "v1" else None)
    composed: list = []
    monkeypatch.setattr("app.features.render.engine.visual.svg_compose.compose_visual",
                        lambda *a, **k: "<svg/>")
    monkeypatch.setattr("app.features.render.engine.visual.svg_raster.save_svg_png",
                        lambda svg, out, w, h, opaque_bg="": composed.append(Path(out).stem) or str(out))
    p = _plan(visuals=[Visual(id="v1", setting_id="hall", character_ids=[]),
                       Visual(id="v2", setting_id="hall", character_ids=[])])
    fallbacks = vs._generate_images(p, tmp_path, "wuxia", 1536, 1024,
                                    job_id="j", effective_channel="c")
    assert p.render.visual_assets["v1"] == "/lib/v1.png"          # matched from library
    assert composed == ["v2"]                                     # only the unmatched one composed SVG
    assert fallbacks == []


def test_gate_off_never_matches(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.delenv("STORY_LIBRARY_FIRST", raising=False)      # default off
    hit = {"n": 0}
    monkeypatch.setattr(vs, "_match_library_background",
                        lambda plan, v: hit.__setitem__("n", hit["n"] + 1) or "/x.png")
    monkeypatch.setattr("app.features.render.engine.visual.svg_compose.compose_visual",
                        lambda *a, **k: "<svg/>")
    monkeypatch.setattr("app.features.render.engine.visual.svg_raster.save_svg_png",
                        lambda svg, out, w, h, opaque_bg="": str(out))
    p = _plan(visuals=[Visual(id="v1", setting_id="hall", character_ids=[])])
    vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c")
    assert hit["n"] == 0                                          # match layer skipped entirely
    assert "v1" in p.render.visual_assets                         # composed via SVG as before
