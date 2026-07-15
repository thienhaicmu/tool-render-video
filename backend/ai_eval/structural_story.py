"""
structural_story.py — deterministic, judge-free structural scorers for StoryPlan v2.

The Story counterpart of ``structural.py`` (which scores RecapPlan). Zero LLM calls,
zero quota, fully unit-testable — the trustworthy instrument for measuring whether a
Story super-plan meets the super-prompt's OWN spec (story_prompts_v2 HARD RULES):

  - rule 2/5: "REUSE a visual across MANY beats … do NOT make one image per beat"
    → beats-per-visual should be well above 1 (over-imaging is the failure mode).
  - rule 7: "mark ONLY 1-3 climactic beats as hook=true" → hook discipline.
  - characters carry a canonical look reused every image → grounding.
  - each beat = one contiguous narrated idea, faithful → narration coverage +
    a degenerate-repeat guard.
  - referential integrity: every visual_id / speaker_id / character_ids resolves.
  - idea mode: the plan's estimated length should fit the requested duration.

Every scorer is a pure function over the StoryPlan domain object, never raises, and
returns raw metrics plus (where meaningful) a 0-100 component score. Raw metrics are
always included so the composite can be re-weighted later without regenerating data.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

# Spec targets (see module docstring). Centralised so a prompt change updates here.
REUSE_TARGET = 2.0          # beats-per-visual at/above which reuse scores 100
HOOK_MIN, HOOK_MAX = 1, 3   # rule 7: 1-3 hook beats
DURATION_BAND = (0.75, 1.25)  # idea-mode: estimated / requested length tolerance


def _clamp100(x: float) -> float:
    return round(max(0.0, min(100.0, float(x))), 1)


def image_reuse(plan: Any) -> dict:
    """Beats-per-visual — the direct measure of the 'reuse a visual across many
    beats' rule. One image per beat (ratio ≤ 1) is the over-imaging failure."""
    try:
        beats = len(plan.timeline)
        visuals = len(plan.visuals)
        if visuals == 0:
            return {"visuals": 0, "beats": beats, "beats_per_visual": 0.0, "reuse_score": 0.0}
        ratio = beats / visuals
        if ratio >= REUSE_TARGET:
            score = 100.0
        elif ratio <= 1.0:
            score = 0.0
        else:
            score = 100.0 * (ratio - 1.0) / (REUSE_TARGET - 1.0)
        return {"visuals": visuals, "beats": beats,
                "beats_per_visual": round(ratio, 2), "reuse_score": _clamp100(score)}
    except Exception:
        return {"visuals": -1, "reuse_score": 0.0, "error": "unreadable_plan"}


def hook_discipline(plan: Any) -> dict:
    """Number of hook beats vs the prompt's 1-3 band. hooks_total is raw so a
    legitimately hook-free (subtitle=off) plan is distinguishable from a mis-count."""
    try:
        hooks = sum(1 for b in plan.timeline if bool(getattr(b, "hook", False)))
        if HOOK_MIN <= hooks <= HOOK_MAX:
            score = 100.0
        elif hooks == 0:
            score = 0.0
        else:  # too many hooks — decays with the excess
            score = 100.0 * (1.0 - (hooks - HOOK_MAX) / HOOK_MAX)
        return {"hooks_total": hooks, "in_band": HOOK_MIN <= hooks <= HOOK_MAX,
                "hook_score": _clamp100(score)}
    except Exception:
        return {"hooks_total": -1, "hook_score": 0.0, "error": "unreadable_plan"}


