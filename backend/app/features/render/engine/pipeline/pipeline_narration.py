"""Render-pipeline narration stage â€” manual-mode AI voice TTS.

Sprint 6.D-1.4 â€” extracted verbatim from render_pipeline.py
(lines 406â€“483 of the pre-1.4 file). No logic changes; pure relocation.

Responsibilities:
  - When voice_enabled is True AND voice_source == "manual":
      * Generate a single narration audio file via generate_narration_audio()
        using subtitle_style as a creator-intent signal for content_type.
      * Run audio cleanup adapters via _maybe_cleanup_narration_audio.
      * On failure: log + emit voice_failed + recovery_success events,
        append a recovery note, and continue rendering without voice.

This function is invoked only when voice_source == "manual". The
auto/per-part TTS path is handled later inside the per-part render loop
(it lives in part_renderer.py, not here).

Why state-init stays in the caller:
  voice_audio_path, _voice_tts_failed, _voice_mix_ok, _voice_part_tts_attempts,
  _sub_translate_*, _recovery_notes are all forward-declared in run_render_pipeline
  because the per-part loop and downstream subtitle code append to them.
  We only extract the try/except that actually runs the manual TTS pass.

Sacred Contracts honored:
  - #3 AI module return-None contract: TTS module is a service, not under
       backend/app/ai/**. The try/except here swallows all exceptions and
       converts them to (None, voice_tts_failed=True) â€” equivalent guarantee.
  - #6 _emit_render_event signature: 3 call sites preserved verbatim
       (voice_tts_started, voice_tts_completed | voice_failed + recovery_success).
"""
from __future__ import annotations

import traceback
from typing import Optional, Tuple

from app.models.schemas import RenderRequest
from app.services import cancel_registry
from app.services.db import update_job_progress
from app.services.audio.tts import generate_narration_audio
from app.features.render.engine.pipeline.audio_cleanup import _maybe_cleanup_narration_audio
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log


def run_manual_voice_tts(
    *,
    payload: RenderRequest,
    job_id: str,
    effective_channel: str,
    current_stage: str,
    current_progress: int,
    recovery_notes: list,
) -> Tuple[Optional[str], bool]:
    """Run the manual-source AI voice TTS pass.

    Args:
        recovery_notes: mutable list â€” appended on failure so the caller
            sees the recovery note in the result_json payload.

    Returns:
        (voice_audio_path, voice_tts_failed)
        - voice_audio_path is str | None
        - voice_tts_failed is True if TTS raised, False otherwise

    Raises:
        cancel_registry.JobCancelledError â€” propagated to caller's outer
        try/except so the existing cancellation handling fires.
    """
    if not (
        getattr(payload, "voice_enabled", False)
        and getattr(payload, "voice_source", "manual") == "manual"
    ):
        return None, False

    if cancel_registry.is_cancelled(job_id):
        raise cancel_registry.JobCancelledError()

    voice_audio_path = None
    voice_tts_failed = False
    try:
        update_job_progress(job_id, current_stage, current_progress, "Generating AI voice...")
        _job_log(effective_channel, job_id, "Generating AI narration audio")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="voice_tts_started",
            level="INFO",
            message="Generating AI voice",
            step="voice.tts",
            context={"language": payload.voice_language, "gender": payload.voice_gender},
        )
        # Infer content type from subtitle_style since manual voice fires before
        # segment scoring. subtitle_style is the best available creator-intent signal.
        _manual_voice_ct = {
            "viral":   "commentary",
            "clean":   "tutorial",
            "story":   "vlog",
            "gaming":  "montage",
        }.get((payload.subtitle_style or "").strip().lower(), "vlog")
        voice_audio_path = generate_narration_audio(
            text=str(payload.voice_text or ""),
            language=payload.voice_language,
            gender=payload.voice_gender,
            rate=payload.voice_rate,
            job_id=job_id,
            voice_id=getattr(payload, "voice_id", None),
            content_type=_manual_voice_ct,
            tts_engine=getattr(payload, "tts_engine", "edge"),
        )
        update_job_progress(job_id, current_stage, current_progress, "AI voice generated")
        _job_log(effective_channel, job_id, f"AI narration audio ready: {voice_audio_path}")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="voice_tts_completed",
            level="INFO",
            message="AI voice generated",
            step="voice.tts",
            context={"audio_path": str(voice_audio_path), "voice_text_length": len(str(payload.voice_text or ""))},
        )
        voice_audio_path = _maybe_cleanup_narration_audio(
            str(voice_audio_path),
            payload,
            effective_channel=effective_channel,
            job_id=job_id,
            source="manual",
        )
    except Exception as voice_exc:
        voice_audio_path = None
        voice_tts_failed = True
        update_job_progress(job_id, current_stage, current_progress, "AI voice failed - continuing with original audio")
        _job_log(effective_channel, job_id, f"AI voice generation failed: {voice_exc}", kind="error")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="voice_failed",
            level="ERROR",
            message=f"AI voice generation failed: {voice_exc}",
            step="voice.tts",
            exception=voice_exc,
            traceback_text=traceback.format_exc(),
            context={"error_code": "VOICE001"},
        )
        # UP24: recovery â€” voice is optional, render continues without it
        recovery_notes.append("AI narration failed â€” rendered without voice")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="recovery_success",
            level="INFO",
            message="Recovery: AI narration failed, rendering without voice (original audio preserved)",
            step="voice.tts",
            context={"recovery_strategy": "skip_voice"},
        )

    return voice_audio_path, voice_tts_failed
