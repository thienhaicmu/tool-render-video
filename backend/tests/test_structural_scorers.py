"""
test_structural_scorers.py — guard for Sprint-1A/1B (deterministic structural
scorers + config-vector).

These scorers are the judge-free instrument for editorial's actual construct
(structure/fatigue/hold-placement), so their math must be pinned exactly.
Built on the real RecapPlan domain classes; fully offline.
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
from ai_eval.runmeta import config_vector
from ai_eval.structural import (
    beat_coverage,
    duration_ratio,
    episode_balance,
    hold_placement,
    scene_fatigue,
    structural_report,
    summarize_structural,
)


def _plan(scenes_by_ep: list[list[RecapScene]], beats: list[StoryBeat] | None = None) -> RecapPlan:
    eps = [Episode(title=f"ep{i}", acts=[Act(title="a", scenes=list(sc))])
           for i, sc in enumerate(scenes_by_ep)]
    return RecapPlan(story=StoryModel(beats=beats or []), episodes=eps)


def _scene(start, end, mode="narrate", climax=False):
    return RecapScene(start=start, end=end, audio_mode=mode, is_climax=climax)


# ── scene_fatigue ────────────────────────────────────────────────────────────

def test_fatigue_clean_plan_scores_100():
    p = _plan([[_scene(0, 20), _scene(20, 50), _scene(50, 80)]])
    f = scene_fatigue(p)
    assert f["scene_count"] == 3
    assert f["fragment_rate"] == 0.0
    assert f["discipline_score"] == 100.0


def test_fatigue_fragments_penalized():
    # 2 of 4 scenes under 8s → fragment_rate 0.5 → discipline 50.
    p = _plan([[_scene(0, 3), _scene(3, 6), _scene(6, 30), _scene(30, 60)]])
    f = scene_fatigue(p)
    assert f["fragment_rate"] == 0.5
    assert f["discipline_score"] == 50.0


def test_fatigue_sprawl_penalized():
    # 91 clean scenes (the observed editorial-OFF sprawl): overflow 51/60.
    scenes = [_scene(i * 10.0, i * 10.0 + 10.0) for i in range(91)]
    f = scene_fatigue(_plan([scenes]))
    assert f["scene_count"] == 91
    assert f["fragment_rate"] == 0.0
    assert f["discipline_score"] == 15.0   # 100 * (1 - 51/60)


def test_fatigue_empty_plan():
    assert scene_fatigue(_plan([[]]))["discipline_score"] == 0.0


# ── hold_placement ───────────────────────────────────────────────────────────

def test_holds_precision_and_recall():
    p = _plan([[
        _scene(0, 20, "narrate"),
        _scene(20, 40, "original", climax=True),   # hold on peak ✓
        _scene(40, 60, "original", climax=False),  # hold off peak ✗
        _scene(60, 80, "narrate", climax=True),    # peak without hold
    ]])
    h = hold_placement(p)
    assert h["holds_total"] == 2 and h["climax_scenes"] == 2
    assert h["hold_precision"] == 0.5
    assert h["climax_recall"] == 0.5


def test_holds_none_when_no_holds():
    h = hold_placement(_plan([[_scene(0, 20), _scene(20, 40, climax=True)]]))
    assert h["hold_precision"] is None      # no holds ≠ mis-placed holds
    assert h["climax_recall"] == 0.0


# ── beat_coverage ────────────────────────────────────────────────────────────

def test_beat_coverage_binds_and_scores():
    beats = [StoryBeat(text="turn", t=25.0), StoryBeat(text="lost", t=500.0)]
    p = _plan([[_scene(0, 30), _scene(30, 60)]], beats=beats)
    b = beat_coverage(p)
    assert b["beats_total"] == 2 and b["beats_bound"] == 1
    assert b["coverage_pct"] == 0.5


def test_beat_coverage_none_without_beats():
    assert beat_coverage(_plan([[_scene(0, 30)]]))["coverage_pct"] is None


# ── episode_balance ──────────────────────────────────────────────────────────

def test_episode_balance_equal_is_100():
    p = _plan([[_scene(0, 60)], [_scene(100, 160)]])
    assert episode_balance(p)["balance_score"] == 100.0


def test_episode_balance_skew_lowers_score():
    p = _plan([[_scene(0, 10)], [_scene(100, 400)]])
    b = episode_balance(p)
    assert b["balance_score"] is not None and b["balance_score"] < 30.0


def test_episode_balance_single_episode_is_none():
    assert episode_balance(_plan([[_scene(0, 60)]]))["balance_score"] is None


# ── duration_ratio ───────────────────────────────────────────────────────────

def test_duration_ratio_in_band_scores_100():
    # 1000s recap of a 5000s film → ratio 0.20, inside the prompt's 10–25% band.
    p = _plan([[_scene(0, 500), _scene(500, 1000)]])
    d = duration_ratio(p, 5000.0)
    assert d["ratio"] == 0.2 and d["in_band"] is True and d["ratio_score"] == 100.0


def test_duration_ratio_undercompression_penalized():
    # The observed failure: ~6% of runtime → shortfall vs 10% floor → score 60.
    p = _plan([[_scene(0, 300)]])          # 300s recap
    d = duration_ratio(p, 5000.0)          # ratio 0.06
    assert d["ratio"] == 0.06 and d["in_band"] is False
    assert d["ratio_score"] == 60.0


def test_duration_ratio_overcompression_penalized():
    # 40% of runtime → excess vs 25% ceiling → 100*(1-0.15/0.25)=40.
    p = _plan([[_scene(0, 2000)]])
    d = duration_ratio(p, 5000.0)
    assert d["ratio"] == 0.4 and d["ratio_score"] == 40.0


def test_duration_ratio_unknown_film_is_none():
    d = duration_ratio(_plan([[_scene(0, 300)]]), 0.0)
    assert d["ratio"] is None and d["ratio_score"] is None


# ── report / robustness / runmeta ────────────────────────────────────────────

def test_structural_report_shape_and_none():
    assert structural_report(None) == {"empty": True}
    rep = structural_report(_plan([[_scene(0, 20, "original", climax=True)]]), film_duration_sec=100.0)
    assert set(rep) == {"fatigue", "holds", "beats", "episodes", "duration"}
    assert rep["duration"]["ratio"] == 0.2
    assert "scenes=" in summarize_structural(rep)
    assert "dur_ratio=0.2" in summarize_structural(rep)
    # Backward compat: no film duration → duration metrics None, no crash.
    rep2 = structural_report(_plan([[_scene(0, 20)]]))
    assert rep2["duration"]["ratio"] is None


def test_scorers_never_raise_on_junk():
    class Junk:  # no scenes()/episodes — every scorer must degrade, not raise
        pass
    assert scene_fatigue(Junk())["discipline_score"] == 0.0
    assert hold_placement(Junk())["holds_total"] == -1
    assert beat_coverage(Junk())["beats_total"] == -1
    assert episode_balance(Junk())["episodes"] == -1


def test_config_vector_flags_overrides_and_versions(monkeypatch):
    monkeypatch.setenv("RECAP_EDITORIAL_PASS", "1")
    cv = config_vector(ab_variable="RECAP_EDITORIAL_PASS", forced_arm="off")
    assert cv["RECAP_EDITORIAL_PASS"] == "1"
    assert cv["ab_variable"] == "RECAP_EDITORIAL_PASS" and cv["forced_arm"] == "off"
    assert isinstance(cv["prompt_version"], int)
    assert "CLIP_DEDUP_IOU" in cv and "GEMINI_DEFAULT_MODEL" in cv
