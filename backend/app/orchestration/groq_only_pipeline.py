"""
groq_only_pipeline.py — Groq-only pre-render path (Phase B).

When payload.groq_only_mode=True, this module REPLACES run_pre_render_scenes().
Groq becomes the sole authority for segment selection — NO scene detection,
NO CLIP scoring, NO heuristic viral scoring, NO AI Director override.

HARD-FAIL semantics (intentional — distinct from AI-module Contract 3):
This is an ORCHESTRATION module, not an AI module. It MUST raise
GroqOnlyPipelineError on any failure. There is no fallback path — the user
explicitly opted into Groq-only mode and expects the job to fail loudly
rather than silently fall back to heuristic selection.

Sacred Contracts honoured:
  - Contract 4: only existing JobStage values used (TRANSCRIBING_FULL,
    SEGMENT_BUILDING). No new stage names introduced.
  - Contract 6: _emit_render_event signature unchanged.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.stage import JobStage
from app.orchestration.groq_stage import run_groq_segment_selection
from app.orchestration.pipeline_cache import (
    _transcription_cache_get,
    _transcription_cache_put,
)
from app.orchestration.render_events import _emit_render_event, _job_log, _safe_unlink
from app.services.db import update_job_progress
from app.services.subtitle_engine import has_audio_stream
from app.services.subtitle_transcription_adapters import transcribe_with_adapter

logger = logging.getLogger("app.render.groq_only")


@dataclass
class PreRenderScenesResult:
    """Pre-render result consumed by run_render_pipeline.

    Moved here from pipeline_pre_render.py in Phase F1 (legacy path removed).
    Field shape preserved for backward-compat with downstream consumers.
    """
    full_srt: Path
    full_srt_available: bool
    early_transcription_done: bool
    scored: list
    total_parts: int
    content_analysis: Any
    target_platform: str
    dna_clean_visual: bool
    early_retrieved_knowledge: list
    seg_min_sec: int
    seg_max_sec: int


class GroqOnlyPipelineError(RuntimeError):
    """HARD-FAIL — no fallback in groq_only_mode.

    Raised when any precondition fails or Groq cannot produce a usable
    segment list. Caller (render_pipeline.py) must propagate this upward
    to fail the job — there is no recovery path in groq_only_mode.
    """


def run_groq_only_pre_render(
    *,
    source_path: Path,
    source: dict,
    work_dir: Path,
    payload: Any,
    tuned: dict,
    job_id: str,
    effective_channel: str,
    retry_count: int,
    cancel_registry: Any,
    set_stage_fn: Callable[..., None],
) -> PreRenderScenesResult:
    """Groq-only replacement for run_pre_render_scenes().

    Raises:
        GroqOnlyPipelineError: any precondition or stage failure (HARD-FAIL).
        cancel_registry.JobCancelledError: job cancelled mid-flight.
    """
    # ── 1. Pre-flight validation (all 5 hard-fail conditions) ────────────
    if not getattr(payload, "groq_analysis_enabled", False):
        raise GroqOnlyPipelineError(
            "groq_only_mode=True requires groq_analysis_enabled=True"
        )
    if getattr(payload, "multi_variant", False):
        raise GroqOnlyPipelineError(
            "groq_only_mode incompatible with multi_variant "
            "(variant logic disabled in this path)"
        )
    from app.core import config as _cfg
    _payload_key = (getattr(payload, "ai_cloud_api_key", "") or "").strip()
    if not (_payload_key or getattr(_cfg, "GROQ_API_KEY", "")):
        raise GroqOnlyPipelineError(
            "groq_only_mode=True requires GROQ_API_KEY (env or ai_cloud_api_key field)"
        )
    if not has_audio_stream(str(source_path)):
        raise GroqOnlyPipelineError(
            "groq_only_mode=True requires source video with an audio stream"
        )
    if cancel_registry.is_cancelled(job_id):
        raise cancel_registry.JobCancelledError()

    full_srt = work_dir / f"{source['slug']}_full.srt"

    # ── 2. Transcription stage event ─────────────────────────────────────
    set_stage_fn(
        JobStage.TRANSCRIBING_FULL, 15,
        "Groq-only: transcribing for analysis",
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id,
        event="groq_only.transcription_started",
        level="INFO",
        message="Groq-only: starting Whisper transcription",
        step="render.groq_only.transcribe",
    )

    # ── 3. Whisper full transcription (with heartbeat + cache + resume) ──
    _resume_hit = (
        getattr(payload, "resume_from_last", False)
        and full_srt.exists()
        and full_srt.stat().st_size > 0
    )

    if _resume_hit:
        _job_log(
            effective_channel, job_id,
            "groq_only.transcription: resume hit, reusing existing SRT",
        )
    else:
        # For Groq/Gemini segment selection the SRT only needs to convey content,
        # not word-perfect transcription. Per-clip subtitles are transcribed
        # SEPARATELY in part_renderer.py with the higher-quality `small` model.
        # Override here keeps full-video Whisper fast; set GROQ_ONLY_WHISPER_MODEL
        # to "" (or the tuned default) to disable the override.
        import os as _os
        _model = (_os.getenv("GROQ_ONLY_WHISPER_MODEL", "tiny") or tuned["whisper_model"]).strip()
        _engine = getattr(payload, "subtitle_transcription_engine", "default")
        _cache_key = f"{_engine}_{int(bool(getattr(payload, 'highlight_per_word', False)))}"
        _cached = _transcription_cache_get(str(source_path), _model, _cache_key)
        if _cached is not None:
            import shutil
            shutil.copy2(str(_cached), str(full_srt))
            _job_log(
                effective_channel, job_id,
                f"groq_only.transcription: cache_hit model={_model}",
            )
        else:
            _t0 = time.perf_counter()
            _hb_stop = threading.Event()

            def _hb_fn(_stop=_hb_stop, _m=_model):
                _pct = 16
                while not _stop.wait(12):
                    _el = round(time.perf_counter() - _t0)
                    update_job_progress(
                        job_id, JobStage.TRANSCRIBING_FULL, _pct,
                        f"Groq-only: transcribing… ({_el}s)",
                    )
                    _pct = _pct + 1 if _pct < 22 else 22

            _hb = threading.Thread(
                target=_hb_fn, daemon=True,
                name=f"groq_only_transcribe_hb_{job_id[:8]}",
            )
            _hb.start()
            _job_log(
                effective_channel, job_id,
                f"groq_only.transcription_started model={_model}",
            )
            try:
                transcribe_with_adapter(
                    str(source_path), str(full_srt),
                    engine=_engine,
                    model_name=_model,
                    retry_count=retry_count,
                    highlight_per_word=getattr(payload, "highlight_per_word", False),
                    logger=logger,
                )
                _ms = int((time.perf_counter() - _t0) * 1000)
                if full_srt.exists() and full_srt.stat().st_size > 0:
                    _transcription_cache_put(str(source_path), _model, _cache_key, full_srt)
                _job_log(
                    effective_channel, job_id,
                    f"groq_only.transcription_done model={_model} elapsed_ms={_ms}",
                )
            except Exception as _exc:
                _safe_unlink(full_srt)
                _job_log(
                    effective_channel, job_id,
                    f"groq_only.transcription_failed: {_exc}",
                    kind="error",
                )
                raise GroqOnlyPipelineError(
                    f"groq_only_mode: Whisper transcription failed: {_exc}"
                ) from _exc
            finally:
                _hb_stop.set()
                _hb.join(timeout=2)

    # ── 4. Verify SRT not empty ──────────────────────────────────────────
    if not (full_srt.exists() and full_srt.stat().st_size > 0):
        raise GroqOnlyPipelineError(
            "groq_only_mode: SRT empty or missing after transcription"
        )

    # ── 5. Segment-selection stage event ─────────────────────────────────
    set_stage_fn(
        JobStage.SEGMENT_BUILDING, 25,
        "Groq-only: selecting segments",
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id,
        event="groq_only.selection_started",
        level="INFO",
        message="Groq-only: requesting segment selection from Groq",
        step="render.groq_only.select",
    )

    # ── 6. Call Groq via existing wrapper ────────────────────────────────
    scored = run_groq_segment_selection(
        full_srt=full_srt,
        full_srt_available=True,
        scored=[],
        payload=payload,
        source=source,
    )
    _min_score = float(getattr(payload, "groq_min_quality_score", 0.6))
    if scored is None:
        raise GroqOnlyPipelineError(
            f"groq_only_mode: Groq returned no usable segments "
            f"(min_quality_score={_min_score})"
        )
    if not scored:
        raise GroqOnlyPipelineError(
            f"groq_only_mode: Groq returned an empty segment list "
            f"(min_quality_score={_min_score})"
        )

    # ── 7. Bound-check segments against video duration ───────────────────
    video_dur = float(source.get("duration") or 0.0)
    bad = [
        s for s in scored
        if float(s.get("end", 0)) > video_dur + 0.5
        or float(s.get("start", 0)) < 0
    ]
    if bad:
        raise GroqOnlyPipelineError(
            f"groq_only_mode: {len(bad)} segments outside video duration "
            f"(video_duration={video_dur:.2f}s)"
        )

    # ── 8. Apply clip_exclude (mirror pipeline_pre_render.py 535-547) ────
    _clip_exclude = [
        x for x in (getattr(payload, "clip_exclude", None) or [])
        if isinstance(x, dict)
    ]
    if _clip_exclude:
        _before_ex = len(scored)

        def _in_exclude_range(seg, _ranges=_clip_exclude):
            s = float(seg.get("start", 0))
            e = float(seg.get("end", s + 1))
            return any(
                s < float(ex.get("end_sec", 0)) and e > float(ex.get("start_sec", 0))
                for ex in _ranges
            )

        scored = [seg for seg in scored if not _in_exclude_range(seg)]
        _job_log(
            effective_channel, job_id,
            f"groq_only.clip_exclude: {_before_ex - len(scored)} segments filtered "
            f"by {len(_clip_exclude)} excluded ranges",
        )
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id,
            event="clip_excluded", level="INFO",
            message=f"Groq-only clip_exclude: {_before_ex - len(scored)} segments removed",
            step="render.groq_only.steering",
            context={
                "excluded_ranges": len(_clip_exclude),
                "segments_removed": _before_ex - len(scored),
            },
        )
        if not scored:
            raise GroqOnlyPipelineError(
                "groq_only_mode: clip_exclude removed all Groq segments"
            )

    # ── 9. Apply clip_lock (mirror pipeline_pre_render.py 605-619) ───────
    _clip_lock = [
        x for x in (getattr(payload, "clip_lock", None) or [])
        if isinstance(x, dict)
    ]
    if _clip_lock:
        def _in_lock_range(seg, _ranges=_clip_lock):
            s = float(seg.get("start", 0))
            e = float(seg.get("end", s + 1))
            return any(
                s < float(lk.get("end_sec", 0)) and e > float(lk.get("start_sec", 0))
                for lk in _ranges
            )

        _locked = [seg for seg in scored if _in_lock_range(seg)]
        _unlocked = [seg for seg in scored if not _in_lock_range(seg)]
        scored = _locked + _unlocked
        _job_log(
            effective_channel, job_id,
            f"groq_only.clip_lock: {len(_locked)} segments promoted "
            f"by {len(_clip_lock)} locked ranges",
        )
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id,
            event="clip_locked", level="INFO",
            message=f"Groq-only clip_lock: {len(_locked)} segments promoted to front",
            step="render.groq_only.steering",
            context={
                "lock_ranges": len(_clip_lock),
                "segments_promoted": len(_locked),
            },
        )

    # ── 10. Emit selection-complete event ────────────────────────────────
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id,
        event="groq_only.selection_complete",
        level="INFO",
        message=f"Groq-only: {len(scored)} segments selected",
        step="render.groq_only.select",
        context={
            "segment_count": len(scored),
            "source": "groq",
            "min_quality_score": _min_score,
        },
    )

    # ── 11. Return PreRenderScenesResult (same shape as standard path) ───
    return PreRenderScenesResult(
        full_srt=full_srt,
        full_srt_available=True,
        early_transcription_done=True,
        scored=scored,
        total_parts=len(scored),
        content_analysis=None,
        target_platform=str(
            getattr(payload, "target_platform", "") or "youtube_shorts"
        ).lower(),
        dna_clean_visual=False,
        early_retrieved_knowledge=[],
        seg_min_sec=int(payload.min_part_sec),
        seg_max_sec=int(payload.max_part_sec),
    )
