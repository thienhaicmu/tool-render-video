"""
G2 reproduction — long-chapter chunk-merge drops the SECOND half of the story.

Story v2 plans a very long chapter by splitting it into two halves, super-planning
EACH half at the full ``ceiling`` visual budget, merging (2×ceiling visuals), then
capping back to ``ceiling`` in first-reference (i.e. first-half) order
(``StoryPlan.cap_visuals``). Because the cap keeps the first ``ceiling`` visuals and
drops beats whose visual was cut, the ENTIRE second half of the chapter can be
discarded — the video only narrates the front of the story.

These tests drive ``run_super_plan`` down the long-chapter path with a fake
``call_fn`` (no network) that returns DISTINCT, marker-tagged content per half:
half A → narration "alphaN"/visuals "vaN"; half B → "betaN"/"vbN". With a small
ceiling the merge+cap must drop one half.

  * ``test_g2_long_chapter_currently_truncates`` — GREEN: pins the observed loss
    today (only half-A survives) so the regression is documented empirically.
  * ``test_g2_long_chapter_second_half_survives`` — xfail(strict): the DESIRED
    behaviour (some half-B content survives). Flips to xpass when Phase 2 balances
    the per-half budget; strict-xfail then fails, prompting removal of the marker.
"""
from __future__ import annotations

import json

import pytest

from app.domain.story_plan_v2 import StoryPlan
from app.features.render.ai.llm.story_director_v2 import run_super_plan

_CEILING = 4
_N = 4  # visuals + beats each half emits (== ceiling, so 2 halves overflow the cap)


def _half_json(tag: str) -> str:
    """A self-consistent StoryPlan JSON for one half: N distinct visuals, N beats,
    each beat pointing at its OWN visual (so dropping a visual drops its beat)."""
    return json.dumps({
        "topic": f"topic_{tag}", "language": "vi", "art_style": "wuxia",
        "characters": [],
        "settings": [{"id": "s1", "name": "hall", "canonical_desc": "cold stone"}],
        "visuals": [{"id": f"v{tag}{i}", "setting_id": "s1", "prompt": f"scene {tag}{i}",
                     "tier": "medium"} for i in range(1, _N + 1)],
        "timeline": [{"id": f"b{tag}{i}", "narration": f"{tag}{i}", "visual_id": f"v{tag}{i}",
                      "focus": "center"} for i in range(1, _N + 1)],
    })


def _long_chapter() -> str:
    """Two equal-length, clearly-marked blocks joined by a paragraph break so the
    splitter cuts cleanly at the boundary (block A → part 0, block B → part 1)."""
    a = "MARKER_A. " + ("aaaa " * 60)   # ~310 chars, starts with MARKER_A
    b = "MARKER_B. " + ("bbbb " * 60)   # same length, starts with MARKER_B
    return a.strip() + "\n\n" + b.strip()


def _fake_call(system: str, user: str) -> str:
    # The half's chapter text is concatenated into ``user`` — route by its marker.
    return _half_json("beta") if "MARKER_B" in user else _half_json("alpha")


def _plan_long(monkeypatch) -> StoryPlan:
    # Force the chunk path: threshold tiny so len(chapter) > threshold*1.2.
    monkeypatch.setenv("STORY_MAX_CHAPTER_CHARS_SINGLE", "100")
    monkeypatch.setenv("STORY_PLAN_REPAIR", "0")   # keep it to exactly 2 calls
    p = run_super_plan(call_fn=_fake_call, source="paste", chapter=_long_chapter(),
                       language="vi", ceiling=_CEILING)
    assert p is not None, "long-chapter path returned no plan"
    return p


def test_g2_long_chapter_currently_truncates(monkeypatch):
    """GREEN characterization: the cap keeps only half-A and never exceeds ceiling —
    every surviving beat is an 'alpha' beat; all 'beta' (second-half) content is gone."""
    p = _plan_long(monkeypatch)
    assert p.image_count() <= _CEILING                       # INV6 respected
    narr = [b.narration for b in p.timeline]
    assert narr, "no beats survived at all"
    assert all(n.startswith("alpha") for n in narr), (
        f"expected only first-half beats to survive, got: {narr}")
    assert not any(n.startswith("beta") for n in narr)       # second half dropped


@pytest.mark.xfail(strict=True, reason="G2: long-chapter merge+cap drops the second "
                                       "half of the story (Phase 2 fix pending)")
def test_g2_long_chapter_second_half_survives(monkeypatch):
    """DESIRED: with a balanced per-half budget, some second-half ('beta') content
    survives the cap so the whole story is narrated, not just its front."""
    p = _plan_long(monkeypatch)
    assert p.image_count() <= _CEILING
    narr = [b.narration for b in p.timeline]
    assert any(n.startswith("beta") for n in narr), (
        f"second-half content was entirely dropped: {narr}")
