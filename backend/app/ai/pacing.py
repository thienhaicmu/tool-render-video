"""
pacing.py — AIPacingConfig: validated AI pacing hint to segment selection.

Phase 5.4 pacing injection point:
  render_pipeline.py line ~1654: SEGMENT_BUILDING stage begins.
  Local variables _seg_min_sec / _seg_max_sec are set before
  build_segments_from_scenes() (line ~1683) and reused in
  refine_segment_boundaries() (~line 2202) and refine_cuts_for_naturalness()
  (~line 2237).
  Safe because: only replaces local variables, never mutates payload, never
  mutates FFmpeg commands, clamped to safe range [1.0, 12.0], user explicit
  values always win.
  Not touching: FFmpeg commands, filter graphs, subtitle rendering, hook
  overlay logic, DB schema, API contracts, websocket payloads.

Public API:
    AIPacingConfig           — dataclass result of build_ai_pacing_config()
    build_ai_pacing_config() — build config from execution hints + payload
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Safe clamp range for cut intervals (seconds) ──────────────────────────────
# Mirrors the validator constraint in validators.py — defensive second layer.
_CUT_SAFE_MIN: float = 1.0
_CUT_SAFE_MAX: float = 12.0

# Payload defaults — if user hasn't changed these, AI may override.
# Must match schemas.py: min_part_sec=15, max_part_sec=60.
_PAYLOAD_DEFAULT_MIN: int = 15
_PAYLOAD_DEFAULT_MAX: int = 60


# ── AIPacingConfig dataclass ───────────────────────────────────────────────────

@dataclass
class AIPacingConfig:
    """Validated pacing configuration derived from AI execution hints.

    Fields:
        enabled:              True if hints were present and processed.
        cut_interval_min:     Minimum segment duration hint (seconds) or None.
        cut_interval_max:     Maximum segment duration hint (seconds) or None.
        source_knowledge_ids: IDs of knowledge items that contributed.
        applied:              True if pacing will actually influence segment selection.
        rejected_reason:      Reason pacing was NOT applied (or None if applied).
        validation_fixups:    List of dicts describing any fixups applied.
    """
    enabled: bool = False
    cut_interval_min: Optional[float] = None
    cut_interval_max: Optional[float] = None
    source_knowledge_ids: list = field(default_factory=list)
    applied: bool = False
    rejected_reason: Optional[str] = None
    validation_fixups: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "cut_interval_min": self.cut_interval_min,
            "cut_interval_max": self.cut_interval_max,
            "source_knowledge_ids": list(self.source_knowledge_ids),
            "applied": self.applied,
            "rejected_reason": self.rejected_reason,
            "validation_fixups": [dict(f) for f in self.validation_fixups],
        }


# ── Public API ─────────────────────────────────────────────────────────────────

def build_ai_pacing_config(
    execution_hints: Any,
    payload: Any = None,
) -> AIPacingConfig:
    """Build a validated AIPacingConfig from execution hints and optional payload.

    Rules (NEVER raises):
    1. execution_hints is None or empty → AIPacingConfig(enabled=False)
    2. Accepts execution_hints as dict or RenderExecutionHints instance.
    3. If both cut_interval_min and cut_interval_max are None → applied=False,
       rejected_reason="no_pacing_hint".
    4. If payload has explicit min_part_sec/max_part_sec (non-None, non-zero,
       different from schema defaults) → user wins → rejected_reason=
       "user_duration_override", applied=False.
    5. Clamp values to [1.0, 12.0] defensively.
    6. If min > max → swap, record fixup.
    7. If user has no explicit duration limits → applied=True.
    8. source_knowledge_ids preserved from hints.
    """
    try:
        return _build(execution_hints, payload)
    except Exception as exc:
        logger.warning("build_ai_pacing_config: unexpected error: %s", exc)
        return AIPacingConfig(enabled=False)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build(execution_hints: Any, payload: Any) -> AIPacingConfig:
    """Core logic. May raise — wrapped by build_ai_pacing_config."""
    # ── Step 1: Normalise hints to dict ──────────────────────────────────────
    raw: dict = _hints_to_dict(execution_hints)
    if not raw:
        return AIPacingConfig(enabled=False)

    # ── Step 2: Extract fields ────────────────────────────────────────────────
    cut_min_raw = raw.get("cut_interval_min")
    cut_max_raw = raw.get("cut_interval_max")
    source_ids = _parse_str_list(raw.get("source_knowledge_ids"))

    cut_min = _parse_float(cut_min_raw)
    cut_max = _parse_float(cut_max_raw)

    # ── Step 3: Both None → no pacing hint ───────────────────────────────────
    if cut_min is None and cut_max is None:
        return AIPacingConfig(
            enabled=True,
            cut_interval_min=None,
            cut_interval_max=None,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="no_pacing_hint",
        )

    # ── Step 4: Defensive clamp to safe range ─────────────────────────────────
    fixups: list[dict] = []

    if cut_min is not None:
        clamped = _clamp(cut_min, _CUT_SAFE_MIN, _CUT_SAFE_MAX)
        if clamped != cut_min:
            fixups.append({
                "field": "cut_interval_min",
                "original": cut_min,
                "action": "clamped",
                "result": clamped,
            })
        cut_min = clamped

    if cut_max is not None:
        clamped = _clamp(cut_max, _CUT_SAFE_MIN, _CUT_SAFE_MAX)
        if clamped != cut_max:
            fixups.append({
                "field": "cut_interval_max",
                "original": cut_max,
                "action": "clamped",
                "result": clamped,
            })
        cut_max = clamped

    # ── Step 5: Enforce min <= max ────────────────────────────────────────────
    if cut_min is not None and cut_max is not None and cut_min > cut_max:
        fixups.append({
            "field": "cut_interval_min/max",
            "original": {"min": cut_min, "max": cut_max},
            "action": "swapped_inverted_range",
            "result": {"min": cut_max, "max": cut_min},
        })
        cut_min, cut_max = cut_max, cut_min

    # ── Step 6: User explicit override check ──────────────────────────────────
    if _user_has_explicit_duration(payload):
        return AIPacingConfig(
            enabled=True,
            cut_interval_min=cut_min,
            cut_interval_max=cut_max,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="user_duration_override",
            validation_fixups=fixups,
        )

    # ── Step 7: All checks passed → apply ────────────────────────────────────
    return AIPacingConfig(
        enabled=True,
        cut_interval_min=cut_min,
        cut_interval_max=cut_max,
        source_knowledge_ids=source_ids,
        applied=True,
        rejected_reason=None,
        validation_fixups=fixups,
    )


def _hints_to_dict(execution_hints: Any) -> dict:
    """Normalise execution_hints to a plain dict. Never raises."""
    if execution_hints is None:
        return {}
    # RenderExecutionHints instance → use to_dict()
    if hasattr(execution_hints, "to_dict"):
        try:
            d = execution_hints.to_dict()
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    # Plain dict
    if isinstance(execution_hints, dict):
        return dict(execution_hints)
    # Anything else → empty
    return {}


def _user_has_explicit_duration(payload: Any) -> bool:
    """Return True if user explicitly set min_part_sec or max_part_sec
    to non-default, non-zero values (user intent overrides AI).

    Schema defaults: min_part_sec=15, max_part_sec=60.
    If user set values equal to defaults → treat as "not explicitly set" (AI may override).
    """
    if payload is None:
        return False
    try:
        min_val = getattr(payload, "min_part_sec", None)
        max_val = getattr(payload, "max_part_sec", None)

        min_explicit = (
            min_val is not None
            and min_val != 0
            and int(min_val) != _PAYLOAD_DEFAULT_MIN
        )
        max_explicit = (
            max_val is not None
            and max_val != 0
            and int(max_val) != _PAYLOAD_DEFAULT_MAX
        )
        return min_explicit or max_explicit
    except Exception:
        return False


def _parse_float(value: Any) -> Optional[float]:
    """Return float or None. Never raises."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


def _parse_str_list(value: Any) -> list:
    """Return list of strings or empty list. Never raises."""
    if value is None:
        return []
    if isinstance(value, list):
        try:
            return [str(v) for v in value if v is not None]
        except Exception:
            return []
    return []
