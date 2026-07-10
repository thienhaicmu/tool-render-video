"""Story Mode v2 — V2: _generate_images persists incrementally + writes to the
persistent visuals dir + emits story.visual.ready per image (offline, mocked)."""
from __future__ import annotations

from pathlib import Path

import app.features.render.engine.pipeline.story_pipeline_v2 as sp2
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

    def fake_img(visual, refs, art_style, w, h, out_path, seed=0):
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
    def fake_img(visual, refs, art_style, w, h, out_path, seed=0):
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
