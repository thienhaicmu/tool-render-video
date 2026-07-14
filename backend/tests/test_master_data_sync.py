"""Master-data consistency guard (Plan 1 — 2026-07-14).

Locks the story-mode master data so the parts can never silently drift apart again:
  · domain enums (story_plan_v2)  — the single source of truth
  · AI structured-output schema (story_schema_v2)  — must equal the domain enums
  · AI prompt TOKEN VOCAB (story_prompts_v2._vocab_block)  — must teach the real tokens
  · procedural builders (svg_presets._ARCH / svg_scene._SCENES)
  · the offline asset-library GENERATOR (scripts/gen_svg_library.py)

The concrete drift this caught: the library generator emitted genre ``xianxia`` while
``GENRE_KEY`` did not list it, so those assets were unreachable by the AI (schema enum
rejected the value). Any future genre/region added to the generator MUST be added to the
domain enum too — this test fails otherwise.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.domain.story_plan_v2 import GENRE_KEY, REGION, BGM_MOODS
from app.features.render.ai.llm.story_prompts_v2 import _MOOD_VOCAB, _vocab_block


def _load_generator():
    p = Path(__file__).resolve().parents[1] / "scripts" / "gen_svg_library.py"
    spec = importlib.util.spec_from_file_location("gen_svg_library", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)          # module-level only defines data; no file writes
    return m


def test_generator_genres_are_all_in_enum():
    g = _load_generator()
    genres = {genre for homes in g.HOMES.values() for _r, genre, _gd in homes}
    genres |= {genre for homes in g.SCENE_HOMES.values() for _r, genre in homes}
    missing = genres - set(GENRE_KEY)
    assert not missing, f"generator genres not in GENRE_KEY (unreachable assets): {missing}"


def test_generator_regions_are_all_in_enum():
    g = _load_generator()
    regions = {r for homes in g.HOMES.values() for r, _g, _gd in homes}
    regions |= {r for homes in g.SCENE_HOMES.values() for r, _g in homes}
    missing = regions - set(REGION)
    assert not missing, f"generator regions not in REGION: {missing}"


def test_prompt_mood_vocab_matches_domain():
    assert set(_MOOD_VOCAB.split("|")) == {m for m in BGM_MOODS if m != "default"}


def test_schema_genre_and_region_enums_match_domain():
    from app.features.render.ai.llm.story_schema_v2 import build_story_plan_schema
    props = build_story_plan_schema()["properties"]
    assert props["genre_key"]["enum"] == [str(v) for v in GENRE_KEY]
    assert props["region"]["enum"] == [str(v) for v in REGION]


def test_vocab_block_teaches_genre_and_region():
    vb = _vocab_block()
    assert "genre_key ∈" in vb and "region ∈" in vb
    for g in (x for x in GENRE_KEY if x):
        assert g in vb, f"genre {g!r} missing from prompt vocab"
    for r in (x for x in REGION if x):
        assert r in vb, f"region {r!r} missing from prompt vocab"


def test_vocab_block_tokens_are_real_builder_tokens():
    from app.features.render.engine.visual.svg_presets import _ARCH
    from app.features.render.engine.visual.svg_scene import _SCENES
    vb = _vocab_block()
    # every archetype the builder knows is advertised to the AI
    for a in _ARCH:
        assert a in vb, f"archetype {a!r} missing from prompt vocab"
    # scenes are deduped by builder FUNCTION (one representative alias per scene) — mirror
    # that so aliases sharing a function (e.g. cafe/coffee_shop) don't false-fail.
    reps: dict = {}
    for alias, fn in _SCENES.items():
        reps.setdefault(fn, alias)
    for alias in reps.values():
        assert alias in vb, f"scene_kind {alias!r} missing from prompt vocab"
