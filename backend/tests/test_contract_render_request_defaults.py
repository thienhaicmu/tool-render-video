"""P3 Contract #2 — RenderRequest new-field defaults conformance.

Per CLAUDE.md Sacred Contract #2:

  Every new field added to `RenderRequest` in `schemas.py` MUST default
  to `False` or the most conservative disabled state possible.

Rationale: RenderRequest is deserialized from stored job records and
from API payloads that predate the new field. If a new field defaults
to True (or any active/enabled state), every existing stored job that
never explicitly set it will silently activate the new behavior on
replay, retry, or history view.

This conformance test guards against future regressions by enforcing
that every bool field on RenderRequest defaults to False UNLESS it
appears in GRANDFATHERED_TRUE_DEFAULTS — a small allowlist of long-
standing baseline-behavior flags whose True default predates the
contract. Adding any new bool that defaults to True requires a
conscious entry in the allowlist with a justification comment.

See docs/review/AUDIT_2026-06-02_followup_11.md for the closure record.
"""
from __future__ import annotations

import pytest


# Allowlist: bool fields that ship with default=True and are NOT new fields.
# Each entry pre-dates Sacred Contract #2 and represents baseline behavior
# (subtitles on, motion crop on, loudnorm on, etc.). Adding to this list
# requires a conscious decision documented in the code review.
GRANDFATHERED_TRUE_DEFAULTS = {
    "cleanup_temp_files",     # delete temp/cache after job — long-standing default
    "auto_detect_scene",      # scene detection is the default segmentation mode
    "add_subtitle",           # subtitles on by default — core product behavior
    "motion_aware_crop",      # default cropping mode — long-standing
    "loudnorm_enabled",       # audio loudness normalization — long-standing
    "reup_overlay_enable",    # reup overlay default-on when reup_mode is used
}


class TestRenderRequestDefaults:
    """Sacred Contract #2 — additive-only RenderRequest field defaults."""

    def test_all_bool_fields_default_to_false_or_grandfathered(self):
        """Every bool field on RenderRequest must default to False
        UNLESS it's in the grandfathered allowlist. Adding a new bool
        that defaults to True triggers this failure with the field
        name + remediation guidance."""
        from app.models.schemas import RenderRequest

        # Pydantic v2: model_fields is the canonical field map.
        violations: list[tuple[str, bool]] = []
        for name, info in RenderRequest.model_fields.items():
            # Only check fields annotated as bool (not Optional[bool], not int).
            if info.annotation is not bool:
                continue
            default = info.default
            if default is True and name not in GRANDFATHERED_TRUE_DEFAULTS:
                violations.append((name, default))

        assert not violations, (
            "Contract #2 violation — new bool field(s) default to True:\n"
            + "\n".join(f"  - {name}: default={default}" for name, default in violations)
            + "\n\nRemediation: change the default to False, OR add the field "
              "name to GRANDFATHERED_TRUE_DEFAULTS with a justification "
              "comment in test_contract_render_request_defaults.py. "
              "Stored job records that omit the field will otherwise "
              "silently activate the new behavior on replay."
        )

    def test_grandfathered_list_only_contains_actual_fields(self):
        """Sanity check: the allowlist refers to real fields. A typo
        would silently weaken the test. If a grandfathered field is
        removed from RenderRequest, this catches it."""
        from app.models.schemas import RenderRequest

        actual_field_names = set(RenderRequest.model_fields.keys())
        ghost_entries = GRANDFATHERED_TRUE_DEFAULTS - actual_field_names
        assert not ghost_entries, (
            f"GRANDFATHERED_TRUE_DEFAULTS contains entries that are no "
            f"longer fields on RenderRequest: {ghost_entries}. "
            f"Remove them from the allowlist."
        )

    def test_grandfathered_fields_actually_default_to_true(self):
        """Sanity check: every grandfathered field IS bool=True. If a
        field was flipped to False, the allowlist entry is dead weight."""
        from app.models.schemas import RenderRequest

        for name in GRANDFATHERED_TRUE_DEFAULTS:
            info = RenderRequest.model_fields[name]
            assert info.annotation is bool, (
                f"Grandfathered field {name!r} should be annotated as "
                f"bool, got {info.annotation!r}."
            )
            assert info.default is True, (
                f"Grandfathered field {name!r} no longer defaults to True "
                f"(default={info.default!r}). Remove it from "
                f"GRANDFATHERED_TRUE_DEFAULTS."
            )

    def test_known_safe_features_default_to_false(self):
        """Spot-check that key feature-gate flags follow the contract.
        If a refactor flips any of these to True by accident, jobs
        replayed from history would auto-activate the feature."""
        from app.models.schemas import RenderRequest

        # These are explicitly listed in CLAUDE.md / Sprint 3 3E commentary
        # as fields that MUST stay False per Contract 2.
        sensitive_defaults_false = {
            "ai_director_enabled",        # removed in Phase G — must stay False
            "ai_auto_cut",                # Subset B flip 2026-06-02
            "ai_use_semantic_hooks",      # Subset B flip
            "ai_render_influence_enabled",# Subset B flip
            "ai_beat_pulse_enabled",      # Subset B flip
            "hook_apply_enabled",         # Subset B flip
            "hook_overlay_enabled",       # Subset B flip
            "voice_enabled",              # opt-in narration
            "multi_variant",              # opt-in multi-output
            "subtitle_translate_enabled", # opt-in translation
            "groq_only_mode",             # explicit opt-in (no fallback)
        }
        for name in sensitive_defaults_false:
            info = RenderRequest.model_fields[name]
            assert info.default is False, (
                f"Contract #2 sensitive default: {name!r} must be False, "
                f"got {info.default!r}."
            )
