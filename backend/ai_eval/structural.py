"""
structural.py — deterministic, judge-free structural scorers for RecapPlan.

Sprint-1A of the evaluation roadmap. These measure the construct that
Editorial/narration changes actually target — STRUCTURE and EXPERIENCE-shape —
which the content-fidelity LLM rubric is blind to. Zero LLM calls, zero quota,
fully unit-testable, and therefore the most trustworthy instrument available
while judging stays Gemini-only (self-preference caveat).

Ground-truth targets come from the recap prompt's OWN spec (recap_prompts.py):
  - each scene "typically 8–40 seconds"; hard floor 6s ("NO 2–5s fragments")
  - "a feature film usually needs 15–40 scenes total"
  - holds ("original" audio) used "sparingly (roughly 1–3 per episode)" at PEAK
    dramatic beats → a hold should coincide with an is_climax scene.

Every scorer: pure function over the RecapPlan domain object, never raises,
returns a dict of raw metrics plus (where meaningful) a 0–100 component score.
Raw metrics are always included so the composite can be re-derived/re-weighted
later without regenerating data.
"""
from __future__ import annotations

from typing import Any, Optional

# Prompt-spec targets (see module docstring). Centralised so a future prompt
# change updates the scorer in one place.
FRAGMENT_SEC = 8.0          # scenes shorter than this are "fragments"
TARGET_SCENE_MAX = 40       # prompt: "15–40 scenes" for a feature film
OVERFLOW_SPAN = 60.0        # scenes beyond target that zero the count factor


def scene_fatigue(plan: Any) -> dict:
    """Viewer-fatigue proxy from scene count + length distribution.

    The observed failure mode (editorial OFF) is 36–91 short, choppy scenes —
    fragment_rate and scene_count capture exactly that. discipline_score is a
    0–100 composite: 100 = no fragments and scene count within the prompt's
    own target; decays with fragment rate and with count overflow.
    """
    try:
        scenes = plan.scenes()
        durs = [max(0.0, float(s.end) - float(s.start)) for s in scenes]
        n = len(durs)
        if n == 0:
            return {"scene_count": 0, "mean_scene_sec": 0.0, "min_scene_sec": 0.0,
                    "fragment_rate": 0.0, "discipline_score": 0.0}
        fragments = sum(1 for d in durs if d < FRAGMENT_SEC)
        frag_rate = fragments / n
        overflow = max(0, n - TARGET_SCENE_MAX)
        count_factor = max(0.0, 1.0 - overflow / OVERFLOW_SPAN)
        return {
            "scene_count": n,
            "mean_scene_sec": round(sum(durs) / n, 1),
            "min_scene_sec": round(min(durs), 1),
            "fragment_rate": round(frag_rate, 3),
            "discipline_score": round(100.0 * (1.0 - frag_rate) * count_factor, 1),
        }
    except Exception:
        return {"scene_count": -1, "discipline_score": 0.0, "error": "unreadable_plan"}


def hold_placement(plan: Any) -> dict:
    """Are the 'original audio' holds placed at the actual dramatic peaks?

    precision = of the holds emitted, how many land on an is_climax scene.
    recall    = of the climax scenes, how many got a hold.
    None (not 0) when the denominator is empty — "no holds" is a different
    fact from "holds all mis-placed", and the aggregate must not conflate them.
    """
    try:
        scenes = plan.scenes()
        holds = [s for s in scenes if str(getattr(s, "audio_mode", "")) == "original"]
        climaxes = [s for s in scenes if bool(getattr(s, "is_climax", False))]
        on_peak = sum(1 for s in holds if bool(getattr(s, "is_climax", False)))
        n_eps = max(1, plan.episode_count())
        return {
            "holds_total": len(holds),
            "climax_scenes": len(climaxes),
            "holds_on_climax": on_peak,
            "hold_precision": round(on_peak / len(holds), 3) if holds else None,
            "climax_recall": round(on_peak / len(climaxes), 3) if climaxes else None,
            "holds_per_episode": round(len(holds) / n_eps, 2),
        }
    except Exception:
        return {"holds_total": -1, "error": "unreadable_plan"}


def beat_coverage(plan: Any) -> dict:
    """Fraction of the StoryModel's plot turns executed by a selected scene.

    Reuses the deterministic reconciler already on the domain object
    (bind_story_beats_to_scenes — idempotent, never raises). None when the
    StoryModel carries no beats (nothing to cover ≠ perfect coverage).
    """
    try:
        plan.bind_story_beats_to_scenes()
        beats = list(getattr(plan.story, "beats", []) or [])
        if not beats:
            return {"beats_total": 0, "beats_bound": 0, "coverage_pct": None}
        return {
            "beats_total": len(beats),
            "beats_bound": plan.story.bound_count(),
            "coverage_pct": round(plan.story.coverage_pct(), 3),
        }
    except Exception:
        return {"beats_total": -1, "error": "unreadable_plan"}


def episode_balance(plan: Any) -> dict:
    """Episodes should be of roughly comparable length (the prompt's own rule).

    balance_score = 100 * (1 - CV) where CV = stdev/mean of episode durations,
    clamped to [0, 100]. None with fewer than 2 episodes (nothing to balance).
    """
    try:
        eps = list(plan.episodes or [])
        if len(eps) < 2:
            return {"episodes": len(eps), "balance_score": None}
        durs = []
        for ep in eps:
            durs.append(sum(max(0.0, float(s.end) - float(s.start)) for s in ep.scenes()))
        mean = sum(durs) / len(durs)
        if mean <= 0:
            return {"episodes": len(eps), "balance_score": None}
        var = sum((d - mean) ** 2 for d in durs) / len(durs)
        cv = (var ** 0.5) / mean
        return {
            "episodes": len(eps),
            "episode_secs": [round(d, 1) for d in durs],
            "balance_score": round(max(0.0, min(100.0, 100.0 * (1.0 - cv))), 1),
        }
    except Exception:
        return {"episodes": -1, "error": "unreadable_plan"}


def structural_report(plan: Any) -> dict:
    """All structural metrics for one RecapPlan, flattened for the store.

    Never raises; a None plan yields an 'empty' marker so accumulation rows
    stay parseable.
    """
    if plan is None:
        return {"empty": True}
    return {
        "fatigue": scene_fatigue(plan),
        "holds": hold_placement(plan),
        "beats": beat_coverage(plan),
        "episodes": episode_balance(plan),
    }


def summarize_structural(report: dict) -> str:
    """One-line human summary for run logs."""
    try:
        f = report.get("fatigue", {})
        h = report.get("holds", {})
        b = report.get("beats", {})
        prec = h.get("hold_precision")
        cov = b.get("coverage_pct")
        return (f"scenes={f.get('scene_count')} frag={f.get('fragment_rate')} "
                f"discipline={f.get('discipline_score')} "
                f"hold_prec={'-' if prec is None else prec} "
                f"beat_cov={'-' if cov is None else cov}")
    except Exception:
        return "structural: unreadable"
