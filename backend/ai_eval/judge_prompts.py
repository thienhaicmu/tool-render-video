"""
judge_prompts.py — build the (system, user) prompt pair for the LLM judge.

The judge is asked to score ONE generated artifact against the feature's
rubric and return a single JSON object: {scores:{criterion:1-5}, rationale,
flags:[]}. The rubric criteria (from rubrics.py) are rendered into the prompt
so the judge and the acceptance gates agree on the exact definition of each
score.

Bias control: the judge should run on a DIFFERENT provider than the one that
generated the artifact (wired in run_eval), and at temperature 0 for
repeatability. The prompt forbids the judge from rewriting the content — it
only scores.
"""
from __future__ import annotations

import json
from typing import Any

from ai_eval.rubrics import Rubric, get_rubric


_SYSTEM_JUDGE = (
    "You are a senior AI content-quality evaluator for a professional video "
    "recap / clip platform. You score generated artifacts strictly against the "
    "given rubric. You are impartial and calibrated: reserve 5 for genuinely "
    "professional-channel quality and 1 for unusable output — do NOT cluster "
    "every score at 4-5. You NEVER rewrite or improve the content; you only "
    "score it and explain why. Output ONLY one JSON object, no prose, no "
    "markdown fences."
)


def _render_criteria(rubric: Rubric) -> str:
    lines: list[str] = []
    for c in rubric.criteria:
        lines.append(f'  - "{c.key}": {c.description}')
    return "\n".join(lines)


def _render_output_shape(rubric: Rubric) -> str:
    keys = ", ".join(f'"{c.key}": <1-5>' for c in rubric.criteria)
    return (
        "{\n"
        f'  "scores": {{ {keys} }},\n'
        '  "rationale": "<2-4 sentences: the single biggest strength and the '
        'single biggest weakness>",\n'
        '  "flags": ["<short tag for any hard problem, e.g. \'hallucinated_name\', '
        '\'mid_thought_cut\', \'generic_reaction\'; [] if none>"]\n'
        "}"
    )


# Per-feature framing of WHAT the judge is looking at, so it reads the payload
# with the right lens. Kept short — the rubric carries the scoring definitions.
_FEATURE_FRAMING: dict[str, str] = {
    "clip": (
        "You are judging a set of short-form CLIPS selected from a longer "
        "source transcript. Each clip has a start/end (seconds), an AI title, "
        "and an AI reason. Judge whether these are the strongest, most "
        "watchable, standalone viral moments — and whether each clip's window "
        "actually contains a complete hook→payoff based on the transcript excerpt."
    ),
    "recap": (
        "You are judging a film RECAP plan: a whole-film story understanding "
        "plus chronological scenes with AI-authored narration. Judge it as a "
        "professional recap producer would — story coverage, cohesive narration, "
        "emotional arc, and deliberate pacing/suspense."
    ),
    "reaction": (
        "You are judging a REACTION edit: interleaved reactor voice-over "
        "segments and silent 'original audio' windows. Judge whether the "
        "reactor sounds like a real creator reacting to SPECIFIC moments, with "
        "a genuine viewpoint and a lead-in→silence→payoff rhythm."
    ),
    "rewrite": (
        "You are judging an AI REWRITE: source utterances rewritten into timed "
        "narration for TTS. Judge naturalness, engagement, time-fit, and whether "
        "the rewritten meaning matches the source utterance."
    ),
    "content": (
        "You are judging a CONTENT-MODE video plan generated from a source "
        "script/article: ordered SCENES, each with a role, an AI-authored "
        "voice-over narration, and a planned duration (seconds). Judge it as a "
        "faceless short-form channel producer would — whether the narration "
        "flows as one cohesive script scene→scene, each scene's length fits its "
        "planned seconds, and it stays faithful to the source script."
    ),
}


def build_judge_prompt(feature: str, case_output: dict[str, Any],
                       case_inputs: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (system, user) for judging one artifact.

    ``case_output`` is the generated artifact (feature-specific shape).
    ``case_inputs`` is optional grounding context the judge needs to check
    faithfulness (e.g. the transcript excerpt the clips were cut from).
    """
    rubric = get_rubric(feature)
    framing = _FEATURE_FRAMING.get(feature, "")
    inputs_block = ""
    if case_inputs:
        inputs_block = (
            "\n═══ SOURCE CONTEXT (ground faithfulness in THIS) ═══\n"
            + json.dumps(case_inputs, ensure_ascii=False, indent=2)
            + "\n"
        )
    user = (
        f"{framing}\n"
        f"{inputs_block}"
        "\n═══ GENERATED ARTIFACT TO SCORE ═══\n"
        f"{json.dumps(case_output, ensure_ascii=False, indent=2)}\n"
        "\n═══ RUBRIC (score each 1-5 by THIS definition) ═══\n"
        f"{_render_criteria(rubric)}\n"
        "\n═══ OUTPUT (return ONLY this JSON object) ═══\n"
        f"{_render_output_shape(rubric)}\n"
        "\nRules: every criterion scored as an integer 1-5. Be calibrated — a "
        "4 means clearly good, a 5 means professional-grade. Put concrete "
        "problems in flags."
    )
    return _SYSTEM_JUDGE, user
