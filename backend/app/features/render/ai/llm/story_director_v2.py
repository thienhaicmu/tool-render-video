"""
story_director_v2.py — provider-agnostic Super-Prompt orchestration for Story v2.

ONE super call → StoryPlan v2 (mode A adapt / mode B create-from-idea, same schema),
+ a bounded repair pass, + a chunk-and-merge path for very long chapters, + the
deterministic post-passes (inject character canon, cap/validate/reindex, seed).

Parameterised by ``call_fn(system, user) -> str | None`` so every provider binds its
own raw model call (key rotation / retry / cache inside call_fn) — mirrors v1
content_director. Sacred Contract #3: never raises; returns None on total failure.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable, Optional

from app.domain.story_plan_v2 import StoryPlan
from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_idea_prompt, build_super_repair_prompt,
    SUPER_PROMPT_VERSION,
)
from app.features.render.ai.llm.story_parser_v2 import parse_super_plan_response

logger = logging.getLogger("app.render.story_director_v2")

SuperCall = Callable[[str, str], Optional[str]]


def estimate_super_plan_cost(*, source_chars: int, ceiling: int, model: str = "gpt-4o") -> dict:
    """Rough $ estimate for ONE super-plan LLM call (F-08 — Story audit).

    Story imagery is procedural SVG ($0), but the planning LLM is NOT free — the
    pre-flight previously reported $0 total, hiding the only real cost. Returns
    ``{input_tokens, output_tokens, cost_usd}`` as an ESTIMATE (not billed usage).
    Per-1M rates are env-tunable (``OPENAI_STORY_PRICE_IN_PER_M`` /
    ``OPENAI_STORY_PRICE_OUT_PER_M``, default gpt-4o). Never raises."""
    try:
        # ~4 chars/token; +~3500 chars fixed prompt overhead (schema+rules+vocab).
        in_tok = int((max(0, int(source_chars)) + 3500) / 4)
        out_tok = int(max(1, int(ceiling)) * 300)   # ~1 visual + its beats per slot
        price_in = float(os.getenv("OPENAI_STORY_PRICE_IN_PER_M", "2.5"))
        price_out = float(os.getenv("OPENAI_STORY_PRICE_OUT_PER_M", "10.0"))
        cost = in_tok / 1_000_000 * price_in + out_tok / 1_000_000 * price_out
        return {"input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": round(cost, 4)}
    except Exception:
        return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


def lint_story_plan(plan) -> list:
    """Best-effort SEMANTIC lint of a BUILT StoryPlan (P3). Returns a list of
    human-readable warnings for a reviewer/monitor. NEVER mutates the plan and
    never raises — structural integrity is already enforced by
    StoryPlan.validate_refs; this only surfaces SOFT quality signals (weak plan)
    and does NOT gate the render (Sacred Contract #3 spirit)."""
    warnings: list = []
    try:
        chars = list(getattr(plan, "characters", []) or [])
        visuals = list(getattr(plan, "visuals", []) or [])
        timeline = list(getattr(plan, "timeline", []) or [])
        by_id = {c.id: c for c in chars}
        spoken = {(b.speaker_id or "") for b in timeline if (b.speaker_id or "")}
        # 1. A speaking character with no canonical look → generic overlay/voice.
        for cid in sorted(spoken):
            c = by_id.get(cid)
            if c is not None and not (c.canonical_desc or "").strip():
                warnings.append(f"character '{cid}' speaks but has no canonical_desc (generic look)")
        # 2. Orphan visuals (composed but no beat uses them → wasted work).
        used_vis = {(b.visual_id or "") for b in timeline}
        for v in visuals:
            if v.id and v.id not in used_vis:
                warnings.append(f"visual '{v.id}' is never used by any beat")
        # 3. Unused cast (defined but never speaks and never in a visual).
        in_visual = {cid for v in visuals for cid in (v.character_ids or [])}
        for c in chars:
            if c.id and c.id not in spoken and c.id not in in_visual:
                warnings.append(f"character '{c.id}' is defined but never speaks or appears")
        # 4. Degenerate repeated narration (possible looping output).
        from collections import Counter
        counts = Counter((b.narration or "").strip() for b in timeline if (b.narration or "").strip())
        for txt, n in counts.items():
            if n >= 3:
                warnings.append(f"narration repeated {n}× (possible loop): {txt[:40]!r}")
        # 5. No narration at all → a silent video.
        if timeline and not any((b.narration or "").strip() for b in timeline):
            warnings.append("no beat has narration (silent video)")
    except Exception:
        return warnings
    return warnings[:20]


def _stable_seed(text: str) -> int:
    try:
        return int(hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()[:8], 16)
    except Exception:
        return 0


def inject_character_canon(plan: StoryPlan) -> StoryPlan:
    """Append each present character's canonical_desc to a visual's prompt (idempotent)
    so image gen keeps the character consistent. No-op without characters. Never raises."""
    try:
        canon = {c.id: (c.canonical_desc or "").strip() for c in plan.characters if (c.canonical_desc or "").strip()}
        if not canon:
            return plan
        for v in plan.visuals:
            frags = []
            for cid in v.character_ids:
                d = canon.get(cid)
                if d and d not in frags:
                    frags.append(d)
            if not frags:
                continue
            inject = "; ".join(frags)
            base = (v.prompt or "").strip()
            if inject in base:
                continue
            v.prompt = f"{base}. {inject}" if base else inject
        return plan
    except Exception as exc:
        logger.info("story_director_v2: inject canon skipped: %s", exc)
        return plan


def _call_and_parse(call_fn: SuperCall, system: str, user: str, ceiling: int) -> Optional[StoryPlan]:
    """One call + parse; on parse-failure, one bounded repair pass (CM-8)."""
    try:
        raw = call_fn(system, user)
    except Exception as exc:
        logger.info("story_director_v2: call raised %s", exc)
        return None
    if not raw:
        return None
    plan = parse_super_plan_response(raw, ceiling)
    if plan is None and os.getenv("STORY_PLAN_REPAIR", "1") == "1":
        try:
            rsys, ruser = build_super_repair_prompt(raw)
            fixed = call_fn(rsys, ruser)
            if fixed:
                plan = parse_super_plan_response(fixed, ceiling)
                if plan is not None:
                    logger.info("story_director_v2: plan recovered via repair pass")
        except Exception as exc:
            logger.info("story_director_v2: repair pass failed %s", exc)
    return plan


def _merge_plans(a: StoryPlan, b: StoryPlan) -> StoryPlan:
    """Concatenate plan b after a: dedupe characters/settings by id, re-id b's visuals
    to avoid collision (remapping its beats), concat timelines. Never raises."""
    try:
        a_char = {c.id for c in a.characters}
        a.characters += [c for c in b.characters if c.id not in a_char]
        a_set = {s.id for s in a.settings}
        a.settings += [s for s in b.settings if s.id not in a_set]
        a_vis = {v.id for v in a.visuals}
        remap: dict = {}
        for v in b.visuals:
            new_id = v.id
            n = 2
            while new_id in a_vis:
                new_id = f"{v.id}_{n}"; n += 1
            remap[v.id] = new_id
            v.id = new_id
            a_vis.add(new_id)
            a.visuals.append(v)
        for beat in b.timeline:
            beat.visual_id = remap.get(beat.visual_id, beat.visual_id)
            a.timeline.append(beat)
        return a
    except Exception as exc:
        logger.info("story_director_v2: merge failed %s", exc)
        return a


def _plan_long_chapter(call_fn, chapter, language, art_style, aspect_ratio, subtitle_mode,
                       ceiling, threshold, prior_context="", library_catalog="") -> Optional[StoryPlan]:
    """Split an over-long chapter at a paragraph boundary into 2 halves, super-plan each
    under a PER-HALF slice of the visual budget, merge. Bounded to 2 calls. None if
    neither half planned."""
    mid = len(chapter) // 2
    cut = chapter.rfind("\n\n", 0, mid)
    if cut < threshold // 3:
        cut = mid
    parts = [p for p in (chapter[:cut].strip(), chapter[cut:].strip()) if p]
    if not parts:
        return None
    # G2 fix: budget the ceiling ACROSS the halves (ceil division) so the merged plan
    # stays ~ceiling — otherwise each half planned at the FULL ceiling and the outer
    # cap_visuals dropped a whole half (the back of the story) after merge.
    per_half = max(1, -(-int(ceiling) // len(parts)))
    plans = []
    for part in parts:
        sysm, user = build_super_story_prompt(part, language, art_style, aspect_ratio,
                                              subtitle_mode, per_half, prior_context, library_catalog)
        p = _call_and_parse(call_fn, sysm, user, per_half)
        if p is not None:
            plans.append(p)
    if not plans:
        return None
    merged = plans[0]
    for p in plans[1:]:
        merged = _merge_plans(merged, p)
    return merged


def run_super_plan(
    *,
    call_fn: SuperCall,
    source: str = "paste",
    chapter: Optional[str] = None,
    idea: Optional[str] = None,
    duration_sec: int = 0,
    genre: str = "",
    language: str = "vi",
    art_style: str = "",
    aspect_ratio: str = "16:9",
    subtitle_mode: str = "hook_only",
    ceiling: int = 15,
    series_id: str = "",
    chapter_no: int = 0,
    seed: int = 0,
    prior_context: str = "",
    library_catalog: str = "",
    provider_label: str = "",
) -> Optional[StoryPlan]:
    """Turn a source (chapter text OR idea) into a StoryPlan v2. ``prior_context`` (G1)
    grounds a later series chapter on earlier ones. Returns None on any failure
    (Sacred Contract #3 — never raises)."""
    try:
        src = (source or "paste").strip().lower()
        _p = provider_label or "?"
        if src == "idea":
            idea = (idea or "").strip()
            if not idea:
                return None
            sysm, user = build_super_idea_prompt(idea, duration_sec, genre, language, art_style,
                                                 aspect_ratio, subtitle_mode, ceiling, prior_context, library_catalog)
            logger.info("story_director_v2[%s]: super=%s IDEA len=%d dur=%ds ceiling=%d",
                        _p, SUPER_PROMPT_VERSION, len(idea), duration_sec, ceiling)
            plan = _call_and_parse(call_fn, sysm, user, ceiling)
            _seed_src = idea
        else:
            chapter = (chapter or "").strip()
            if not chapter:
                return None
            threshold = int(os.getenv("STORY_MAX_CHAPTER_CHARS_SINGLE", "18000") or 18000)
            logger.info("story_director_v2[%s]: super=%s PASTE len=%d ceiling=%d",
                        _p, SUPER_PROMPT_VERSION, len(chapter), ceiling)
            if len(chapter) > int(threshold * 1.2):
                plan = _plan_long_chapter(call_fn, chapter, language, art_style, aspect_ratio,
                                          subtitle_mode, ceiling, threshold, prior_context, library_catalog)
            else:
                sysm, user = build_super_story_prompt(chapter, language, art_style, aspect_ratio,
                                                      subtitle_mode, ceiling, prior_context, library_catalog)
                plan = _call_and_parse(call_fn, sysm, user, ceiling)
            _seed_src = chapter
        if plan is None:
            logger.warning("story_director_v2[%s]: no usable plan", _p)
            return None

        # ── Deterministic post-passes ────────────────────────────────────────
        # (No inject_character_canon: it appended a character's look to visual.prompt
        # for an IMAGE-GEN provider. Story is SVG-only — visual.prompt was removed
        # from the schema (s11) and the render composes from setting/archetype/asset —
        # so there is nothing to inject into. Character continuity lives in
        # canonical_desc via the series-memory block, not the visual prompt.)
        plan.cap_visuals(ceiling)
        plan.validate_refs()
        plan.reindex()
        plan.seed = int(seed) if seed else _stable_seed(_seed_src)
        if series_id:
            plan.series_id = series_id
        if chapter_no:
            plan.chapter_no = chapter_no
        if language:
            plan.language = language
        if not plan.art_style and art_style:
            plan.art_style = art_style
        if aspect_ratio:
            plan.aspect_ratio = aspect_ratio

        if plan.is_empty() or not plan.visuals:
            return None
        logger.info("story_director_v2[%s]: OK chars=%d visuals=%d beats=%d topic=%r",
                    _p, len(plan.characters), plan.image_count(), plan.beat_count(), plan.topic)
        return plan
    except Exception as exc:
        logger.warning("story_director_v2[%s]: unexpected %s", provider_label or "?", exc, exc_info=True)
        return None


__all__ = ["run_super_plan", "inject_character_canon", "estimate_super_plan_cost",
           "lint_story_plan", "SuperCall"]
