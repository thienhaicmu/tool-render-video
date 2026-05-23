"""
subtitle_hints.py — AISubtitleEmphasisConfig: validated AI subtitle emphasis hint.

Phase 5.5 subtitle injection point:
  render_pipeline.py line ~3612: subtitle_emphasis_pass() call in the per-part
  subtitle processing block (inside `for idx, seg in enumerate(scored, start=1):`
  loop at line 3073, inside `if part_subtitle_enabled:` at line 3307, inside
  `if _srt_source_is_fresh and _ass_srt_source.exists():` guard at line 3612).
  The AI hint is applied by passing emphasis_level_override to subtitle_emphasis_pass().
  Safe because: only influences text emphasis level (uppercase/markers), never
  alters SRT timestamps, never creates new ASS preset IDs, never touches
  FFmpeg commands. The _effective_subtitle_style (preset ID) used for ASS
  generation is NOT changed — only the emphasis level used inside
  subtitle_emphasis_pass() changes when AI hint is applied.
  Not touching: srt_to_ass_bounce/karaoke, FFmpeg filter graph, SRT timestamps,
  _effective_subtitle_style resolution hierarchy, payload fields, DB schema,
  API contracts, websocket payloads.
  Timing safety: subtitle timing (start/end seconds in SRT) is owned by
  slice_srt_by_time() and resegment_srt_for_readability(). subtitle_emphasis_pass()
  modifies only b['text'] — never b['start'] or b['end']. The AI hint is
  passed only to subtitle_emphasis_pass(), so timing is guaranteed unchanged.

Public API:
    AISubtitleEmphasisConfig           — dataclass result of build_ai_subtitle_emphasis_config()
    build_ai_subtitle_emphasis_config() — build config from execution hints + optional payload
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Allowed emphasis style values — must match RenderExecutionHints contract.
_ALLOWED_EMPHASIS_STYLES = frozenset({"subtle", "medium", "strong", "word_only"})


# ── AISubtitleEmphasisConfig dataclass ────────────────────────────────────────

@dataclass
class AISubtitleEmphasisConfig:
    """Validated subtitle emphasis configuration derived from AI execution hints.

    Fields:
        enabled:              True if hints were present and processed.
        emphasis_style:       One of "subtle"/"medium"/"strong"/"word_only" or None.
        source_knowledge_ids: IDs of knowledge items that contributed.
        applied:              True if the hint will actually influence emphasis.
        rejected_reason:      Reason emphasis was NOT applied (or None if applied).
        validation_fixups:    List of dicts describing any fixups applied.

    IMPORTANT: This config MUST NOT produce a new subtitle style ID.
    It only affects emphasis behavior inside subtitle_emphasis_pass().
    The _effective_subtitle_style (preset ID) used for ASS generation is unchanged.
    """
    enabled: bool = False
    emphasis_style: Optional[str] = None
    source_knowledge_ids: list = field(default_factory=list)
    applied: bool = False
    rejected_reason: Optional[str] = None
    validation_fixups: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "emphasis_style": self.emphasis_style,
            "source_knowledge_ids": list(self.source_knowledge_ids),
            "applied": self.applied,
            "rejected_reason": self.rejected_reason,
            "validation_fixups": [dict(f) for f in self.validation_fixups],
        }


# ── Public API ─────────────────────────────────────────────────────────────────

def build_ai_subtitle_emphasis_config(
    execution_hints: Any,
    payload: Any = None,
) -> AISubtitleEmphasisConfig:
    """Build a validated AISubtitleEmphasisConfig from execution hints.

    Rules (NEVER raises):
    1. execution_hints is None or empty → AISubtitleEmphasisConfig(enabled=False)
    2. Accepts execution_hints as dict or RenderExecutionHints instance.
    3. If no subtitle_emphasis_style in hints → applied=False,
       rejected_reason="no_subtitle_emphasis_hint".
    4. If subtitle_emphasis_style is not in allowed set → applied=False,
       rejected_reason="invalid_emphasis_style".
    5. If style is valid → applied=True.
    6. source_knowledge_ids preserved from hints.
    7. payload is accepted for future user override checks (not used yet).
    """
    try:
        return _build(execution_hints, payload)
    except Exception as exc:
        logger.warning("build_ai_subtitle_emphasis_config: unexpected error: %s", exc)
        return AISubtitleEmphasisConfig(enabled=False)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build(execution_hints: Any, payload: Any) -> AISubtitleEmphasisConfig:
    """Core logic. May raise — wrapped by build_ai_subtitle_emphasis_config."""
    # ── Step 1: Normalise hints to dict ──────────────────────────────────────
    raw: dict = _hints_to_dict(execution_hints)
    if not raw:
        return AISubtitleEmphasisConfig(enabled=False)

    # ── Step 2: Extract fields ────────────────────────────────────────────────
    emphasis_style_raw = raw.get("subtitle_emphasis_style")
    source_ids = _parse_str_list(raw.get("source_knowledge_ids"))

    # ── Step 3: No emphasis style → no hint ───────────────────────────────────
    if emphasis_style_raw is None:
        return AISubtitleEmphasisConfig(
            enabled=True,
            emphasis_style=None,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="no_subtitle_emphasis_hint",
        )

    # ── Step 4: Validate style value ─────────────────────────────────────────
    emphasis_style = str(emphasis_style_raw).strip().lower()
    if emphasis_style not in _ALLOWED_EMPHASIS_STYLES:
        return AISubtitleEmphasisConfig(
            enabled=True,
            emphasis_style=None,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="invalid_emphasis_style",
        )

    # ── Step 5: All checks passed → apply ────────────────────────────────────
    return AISubtitleEmphasisConfig(
        enabled=True,
        emphasis_style=emphasis_style,
        source_knowledge_ids=source_ids,
        applied=True,
        rejected_reason=None,
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
    # Anything else (list, int, str, etc.) → empty
    return {}


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
