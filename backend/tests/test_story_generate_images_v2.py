"""Story Mode v2 — _generate_images persists incrementally + writes to the persistent
visuals dir + emits story.visual.ready per image. Story Mode is SVG-only, so image gen
composes procedural SVG (svg_raster.save_svg_png is mocked for deterministic control)."""
from __future__ import annotations

from pathlib import Path

import app.features.render.engine.stages.story.visuals_stage as sp2
from app.domain.story_plan_v2 import StoryPlan, Visual, Beat

_SAVE = "app.features.render.engine.visual.svg_raster.save_svg_png"


def _plan():
    return StoryPlan(language='vi',
                     visuals=[Visual(id='v1', prompt='a'), Visual(id='v2', prompt='b')],
                     timeline=[Beat(id='b1', narration='x', visual_id='v1'),
                               Beat(id='b2', narration='y', visual_id='v2')])


def test_incremental_persist_and_persistent_dir(monkeypatch, tmp_path):
    persisted: list[str] = []
    events: list[dict] = []
    monkeypatch.setenv('STORY_IMAGE_WORKERS', '1')   # serial → deterministic reveal order
    monkeypatch.setattr(sp2, 'update_story_plan', lambda jid, blob: persisted.append(blob))
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **kw: events.append(kw))

    def fake_save(svg, out_path, w, h, opaque_bg=''):
        Path(out_path).write_bytes(b'\x89PNG')
        return str(out_path)
    monkeypatch.setattr(_SAVE, fake_save)

    p = _plan()
    out_dir = tmp_path / 'story_visuals' / 'job1'
    out_dir.mkdir(parents=True)
    fallbacks = sp2._generate_images(p, out_dir, '', 1536, 1024,
                                     job_id='job1', effective_channel='vn')

    assert fallbacks == []
    # Both visuals written under the persistent out_dir (not a temp shots dir).
    assert p.render.visual_assets['v1'] == str(out_dir / 'v1.png')
    assert (out_dir / 'v1.png').exists() and (out_dir / 'v2.png').exists()
    # Persisted once per image → the FE reveals visuals one by one.
    assert len(persisted) == 2
    # A story.visual.ready event per image.
    ready = [e for e in events if e.get('event') == 'story.visual.ready']
    assert len(ready) == 2
    assert ready[0]['context']['visual_id'] == 'v1'
    assert ready[1]['context']['total'] == 2


def test_fallback_skips_persist(monkeypatch, tmp_path):
    persisted: list[str] = []
    monkeypatch.setattr(sp2, 'update_story_plan', lambda jid, blob: persisted.append(blob))
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **kw: None)

    # v1 ok, v2 fails (raster returns None → solid-background fallback).
    def fake_save(svg, out_path, w, h, opaque_bg=''):
        if str(out_path).endswith('v2.png'):
            return None
        Path(out_path).write_bytes(b'\x89PNG')
        return str(out_path)
    monkeypatch.setattr(_SAVE, fake_save)

    p = _plan()
    out_dir = tmp_path / 'v'; out_dir.mkdir()
    fallbacks = sp2._generate_images(p, out_dir, '', 1024, 1024, job_id='j', effective_channel='vn')

    assert fallbacks == ['v2']
    assert 'v1' in p.render.visual_assets and 'v2' not in p.render.visual_assets
    assert len(persisted) == 1  # only the successful visual persisted


# ── A3: character masters for overlaid speakers ───────────────────────────────

