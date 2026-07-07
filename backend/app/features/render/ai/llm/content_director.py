"""
content_director.py — provider-agnostic orchestration for Content Mode planning
(render_format="content": Script → AI narration + visual plan → ContentPlan).

CM-2 (2026-07-07): the two-pass Content Director flow (CU-4 Story Bible → grounded
plan → CU-5 validate/repair → CU-6 character injection) used to live inside
``providers/gemini.py:select_content_plan``, which is why only Gemini could plan a
Content video and the ``select_content_plan`` fallback chain was a no-op. That
orchestration is provider-agnostic EXCEPT the raw model call — so it lives here,
parameterised by a ``call_fn(system, user) -> str | None`` that each provider
binds to its own content call (key rotation / retry / cache stay inside call_fn).

Adding a provider is now: expose a ``_call_<p>_content`` helper + a thin
``select_content_plan`` that binds it and delegates here. No duplication of the
CU-4/5/6 logic → no divergence risk (mirrors the NVENC resolver-parity concern).

Sacred Contract #3: never raises — returns None on any failure so a render job
fails cleanly (or the dispatcher falls through to the next provider).
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from app.features.render.ai.llm.content_prompts import (
    build_content_narration_refine_prompt,
    build_content_plan_prompt,
    build_content_plan_repair_prompt,
    build_story_bible_prompt,
    CONTENT_PLAN_PROMPT_VERSION,
)
from app.features.render.ai.llm.content_parser import (
    parse_content_plan_response,
    parse_story_bible_response,
)
from app.features.render.ai.llm.recap_parser import parse_episode_narration_response
from app.features.render.ai.llm.content_quality import (
    inject_character_fragments,
    validate_and_repair,
)

logger = logging.getLogger("app.render.llm_content_director")

# CU-4: two-pass Content Director gate. Pass A commits a Story Bible (characters +
# through-line); Pass B writes the plan GROUNDED in it → consistent narration +
# visuals. Default on; CONTENT_MULTIPASS=0 → single call. The extra bible call is
# gated by script length (P2.1): short scripts rarely have recurring characters so
# Pass B alone suffices — skipping Pass A there saves ~1 LLM call at no quality
# loss. These read the SAME env vars gemini used, so behaviour is unchanged when
# gemini delegates here. Canonical home for the gate (was duplicated in gemini.py).
_CONTENT_MULTIPASS = os.getenv("CONTENT_MULTIPASS", "1") == "1"
_CONTENT_MULTIPASS_MIN_CHARS = int(os.getenv("CONTENT_MULTIPASS_MIN_CHARS", "1200"))

# Type of the per-provider raw call: (system_prompt, user_prompt) -> raw text|None.
ContentCall = Callable[[str, str], Optional[str]]


def run_content_director(
    *,
    call_fn: ContentCall,
    script: str,
    target_duration_sec: float = 90.0,
    target_language: str = "vi-VN",
    tone: str = "",
    provider_label: str = "",
) -> Optional["object"]:
    """Turn a raw script into a ContentPlan via the two-pass Content Director,
    using ``call_fn`` for every model call. Returns a ContentPlan or None on any
    failure (Sacred Contract #3 — never raises).

    ``call_fn`` owns all provider specifics (SDK client, key rotation, retry,
    response caching). The caller is responsible for its own SDK/key/script
    guards BEFORE calling here; this orchestrator assumes a usable ``call_fn``."""
    try:
        if not script or not str(script).strip():
            return None
        _p = provider_label or "?"

        # ── CU-4 Pass A — Story Bible (best-effort; failure → single-pass) ────
        bible = None
        meta: dict = {}
        if _CONTENT_MULTIPASS and len(str(script).strip()) >= _CONTENT_MULTIPASS_MIN_CHARS:
            try:
                _bsys, _buser = build_story_bible_prompt(script, target_language, tone)
                _braw = call_fn(_bsys, _buser)
                _parsed = parse_story_bible_response(_braw) if _braw else None
                if _parsed is not None:
                    bible, meta = _parsed
                    logger.info(
                        "content_director[%s]: pass-A bible OK characters=%d",
                        _p, len(bible.characters),
                    )
            except Exception as _be:
                logger.info("content_director[%s]: pass-A bible failed (%s) — single-pass", _p, _be)
                bible = None

        # ── Pass B — the plan, GROUNDED in the Bible when available ──────────
        system_prompt, user_prompt = build_content_plan_prompt(
            script, target_duration_sec, target_language, tone, bible=bible,
        )
        logger.info(
            "content_director[%s]: calling content prompt=%s target_dur=%.0fs lang=%s in_chars=%d grounded=%s",
            _p, CONTENT_PLAN_PROMPT_VERSION, float(target_duration_sec or 0.0),
            target_language, len(script), bible is not None,
        )
        raw = call_fn(system_prompt, user_prompt)
        if not raw:
            logger.warning("content_director[%s]: empty content response", _p)
            return None
        plan = parse_content_plan_response(raw, target_duration_sec)
        if plan is None:
            # CM-8: one bounded repair pass — ask the model to fix its own
            # malformed/truncated JSON, then parse again. Recovers a plan the
            # deterministic salvage couldn't, instead of failing the render.
            # Kill-switch CONTENT_PLAN_REPAIR=0. Best-effort — never raises.
            if raw and os.getenv("CONTENT_PLAN_REPAIR", "1") == "1":
                try:
                    _rsys, _ruser = build_content_plan_repair_prompt(raw)
                    _fixed = call_fn(_rsys, _ruser)
                    if _fixed:
                        plan = parse_content_plan_response(_fixed, target_duration_sec)
                        if plan is not None:
                            logger.info("content_director[%s]: plan recovered via repair pass", _p)
                except Exception as _repexc:
                    logger.info("content_director[%s]: repair pass failed (%s)", _p, _repexc)
            if plan is None:
                return None

        # Assemble: stamp the Bible + pass-A metadata, then deterministic CU-5/CU-6.
        if bible is not None and plan.story_bible.is_empty():
            plan.story_bible = bible
        for _k in ("topic", "tone", "audience", "video_style"):
            if meta.get(_k) and not (getattr(plan, _k, "") or "").strip():
                setattr(plan, _k, meta[_k])
        plan = validate_and_repair(plan, plan.story_bible)       # CU-5
        plan = inject_character_fragments(plan, plan.story_bible)  # CU-6

        # CM-7: multi-step "quality" mode (CONTENT_PLAN_MODE=quality, default
        # "fast" = single plan pass, unchanged). Adds ONE focused narration-refine
        # pass so the voice-over flows scene→scene and each scene's length matches
        # its planned seconds — the plan's weakest point when written in one shot.
        # Reuses the EXISTING refine prompt + parser via call_fn (no new prompt,
        # no extra provider surface). Best-effort: any failure keeps the original
        # narration (Sacred Contract #3 spirit).
        if os.getenv("CONTENT_PLAN_MODE", "fast").strip().lower() == "quality" and plan.scenes:
            try:
                _payload = [
                    {
                        "index": i, "role": (s.role or ""),
                        "seconds": float(getattr(s, "est_duration_sec", 0.0) or 0.0),
                        "narration": (s.narration or ""),
                    }
                    for i, s in enumerate(plan.scenes)
                ]
                _nsys, _nuser = build_content_narration_refine_prompt(
                    _payload, topic=(plan.topic or ""), tone=tone, target_language=target_language,
                )
                _nraw = call_fn(_nsys, _nuser)
                _refined = parse_episode_narration_response(_nraw) if _nraw else {}
                _n = 0
                for i, s in enumerate(plan.scenes):
                    _txt = _refined.get(i)
                    if _txt and _txt.strip():
                        s.narration = _txt.strip()
                        _n += 1
                if _n:
                    logger.info(
                        "content_director[%s]: quality narration refine applied (%d scene(s))", _p, _n,
                    )
            except Exception as _qexc:
                logger.info("content_director[%s]: quality refine skipped (%s)", _p, _qexc)

        logger.info(
            "content_director[%s]: content OK scenes=%d total=%.0fs topic=%r chars=%d",
            _p, plan.scene_count(), plan.total_target_sec, plan.topic,
            len(plan.story_bible.characters),
        )
        return plan
    except Exception as exc:
        logger.warning(
            "content_director[%s]: unexpected error %s", provider_label or "?", exc, exc_info=True,
        )
        return None


__all__ = ["run_content_director", "ContentCall"]
