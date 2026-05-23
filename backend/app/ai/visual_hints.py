"""
visual_hints.py — AIVisualIntensityConfig: validated AI visual intensity hint.

Phase 5.7 visual injection point:
  [FOUND: safe visual_intensity_hint parameter added to render_part(), render_part_smart(),
   and render_base_clip() in Phase 5.7. The renderer OWNS the mapping table.]

  Injection mechanism (Phase 5.7):
    AI passes visual_intensity_hint=<"low"|"medium"|"high"> to the renderer.
    The renderer calls resolve_effect_preset_with_intensity() which maps:
      "low"    → "story_clean_01"  (subtle, gentle processing)
      "medium" → "slay_soft_01"   (natural default, no change from schema default)
      "high"   → "slay_pop_01"    (energetic pop look)
    AI NEVER picks a preset name or FFmpeg filter string.
    The renderer OWNS the mapping table — mapping is in ffmpeg_helpers.py.
    User explicit effect_preset always wins (renderer enforces this via
    user_effect_is_explicit=True → returns original effect_preset unchanged).

  Phase 5.6 investigation findings (retained for history):
    render_part() and render_part_smart() in legacy_renderer.py accept effect_preset
    (a string like "slay_soft_01") which maps directly to an FFmpeg filter string
    via _effect_filter() in ffmpeg_helpers.py. There are no intermediate intensity
    level parameters (e.g. effect_level, effect_strength, visual_energy) that sit
    between the caller and the FFmpeg command.
    Phase 5.7 solution: added visual_intensity_hint as a NEW optional parameter
    (default None) that sits alongside effect_preset. The renderer resolves the
    effective preset from the hint before calling _effect_filter(). The original
    effect_preset argument is preserved for logging/metadata.

  Phase 5.7 render_overrides:
    render_overrides = {"visual_intensity_hint": <hint_value>} when applied=True.
    This contains ONLY the intensity level — not a preset name or FFmpeg string.
    The render_pipeline.py extracts this value and passes it to the renderer.

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

# Phase 5.7: safe injection point found.
# visual_intensity_hint parameter added to render_part(), render_part_smart(), and
# render_base_clip() with default None (backward compatible). Renderer OWNS the
# mapping from hint to effect preset — AI never picks a preset name directly.
# render_overrides now carries {"visual_intensity_hint": <value>} when applied=True.
# render_pipeline.py extracts this value and passes it to the renderer.
_NO_SAFE_INJECTION_POINT = False


# ── AIVisualIntensityConfig dataclass ─────────────────────────────────────────

@dataclass
class AIVisualIntensityConfig:
    """Validated visual intensity configuration derived from AI execution hints.

    Fields:
        enabled:              True if hints were present and processed.
        visual_intensity:     One of "low"/"medium"/"high" or None.
        source_knowledge_ids: IDs of knowledge items that contributed.
        applied:              True if the hint will actually influence rendering.
                              Now possible in Phase 5.7 — safe injection point found.
        rejected_reason:      Reason hint was NOT applied (or None if applied).
        validation_fixups:    List of dicts describing any fixups applied.
        render_overrides:     Dict of render parameter overrides to apply.
                              {"visual_intensity_hint": <value>} when applied=True.
                              {} when not applied.

    Phase 5.7: Safe injection point found.
    When applied=True: render_overrides={"visual_intensity_hint": <hint>}.
    The render_pipeline extracts this value and passes it to the renderer.
    The renderer OWNS the mapping from hint to effect preset.
    AI never picks a preset name or FFmpeg filter string.
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

    # ── Step 6: Phase 5.6 guard (now disabled in Phase 5.7) ──────────────────
    # _NO_SAFE_INJECTION_POINT=False in Phase 5.7: safe injection point confirmed.
    # visual_intensity_hint parameter added to render_part(), render_part_smart(),
    # and render_base_clip() — all with default None (fully backward compatible).
    # The renderer owns the mapping from hint to known effect presets.
    if _NO_SAFE_INJECTION_POINT:
        return AIVisualIntensityConfig(
            enabled=True,
            visual_intensity=visual_intensity,
            source_knowledge_ids=source_ids,
            applied=False,
            rejected_reason="no_safe_visual_injection_point",
            render_overrides={},
        )

    # ── Step 7: Build render_overrides (Phase 5.7) ───────────────────────────
    # render_overrides contains ONLY the intensity level — not a preset name
    # and not an FFmpeg filter string. The render_pipeline extracts this value
    # and passes it as visual_intensity_hint to the renderer. The renderer
    # calls resolve_effect_preset_with_intensity() which maps hint to preset.
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

    Phase 5.7: Returns {"visual_intensity_hint": <value>}.
    This key is a REAL existing parameter added to render_part(),
    render_part_smart(), and render_base_clip() in Phase 5.7.
    The render_pipeline extracts this value and passes it to the renderer.

    IMPORTANT: render_overrides MUST NOT contain:
      - Effect preset names (AI does not pick presets)
      - FFmpeg filter strings (AI never touches FFmpeg)
      - Any key that is not a verified real renderer parameter
    """
    return {"visual_intensity_hint": visual_intensity}


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
