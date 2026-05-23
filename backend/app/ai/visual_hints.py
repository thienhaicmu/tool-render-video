"""
visual_hints.py — AIVisualIntensityConfig: validated AI visual intensity hint.

Phase 5.6 visual injection point:
  [NOT FOUND: no safe visual intensity injection point exists — will log rejected]
  Investigation findings:
    render_part() and render_part_smart() in legacy_renderer.py accept effect_preset
    (a string like "slay_soft_01") which maps directly to an FFmpeg filter string
    via _effect_filter() in ffmpeg_helpers.py. There are no intermediate intensity
    level parameters (e.g. effect_level, effect_strength, visual_energy) that sit
    between the caller and the FFmpeg command. To change visual intensity, AI would
    need to either: (a) change effect_preset — which is payload.effect_preset
    (an explicit user-set field that must not be overridden), or (b) directly modify
    an FFmpeg filter string — which is forbidden by the AI render contract.
    render_base_clip() in base_clip_renderer.py has the same structure.
    Local variables in render_pipeline.py:
      - No _effect_intensity, _visual_energy, effect_level, visual_profile,
        effect_strength, or equivalent found.
      - _visual_trim is a bad-first-frame detection offset (seconds), not an
        artistic intensity control.
      - _dna_clean_visual is a bool signal for subtitle bias, not a render
        visual intensity parameter.
    _cinematic_color_filter() and _cinematic_sharpen_filter() accept content_type
    and src_h — these are content classification/source quality, not intensity levers.
    Content_type is resolved from payload.content_type (user field), not from AI hints.
  Safe because: no action taken — applied=False, render_overrides={}, decision logged.
  Not touching: effect_preset, effect_preset in payload, FFmpeg filter strings,
    _effect_filter(), _cinematic_color_filter(), _cinematic_sharpen_filter(),
    content_type, visual_trim, FFmpeg commands, audio, subtitles, timestamps,
    DB schema, API schema, websocket payloads.
  render_overrides = {} because no real existing parameters were found that could
  safely accept a visual intensity override without touching FFmpeg command strings.

Public API:
    AIVisualIntensityConfig               — dataclass result of build_ai_visual_intensity_config()
    build_ai_visual_intensity_config()    — build config from execution hints + optional payload
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Allowed visual intensity values — must match RenderExecutionHints contract.
_ALLOWED_VISUAL_INTENSITIES = frozenset({"low", "medium", "high"})

# Phase 5.6 decision: no safe injection point found.
# render_overrides must only contain keys that correspond to REAL existing
# parameters in render_pipeline.py / legacy_renderer.py / base_clip_renderer.py.
# Since no safe intensity parameters were found, render_overrides is always empty
# and applied is always False regardless of hint validity.
_NO_SAFE_INJECTION_POINT = True


# ── AIVisualIntensityConfig dataclass ─────────────────────────────────────────

@dataclass
class AIVisualIntensityConfig:
    """Validated visual intensity configuration derived from AI execution hints.

    Fields:
        enabled:              True if hints were present and processed.
        visual_intensity:     One of "low"/"medium"/"high" or None.
        source_knowledge_ids: IDs of knowledge items that contributed.
        applied:              True if the hint will actually influence rendering.
                              Always False in Phase 5.6 — no safe injection point.
        rejected_reason:      Reason hint was NOT applied (or None if applied).
        validation_fixups:    List of dicts describing any fixups applied.
        render_overrides:     Dict of render parameter overrides to apply.
                              Always {} in Phase 5.6 — no safe injection point.

    IMPORTANT (Phase 5.6): No safe visual intensity injection point was found.
    render_overrides is always {}. applied is always False.
    The hint is validated and logged as advisory only.
    See module docstring for full investigation details.
    """
    enabled: bool = False
    visual_intensity: Optional[str] = None
    source_knowledge_ids: list = field(default_factory=list)
    applied: bool = False
    rejected_reason: Optional[str] = None
    validation_fixups: list = field(default_factory=list)
    render_overrides: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "visual_intensity": self.visual_intensity,
            "source_knowledge_ids": list(self.source_knowledge_ids),
            "applied": self.applied,
            "rejected_reason": self.rejected_reason,
            "validation_fixups": [dict(f) for f in self.validation_fixups],
            "render_overrides": dict(self.render_overrides),
        }


# ── Public API ─────────────────────────────────────────────────────────────────

def build_ai_visual_intensity_config(
    execution_hints: Any,
    payload: Any = None,
) -> AIVisualIntensityConfig:
    """Build a validated AIVisualIntensityConfig from execution hints.

    Rules (NEVER raises):
    1. execution_hints is None or empty → AIVisualIntensityConfig(enabled=False)
    2. Accepts execution_hints as dict or RenderExecutionHints instance.
    3. If no visual_intensity in hints → applied=False,
       rejected_reason="no_visual_intensity_hint".
    4. If visual_intensity is not in allowed set → applied=False,
       rejected_reason="invalid_visual_intensity".
    5. If user has explicitly set effect_preset (non-default) → applied=False,
       rejected_reason="user_visual_override".
    6. Phase 5.6: No safe injection point found → applied=False,
       rejected_reason="no_safe_visual_injection_point", render_overrides={}.
    7. source_knowledge_ids preserved from hints.
    8. payload is inspected for user override detection only — never mutated.
    """
    try:
        return _build(execution_hints, payload)
    except Exception as exc:
        logger.warning("build_ai_visual_intensity_config: unexpected error: %s", exc)
        return AIVisualIntensityConfig(enabled=False)


# ── Internal helpers ───────────────────────────────────────────────────────────

# Default value of effect_preset in the render payload schema.
# Used to detect whether the user has explicitly changed the effect preset.
_DEFAULT_EFFECT_PRESET = "slay_soft_01"


def _build(execution_hints: Any, payload: Any) -> AIVisualIntensityConfig:
    """Core logic. May raise — wrapped by build_ai_visual_intensity_config."""
    # ── Step 1: Normalise hints to dict ──────────────────────────────────────
    raw: dict = _hints_to_dict(execution_hints)
    if not raw:
        return AIVisualIntensityConfig(enabled=False)

    # ── Step 2: Extract fields ────────────────────────────────────────────────
    visual_intensity_raw = raw.get("visual_intensity")
    source_ids = _parse_str_list(raw.get("source_knowledge_ids"))

    # ── Step 3: No visual_intensity → no hint ────────────────────────────────
    if visual_intensity_raw is None:
        return AIVisualIntensityConfig(
            enabled=True,
            visual_intensity=None,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="no_visual_intensity_hint",
        )

    # ── Step 4: Validate intensity value ─────────────────────────────────────
    visual_intensity = str(visual_intensity_raw).strip().lower()
    if visual_intensity not in _ALLOWED_VISUAL_INTENSITIES:
        return AIVisualIntensityConfig(
            enabled=True,
            visual_intensity=None,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="invalid_visual_intensity",
        )

    # ── Step 5: Check for user visual override ───────────────────────────────
    # If payload has an explicit (non-default) effect_preset, user wins.
    if _user_has_visual_override(payload):
        return AIVisualIntensityConfig(
            enabled=True,
            visual_intensity=visual_intensity,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="user_visual_override",
        )

    # ── Step 6: Phase 5.6 — no safe injection point found ────────────────────
    # Even though the hint is valid, we cannot safely apply it because no
    # existing render parameter accepts a visual intensity level without
    # bypassing renderer validation or editing FFmpeg command strings.
    # Document: render_overrides is intentionally empty.
    #
    # Future phases may find a safe injection point and set applied=True here.
    # When that happens, render_overrides should be populated with ONLY keys
    # that correspond to real existing parameters verified in code reading.
    if _NO_SAFE_INJECTION_POINT:
        return AIVisualIntensityConfig(
            enabled=True,
            visual_intensity=visual_intensity,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="no_safe_visual_injection_point",
            render_overrides={},
        )

    # ── Step 7: (Future) Build render_overrides ───────────────────────────────
    # This code path is currently unreachable because _NO_SAFE_INJECTION_POINT=True.
    # When a safe injection point is confirmed, set _NO_SAFE_INJECTION_POINT=False
    # and populate render_overrides with ONLY verified real parameter keys.
    render_overrides = _build_render_overrides(visual_intensity)
    return AIVisualIntensityConfig(
        enabled=True,
        visual_intensity=visual_intensity,
        source_knowledge_ids=source_ids,
        applied=True,
        rejected_reason=None,
        render_overrides=render_overrides,
    )


def _user_has_visual_override(payload: Any) -> bool:
    """Return True if the user has explicitly set a non-default effect_preset.

    Checks payload.effect_preset against the schema default ("slay_soft_01").
    If payload is None or effect_preset is absent, returns False (no override).
    """
    if payload is None:
        return False
    try:
        effect_preset = getattr(payload, "effect_preset", None)
        if effect_preset is None:
            # Try dict access
            if isinstance(payload, dict):
                effect_preset = payload.get("effect_preset")
        if effect_preset is None:
            return False
        return str(effect_preset).strip() != _DEFAULT_EFFECT_PRESET
    except Exception:
        return False


def _build_render_overrides(visual_intensity: str) -> dict:
    """Build render_overrides dict for a given visual intensity.

    NOTE (Phase 5.6): This function is currently unreachable because
    _NO_SAFE_INJECTION_POINT=True. The keys below are RESERVED for a future
    phase when a safe injection point is confirmed. They MUST NOT be used
    until they have been verified as real, existing render parameters.

    The mapping is documented here for reference only:
      "low"    → {"visual_energy": "low",    "effect_strength": "subtle"}
      "medium" → {"visual_energy": "medium", "effect_strength": "normal"}
      "high"   → {"visual_energy": "high",   "effect_strength": "strong"}

    Until a safe injection point is found, returns {} always.
    """
    # No real parameters found — return empty overrides.
    return {}


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
