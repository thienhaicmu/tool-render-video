"""P2 smoke — part_voice_mix.run_part_voice_mix signature.

Per Track D D2 audit (followup_7), stages/part_voice_mix.py has
zero direct test consumers. The voice-mix block is conditionally
executed (only when voice_enabled=True); a kwarg rename would silently
skip the mix because the caller binds by name.

Also covered: the function returns None and mutates state by reference
(ctx.voice_part_tts_attempts, ctx.voice_mix_ok, part_manifest).

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import inspect


VOICE_MIX_PARAMS = {
    "ctx", "idx", "seg",
    "srt_part", "translated_srt_part",
    "final_part", "part_manifest",
}


class TestPartVoiceMixSurface:
    """Signature conformance for the voice/mix stage."""

    def test_run_part_voice_mix_signature(self):
        from app.orchestration.stages.part_voice_mix import run_part_voice_mix
        sig = inspect.signature(run_part_voice_mix)
        params = set(sig.parameters.keys())
        missing = VOICE_MIX_PARAMS - params
        assert not missing, (
            f"run_part_voice_mix missing expected params: {missing}."
        )

    def test_run_part_voice_mix_returns_none(self):
        """Side-effect only — must not return a value that callers
        could depend on. Documented in the module docstring.
        With `from __future__ import annotations`, the return annotation
        is the string 'None'."""
        from app.orchestration.stages.part_voice_mix import run_part_voice_mix
        sig = inspect.signature(run_part_voice_mix)
        assert sig.return_annotation == "None"

    def test_voice_mix_skipped_when_voice_disabled(self, tmp_path):
        """Behavioral smoke: with voice_enabled=False, the function
        returns without writing anything. Guards against a future
        refactor that mistakenly removes the early-return."""
        from unittest.mock import MagicMock
        from app.orchestration.stages.part_voice_mix import run_part_voice_mix

        ctx = MagicMock()
        ctx.payload.voice_enabled = False
        ctx.payload.reup_bgm_enable = False
        ctx.payload.subtitle_translate_enabled = False
        ctx.payload.translate_voice_path = None
        ctx.payload.video_codec = "libx264"
        ctx.payload.cleanup_temp_files = False
        ctx.voice_audio_path = None
        ctx.job_id = "j"
        ctx.effective_channel = "manual"
        ctx.cancel_registry.is_cancelled.return_value = False

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("s", encoding="utf-8")
        translated_srt = tmp_path / "p_t.srt"
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)
        part_manifest = MagicMock()

        # Should return cleanly — no exception, no return value.
        result = run_part_voice_mix(
            ctx=ctx, idx=1, seg={"start": 0.0, "end": 5.0, "duration": 5.0},
            srt_part=srt_part, translated_srt_part=translated_srt,
            final_part=final_part, part_manifest=part_manifest,
        )
        assert result is None
