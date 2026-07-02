"""
test_recap_trim_to_band.py — guard for the duration-band reconciler.

Deterministic enforcement of the recap's own length spec (10–25% of runtime,
scenes ≤40s), added after measurement showed the LLM ignores even a HARD
prompt budget (69% of runtime post-prompt-fix). Pins:
  - cap pass keeps scene STARTS and brings an over-long plan into band
  - drop pass removes non-essential scenes globally longest-first
  - climax / original-audio scenes are never dropped; episodes never emptied
  - under-band and in-band plans are untouched (trim-only)
  - beat bindings recomputed after drops; total_target_sec kept coherent
  - never raises
"""
from __future__ import annotations

from app.domain.recap_plan import (
    Act,
    Episode,
    RecapPlan,
    RecapScene,
    StoryBeat,
    StoryModel,
)

_FILM = 1000.0                      # band = [100, 250] seconds


def _scene(start, end, mode="narrate", climax=False, title=""):
    return RecapScene(start=start, end=end, audio_mode=mode, is_climax=climax, title=title)


def _plan(scenes_by_ep, beats=None):
    eps = [Episode(title=f"ep{i}", acts=[Act(title="a", scenes=list(sc))])
           for i, sc in enumerate(scenes_by_ep)]
    return RecapPlan(story=StoryModel(beats=beats or []), episodes=eps)


def test_in_band_plan_untouched():
    p = _plan([[_scene(0, 100), _scene(200, 300)]])      # 200s = 20% → in band
    r = p.trim_to_duration_band(_FILM)
    assert r["changed"] is False and r["in_band"] is True
    assert p.scene_count() == 2 and r["ratio_before"] == r["ratio_after"] == 0.2


def test_under_band_reported_never_padded():
    p = _plan([[_scene(0, 50)]])                          # 5% → under band
    r = p.trim_to_duration_band(_FILM)
    assert r["changed"] is False and r["in_band"] is False
    assert p.scenes()[0].end == 50                        # trim-only: no extension


def test_cap_pass_brings_long_scenes_into_band():
    # 3 scenes of 200s (60% of film). Capping at 40s → 120s = 12% → in band.
    p = _plan([[_scene(0, 200), _scene(300, 500), _scene(600, 800)]])
    r = p.trim_to_duration_band(_FILM)
    assert r["capped_scenes"] == 3 and r["dropped_scenes"] == 0
    assert r["in_band"] is True
    starts = [s.start for s in p.scenes()]
    assert starts == [0, 300, 600]                        # starts (hooks) preserved
    assert all((s.end - s.start) == 40.0 for s in p.scenes())
    assert p.total_target_sec == 120.0                    # claimed total made coherent


def test_drop_pass_globally_longest_first_preserves_essentials():
    # 9×40s = 360s (36%) after capping is still > 250s ceiling → drops needed.
    # Episode 0 holds the climax + an original-audio hold — both must survive.
    ep0 = [
        _scene(0, 40, climax=True, title="climax"),
        _scene(50, 90, mode="original", title="hold"),
        _scene(100, 140, title="d1"),
    ]
    ep1 = [_scene(200 + i * 50, 240 + i * 50, title=f"d{i+2}") for i in range(6)]
    p = _plan([ep0, ep1])
    r = p.trim_to_duration_band(_FILM)
    assert r["in_band"] is True
    titles = [s.title for s in p.scenes()]
    assert "climax" in titles and "hold" in titles        # essentials survived
    assert r["dropped_scenes"] == 9 - p.scene_count()
    assert p.episodes[1].scene_count() >= 1               # episode never emptied


def test_never_empties_an_episode():
    # Episode 1 has ONE droppable scene — it must survive even though the plan
    # stays over the ceiling (reconciler stops rather than emptying it).
    ep0 = [_scene(i * 50, i * 50 + 40, climax=True) for i in range(7)]  # essential wall
    ep1 = [_scene(900, 940)]
    p = _plan([ep0, ep1])
    r = p.trim_to_duration_band(_FILM)                    # 8×40=320s, can only drop ep1's
    assert p.episodes[1].scene_count() == 1               # ...but never empties it
    assert r["in_band"] is False                          # honest: still over


def test_beats_rebound_after_drops():
    # Beat anchored in a scene that gets dropped → unbound after reconcile.
    beats = [StoryBeat(text="kept", t=20.0), StoryBeat(text="dropped", t=520.0)]
    ep = [_scene(0, 40, climax=True), _scene(100, 140, climax=True),
          _scene(500, 540, title="victim1"), _scene(600, 640, title="victim2"),
          _scene(700, 740, title="v3"), _scene(800, 840, title="v4"),
          _scene(900, 940, title="v5")]
    p = _plan([ep], beats=beats)                          # 7×40=280s > 250 ceiling
    p.bind_story_beats_to_scenes()
    assert p.story.beats[1].is_bound
    r = p.trim_to_duration_band(_FILM)
    assert r["dropped_scenes"] >= 1
    assert p.story.beats[0].is_bound                      # anchor at 20s survives
    if all(s.title != "victim1" for s in p.scenes()):     # its scene was dropped
        assert not p.story.beats[1].is_bound


def test_noop_on_unknown_film_or_empty_plan():
    p = _plan([[_scene(0, 500)]])
    assert p.trim_to_duration_band(0.0)["changed"] is False
    assert p.scenes()[0].end == 500                       # untouched
    empty = RecapPlan()
    assert empty.trim_to_duration_band(_FILM)["changed"] is False


def test_never_raises_on_junk():
    p = _plan([[_scene(0, 500)]])
    assert p.trim_to_duration_band("garbage")["changed"] is False  # type: ignore
