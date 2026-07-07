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
    build_content_plan_prompt,
    build_story_bible_prompt,
)
from app.features.render.ai.llm.content_parser import (
    parse_content_plan_response,
    parse_story_bible_response,
)
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
            "content_director[%s]: calling content target_dur=%.0fs lang=%s in_chars=%d grounded=%s",
            _p, float(target_duration_sec or 0.0), target_language, len(script), bible is not None,
        )
        raw = call_fn(system_prompt, user_prompt)
        if not raw:
            logger.warning("content_director[%s]: empty content response", _p)
            return None
        plan = parse_content_plan_response(raw, target_duration_sec)
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