def character_grounding(plan: Any) -> dict:
    """Fraction of characters (and of SPEAKING characters) with a canonical look —
    the reused-look signal that keeps image gen consistent. None when no cast."""
    try:
        chars = list(plan.characters)
        if not chars:
            return {"characters": 0, "grounded_pct": None, "spoken_grounded_pct": None,
                    "grounding_score": None}
        grounded = sum(1 for c in chars if (getattr(c, "canonical_desc", "") or "").strip())
        spoken = {(b.speaker_id or "") for b in plan.timeline if (b.speaker_id or "")}
        by_id = {c.id: c for c in chars}
        spk = [by_id[s] for s in spoken if s in by_id]
        spk_grounded = sum(1 for c in spk if (getattr(c, "canonical_desc", "") or "").strip())
        return {
            "characters": len(chars),
            "grounded_pct": round(grounded / len(chars), 3),
            "spoken_grounded_pct": round(spk_grounded / len(spk), 3) if spk else None,
            "grounding_score": _clamp100(100.0 * grounded / len(chars)),
        }
    except Exception:
        return {"characters": -1, "grounding_score": 0.0, "error": "unreadable_plan"}


def narration_quality(plan: Any) -> dict:
    """Narration coverage + a degenerate-repeat guard (looping output). Score =
    coverage minus a penalty proportional to the repeated-beat fraction."""
    try:
        beats = list(plan.timeline)
        if not beats:
            return {"beats": 0, "narrated_pct": 0.0, "repeat_rate": 0.0, "narration_score": 0.0}
        texts = [(b.narration or "").strip() for b in beats]
        narrated = sum(1 for t in texts if t)
        counts = Counter(t for t in texts if t)
        repeated = sum(n for n in counts.values() if n >= 2)
        repeat_rate = repeated / len(beats)
        cover = narrated / len(beats)
        mean_chars = round(sum(len(t) for t in texts) / len(beats), 1)
        return {
            "beats": len(beats),
            "narrated_pct": round(cover, 3),
            "mean_narration_chars": mean_chars,
            "repeat_rate": round(repeat_rate, 3),
            "narration_score": _clamp100(100.0 * cover * (1.0 - repeat_rate)),
        }
    except Exception:
        return {"beats": -1, "narration_score": 0.0, "error": "unreadable_plan"}


def ref_integrity(plan: Any) -> dict:
    """Every beat.visual_id / speaker_id and every visual.character_ids must resolve.
    A validated plan scores 100; a raw plan surfaces the AI's dangling references."""
    try:
        cids = {c.id for c in plan.characters}
        vids = {v.id for v in plan.visuals}
        checks = dangling = 0
        for b in plan.timeline:
            checks += 1
            if b.visual_id not in vids:
                dangling += 1
            if b.speaker_id:
                checks += 1
                if b.speaker_id not in cids:
                    dangling += 1
        for v in plan.visuals:
            for c in (v.character_ids or []):
                checks += 1
                if c not in cids:
                    dangling += 1
        ok = (checks - dangling) / checks if checks else 1.0
        return {"checks": checks, "dangling": dangling,
                "integrity_score": _clamp100(100.0 * ok)}
    except Exception:
        return {"checks": -1, "integrity_score": 0.0, "error": "unreadable_plan"}


def duration_fit(plan: Any, requested_sec: float = 0.0) -> dict:
    """Estimated plan length vs the requested duration (idea mode). None when the
    duration is unknown (paste mode) — unknown ≠ bad."""
    try:
        req = float(requested_sec or 0.0)
        if req <= 0:
            return {"estimated_sec": round(plan.estimated_total_sec(), 1),
                    "ratio": None, "duration_score": None}
        est = plan.estimated_total_sec()
        ratio = est / req if req > 0 else 0.0
        lo, hi = DURATION_BAND
        if lo <= ratio <= hi:
            score = 100.0
        elif ratio < lo:
            score = 100.0 * ratio / lo
        else:
            score = 100.0 * (1.0 - (ratio - hi) / hi)
        return {"estimated_sec": round(est, 1), "requested_sec": round(req, 1),
                "ratio": round(ratio, 3), "duration_score": _clamp100(score)}
    except Exception:
        return {"estimated_sec": -1, "duration_score": None, "error": "unreadable_plan"}


