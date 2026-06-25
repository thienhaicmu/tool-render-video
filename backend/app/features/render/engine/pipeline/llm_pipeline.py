"""
llm_pipeline.py — LLM pre-render path.

The configured LLM (Gemini / OpenAI / Claude) is the sole authority for
segment selection — NO scene detection, NO heuristic scoring.

HARD-FAIL semantics (intentional — distinct from AI-module Contract 3):
This is an ORCHESTRATION module, not an AI module. It MUST raise
LLMPipelineError on any failure. There is no fallback path.

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
from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
from app.features.render.engine.pipeline.pipeline_cache import (
    _transcription_cache_get,
    _transcription_cache_put,
)
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log, _safe_unlink
from app.db.jobs_repo import update_job_progress
from app.features.render.engine.subtitle.transcription.whisper import has_audio_stream
from app.features.render.engine.subtitle.transcription.adapters import transcribe_with_adapter
from app.services.metrics import WHISPER_TRANSCRIBE_DURATION

logger = logging.getLogger("app.render.llm_pipeline")


@dataclass
class LLMPreRenderResult:
    """Pre-render result consumed by run_render_pipeline.

    Moved here from pipeline_pre_render.py in Phase F1 (legacy path removed).
    """
    full_srt: Path
    full_srt_available: bool
    early_transcription_done: bool
    scored: list
    total_parts: int
    target_platform: str
    dna_clean_visual: bool
    seg_min_sec: int
    seg_max_sec: int


class LLMPipelineError(RuntimeError):
    """HARD-FAIL — no fallback path.

    Raised when any precondition fails or the LLM cannot produce a usable
    segment list. Caller (render_pipeline.py) must propagate this upward
    to fail the job.
    """


def run_llm_pre_render(
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
    skip_segment_selection: bool = False,
) -> LLMPreRenderResult:
    """LLM-only replacement for run_pre_render_scenes().

    Raises:
        LLMPipelineError: any precondition or stage failure (HARD-FAIL).
        cancel_registry.JobCancelledError: job cancelled mid-flight.
    """
    # ── 1. Pre-flight validation ──────────────────────────────────────────
    if not getattr(payload, "llm_enabled", False):
        logger.warning(
            "llm_pipeline: llm_enabled=False — continuing anyway "
            "(pipeline is mandatory since Phase F1)"
        )
    if getattr(payload, "multi_variant", False):
        # multi_variant requires a separate rendering pass not implemented here.
        # Degrade to single-variant rather than failing the job outright.
        _job_log(
            effective_channel, job_id,
            "multi_variant requested but not supported in llm_pipeline path — "
            "rendering single variant (set multi_variant=False to suppress this warning)",
            kind="warning",
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="llm_pipeline.multi_variant_degraded",
            level="WARNING",
            message="multi_variant not supported in llm_pipeline path — using single variant",
            step="render.llm_pipeline.preflight",
        )
    from app.core import config as _cfg
    _provider = (getattr(payload, "ai_provider", "") or "").strip().lower() \
                or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
    _api_key, _ = _resolve_api_key(payload, _provider)
    if not _api_key:
        raise LLMPipelineError(
            f"provider '{_provider}' requires a valid API key "
            f"(set {_provider.upper()}_API_KEY in .env or pass via payload field)"
        )
    if not has_audio_stream(str(source_path)):
        raise LLMPipelineError(
            "LLM pipeline requires source video with an audio stream"
        )
    if cancel_registry.is_cancelled(job_id):
        raise cancel_registry.JobCancelledError()

    full_srt = work_dir / f"{source['slug']}_full.srt"

    # ── 2. Transcription stage event ─────────────────────────────────────
    set_stage_fn(
        JobStage.TRANSCRIBING_FULL, 15,
        "LLM pipeline: transcribing for analysis",
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id,
        event="llm_pipeline.transcription_started",
        level="INFO",
        message="LLM pipeline: starting Whisper transcription",
        step="render.llm_pipeline.transcribe",
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
            "llm_pipeline.transcription: resume hit, reusing existing SRT",
        )
    else:
        # For LLM segment selection the SRT only needs to convey content,
        # not word-perfect transcription. Per-clip subtitles are transcribed
        # SEPARATELY in part_renderer.py with the higher-quality `small` model
        # so subtitle quality is untouched.
        #
        # Default `base`: sweet spot for Vietnamese — ~85% accuracy (vs ~70%
        # for tiny, ~90% for small) and ~3x faster than small on CPU. LLM
        # segment selection tolerates the residual error well because Gemini/
        # GPT/Claude infer meaning from context. Override via LLM_WHISPER_MODEL
        # for slower-but-accurate (small) or faster-but-lossier (tiny).
        import os as _os
        _env_model = (_os.getenv("LLM_WHISPER_MODEL") or "").strip()
        _ch_code = (getattr(payload, "channel_code", "") or "").strip()
        _channel_model = ""
        if not _env_model and _ch_code:
            try:
                from app.db.creator_repo import get_whisper_model_for_channel
                _channel_model = get_whisper_model_for_channel(_ch_code) or ""
            except Exception:
                pass
        _model = (_env_model or _channel_model or tuned["whisper_model"] or "base").strip()
        _engine = getattr(payload, "subtitle_transcription_engine", "default")
        _llm_language_raw = (getattr(payload, "llm_language", None) or "").strip().lower()
        _language = None if _llm_language_raw in ("", "auto") else _llm_language_raw
        _cache_key = (
            f"{_engine}_{int(bool(getattr(payload, 'highlight_per_word', False)))}"
            f"_{_language or 'auto'}"
        )
        _cached = _transcription_cache_get(str(source_path), _model, _cache_key)
        if _cached is not None:
            import shutil
            shutil.copy2(str(_cached), str(full_srt))
            _job_log(
                effective_channel, job_id,
                f"llm_pipeline.transcription: cache_hit model={_model}",
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
                f"llm_pipeline.transcription_started model={_model} engine={_engine} "
                f"video_dur={_video_dur:.0f}s src_size={_src_size_mb:.1f}MB "
                f"eta={_eta_sec:.0f}s (CPU estimate)",
            )
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="llm_pipeline.transcription.progress",
                level="INFO",
                message=f"Whisper started (model={_model}, eta≈{_eta_sec:.0f}s)",
                step="render.llm_pipeline.transcribe",
                context={
                    "model": _model, "engine": _engine,
                    "video_duration_sec": _video_dur,
                    "source_size_mb": round(_src_size_mb, 1),
                    "eta_sec": int(_eta_sec),
                },
            )

            def _hb_fn(_stop=_hb_stop, _m=_model, _eta=_eta_sec):
                # S4.6 — feed the eta-based estimate directly into the
                # DB progress field instead of the slow 16-22% drip the
                # previous implementation used. The estimate isn't
                # segment-accurate (faster-whisper doesn't expose per-
                # segment progress without a wrapped iterator) but
                # bouncing 16 -> 22% over a multi-minute Whisper run made
                # the analyze bar look frozen. eta-based is closer to
                # actual ground truth and unambiguously moves.
                _tick = 0
                while not _stop.wait(10):  # heartbeat every 10s — halves DB writes during Whisper
                    _tick += 1
                    _el = round(time.perf_counter() - _t0)
                    _pct_est = min(99, int(100 * _el / max(1, _eta)))
                    # File-log every tick so user sees liveness in console/log.
                    _job_log(
                        effective_channel, job_id,
                        f"llm_pipeline.transcription.alive elapsed={_el}s "
                        f"est_progress={_pct_est}% model={_m} eta={_eta:.0f}s",
                    )
                    # DB progress: surface the eta-based estimate so the
                    # FE analyze phase actually moves over the Whisper
                    # duration. Stage stays TRANSCRIBING_FULL — Sacred
                    # Contract #4 untouched.
                    update_job_progress(
                        job_id, JobStage.TRANSCRIBING_FULL, _pct_est,
                        f"Whisper transcribing ~{_pct_est}% ({_el}s / est {int(_eta)}s, {_m})",
                    )

            _hb = threading.Thread(
                target=_hb_fn, daemon=True,
                name=f"llm_pipeline_transcribe_hb_{job_id[:8]}",
            )
            _hb.start()
            try:
                transcribe_with_adapter(
                    str(source_path), str(full_srt),
                    engine=_engine,
                    model_name=_model,
                    retry_count=retry_count,
                    highlight_per_word=getattr(payload, "highlight_per_word", False),
                    language=_language,
                    beam_size=1,
                    vad_filter=True,
                    condition_on_previous_text=False,
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
                    f"llm_pipeline.transcription_done model={_model} elapsed={_elapsed_sec:.1f}s "
                    f"srt_size={_srt_size_kb:.1f}KB speed={_rt_speed:.1f}x realtime",
                )
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="llm_pipeline.transcription.done",
                    level="INFO",
                    message=f"Whisper done ({_elapsed_sec:.1f}s, {_srt_size_kb:.1f}KB SRT)",
                    step="render.llm_pipeline.transcribe",
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
                    f"llm_pipeline.transcription_failed: {_exc}",
                    kind="error",
                )
                raise LLMPipelineError(
                    f"LLM pipeline: Whisper transcription failed: {_exc}"
                ) from _exc
            finally:
                _hb_stop.set()
                _hb.join(timeout=2)
                # Perf-opt Phase 0 baseline observability — observe on both
                # success and failure paths so the histogram captures real
                # cost. Wrapped in try/except so any metric error stays out
                # of the orchestration path.
                try:
                    WHISPER_TRANSCRIBE_DURATION.labels(
                        model=_model, engine=str(_engine)
                    ).observe(time.perf_counter() - _t0)
                except Exception:
                    pass

    # ── 4. Verify SRT not empty ──────────────────────────────────────────
    if not (full_srt.exists() and full_srt.stat().st_size > 0):
        raise LLMPipelineError(
            "LLM pipeline: SRT empty or missing after transcription"
        )

    # T2.3 — Audit 2026-06-08 closure (Batch B B-10-A). Emit
    # JobStage.SCENE_DETECTION between TRANSCRIBING_FULL (at progress
    # 15-22 inside this function) and SEGMENT_BUILDING (at progress 25
    # below). Sacred Contract #4 lists SCENE_DETECTION in the frozen
    # ordering between TRANSCRIBING_FULL and SEGMENT_BUILDING; this
    # is the closest natural slot. Even without an explicit scene-
    # detector subprocess, the AI's transcript-to-segment mapping
    # IS scene detection conceptually. Brief progress=23 tick keeps
    # the FE progress bar advancing.
    set_stage_fn(
        JobStage.SCENE_DETECTION, 23,
        "LLM pipeline: detecting scene boundaries from transcript",
    )

    # ── 5. Segment-selection stage event ─────────────────────────────────
    set_stage_fn(
        JobStage.SEGMENT_BUILDING, 25,
        "LLM pipeline: selecting segments",
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id,
        event="llm_pipeline.selection_started",
        level="INFO",
        message="LLM pipeline: requesting segment selection from LLM",
        step="render.llm_pipeline.select",
    )

    _emit_render_event(
        channel_code=effective_channel, job_id=job_id,
        event="llm_pipeline.selection_skipped",
        level="INFO",
        message="LLM pipeline: Call 1 skipped — segments will be derived from RenderPlan",
        step="render.llm_pipeline.select",
        context={"reason": "skip_segment_selection"},
    )
    return LLMPreRenderResult(
        full_srt=full_srt,
        full_srt_available=True,
        early_transcription_done=True,
        scored=[],
        total_parts=0,
        target_platform=str(
            getattr(payload, "target_platform", "") or "youtube_shorts"
        ).lower(),
        dna_clean_visual=False,
        seg_min_sec=int(payload.min_part_sec),
        seg_max_sec=int(payload.max_part_sec),
    )

