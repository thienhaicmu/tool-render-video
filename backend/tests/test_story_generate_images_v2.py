"""Story Mode v2 — V2: _generate_images persists incrementally + writes to the
persistent visuals dir + emits story.visual.ready per image (offline, mocked)."""
from __future__ import annotations

from pathlib import Path

# A0 refactor: _generate_images + its deps (update_story_plan / _emit_render_event /
# generate_visual_image) live in visuals_stage now — unit-test it there.
import app.features.render.engine.stages.story.visuals_stage as sp2
from app.domain.story_plan_v2 import StoryPlan, Visual, Beat


def _plan():
    return StoryPlan(language='vi',
                     visuals=[Visual(id='v1', prompt='a'), Visual(id='v2', prompt='b')],
                     timeline=[Beat(id='b1', narration='x', visual_id='v1'),
                               Beat(id='b2', narration='y', visual_id='v2')])


def test_incremental_persist_and_persistent_dir(monkeypatch, tmp_path):
    persisted: list[str] = []
    events: list[dict] = []
    monkeypatch.setattr(sp2, 'update_story_plan', lambda jid, blob: persisted.append(blob))
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **kw: events.append(kw))

    def fake_img(visual, refs, art_style, w, h, out_path, seed=0, provider="gpt_image"):
        Path(out_path).write_bytes(b'\x89PNG')
        return out_path
    monkeypatch.setattr(sp2, 'generate_visual_image', fake_img)

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
    # v1 ok, v2 fails (None).
    def fake_img(visual, refs, art_style, w, h, out_path, seed=0, provider="gpt_image"):
        if visual.id == 'v2':
            return None
        Path(out_path).write_bytes(b'\x89PNG')
        return out_path
    monkeypatch.setattr(sp2, 'generate_visual_image', fake_img)

    p = _plan()
    out_dir = tmp_path / 'v'; out_dir.mkdir()
    fallbacks = sp2._generate_images(p, out_dir, '', 1024, 1024, job_id='j', effective_channel='vn')

    assert fallbacks == ['v2']
    assert 'v1' in p.render.visual_assets and 'v2' not in p.render.visual_assets
    assert len(persisted) == 1  # only the successful visual persisted


# ── A3: character masters for overlaid speakers ───────────────────────────────

def test_generate_character_masters_only_overlaid_speakers(monkeypatch):
    from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Visual, Beat
    import app.features.render.engine.visual.story_reference_sheet as rs
    monkeypatch.setattr(sp2, 'update_story_plan', lambda *a: None)
    monkeypatch.setattr(sp2, '_emit_render_event', lambda **k: None)
    monkeypatch.setattr(rs, 'generate_character_master', lambda c, art_style='': f'/m/{c.id}.png')

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
    import app.features.render.engine.visual.story_reference_sheet as rs
    called = {'n': 0}
    monkeypatch.setattr(rs, 'generate_character_master',
                        lambda c, art_style='': called.__setitem__('n', called['n'] + 1) or '/x.png')
    p = StoryPlan(characters=[CharacterDef(id='han', name='Han')],
                  visuals=[Visual(id='v1', prompt='x')],
                  timeline=[Beat(id='b1', narration='a', visual_id='v1', speaker_id='han', char_anchor='none')])
    sp2._generate_character_masters(p, '', job_id='j', effective_channel='c')
    assert p.render.masters == {} and called['n'] == 0   # no overlay beat → no gen