def lint_load(plan: Any) -> dict:
    """Soft-lint warning count (reuses the production lint_story_plan). Fewer is
    better; each warning costs 12 points off 100."""
    try:
        from app.features.render.ai.llm.story_director_v2 import lint_story_plan
        warns = lint_story_plan(plan)
        return {"lint_warnings": len(warns),
                "lint_score": _clamp100(100.0 - 12.0 * len(warns))}
    except Exception:
        return {"lint_warnings": -1, "lint_score": 0.0, "error": "unreadable_plan"}


def scene_shot_quality(plan: Any) -> dict:
    """First-class scene/shot coverage and camera diversity."""
    try:
        from app.features.render.ai.llm.story_director_v2 import shot_grammar_report
        return shot_grammar_report(plan)
    except Exception:
        return {"scenes": 0, "shots": 0, "shot_score": 0.0, "error": "unreadable_plan"}


# Composite weights — sum to 1.0. Reuse + narration dominate (the two behaviours the
# super-prompt most insists on); integrity is a hard guard; duration only counts in
# idea mode (weight redistributed when None).
_WEIGHTS = {
    "reuse_score": 0.18, "hook_score": 0.10, "grounding_score": 0.16,
    "narration_score": 0.20, "integrity_score": 0.12, "duration_score": 0.05,
    "lint_score": 0.05, "shot_score": 0.14,
}


def story_structural_report(plan: Any, requested_duration_sec: float = 0.0) -> dict:
    """All structural metrics for one StoryPlan, flattened + a weighted overall
    score. Never raises; a None plan yields an 'empty' marker."""
    if plan is None:
        return {"empty": True, "overall_score": 0.0}
    report = {
        "reuse": image_reuse(plan),
        "hooks": hook_discipline(plan),
        "grounding": character_grounding(plan),
        "narration": narration_quality(plan),
        "integrity": ref_integrity(plan),
        "duration": duration_fit(plan, requested_duration_sec),
        "lint": lint_load(plan),
        "scene_shot": scene_shot_quality(plan),
    }
    # Weighted composite over available component scores (skip None → redistribute).
    comp = {
        "reuse_score": report["reuse"].get("reuse_score"),
        "hook_score": report["hooks"].get("hook_score"),
        "grounding_score": report["grounding"].get("grounding_score"),
        "narration_score": report["narration"].get("narration_score"),
        "integrity_score": report["integrity"].get("integrity_score"),
        "duration_score": report["duration"].get("duration_score"),
        "lint_score": report["lint"].get("lint_score"),
        "shot_score": report["scene_shot"].get("shot_score"),
    }
    num = den = 0.0
    for k, w in _WEIGHTS.items():
        v = comp.get(k)
        if v is None:
            continue
        num += w * float(v)
        den += w
    report["overall_score"] = round(num / den, 1) if den else 0.0
    return report


def summarize_story_structural(report: dict) -> str:
    """One-line human summary for run logs."""
    try:
        r = report.get("reuse", {})
        n = report.get("narration", {})
        g = report.get("grounding", {})
        return (f"overall={report.get('overall_score')} "
                f"beats/vis={r.get('beats_per_visual')} reuse={r.get('reuse_score')} "
                f"hooks={report.get('hooks', {}).get('hooks_total')} "
                f"ground={g.get('grounding_score')} narr={n.get('narration_score')} "
                f"integ={report.get('integrity', {}).get('integrity_score')} "
                f"lint={report.get('lint', {}).get('lint_warnings')} "
                f"shot={report.get('scene_shot', {}).get('shot_score')}")
    except Exception:
        return "story-structural: unreadable"


__all__ = [
    "image_reuse", "hook_discipline", "character_grounding", "narration_quality",
    "ref_integrity", "duration_fit", "lint_load", "scene_shot_quality",
    "story_structural_report", "summarize_story_structural",
]
