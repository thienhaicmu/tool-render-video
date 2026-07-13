"""
runmeta.py — config-vector snapshot for every accumulated sample (Sprint-1B).

Each measurement row records the FULL configuration that produced it, so the
accumulation store becomes an ablation DATABASE: any config-vs-config
comparison later is a query over existing rows instead of a fresh (quota-
costing) run.

Never raises; missing values recorded as defaults so old and new rows stay
comparable.
"""
from __future__ import annotations

import os
from typing import Any


# The env flags that change AI behaviour (the ablation axes). Values are read
# raw so the row reflects exactly what the process saw.
_FLAG_ENVS = (
    "RECAP_TWO_PASS",
    "RECAP_EDITORIAL_PASS",
    "RECAP_PER_EPISODE_NARRATION",
    "RECAP_DURATION_ANCHOR",
    "RECAP_TRIM_TO_BAND",
    "CLIP_STORY_INTELLIGENCE_DEFAULT",
    "RANKING_DETERMINISTIC_SPEECH_DENSITY",
    "CLIP_PROMPT_FOCUSED",
    "CLIP_DEDUP_IOU",
    "GEMINI_DEFAULT_MODEL",
    "GEMINI_STORY_MAX_TOKENS",
    "GEMINI_STORY_THINKING_BUDGET",
    # Story Mode v2 super-plan axes (P3-3).
    "STORY_AI_PROVIDER",
    "STORY_SUPER_MODEL",
    "OPENAI_STORY_JSON_SCHEMA",
    "OPENAI_STORY_PLAN_TEMPERATURE",
    "OPENAI_STORY_PLAN_MAX_TOKENS",
    "STORY_LIBRARY_PICK",
    "STORY_IDEA_LENGTH_FACTOR",
    "STORY_IDEA_DEFAULT_SEC",
)


def config_vector(**overrides: Any) -> dict:
    """Snapshot of the AI-behaviour config for one sample.

    ``overrides`` records values the runner FORCES per-arm (e.g. the recap
    editorial A/B toggles ``_RECAP_EDITORIAL_PASS`` in-process, so the env
    value alone would lie). Overrides win over env.
    """
    out: dict[str, Any] = {}
    try:
        for name in _FLAG_ENVS:
            out[name] = os.getenv(name, "")
    except Exception:
        pass
    try:
        from app.features.render.ai.llm.prompts import PROMPT_VERSION
        out["prompt_version"] = int(PROMPT_VERSION)
    except Exception:
        out["prompt_version"] = -1
    try:
        from app.domain.recap_plan import SCHEMA_VERSION, STORY_SCHEMA_VERSION
        out["recap_schema_version"] = int(SCHEMA_VERSION)
        out["story_schema_version"] = int(STORY_SCHEMA_VERSION)
    except Exception:
        pass
    for k, v in overrides.items():
        out[k] = v
    return out
