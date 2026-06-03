"""P2 smoke — PartRenderContext dataclass field integrity.

Per Track D D2 audit (followup_7 Finding 1), stages/part_render_context.py
has zero direct test consumers. The module exports the PartRenderContext
dataclass that all 8 stage helpers consume. A renamed field would
silently strand callers (the rest of part_renderer treats `ctx.X` as
optional via getattr in many places — a renamed field returns None).

Tests assert all documented fields exist on the dataclass.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses


# Fields documented in the PartRenderContext docstring + body.
EXPECTED_FIELDS = {
    # Job identity
    "job_id", "effective_channel", "total_parts", "retry_count",
    # I/O paths
    "work_dir", "output_dir", "source_path", "source", "output_stem",
    # Payload
    "payload",
    # Resume
    "existing_parts",
    # AI state
    "ai_edit_plan", "vis_intensity_hint",
    # Platform/render config
    "target_platform", "tuned", "ffmpeg_threads",
    # Cancel
    "cancel_registry",
    # Motion
    "src_stat_for_motion",
    # Subtitle
    "full_srt", "full_srt_available", "subtitle_enabled_by_idx", "subtitle_cutoff",
    # Voice
    "voice_audio_path",
    # Market/hook
    "mv_market", "mv_cfg", "hook_apply_enabled", "hook_applied_text",
    "hook_score", "hook_overlay_enabled",
    # AI subtitle
    "dna_clean_visual", "ai_subtitle_emphasis_config",
    # Text layers
    "normalized_text_layers",
    # Mutable shared lists
    "voice_part_tts_attempts", "voice_mix_ok",
    "sub_translate_attempts", "sub_translate_partial",
    "sub_translate_clean", "sub_translate_failed_parts",
    "recovery_notes",
}


class TestPartRenderContextDataclass:
    """Dataclass field-shape conformance for PartRenderContext."""

    def test_is_a_dataclass(self):
        from app.orchestration.stages.part_render_context import PartRenderContext
        assert dataclasses.is_dataclass(PartRenderContext)

    def test_all_expected_fields_present(self):
        from app.orchestration.stages.part_render_context import PartRenderContext
        actual = {f.name for f in dataclasses.fields(PartRenderContext)}
        missing = EXPECTED_FIELDS - actual
        assert not missing, (
            f"PartRenderContext missing expected fields: {missing}. "
            f"Renaming/removing a field silently breaks every stage "
            f"helper that reads ctx.<field>."
        )

    def test_mutable_shared_lists_have_default_factory(self):
        """The 7 mutable shared lists must use field(default_factory=list).
        A bare default would create a single shared list across instances —
        a subtle bug that corrupts cross-job state."""
        from app.orchestration.stages.part_render_context import PartRenderContext

        shared_list_fields = {
            "voice_part_tts_attempts", "voice_mix_ok",
            "sub_translate_attempts", "sub_translate_partial",
            "sub_translate_clean", "sub_translate_failed_parts",
            "recovery_notes",
        }
        for f in dataclasses.fields(PartRenderContext):
            if f.name in shared_list_fields:
                assert f.default_factory is list, (
                    f"Field {f.name!r} must use field(default_factory=list). "
                    f"Got default_factory={f.default_factory!r}, default={f.default!r}."
                )