def test_generate_character_masters_only_overlaid_speakers(monkeypatch):
    from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Visual, Beat
    import app.features.render.engine.visual.library_v3 as v3
    monkeypatch.setattr(sp2, 'update_story_plan', lambda *a: None)
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **k: None)
    # V3 path: no approved identity master → the deterministic V3 renderer generates.
    monkeypatch.setattr(v3, 'resolve_character_preview', lambda *a, **k: '')
    monkeypatch.setattr(v3, 'render_planner_character_png',
                        lambda c, out, **k: f'/m/{c.id}.png')

    p = StoryPlan(
        characters=[CharacterDef(id='han', name='Han'), CharacterDef(id='lo', name='Lo')],
        visuals=[Visual(id='v1', prompt='x')],
        timeline=[
            Beat(id='b1', narration='a', visual_id='v1', speaker_id='han', char_anchor='left'),
            Beat(id='b2', narration='b', visual_id='v1', speaker_id='lo', char_anchor='none'),  # not overlaid
        ])
    sp2._generate_character_masters(p, '', job_id='j', effective_channel='c')
    # Only the speaker with char_anchor != 'none' gets a master.
    assert p.render.masters == {'han': '/m/han.png'}


def test_generate_character_masters_noop_without_overlay(monkeypatch):
    from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Visual, Beat
    import app.features.render.engine.visual.library_v3 as v3
    called = {'n': 0}
    monkeypatch.setattr(v3, 'render_planner_character_png',
                        lambda c, out, **k: called.__setitem__('n', called['n'] + 1) or '/x.png')
    p = StoryPlan(characters=[CharacterDef(id='han', name='Han')],
                  visuals=[Visual(id='v1', prompt='x')],
                  timeline=[Beat(id='b1', narration='a', visual_id='v1', speaker_id='han', char_anchor='none')])
    sp2._generate_character_masters(p, '', job_id='j', effective_channel='c')
    assert p.render.masters == {} and called['n'] == 0   # no overlay beat → no gen


# ── AL3: library-first (skip a pre-assigned visual) ───────────────────────────

def test_library_first_skips_preassigned_visual(monkeypatch, tmp_path):
    from app.domain.story_plan_v2 import StoryPlan, Visual, Beat
    monkeypatch.setattr(sp2, 'update_story_plan', lambda *a: None)
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **k: None)
    calls = {"n": 0}

    def fake_save(svg, out_path, w, h, opaque_bg=''):
        calls["n"] += 1
        Path(out_path).write_bytes(b'\x89PNG')
        return str(out_path)
    monkeypatch.setattr(_SAVE, fake_save)
    lib = tmp_path / 'lib_bg.png'
    lib.write_bytes(b'\x89PNG')                       # a library background already on disk
    p = StoryPlan(visuals=[Visual(id='v1', prompt='x'), Visual(id='v2', prompt='y')],
                  timeline=[Beat(id='b1', narration='a', visual_id='v1')])
    p.render.visual_assets['v1'] = str(lib)           # v1 assigned from the library
    fb = sp2._generate_images(p, tmp_path, '', 1024, 1024, job_id='j', effective_channel='c')
    assert calls["n"] == 1                            # only v2 composed (v1 came from library)
    assert p.render.visual_assets['v1'] == str(lib)   # library asset untouched
    assert 'v2' in p.render.visual_assets and fb == []


# ── V3: an approved identity master wins over the procedural renderer ─────────

def test_character_master_prefers_v3_identity(monkeypatch):
    from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Visual, Beat
    import app.features.render.engine.visual.library_v3 as v3
    monkeypatch.setattr(sp2, 'update_story_plan', lambda *a: None)
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **k: None)
    gen = {'n': 0}
    monkeypatch.setattr(v3, 'resolve_character_preview', lambda *a, **k: '/v3/han_master.png')
    monkeypatch.setattr(v3, 'render_planner_character_png',
                        lambda c, out, **k: gen.__setitem__('n', gen['n'] + 1) or '/ai/gen.png')

    p = StoryPlan(characters=[CharacterDef(id='han', name='Han', visual_identity_id='v3_han')],
                  visuals=[Visual(id='v1', prompt='x')],
                  timeline=[Beat(id='b1', narration='a', visual_id='v1', speaker_id='han', char_anchor='left')])
    sp2._generate_character_masters(p, '', job_id='j', effective_channel='c')
    assert p.render.masters == {'han': '/v3/han_master.png'}   # identity master used
    assert gen['n'] == 0                                       # procedural gen never called
