"""Phase 4 / R5 (architecture-review, 2026-06-30) — recap.plan.ready WS shape.

The ``recap.plan.ready`` event is the ONLY Story-Intelligence WS event the
frontend consumes semantically (RecapLiveView). Its ``context.scenes[]`` /
``context.episodes[]`` projection is built inline in
``recap_pipeline.py`` (the ``_scene_blocks`` list comprehension) and mirrored
on the FE by ``RecapSceneBlock`` / ``RecapEpisodeInfo`` in
``frontend/src/websocket/events.ts``.

There is no shared schema between emitter and consumer — a key rename on either
side breaks ``RecapLiveView`` silently (the FE reads ``undefined`` and renders
an empty timeline; nothing throws). This test pins the emitted key set so such
a rename fails CI instead.

Contract mirror (keep both in lockstep):

    backend recap_pipeline.py `_scene_blocks`  ⇄  FE RecapSceneBlock
    backend `episodes` projection              ⇄  FE RecapEpisodeInfo

Style follows the existing source-level wire-smoke test
``test_d2_motion_e2e_wire_smoke.py`` (asserts against module source), because
the emit site sits inside the full recap render function and cannot be driven
in isolation without a live LLM + FFmpeg render context.
"""
from __future__ import annotations

import re
from pathlib import Path

import app.features.render.engine.pipeline.recap_pipeline as recap_pipeline

# The exact key set the FE RecapSceneBlock interface depends on. If you add a
# key here you MUST add it to frontend/src/websocket/events.ts RecapSceneBlock
# (and vice-versa) — that's the whole point of this test.
_EXPECTED_SCENE_KEYS = {"n", "ep", "act", "start", "end", "dur", "title", "mode", "climax"}


def _source() -> str:
    return Path(recap_pipeline.__file__).read_text(encoding="utf-8")


def _scene_block_region(src: str) -> str:
    """Slice the single dict literal inside the ``_scene_blocks`` comprehension.

    Scoped so that keys used elsewhere in the file (e.g. the ``acts``
    projection also has a ``title`` key) cannot produce a false pass."""
    start = src.index("_scene_blocks = [")
    # The comprehension header terminates the dict literal.
    end = src.index("for i, s in enumerate(scored", start)
    return src[start:end]


def test_event_name_present():
    """The emitted event name must stay 'recap.plan.ready' — the FE latches on
    this exact string (useRenderSocket.ts, RecapLiveView.tsx)."""
    assert 'event="recap.plan.ready"' in _source()


def test_scene_block_keys_match_fe_interface():
    """The scene-block dict keys must be EXACTLY the FE RecapSceneBlock keys —
    no more, no less. Catches a backend rename/removal AND a backend addition
    that the FE type doesn't know about."""
    region = _scene_block_region(_source())
    emitted_keys = set(re.findall(r'"(\w+)":', region))
    assert emitted_keys == _EXPECTED_SCENE_KEYS, (
        f"recap.plan.ready scene-block keys drifted from the FE RecapSceneBlock "
        f"interface.\n  emitted : {sorted(emitted_keys)}\n  expected: "
        f"{sorted(_EXPECTED_SCENE_KEYS)}\nUpdate frontend/src/websocket/events.ts "
        f"RecapSceneBlock and this test together."
    )


def test_episode_projection_shape():
    """The episodes[] projection must keep the {title, acts, scenes} shape the
    FE RecapEpisodeInfo interface reads."""
    src = _source()
    assert '"title": ep.title' in src
    assert '"acts": len(ep.acts)' in src
    assert '"scenes": ep.scene_count()' in src


def test_story_model_still_shipped():
    """The recap.plan.ready context must keep shipping story_model so the FE
    StoryModelCard (Phase 3a) has data. Uses the JSON-safe public dict."""
    src = _source()
    assert '"story_model": recap_plan.story.to_public_dict()' in src
