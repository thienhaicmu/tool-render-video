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
    # ── 1. Pre-flight validation ──────────────────────────────────────────
    if not getattr(payload, "groq_analysis_enabled", False):
        # Phase F1: pipeline is now mandatory for all jobs. This guard was written
        # for the old optional-mode path. Old stored jobs and misconfigured clients
        # can arrive with groq_analysis_enabled=False; failing them is wrong.
        logger.warning(
            "groq_only_pipeline: groq_analysis_enabled=False — continuing anyway "
            "(pipeline is mandatory since Phase F1; check GROQ_ONLY_DEFAULT env var)"
        )
    if getattr(payload, "multi_variant", False):
        # multi_variant requires a separate rendering pass not implemented here.
        # Degrade to single-variant rather than failing the job outright.
        _job_log(
            effective_channel, job_id,
            "multi_variant requested but not supported in groq_only path — "
            "rendering single variant (set multi_variant=False to suppress this warning)",
            kind="warning",
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="groq_only.multi_variant_degraded",
            level="WARNING",
            message="multi_variant not supported in groq_only path — using single variant",
            step="render.groq_only.preflight",
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
        # SEPARATELY in part_renderer.py with the higher-quality `small` model
        # so subtitle quality is untouched.
        #
        # Default `base`: sweet spot for Vietnamese — ~85% accuracy (vs ~70%
        # for tiny, ~90% for small) and ~3x faster than small on CPU. LLM
        # segment selection tolerates the residual error well because Groq/
        # Gemini infer meaning from context. Override via GROQ_ONLY_WHISPER_MODEL
        # for slower-but-accurate (small) or faster-but-lossier (tiny).
        import os as _os
        _model = (_os.getenv("GROQ_ONLY_WHISPER_MODEL", "base") or tuned["whisper_model"]).strip()
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

            # Diagnostics so the log shows what's happening, not just silence.
            _src_size_mb = source_path.stat().st_size / (1024 * 1024)
            _video_dur = float(source.get("duration") or 0.0)
            # Rough CPU realtime multipliers for faster-whisper:
            # tiny ~10x, base ~7x, small ~4x, medium ~2x, large 1x
            _rt_mult = {"tiny": 10, "base": 7, "small": 4, "medium": 2, "large": 1}.get(_model, 5)
            _eta_sec = max(5, _video_dur / max(1, _rt_mult))
            _job_log(
                effective_channel, job_id,
                f"groq_only.transcription_started model={_model} engine={_engine} "
                f"video_dur={_video_dur:.0f}s src_size={_src_size_mb:.1f}MB "
                f"eta={_eta_sec:.0f}s (CPU estimate)",
            )
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="groq_only.transcription.progress",
                level="INFO",
                message=f"Whisper started (model={_model}, eta≈{_eta_sec:.0f}s)",
                step="render.groq_only.transcribe",
                context={
                    "model": _model, "engine": _engine,
                    "video_duration_sec": _video_dur,
                    "source_size_mb": round(_src_size_mb, 1),
                    "eta_sec": int(_eta_sec),
                },
            )

            def _hb_fn(_stop=_hb_stop, _m=_model, _eta=_eta_sec):
                _pct = 16
                _tick = 0
                while not _stop.wait(5):  # heartbeat every 5s (was 12s)
                    _tick += 1
                    _el = round(time.perf_counter() - _t0)
                    _pct_est = min(99, int(100 * _el / max(1, _eta)))
                    # File-log every tick so user sees liveness in console/log.
                    _job_log(
                        effective_channel, job_id,
                        f"groq_only.transcription.alive elapsed={_el}s "
                        f"est_progress={_pct_est}% model={_m} eta={_eta:.0f}s",
                    )
                    # DB progress: only bump stage % gradually (UI cap).
                    update_job_progress(
                        job_id, JobStage.TRANSCRIBING_FULL, _pct,
                        f"Whisper transcribing… {_el}s elapsed (~{_pct_est}% of eta)",
                    )
                    _pct = _pct + 1 if _pct < 22 else 22

            _hb = threading.Thread(
                target=_hb_fn, daemon=True,
                name=f"groq_only_transcribe_hb_{job_id[:8]}",
            )
            _hb.start()
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
                _srt_size_kb = full_srt.stat().st_size / 1024 if full_srt.exists() else 0
                _elapsed_sec = max(0.001, _ms / 1000)
                _rt_speed = (_video_dur / _elapsed_sec) if _video_dur > 0 else 0.0
                _job_log(
                    effective_channel, job_id,
                    f"groq_only.transcription_done model={_model} elapsed={_elapsed_sec:.1f}s "
                    f"srt_size={_srt_size_kb:.1f}KB speed={_rt_speed:.1f}x realtime",
                )
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="groq_only.transcription.done",
                    level="INFO",
                    message=f"Whisper done ({_elapsed_sec:.1f}s, {_srt_size_kb:.1f}KB SRT)",
                    step="render.groq_only.transcribe",
                    context={
                        "elapsed_ms": _ms,
                        "srt_size_bytes": full_srt.stat().st_size if full_srt.exists() else 0,
                        "realtime_speed": round(_rt_speed, 2),
                    },
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
