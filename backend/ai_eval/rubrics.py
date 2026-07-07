"""
rubrics.py — per-feature quality rubrics + acceptance gates.

A Rubric is pure data: a list of scored Criteria (1-5 each, weighted) plus
hard Gates that a passing output must clear regardless of the weighted mean
(faithfulness is the canonical example — a hallucinated fact fails the
output even if everything else is excellent).

These rubrics are the objective definition of "good" for each feature.
Changing a threshold here changes the ship bar — treat edits as policy
changes, not code tweaks.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Criterion:
    key: str            # machine key, e.g. "hook_strength"
    description: str    # what a 5 vs a 1 means — shown to the judge
    weight: float = 1.0 # relative weight in the weighted mean


@dataclass(frozen=True)
class Gate:
    """A hard pass/fail threshold on a single criterion. The output FAILS the
    gate (and the whole case) when ``scores[criterion_key] < min_score``,
    even if the weighted mean is high."""
    criterion_key: str
    min_score: float
    reason: str


@dataclass(frozen=True)
class Rubric:
    feature: str
    criteria: list[Criterion]
    gates: list[Gate] = field(default_factory=list)
    # Ship bar for the weighted mean (0-5). Used by run_eval's summary gate.
    accept_min_weighted: float = 4.0

    def weight_total(self) -> float:
        return sum(c.weight for c in self.criteria) or 1.0

    def weighted_mean(self, scores: dict[str, float]) -> float:
        """Weighted mean over the criteria this rubric defines. Missing
        criterion scores count as 0 (a judge that omitted a field is a
        quality signal, not something to silently ignore)."""
        total = 0.0
        for c in self.criteria:
            total += float(scores.get(c.key, 0.0)) * c.weight
        return round(total / self.weight_total(), 3)

    def gate_failures(self, scores: dict[str, float]) -> list[str]:
        """Return the reasons for every failed hard gate ([] = all passed)."""
        out: list[str] = []
        for g in self.gates:
            if float(scores.get(g.criterion_key, 0.0)) < g.min_score:
                out.append(
                    f"{g.criterion_key}={scores.get(g.criterion_key, 0.0)} "
                    f"< {g.min_score}: {g.reason}"
                )
        return out


# ── Faithfulness is a shared hard gate on every generative feature. A recap /
#    clip / narration that invents a fact, name, or number is the one
#    unforgivable failure — it must fail regardless of craft scores. ──────────
_FAITHFULNESS = Criterion(
    key="faithfulness",
    description=(
        "5 = every fact, name, number, and event is grounded in the source; "
        "nothing invented, exaggerated, or dropped. "
        "1 = fabricates or materially distorts the source."
    ),
    weight=2.0,
)


RUBRICS: dict[str, Rubric] = {
    # ── CLIP ──────────────────────────────────────────────────────────────
    "clip": Rubric(
        feature="clip",
        criteria=[
            Criterion("hook_strength",
                      "5 = the first ~3 seconds grab attention hard (question, "
                      "reveal, bold claim). 1 = opens on filler / setup.",
                      weight=1.5),
            Criterion("standalone",
                      "5 = understandable with zero prior context. "
                      "1 = needs the rest of the video to make sense.",
                      weight=1.0),
            Criterion("payoff_completeness",
                      "5 = the clip ends after the thought/payoff lands. "
                      "1 = cuts mid-thought, no resolution.",
                      weight=1.5),
            Criterion("virality",
                      "5 = surprising / emotional / shareable. 1 = flat.",
                      weight=1.0),
            Criterion("dedup_distinctness",
                      "5 = each clip is a distinct idea. 1 = near-duplicate of "
                      "another selected clip.",
                      weight=0.5),
            _FAITHFULNESS,
        ],
        gates=[Gate("faithfulness", 4.5, "clip must not misrepresent the source")],
    ),
    # ── RECAP ─────────────────────────────────────────────────────────────
    "recap": Rubric(
        feature="recap",
        criteria=[
            Criterion("story_coverage",
                      "5 = scenes span the whole film start→ending and cover "
                      "the key beats. 1 = clusters at the start / big gaps.",
                      weight=1.5),
            Criterion("chronology",
                      "5 = scenes in correct chronological order, no overlaps. "
                      "1 = jumbled timeline.",
                      weight=1.0),
            Criterion("narration_fluency",
                      "5 = narration flows scene→scene as one cohesive script, "
                      "vivid and natural. 1 = disconnected dry descriptions.",
                      weight=1.5),
            Criterion("emotion_preservation",
                      "5 = the emotional arc (tension, payoff, catharsis) is "
                      "conveyed. 1 = emotionally flat.",
                      weight=1.0),
            Criterion("pacing_suspense",
                      "5 = deliberately slows/holds at peaks, uses silence for "
                      "impact. 1 = uniform, no suspense control.",
                      weight=1.0),
            _FAITHFULNESS,
        ],
        gates=[Gate("faithfulness", 4.5, "recap must retell, never fabricate")],
    ),
    # ── REACTION ──────────────────────────────────────────────────────────
    "reaction": Rubric(
        feature="reaction",
        criteria=[
            Criterion("specificity",
                      "5 = reactions name a concrete moment ('the way he lied to "
                      "the cop'). 1 = generic lines that fit any video.",
                      weight=2.0),
            Criterion("interleave_rhythm",
                      "5 = lead-in → silence → original payoff rhythm; leaves "
                      "clear original windows. 1 = wall-to-wall talk / no gaps.",
                      weight=1.5),
            Criterion("personality",
                      "5 = a real viewpoint (opinion, prediction, humor). "
                      "1 = neutral narration with no stance.",
                      weight=1.0),
            Criterion("naturalness",
                      "5 = sounds like a real person talking. 1 = scripted/stiff.",
                      weight=1.0),
            _FAITHFULNESS,
        ],
        gates=[Gate("faithfulness", 4.5, "reaction must not invent events/quotes")],
    ),
    # ── REWRITE ───────────────────────────────────────────────────────────
    "rewrite": Rubric(
        feature="rewrite",
        criteria=[
            Criterion("naturalness",
                      "5 = idiomatic native phrasing a narrator would speak. "
                      "1 = literal translationese / stiff.",
                      weight=1.5),
            Criterion("engagement",
                      "5 = hook-first, sentence variety, zero filler. "
                      "1 = monotone, filler-laden.",
                      weight=1.0),
            Criterion("time_fit",
                      "5 = each segment's wording fits its window at a natural "
                      "pace. 1 = clearly over/under-runs the slot.",
                      weight=1.0),
            Criterion("meaning_preservation",
                      "5 = same meaning as the source utterance. "
                      "1 = drifts from or drops the source meaning.",
                      weight=1.5),
            _FAITHFULNESS,
        ],
        gates=[Gate("faithfulness", 4.5, "rewrite must preserve source facts")],
    ),
    # ── CONTENT (Content Mode plan; CM-7 quality-mode A/B) ─────────────────
    "content": Rubric(
        feature="content",
        criteria=[
            Criterion("narration_fluency",
                      "5 = the per-scene narration reads as ONE cohesive script "
                      "that flows scene→scene (smooth transitions, strong hook "
                      "first, clear close, no repetition). 1 = disconnected, "
                      "repetitive, or abrupt scene jumps.",
                      weight=1.5),
            Criterion("time_fit",
                      "5 = each scene's narration length fits its planned seconds "
                      "at a natural pace (~15 characters/second); no scene is "
                      "clearly overloaded (rushes) or sparse (silence). "
                      "1 = lengths badly mismatch the planned durations.",
                      weight=1.5),
            Criterion("engagement",
                      "5 = hook-first, vivid, varied sentences a real channel "
                      "would use. 1 = monotone, filler-laden, generic.",
                      weight=1.0),
            _FAITHFULNESS,
        ],
        gates=[Gate("faithfulness", 4.5, "content narration must not invent facts")],
    ),
}


def get_rubric(feature: str) -> Rubric:
    """Return the rubric for a feature. Raises KeyError for an unknown feature
    (a typo in a golden case id is a test-authoring bug worth surfacing loudly)."""
    key = (feature or "").strip().lower()
    return RUBRICS[key]


SUPPORTED_FEATURES = tuple(RUBRICS.keys())
