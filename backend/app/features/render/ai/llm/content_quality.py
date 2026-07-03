"""
content_quality.py — deterministic post-AI passes for the Content Director.

CU-5 (validate + repair) and CU-6 (character-consistency injection). Both run
AFTER the LLM produces a ContentPlan, are purely deterministic (no LLM), and are
defensive — they never raise and return the plan unchanged on any error (Sacred
Contract #3 spirit). Keeping them out of the parser keeps "parse the model
output" separate from "enforce our invariants + enrich for consistency".
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("app.render.content_quality")


def validate_and_repair(plan, bible=None):
    """CU-5 — deterministic validation + repair of a ContentPlan.

    - Drops scenes with empty narration and re-indexes densely (parser already
      does this, re-affirmed here for a plan that arrived via another path).
    - Filters each scene's ``characters`` to ids/names that actually exist in the
      Story Bible (so a hallucinated character can't drive injection); clears them
      when there is no bible.
    Returns the (mutated) plan, or the input unchanged on any error. Never raises."""
    if plan is None:
        return plan
    try:
        # Re-affirm: only keep narrated scenes, densely indexed.
        kept = [s for s in plan.scenes if (getattr(s, "narration", "") or "").strip()]
        for i, s in enumerate(kept):
            s.index = i
        plan.scenes = kept

        known: set[str] = set()
        chars = getattr(bible, "characters", None) if bible is not None else None
        for c in (chars or []):
            for v in (getattr(c, "id", ""), getattr(c, "name", "")):
                v = (v or "").strip().lower()
                if v:
                    known.add(v)
        for s in plan.scenes:
            refs = getattr(s, "characters", None) or []
            s.characters = [r for r in refs if (r or "").strip().lower() in known] if known else []
        return plan
    except Exception as exc:
        logger.info("content_quality: validate_and_repair skipped: %s", exc)
        return plan


def inject_character_fragments(plan, bible=None):
    """CU-6 — visual consistency. For each scene, append the CANONICAL description
    of every Story Bible character present in that scene to the scene's
    ``visual_prompt`` (idempotent — skips a fragment already present), so an image
    generator draws the same character consistently across scenes. No-op without a
    bible / characters. Returns the (mutated) plan. Never raises."""
    if plan is None or bible is None:
        return plan
    try:
        if not getattr(bible, "characters", None):
            return plan
        for s in plan.scenes:
            frags: list[str] = []
            for cid in (getattr(s, "characters", None) or []):
                c = bible.character(cid) if hasattr(bible, "character") else None
                desc = (getattr(c, "description", "") or "").strip() if c is not None else ""
                if desc and desc not in frags:
                    frags.append(desc)
            if not frags:
                continue
            base = (getattr(s, "visual_prompt", "") or "").strip()
            inject = "; ".join(frags)
            if inject in base:
                continue
            s.visual_prompt = f"{base}. {inject}" if base else inject
        return plan
    except Exception as exc:
        logger.info("content_quality: inject_character_fragments skipped: %s", exc)
        return plan


__all__ = ["validate_and_repair", "inject_character_fragments"]
