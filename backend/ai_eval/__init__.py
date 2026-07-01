"""
ai_eval — offline content-quality evaluation harness (P0-1).

This package is TOOLING, not part of the FastAPI app. It scores the AI's
generated artifacts (clip selections, recap plans + narration, rewrite /
reaction segments) with an LLM-as-Judge against per-feature rubrics, so
that every future prompt / flag change can be measured objectively
against a frozen golden dataset.

Design rules:
- Depends on ``app`` (config keys + retry util) but ``app`` NEVER imports
  ``ai_eval`` — no production back-edge.
- The judge is fully injectable (``complete_fn``) so unit tests run
  offline with a fake completion function — no network, deterministic.
- Never raises into a caller: a failed judge call yields an error result
  with ``ok=False`` rather than crashing a batch run.

Entry points:
    python -m ai_eval.run_eval --dataset tests/fixtures/quality --provider gemini
    from ai_eval.judge import score_case
    from ai_eval.rubrics import RUBRICS
"""
from __future__ import annotations

__all__ = ["rubrics", "judge_prompts", "judge", "dataset", "llm_client"]
