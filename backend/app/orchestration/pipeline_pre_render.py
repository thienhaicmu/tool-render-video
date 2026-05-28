"""
pipeline_pre_render.py — Scene detection and segment scoring extracted from run_render_pipeline().

Covers Phase 45 (early transcription), Phase 46 (content analysis), Phase 5.4
(early AI pacing), scene detection, segment building, CLIP scoring, selection
filters, DNA/platform bias, and story-arc sequencing.

Phase A-6 extraction.  Frozen contracts unchanged.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.stage import JobStage
from app.orchestration.pipeline_cache import (
    _render_cache_key,
    _scene_cache_get, _scene_cache_put,
    _score_cache_get, _score_cache_put,
    _transcription_cache_get, _transcription_cache_put,
)
from app.orchestration.pipeline_helpers import _PLATFORM_PROFILES, _build_variant_segments
from app.orchestration.render_events import _emit_render_event, _job_log, _safe_unlink
from app.orchestration.visual_analysis import VisualAnalysisResult
from app.services.clip_scorer import score_scenes_clip, CLIP_SCORER_VERSION
from app.services.db import update_job_progress
from app.services.scene_detector import detect_scenes
from app.services.segment_builder import build_segments_from_scenes
from app.services.subtitle_engine import has_audio_stream
from app.services.subtitle_transcription_adapters import transcribe_with_adapter
from app.services.viral_scorer import score_segments

logger = logging.getLogger("app.render")

HIGH_MOTION_MIN_SCORE = 60
HIGH_MOTION_MIN_KEEP = 3


@dataclass
class PreRenderScenesResult:
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


def run_pre_render_scenes(
    source_path: Path,
    source: dict,
    work_dir: Path,
    payload: Any,
    tuned: dict,
    job_id: str,
    effective_channel: str,
    retry_count: int,
    cancel_registry: Any,
    set_stage_fn: Callable,
) -> PreRenderScenesResult:
    """Detect scenes, build and score segments, apply selection filters.

    Phase A-6 extraction. Encapsulates Phase 45 early transcription, Phase 46
    content analysis, Phase 5.4 AI pacing, scene detection, segment building,
    CLIP scoring, clip exclude/lock, DNA/platform bias, and story-arc sequencing.

    payload may be mutated in-place (subtitle_emphasis adjusts sub_font_size).
    set_stage_fn is the _set_stage closure from run_render_pipeline — it uses
    nonlocal current_stage/current_progress and propagates stage changes back
    to the outer scope.
    """
    full_srt = work_dir / f"{source['slug']}_full.srt"
    full_srt_available = False
    _early_transcription_done = False
    
    set_stage_fn(JobStage.SCENE_DETECTION, 15, "Detecting scenes")
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.scene.detect.start",
        level="INFO",
        message="Detecting scenes",
        step="render.scene.detect",
    )
    if cancel_registry.is_cancelled(job_id):
        raise cancel_registry.JobCancelledError()
    _t_scene = time.perf_counter()
    _scene_cache_hit = False
    if payload.auto_detect_scene:
        _cached_scenes = _scene_cache_get(str(source_path))
        if _cached_scenes is not None:
            scenes = _cached_scenes
            _scene_cache_hit = True
        else:
            scenes = detect_scenes(str(source_path))
            _scene_cache_put(str(source_path), scenes)
    else:
        scenes = []
    _scene_ms = int((time.perf_counter() - _t_scene) * 1000)
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.scene.detect.success",
        level="INFO",
        message=f"Detected {len(scenes)} scenes",
        step="render.scene.detect",
        context={"scene_count": len(scenes), "duration_ms": _scene_ms, "cache_hit": _scene_cache_hit},
        duration_ms=_scene_ms,
    )
    _job_log(effective_channel, job_id, f"{'cache_hit' if _scene_cache_hit else 'cache_miss'} type=scene_detect scenes={len(scenes)} elapsed_ms={_scene_ms}")
    _job_log(effective_channel, job_id, f"Scene detection done: {len(scenes)} scenes in {_scene_ms}ms")
    
    # Layer 4 â†’ Layer 5 boundary: capture Visual Analysis outputs before segment building.
    _visual_analysis = VisualAnalysisResult(
        scene_count=len(scenes),
        detection_ms=_scene_ms,
        cache_hit=_scene_cache_hit,
    )
    logger.info(
        "visual_analysis scene_count=%d detection_ms=%d cache_hit=%s",
        _visual_analysis.scene_count, _visual_analysis.detection_ms, _visual_analysis.cache_hit,
    )
    
    # â”€â”€ Phase 45: Early transcription for AI content understanding â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Fires before segment building when ai_early_transcription=True OR
    # ai_content_driven_selection=True. Produces full_srt for AI Director and
    # S4.1/S4.2/S4.5 refinements BEFORE the heuristic viral-score filter cuts
    # the candidate pool. On any failure â†’ full_srt_available stays False,
    # render continues unchanged. NEVER raises. NEVER changes stage names.
    if (
        getattr(payload, "ai_early_transcription", False)
        or getattr(payload, "ai_content_driven_selection", False)
    ):
        try:
            _p45_has_audio = has_audio_stream(str(source_path))
            _p45_resume_hit = (
                payload.resume_from_last
                and full_srt.exists()
                and full_srt.stat().st_size > 0
            )
            if not _p45_has_audio:
                _job_log(effective_channel, job_id,
                         "phase45_early_transcription_skipped: no audio stream",
                         kind="warning")
            elif _p45_resume_hit:
                full_srt_available = True
                _early_transcription_done = True
                _job_log(effective_channel, job_id,
                         "phase45_early_transcription: resume hit, reusing existing SRT")
            else:
                _p45_model = tuned["whisper_model"]
                _p45_engine = getattr(payload, "subtitle_transcription_engine", "default")
                _p45_cache_key = f"{_p45_engine}_{int(bool(payload.highlight_per_word))}"
                _p45_cached = _transcription_cache_get(str(source_path), _p45_model, _p45_cache_key)
                if _p45_cached is not None:
                    shutil.copy2(str(_p45_cached), str(full_srt))
                    full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                    _early_transcription_done = full_srt_available
                    _job_log(effective_channel, job_id,
                             f"phase45_early_transcription: cache_hit model={_p45_model} "
                             f"available={full_srt_available}")
                else:
                    set_stage_fn(JobStage.TRANSCRIBING_FULL, 17, "Transcribing for AI analysis")
                    _t_p45 = time.perf_counter()
                    _p45_hb_stop = threading.Event()
    
                    def _p45_hb_fn(_stop=_p45_hb_stop, _m=_p45_model):
                        _pct = 18
                        while not _stop.wait(12):
                            _el = round(time.perf_counter() - _t_p45)
                            update_job_progress(
                                job_id, JobStage.TRANSCRIBING_FULL, _pct,
                                f"Transcribing for AI analysisâ€¦ ({_el}s)"
                            )
                            _pct = _pct + 1 if _pct < 22 else 22
    
                    _p45_hb = threading.Thread(
                        target=_p45_hb_fn, daemon=True,
                        name=f"p45_transcribe_hb_{job_id[:8]}"
                    )
                    _p45_hb.start()
                    _job_log(effective_channel, job_id,
                             f"phase45_early_transcription_started model={_p45_model}")
                    _emit_render_event(
                        channel_code=effective_channel, job_id=job_id,
                        event="early_transcription_started",
                        level="INFO",
                        message=f"Phase 45: Transcribing for AI content analysis model={_p45_model}",
                        step="ai_director.transcribe",
                        context={"whisper_model": _p45_model},
                    )
                    try:
                        _p45_result = transcribe_with_adapter(
                            str(source_path), str(full_srt),
                            engine=_p45_engine,
                            model_name=_p45_model,
                            retry_count=retry_count,
                            highlight_per_word=payload.highlight_per_word,
                            logger=logger,
                        )
                        full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                        _early_transcription_done = full_srt_available
                        _p45_ms = int((time.perf_counter() - _t_p45) * 1000)
                        if _early_transcription_done:
                            _transcription_cache_put(
                                str(source_path), _p45_model, _p45_cache_key, full_srt
                            )
                        _job_log(effective_channel, job_id,
                                 f"phase45_early_transcription_done model={_p45_model} "
                                 f"available={full_srt_available} elapsed_ms={_p45_ms}")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="early_transcription_completed",
                            level="INFO",
                            message=f"Phase 45: Early transcription complete elapsed={_p45_ms}ms",
                            step="ai_director.transcribe",
                            context={"whisper_model": _p45_model, "elapsed_ms": _p45_ms,
                                     "available": full_srt_available},
                        )
                    except Exception as _p45_exc:
                        full_srt_available = False
                        _early_transcription_done = False
                        _safe_unlink(full_srt)
                        _job_log(effective_channel, job_id,
                                 f"phase45_early_transcription_failed: {_p45_exc}",
                                 kind="warning")
                    finally:
                        _p45_hb_stop.set()
                        _p45_hb.join(timeout=2)
        except Exception as _p45_outer_err:
            _job_log(effective_channel, job_id,
                     f"phase45_early_transcription_outer_failed: {_p45_outer_err}",
                     kind="warning")
    
    # â”€â”€ Phase 46: Content analysis (single-pass, before segment building) â”€â”€
    # Runs when transcript is available (full_srt_available=True).
    # Produces ContentAnalysisResult shared by AI Director, segment scoring,
    # and S4.x refinements â€” each consumer reads pre-computed analysis instead
    # of re-running analyzers independently. Advisory metadata only.
    # NEVER raises. NEVER modifies payload. NEVER crashes render.
    _content_analysis = None
    if full_srt_available:
        try:
            from app.ai.content.content_analyzer import ContentAnalyzer as _ContentAnalyzer
            _t_ca = time.perf_counter()
            _content_analysis = _ContentAnalyzer.analyze(
                source_path=str(source_path),
                srt_path=str(full_srt),
                source_duration=float(source.get("duration", 0.0)),
            )
            _ca_ms = int((time.perf_counter() - _t_ca) * 1000)
            if _content_analysis.available:
                _job_log(
                    effective_channel, job_id,
                    f"phase46_content_analysis: chunks={len(_content_analysis.chunks)} "
                    f"emotion={_content_analysis.dominant_emotion} "
                    f"arc_phases={len(_content_analysis.narrative_arc)} "
                    f"hooks={len(_content_analysis.hook_positions)} "
                    f"beat={_content_analysis.beat_available} "
                    f"elapsed_ms={_ca_ms}",
                )
            else:
                _job_log(
                    effective_channel, job_id,
                    f"phase46_content_analysis_unavailable: {_content_analysis.warnings}",
                    kind="warning",
                )
        except Exception as _ca_err:
            _job_log(
                effective_channel, job_id,
                f"phase46_content_analysis_failed: {_ca_err}",
                kind="warning",
            )
    
    # â”€â”€ Phase 5.4: Early AI pacing retrieval (before segment building) â”€â”€â”€â”€â”€
    # Runs only when ai_director_enabled=True. Retrieves knowledge to get
    # pacing hints BEFORE build_segments_from_scenes() so they can influence
    # segment duration config. Results are stored in _early_retrieved_knowledge
    # to avoid a second FAISS query in the Phase 5.2/5.3 AI director block.
    # NEVER raises. NEVER modifies payload. NEVER crashes render.
    # Priority: user explicit limits > AI hints > payload defaults.
    _early_retrieved_knowledge: list = []
    _early_pacing_tracer = None
    _pacing_config = None
    if getattr(payload, "ai_director_enabled", False):
        try:
            from app.ai.rag.knowledge_warmup import get_knowledge_index as _get_kidx
            from app.ai.render_mapper import map_knowledge_to_execution_hints as _map_hints
            from app.ai.pacing import build_ai_pacing_config as _build_pacing
            from app.ai.tracing import AITraceLogger as _AITraceLogger
    
            # Build knowledge filters (same logic as Phase 5.2 block below)
            _early_filters: dict = {}
            try:
                _early_filters = {
                    k: v for k, v in {
                        "platform": getattr(payload, "render_profile", None) or None,
                        "niche": None,
                        "style": None,
                        "duration": source.get("duration", None),
                        "aspect_ratio": getattr(payload, "aspect_ratio", None) or None,
                        "subtitle_style": getattr(payload, "subtitle_style", None) or None,
                        "target_goal": None,
                    }.items() if v is not None
                }
            except Exception:
                _early_filters = {}
    
            # Early knowledge retrieval
            try:
                _early_kidx = _get_kidx()
                if _early_kidx.is_ready():
                    _early_retrieved_knowledge = _early_kidx.query(_early_filters, top_k=10)
                    logger.debug(
                        "phase54_early_knowledge_retrieved job_id=%s count=%d",
                        job_id, len(_early_retrieved_knowledge),
                    )
            except Exception as _early_kr_err:
                logger.debug("phase54_early_retrieval_failed job_id=%s: %s", job_id, _early_kr_err)
                _early_retrieved_knowledge = []
    
            # Map knowledge â†’ execution hints â†’ pacing config
            if _early_retrieved_knowledge:
                try:
                    _early_hint_result = _map_hints(_early_retrieved_knowledge)
                    _early_exec_hints = _early_hint_result.hints if _early_hint_result else None
                    _pacing_config = _build_pacing(_early_exec_hints, payload)
                except Exception as _pacing_build_err:
                    logger.debug("phase54_pacing_build_failed job_id=%s: %s", job_id, _pacing_build_err)
                    _pacing_config = None
    
            # Trace logger for pacing
            try:
                _early_pacing_tracer = _AITraceLogger(job_id)
            except Exception:
                _early_pacing_tracer = None
    
            if _pacing_config is not None and _early_pacing_tracer is not None:
                try:
                    if _pacing_config.applied:
                        _early_pacing_tracer.log_pacing_applied({
                            "applied": True,
                            "cut_interval_min": _pacing_config.cut_interval_min,
                            "cut_interval_max": _pacing_config.cut_interval_max,
                            "source_knowledge_ids": _pacing_config.source_knowledge_ids,
                            "reason": "valid_ai_pacing_hint",
                        })
                    else:
                        _rejected_reason = _pacing_config.rejected_reason or "no_pacing_hint"
                        _early_pacing_tracer.log_decision_rejected(
                            _rejected_reason,
                            detail={
                                "hint": "pacing",
                                "cut_interval_min": _pacing_config.cut_interval_min,
                                "cut_interval_max": _pacing_config.cut_interval_max,
                                "reason": _rejected_reason,
                            },
                        )
                except Exception:
                    pass
        except Exception as _p54_err:
            logger.debug("phase54_early_pacing_block_failed job_id=%s: %s", job_id, _p54_err)
    
    # Resolve effective segment duration limits:
    # AI pacing hint (if applied) overrides payload defaults; user explicit limits always win.
    # _seg_min_sec and _seg_max_sec are used for ALL segment building calls below.
    _seg_min_sec: int = int(payload.min_part_sec)
    _seg_max_sec: int = int(payload.max_part_sec)
    if (
        _pacing_config is not None
        and _pacing_config.applied
        and _pacing_config.cut_interval_min is not None
        and _pacing_config.cut_interval_max is not None
    ):
        _seg_min_sec = int(_pacing_config.cut_interval_min)
        _seg_max_sec = int(_pacing_config.cut_interval_max)
        logger.info(
            "phase54_pacing_applied job_id=%s seg_min=%s seg_max=%s "
            "(ai hint overrides payload defaults)",
            job_id, _seg_min_sec, _seg_max_sec,
        )
    
    set_stage_fn(JobStage.SEGMENT_BUILDING, 25, "Building smart segments")
    if cancel_registry.is_cancelled(job_id):
        raise cancel_registry.JobCancelledError()
    # UP28.1 + R3.5: segment score cache probed BEFORE CLIP scoring.
    # Cache key is independent of CLIP output (file mtime/size + scene count + version),
    # so the probe is safe to hoist.  On hit, cached segments already incorporate CLIP
    # scores from the original cache-miss run â€” returning them is bit-identical.
    try:
        _src_st = source_path.stat()
        _score_ck = _render_cache_key(
            str(source_path), _src_st.st_mtime, _src_st.st_size,
            _seg_min_sec, _seg_max_sec, len(scenes),
            CLIP_SCORER_VERSION,
        )
        _cached_scored = _score_cache_get(_score_ck)
    except Exception:
        _score_ck = None
        _cached_scored = None
    if _cached_scored is not None:
        scored = _cached_scored
        _job_log(effective_channel, job_id, f"score_cache_hit type=segment_scores segments={len(scored)}")
    else:
        # OQ-5.3: CLIP semantic scoring â€” enriches scene dicts with clip_semantic_score [-8, +20]
        # Runs only on cache miss; skipped on re-renders of the same source (R3.5).
        if scenes:
            _t_clip = time.perf_counter()
            scenes = score_scenes_clip(str(source_path), scenes)
            _clip_ms = int((time.perf_counter() - _t_clip) * 1000)
            _job_log(effective_channel, job_id, f"clip_scoring_done scenes={len(scenes)} elapsed_ms={_clip_ms}")
        segments = build_segments_from_scenes(scenes, source["duration"], _seg_min_sec, _seg_max_sec)
        scored = score_segments(segments, scenes, content_analysis=_content_analysis)
        _job_log(effective_channel, job_id, f"score_cache_miss type=segment_scores segments={len(scored)}")
        if _score_ck:
            _score_cache_put(_score_ck, scored)
    # UP26: Clip exclude â€” remove creator-blacklisted timestamp ranges before selection
    _clip_exclude = [x for x in (getattr(payload, 'clip_exclude', None) or []) if isinstance(x, dict)]
    if _clip_exclude:
        _before_ex = len(scored)
        def _in_exclude_range(seg, _ranges=_clip_exclude):
            s = float(seg.get('start', 0))
            e = float(seg.get('end', s + 1))
            return any(s < float(ex.get('end_sec', 0)) and e > float(ex.get('start_sec', 0)) for ex in _ranges)
        scored = [seg for seg in scored if not _in_exclude_range(seg)]
        _job_log(effective_channel, job_id,
                 f"clip_exclude: {_before_ex - len(scored)} segments filtered by {len(_clip_exclude)} excluded ranges")
        _emit_render_event(channel_code=effective_channel, job_id=job_id, event="clip_excluded", level="INFO",
            message=f"UP26 clip_exclude: {_before_ex - len(scored)} segments removed", step="render.steering",
            context={"excluded_ranges": len(_clip_exclude), "segments_removed": _before_ex - len(scored)})
    # High-motion preference: boost high-energy clips without hard eviction.
    # Talking-head, interview, and commentary content remain competitive in the pool.
    _high_motion_count = sum(1 for s in scored if int(s.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE)
    _apply_motion_boost = _high_motion_count >= HIGH_MOTION_MIN_KEEP
    if _apply_motion_boost:
        _job_log(effective_channel, job_id,
                 f"high_motion_preference: {_high_motion_count} high-energy clips detected â€” "
                 f"preference boost applied (no eviction); low-motion clips remain in pool")
    # Sort by viral/motion score first for selection (top N), then re-order for output numbering.
    # viral_score is primary â€” it now incorporates transition quality, not just cut density.
    _target_platform = str(getattr(payload, "target_platform", "") or "youtube_shorts").strip().lower()
    _platform_hook_bonus = _PLATFORM_PROFILES.get(_target_platform, {}).get("hook_sort_bonus", 0)
    # UP20: Creator Style DNA â€” inferred identity nudges (after platform, before default)
    _dna = getattr(payload, "creator_dna", {}) or {}
    _dna_confident    = bool(_dna.get("confident", False))
    _dna_hook_bonus   = 3 if (_dna_confident and float(_dna.get("hook_forward",  0) or 0) >= 0.5) else 0
    _dna_clean_visual = _dna_confident and float(_dna.get("clean_visual", 0) or 0) >= 0.67
    _dna_action_count = int(_dna.get("action_count", 0) or 0)
    # UP26: Structure bias â€” gentle ranking re-weight (creator intent, above DNA, below explicit lock)
    _sb = str(getattr(payload, 'structure_bias', '') or 'balanced').strip().lower()
    _sb_hook_mult  = 1.25 if _sb == 'hook'  else (0.85 if _sb == 'story' else 1.0)
    _sb_viral_mult = 0.85 if _sb == 'hook'  else (1.15 if _sb == 'story' else 1.0)
    # UP26: Subtitle emphasis â€” adjust font size before part loop reads payload.sub_font_size
    _sub_emphasis = str(getattr(payload, 'subtitle_emphasis', '') or 'balanced').strip().lower()
    if _sub_emphasis in ('subtle', 'aggressive'):
        _base_sz = int(getattr(payload, 'sub_font_size', 0) or 46)
        payload.sub_font_size = (max(24, int(_base_sz * 0.82)) if _sub_emphasis == 'subtle'
                                 else min(120, int(_base_sz * 1.20)))
    _combined_enabled = bool(getattr(payload, "combined_scoring_enabled", False))
    if _combined_enabled:
        def _provisional_combined(s):
            vs = float(s.get("viral_score", 0) or 0)
            hs = float(s.get("hook_text_score") or s.get("hook_timing_score") or
                       s.get("hook_opening_score") or s.get("hook_score") or 0)
            # mv not yet computed; fallback = vs â†’ vs*0.50 + vs*0.30 + hs*0.20 = vs*0.80 + hs*0.20
            # UP20.1 Part A: DNA hook bonus â€” same gentle nudge as standard sort path.
            # UP26: Structure bias multipliers applied after DNA nudge.
            return (vs * 0.80 * _sb_viral_mult) + hs * (0.20 + _dna_hook_bonus / 100) * _sb_hook_mult
        scored.sort(key=_provisional_combined, reverse=True)
    else:
        scored.sort(
            key=lambda x: (
                int(x.get("viral_score", 0) * _sb_viral_mult)
                + (8 if _apply_motion_boost and int(x.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE else 0)
                + int(float(x.get("hook_score", 0) or 0) * (_platform_hook_bonus + _dna_hook_bonus) / 100 * _sb_hook_mult),
                int(x.get("motion_score", 0)),
            ),
            reverse=True,
        )
    # UP73.3: First-render quality floor â€” drop candidates below viral_score 25.
    # Procedure: sort (already done) â†’ filter â†’ fallback-to-top-1 â†’ slice.
    # Micro-safety: skip when pool is â‰¤ 2 to avoid over-pruning sparse content.
    if len(scored) > 2:
        _floor_filtered = [s for s in scored if float(s.get("viral_score", 0) or 0) >= 25]
        scored = _floor_filtered if _floor_filtered else scored[:1]
    if payload.max_export_parts and payload.max_export_parts > 0:
        scored = scored[:payload.max_export_parts]
    # UP26: Clip lock â€” promote creator-selected timestamp ranges to front of pool (after slice)
    _clip_lock = [x for x in (getattr(payload, 'clip_lock', None) or []) if isinstance(x, dict)]
    if _clip_lock:
        def _in_lock_range(seg, _ranges=_clip_lock):
            s = float(seg.get('start', 0))
            e = float(seg.get('end', s + 1))
            return any(s < float(lk.get('end_sec', 0)) and e > float(lk.get('start_sec', 0)) for lk in _ranges)
        _locked = [seg for seg in scored if _in_lock_range(seg)]
        _unlocked = [seg for seg in scored if not _in_lock_range(seg)]
        scored = _locked + _unlocked
        _job_log(effective_channel, job_id,
                 f"clip_lock: {len(_locked)} segments promoted by {len(_clip_lock)} locked ranges")
        _emit_render_event(channel_code=effective_channel, job_id=job_id, event="clip_locked", level="INFO",
            message=f"UP26 clip_lock: {len(_locked)} segments promoted to front", step="render.steering",
            context={"lock_ranges": len(_clip_lock), "segments_promoted": len(_locked)})
    # â”€â”€ Multi-variant: replace pool with 3 purposeful single-clip selections â”€â”€
    _multi_variant = bool(getattr(payload, "multi_variant", False))
    if _multi_variant:
        scored = _build_variant_segments(scored, payload)
        _job_log(
            effective_channel, job_id,
            f"multi_variant: {len(scored)} variants selected "
            f"(aggressive/balanced/story_first) "
            f"segments={[s.get('variant_type') for s in scored]}",
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="multi_variant_selected",
            level="INFO",
            message=f"Multi-variant mode: {len(scored)} purposeful variants",
            step="render.multi_variant",
            context={
                "variant_types": [s.get("variant_type") for s in scored],
                "variants": [
                    {
                        "variant": s.get("variant_type"),
                        "start": round(float(s.get("start") or 0), 1),
                        "hook_score": round(float(s.get("hook_score") or 0), 1),
                        "speed": s.get("variant_playback_speed"),
                        "subtitle": s.get("variant_subtitle_style"),
                    }
                    for s in scored
                ],
            },
        )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="platform_bias_applied",
        level="INFO",
        message=f"Platform-aware editing: {_target_platform}",
        step="render.platform",
        context={
            "target_platform": _target_platform,
            "hook_sort_bonus": _platform_hook_bonus,
            "speed_delta": _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0),
        },
    )
    _job_log(effective_channel, job_id,
             f"platform_bias: target={_target_platform} hook_bonus={_platform_hook_bonus}")
    # UP20.1 Part B: DNA observability â€” always emit confidence; log applied/suppressed separately.
    _dna_hf = float(_dna.get("hook_forward", 0) or 0)
    _dna_cv = float(_dna.get("clean_visual", 0) or 0)
    _dna_ns = float(_dna.get("narrative_structure", 0) or 0)
    _dna_suppressed_signals = _dna.get("suppressed_signals") or []
    _job_log(
        effective_channel, job_id,
        f"dna_confidence: confident={_dna_confident} action_count={_dna_action_count} "
        f"hook_forward={_dna_hf:.2f} clean_visual={_dna_cv:.2f} "
        f"narrative_structure={_dna_ns:.2f} "
        f"suppressed_signals={_dna_suppressed_signals}",
        kind="info",
    )
    if _dna_confident and (_dna_hook_bonus > 0 or _dna_clean_visual):
        _nudges = []
        if _dna_hook_bonus > 0:       _nudges.append(f"hook_bonus={_dna_hook_bonus}")
        if _dna_clean_visual:         _nudges.append("subtitle_clean_bias=active")
        _job_log(
            effective_channel, job_id,
            f"dna_applied: {' '.join(_nudges)}",
            kind="info",
        )
    elif _dna_confident:
        _job_log(
            effective_channel, job_id,
            f"dna_suppressed: all nudges below threshold â€” "
            f"hook_forward={_dna_hf:.2f}(<0.5) clean_visual={_dna_cv:.2f}(<0.67)",
            kind="info",
        )
    # Re-order for output numbering: timeline = chronological, viral/combined = by score
    part_order = str(getattr(payload, "part_order", "viral") or "viral").strip().lower()
    if part_order == "timeline":
        scored.sort(key=lambda x: float(x.get("start", 0)))
        _job_log(effective_channel, job_id, f"Part order: timeline (chronological)")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="hook_first_skipped",
            level="INFO",
            message="Hook-first skipped: timeline mode",
            step="render.hook_first",
            context={"reason": "timeline_mode", "total_clips": len(scored)},
        )
    elif part_order == "viral" and _combined_enabled:
        # P4-1: Hook-first sequencing â€” strongest hook at index 0
        def _hook_score(c):
            return (
                c.get("combined_score")
                or c.get("market_viral_score")
                or c.get("viral_score")
                or 0
            )
        _sorted = sorted(scored, key=_hook_score, reverse=True)
        _best = _sorted[0]
        _best_score = _hook_score(_best)
        _used_combined = bool(_best.get("combined_score"))
        scored = [_best] + [c for c in _sorted if c is not _best]
        _job_log(effective_channel, job_id, f"Part order: hook-first (combined+viral, best_score={_best_score})")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="hook_first_applied",
            level="INFO",
            message=f"Hook-first applied: best_part_no=1 score={_best_score} total={len(scored)}",
            step="render.hook_first",
            context={
                "best_part_no": 1,
                "best_score": _best_score,
                "used_combined_score": _used_combined,
                "total_clips": len(scored),
            },
        )
    elif _combined_enabled:
        scored.sort(key=_provisional_combined, reverse=True)
        _job_log(effective_channel, job_id, "Part order: combined score (viral+hook, experimental)")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="hook_first_skipped",
            level="INFO",
            message="Hook-first skipped: part_order is not viral",
            step="render.hook_first",
            context={"reason": "part_order_not_viral", "part_order": part_order, "total_clips": len(scored)},
        )
    else:
        _job_log(effective_channel, job_id, f"Part order: viral score (highest first)")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="hook_first_skipped",
            level="INFO",
            message="Hook-first skipped: combined scoring disabled",
            step="render.hook_first",
            context={"reason": "combined_disabled", "total_clips": len(scored)},
        )
    
    # â”€â”€ Story arc sequencing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Lightweight hook â†’ build â†’ payoff reorder applied after score-based
    # selection.  Deterministic heuristic â€” predictable and explainable.
    #
    # Conditions: non-timeline mode, 3+ clips, non-montage dominant type.
    # For montage: energy-first order is already correct â€” skip.
    # For 1-2 clips: no meaningful arc â€” skip.
    if part_order != "timeline" and len(scored) >= 3 and not _multi_variant:
        _ct_counts: dict[str, int] = {}
        for _s in scored:
            _ct = str(_s.get("content_type_hint") or "vlog")
            _ct_counts[_ct] = _ct_counts.get(_ct, 0) + 1
        _dominant_ct = max(_ct_counts, key=_ct_counts.get)
    
        if _dominant_ct != "montage":
            # Hook: clip with strongest opening signal (starts at scene cut,
            # early position, correct duration).  hook_score = starts_at_cutÃ—40
            # + position_scoreÃ—40 + duration_scoreÃ—20.
            _arc_hook = max(scored, key=lambda s: float(s.get("hook_score", 0) or 0))
    
            # Payoff: latest clip in source video that is not the hook.
            # Protects reveals, answers, punchlines, before/after moments
            # from being buried in the middle of the export.
            _arc_non_hook = [s for s in scored if s is not _arc_hook]
            _arc_payoff = max(_arc_non_hook, key=lambda s: float(s.get("start", 0) or 0))
    
            # Build: everything between hook and payoff.
            _arc_build = [s for s in scored if s is not _arc_hook and s is not _arc_payoff]
    
            # Build order by content type:
            #   interview/tutorial/vlog â€” source chronological preserves the
            #     original logic/explanation/narrative structure
            #   commentary â€” descending viral score: strongest supporting
            #     evidence before diminishing evidence
            if _dominant_ct in ("interview", "tutorial", "vlog"):
                _arc_build.sort(key=lambda s: float(s.get("start", 0) or 0))
            else:
                _arc_build.sort(key=lambda s: float(s.get("viral_score", 0) or 0), reverse=True)
    
            scored = [_arc_hook] + _arc_build + [_arc_payoff]
    
            _job_log(
                effective_channel, job_id,
                f"story_arc_applied dominant={_dominant_ct} clips={len(scored)} "
                f"hook_start={float(_arc_hook.get('start', 0) or 0):.1f}s "
                f"payoff_start={float(_arc_payoff.get('start', 0) or 0):.1f}s "
                f"hook_score={float(_arc_hook.get('hook_score', 0) or 0):.1f}",
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="story_arc_applied",
                level="INFO",
                message=(
                    f"Story arc: hook=part1 payoff=part{len(scored)} "
                    f"dominant={_dominant_ct}"
                ),
                step="render.story_arc",
                context={
                    "dominant_content_type": _dominant_ct,
                    "total_clips": len(scored),
                    "hook_start_sec": round(float(_arc_hook.get("start", 0) or 0), 1),
                    "hook_score": round(float(_arc_hook.get("hook_score", 0) or 0), 1),
                    "payoff_start_sec": round(float(_arc_payoff.get("start", 0) or 0), 1),
                    "build_order": "chronological" if _dominant_ct in ("interview", "tutorial", "vlog") else "score_desc",
                },
            )
        else:
            _job_log(
                effective_channel, job_id,
                f"story_arc_skipped reason=montage clips={len(scored)}",
            )
    
    if not scored:
        raise RuntimeError("No exportable segments were created")
    
    total_parts = len(scored)

    return PreRenderScenesResult(
        full_srt=full_srt,
        full_srt_available=full_srt_available,
        early_transcription_done=_early_transcription_done,
        scored=scored,
        total_parts=total_parts,
        content_analysis=_content_analysis,
        target_platform=_target_platform,
        dna_clean_visual=_dna_clean_visual,
        early_retrieved_knowledge=_early_retrieved_knowledge,
        seg_min_sec=_seg_min_sec,
        seg_max_sec=_seg_max_sec,
    )
