"""
execution_mode_engine.py — Phase 60D AI Execution Modes & Rollback.

Control-only module. Resolves the effective AI execution mode from the
payload, environment variable, or app default. Returns deterministic
policy metadata used to gate Phase 59 promotion calls in the pipeline.

NO render mutation.  NO new AI behavior.  NO executor override.
Controls ONLY whether and how much existing Phase 59 influence is allowed.

Supported modes
---------------
    off        — Block all AI execution promotion. Advisory metadata allowed.
    safe       — Conservative influence. Confidence thresholds raised.
    balanced   — Default production behavior. Standard Phase 59 thresholds.
    aggressive — Slightly lower thresholds. All hard caps and quality gates
                 still enforced. Never bypasses safety.

Mode source priority
--------------------
    1. payload field  ``ai_execution_mode``
    2. environment var ``AI_EXECUTION_MODE``
    3. app default     ``safe``

Invalid values fall back to ``safe`` with source="*_invalid_fallback".

Public API
----------
    resolve_execution_mode(payload=None, context=None) -> dict
    get_mode_policy(mode) -> dict

Output shape
------------
    {
        "ai_execution_mode": {
            "mode":            "balanced",
            "source":          "payload",
            "effective_mode":  "balanced",
            "allowed_domains": ["subtitle", "camera", "segment"],
            "confidence_policy": {
                "subtitle_threshold_delta": 0.0,
                "camera_threshold_delta":   0.0,
                "segment_threshold_delta":  0.0
            },
            "rollback_safe": false,
            "reasoning": ["Mode=balanced: standard Phase 59 influence with normal thresholds."]
        }
    }

Fallback output (on any exception)
-----------------------------------
    {
        "ai_execution_mode": {
            "mode":            "safe",
            "source":          "default",
            "effective_mode":  "safe",
            "allowed_domains": [],
            "confidence_policy": {
                "subtitle_threshold_delta": 0.05,
                "camera_threshold_delta":   0.08,
                "segment_threshold_delta":  0.10
            },
            "rollback_safe": true,
            "reasoning": []
        }
    }

Safety contract
---------------
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No executor override
    ✅ Deterministic: same inputs → same output
    ✅ Reads payload/env only — no side effects
    ✅ Returns fallback on any error
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("app.ai.execution_mode")

# ---------------------------------------------------------------------------
# Mode constants
# ---------------------------------------------------------------------------
_DEFAULT_MODE: str = "safe"
_VALID_MODES: frozenset[str] = frozenset({"off", "safe", "balanced", "aggressive"})
_ENV_VAR: str = "AI_EXECUTION_MODE"

# ---------------------------------------------------------------------------
# Per-mode confidence threshold deltas
# Positive delta = raise threshold (more conservative / harder to apply).
# Negative delta = lower threshold (more permissive).
# ---------------------------------------------------------------------------
_MODE_THRESHOLD_DELTAS: dict[str, dict[str, float]] = {
    "off":        {"subtitle": 0.0,   "camera": 0.0,   "segment": 0.0},
    "safe":       {"subtitle": 0.05,  "camera": 0.08,  "segment": 0.10},
    "balanced":   {"subtitle": 0.0,   "camera": 0.0,   "segment": 0.0},
    "aggressive": {"subtitle": -0.03, "camera": -0.03, "segment": -0.05},
}

# ---------------------------------------------------------------------------
# Domains allowed per mode (empty = no promotion allowed)
# ---------------------------------------------------------------------------
_MODE_ALLOWED_DOMAINS: dict[str, list[str]] = {
    "off":        [],
    "safe":       ["subtitle", "camera", "segment"],
    "balanced":   ["subtitle", "camera", "segment"],
    "aggressive": ["subtitle", "camera", "segment"],
}

# rollback_safe: True = mode prevents/limits AI from mutating render behavior
_MODE_ROLLBACK_SAFE: dict[str, bool] = {
    "off":        True,   # strongest rollback — no AI promotion at all
    "safe":       True,   # conservative — near-baseline
    "balanced":   False,  # normal production AI influence
    "aggressive": False,  # more permissive AI influence
}

_MODE_REASONING: dict[str, str] = {
    "off":        "Mode=off: all AI execution promotion blocked; advisory metadata allowed.",
    "safe":       "Mode=safe: conservative influence only; confidence thresholds raised.",
    "balanced":   "Mode=balanced: standard Phase 59 influence with normal thresholds.",
    "aggressive": "Mode=aggressive: slightly lowered thresholds; hard caps and quality gates still enforced.",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_execution_mode(
    payload: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Resolve effective AI execution mode and return policy metadata.

    Returns:
        {"ai_execution_mode": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _resolve(payload, job_id)
    except Exception as exc:
        logger.warning("execution_mode_unexpected_error job_id=%s: %s", job_id, exc)
        return _fallback_mode()


def get_mode_policy(mode: str) -> dict:
    """Return policy dict for a given mode. Returns safe policy for unknown modes."""
    if mode not in _VALID_MODES:
        mode = _DEFAULT_MODE
    return {
        "mode":               mode,
        "rollback_safe":      _MODE_ROLLBACK_SAFE[mode],
        "blocks_promotion":   mode == "off",
        "threshold_deltas":   _MODE_THRESHOLD_DELTAS[mode],
        "allowed_domains":    _MODE_ALLOWED_DOMAINS[mode],
    }


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------

def _resolve(payload: Any, job_id: str) -> dict:
    # Priority 1: explicit payload field
    mode, source = _from_payload(payload)

    # Priority 2: environment variable
    if mode is None:
        mode, source = _from_env()

    # Priority 3: app default
    if mode is None:
        mode = _DEFAULT_MODE
        source = "default"

    deltas = _MODE_THRESHOLD_DELTAS[mode]

    logger.info(
        "execution_mode_resolved job_id=%s mode=%s source=%s rollback_safe=%s",
        job_id, mode, source, _MODE_ROLLBACK_SAFE[mode],
    )

    return {
        "ai_execution_mode": {
            "mode":           mode,
            "source":         source,
            "effective_mode": mode,
            "allowed_domains": list(_MODE_ALLOWED_DOMAINS[mode]),
            "confidence_policy": {
                "subtitle_threshold_delta": deltas["subtitle"],
                "camera_threshold_delta":   deltas["camera"],
                "segment_threshold_delta":  deltas["segment"],
            },
            "rollback_safe": _MODE_ROLLBACK_SAFE[mode],
            "reasoning":     [_MODE_REASONING[mode]],
        }
    }


# ---------------------------------------------------------------------------
# Source extractors
# ---------------------------------------------------------------------------

def _from_payload(payload: Any) -> tuple[Optional[str], str]:
    """Extract mode from payload.ai_execution_mode field."""
    if payload is None:
        return None, "default"
    try:
        val = (
            payload.get("ai_execution_mode")
            if isinstance(payload, dict)
            else getattr(payload, "ai_execution_mode", None)
        )
        if val is None:
            return None, "default"
        mode = str(val).lower().strip()
        if mode in _VALID_MODES:
            return mode, "payload"
        logger.warning(
            "execution_mode_invalid_payload_value raw=%r → fallback=%s", val, _DEFAULT_MODE
        )
        return _DEFAULT_MODE, "payload_invalid_fallback"
    except Exception:
        return None, "default"


def _from_env() -> tuple[Optional[str], str]:
    """Extract mode from AI_EXECUTION_MODE environment variable."""
    raw = os.environ.get(_ENV_VAR, "").strip().lower()
    if not raw:
        return None, "default"
    if raw in _VALID_MODES:
        return raw, "env"
    logger.warning(
        "execution_mode_invalid_env_value raw=%r → fallback=%s", raw, _DEFAULT_MODE
    )
    return _DEFAULT_MODE, "env_invalid_fallback"


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_mode() -> dict:
    """Ultra-conservative fallback on unexpected errors: safe mode, no domains."""
    deltas = _MODE_THRESHOLD_DELTAS[_DEFAULT_MODE]
    return {
        "ai_execution_mode": {
            "mode":           _DEFAULT_MODE,
            "source":         "default",
            "effective_mode": _DEFAULT_MODE,
            "allowed_domains": [],            # conservative: empty on exception
            "confidence_policy": {
                "subtitle_threshold_delta": deltas["subtitle"],
                "camera_threshold_delta":   deltas["camera"],
                "segment_threshold_delta":  deltas["segment"],
            },
            "rollback_safe": True,
            "reasoning":     [],
        }
    }
