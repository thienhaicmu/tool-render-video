"""
dna_engine.py — S2.6 Creator DNA Editing Memory.

Reads the creator_dna dict (computed by creator-dna.js on the frontend from
10–15+ sessions of repeated creator behavior) and applies conservative, bounded
soft biases to mode_config weights before clip selection.

Design:
  - No backend learning. Frontend snapshot always wins. DNA decay is natural:
    when creator changes behavior, the next request carries a fresh snapshot
    and the new weights take effect immediately (required change 2).
  - Confidence gate: dimension must reach >= _DNA_MIN_CONFIDENCE (0.55) before
    any influence fires. Below threshold → zero influence (required change 1).
  - suppressed_signals hard-block: if the frontend gated a signal, the backend
    absolutely does not apply it — no soft ignore (required change 4).
  - All adjustments are bounded [original * 0.90, original * 1.15].
  - CREATOR_DNA_ENABLED=0 disables entirely (rollback gate).

Creator intent ALWAYS wins. DNA is last-mile refinement:
  priority: user explicit settings → goal/style/format → creator DNA

Public API:
    apply_creator_dna(mode_config, creator_dna, goal) -> (dict, dict)
        Returns (evolved_mode_config_copy, creator_dna_applied_report).
        evolved_mode_config_copy is a new dict; original is never mutated.
        creator_dna_applied_report structure:
            {dimension: {"confidence": float, "effect": str}}
        Only dimensions that were actually applied are included.

    CREATOR_DNA_ENABLED: bool
"""
from __future__ import annotations

import os

CREATOR_DNA_ENABLED: bool = (
    os.environ.get("CREATOR_DNA_ENABLED", "1") == "1"
)

_DNA_MIN_CONFIDENCE: float = 0.55   # required change 1: was 0.40
_DNA_MAX_MULT: float = 1.15          # hard cap on weight increase
_DNA_MIN_MULT: float = 0.90          # hard floor on weight decrease

# Influence table: (dimension, mode_config_field, direction, max_delta_fraction)
#   direction +1.0 = increase the field, -1.0 = decrease the field
#   max_delta_fraction: at confidence=1.0, field is multiplied by (1 + direction * max_delta)
#
# hook_forward    → creator prefers strong hooks          → boost hook_weight
# clean_visual    → creator prefers clean, quiet editing  → reduce density weight,
#                   increase silence penalty (penalize noisy clips more)
# narrative_structure → creator prefers structured clips  → boost structure bonus scale
#
# retry_structure_scale is read by clip_selector on every pass (not just retry), so
# setting it here causes structure coherence to be weighted more heavily on pass 1
# for narrative-preferring creators.
_INFLUENCE_TABLE: list[tuple[str, str, float, float]] = [
    ("hook_forward",        "hook_weight",            +1.0, 0.10),
    ("clean_visual",        "speech_density_weight",  -1.0, 0.05),
    ("clean_visual",        "silence_penalty_weight", +1.0, 0.05),
    ("narrative_structure", "retry_structure_scale",  +1.0, 0.08),
]

# Primary reporting field per dimension — used for the effect string in the report.
_DIMENSION_PRIMARY_FIELD: dict[str, str] = {
    "hook_forward":        "hook_weight",
    "clean_visual":        "speech_density_weight",
    "narrative_structure": "retry_structure_scale",
}


def apply_creator_dna(
    mode_config: dict,
    creator_dna: dict,
    goal: str = "",
) -> tuple[dict, dict]:
    """Apply creator DNA biases to a copy of mode_config.

    Returns (evolved_copy, report) where:
      evolved_copy — mode_config dict with DNA-biased weight adjustments
      report       — per-dimension explainability dict (required change 3):
                     {dimension: {"confidence": float, "effect": str}}
                     Only includes dimensions that were actually applied.

    Graceful degradation:
      - CREATOR_DNA_ENABLED=False → returns (dict(mode_config), {})
      - creator_dna empty/None   → returns (dict(mode_config), {})
      - dimension below confidence threshold → skipped, not in report
      - dimension in suppressed_signals → hard-blocked, not in report
    """
    if not CREATOR_DNA_ENABLED:
        return dict(mode_config), {}
    if not creator_dna:
        return dict(mode_config), {}

    # required change 4: suppressed_signals is a hard block — no soft ignore.
    suppressed: set[str] = set(creator_dna.get("suppressed_signals", []) or [])

    evolved = dict(mode_config)
    # Track applied adjustments per dimension for the report.
    # {dimension: {field: (orig, new)}}
    _applied: dict[str, dict[str, tuple[float, float]]] = {}

    for dimension, field_key, direction, max_delta in _INFLUENCE_TABLE:
        # Hard block suppressed signals first (required change 4).
        if dimension in suppressed:
            continue

        confidence = float(creator_dna.get(dimension, 0.0) or 0.0)

        # Confidence gate (required change 1: threshold = 0.55).
        if confidence < _DNA_MIN_CONFIDENCE:
            continue

        # Field must exist in mode_config to be adjustable.
        if field_key not in evolved:
            continue

        # Linear strength: 0.0 at threshold, 1.0 at confidence=1.0.
        strength = (confidence - _DNA_MIN_CONFIDENCE) / max(0.001, 1.0 - _DNA_MIN_CONFIDENCE)
        strength = max(0.0, min(1.0, strength))

        orig = float(evolved[field_key])
        delta_mult = 1.0 + direction * max_delta * strength
        new_val = orig * delta_mult
        # Clamp to absolute bounds.
        new_val = max(orig * _DNA_MIN_MULT, min(orig * _DNA_MAX_MULT, new_val))
        evolved[field_key] = round(new_val, 4)

        if dimension not in _applied:
            _applied[dimension] = {}
        _applied[dimension][field_key] = (orig, new_val)

    report = _build_report(_applied, creator_dna, _DIMENSION_PRIMARY_FIELD)
    return evolved, report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_report(
    applied: dict[str, dict[str, tuple[float, float]]],
    creator_dna: dict,
    primary_fields: dict[str, str],
) -> dict:
    """Build structured explainability report (required change 3).

    Shape: {dimension: {"confidence": float, "effect": str}}
    Only dimensions where at least one field was adjusted are included.
    effect is the percentage change on the primary reporting field.
    """
    report: dict = {}
    for dimension, field_changes in applied.items():
        primary = primary_fields.get(dimension)
        if primary and primary in field_changes:
            orig, new_val = field_changes[primary]
        elif field_changes:
            # Fallback to first available field.
            orig, new_val = next(iter(field_changes.values()))
        else:
            continue

        pct = (new_val - orig) / max(abs(orig), 0.001) * 100
        sign = "+" if pct >= 0 else ""
        effect_str = f"{sign}{pct:.0f}%"

        report[dimension] = {
            "confidence": round(float(creator_dna.get(dimension, 0.0) or 0.0), 3),
            "effect": effect_str,
        }
    return report
