"""
parallel_analysis.py — Concurrent scene detection + Whisper transcription.

Saves 30–90 s per job by running two independent CPU-bound operations in
separate threads instead of sequentially.

Contract:
  - Never raises — returns ParallelAnalysisResult with degraded data on error.
  - All cache interactions use the same helpers as the sequential path.
  - Thread count capped at 2 (scene thread + transcription thread).
  - Compatible with existing heartbeat / progress patterns in the caller.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

logger = logging.getLogger("app.render.parallel_analysis")

_EXECUTOR_TIMEOUT_SEC = 600  # hard cap; transcription rarely exceeds 10 min


# ── Public result type ─────────────────────────────────────────────────────────

@dataclass
class ParallelAnalysisResult:
    # Scene detection outputs
    scenes: List[Any] = field(default_factory=list)
    scene_ms: int = 0
    scene_cache_hit: bool = False
    scene_error: Optional[str] = None

    # Transcription outputs
    full_srt_available: bool = False
    transcription_ms: int = 0
    transcription_cache_hit: bool = False
    transcription_error: Optional[str] = None

    @property
    def scene_ok(self) -> bool:
        return self.scene_error is None

    @property
    def transcription_ok(self) -> bool:
        return self.full_srt_available


# ── Public entry point ─────────────────────────────────────────────────────────

def run_parallel_analysis(
    *,
    source_path: Path,
    full_srt: Path,
    do_scene_detection: bool,
    do_transcription: bool,
    auto_detect_scene: bool,
    payload: Any,
    tuned: dict,
    retry_count: int,
    resume_from_last: bool,
    # Cache helpers (same signatures as pipeline_cache.py)
    scene_cache_get: Callable[[str], Optional[list]],
    scene_cache_put: Callable[[str, list], None],
    transcription_cache_get: Callable[[str, str, str], Optional[Path]],
    transcription_cache_put: Callable[[str, str, str, Path], None],
    # Progress callback (optional) — signature: (msg: str) -> None
    progress_cb: Optional[Callable[[str], None]] = None,
) -> ParallelAnalysisResult:
    """
    Run scene detection and/or transcription concurrently.

    When only one operation is requested, runs it directly (no thread overhead).
    When both are requested, submits them to a 2-worker thread pool and waits
    for both to complete.

    Always returns ParallelAnalysisResult — never raises.
    """
    try:
        return _run(
            source_path=source_path,
            full_srt=full_srt,
            do_scene_detection=do_scene_detection,
            do_transcription=do_transcription,
            auto_detect_scene=auto_detect_scene,
            payload=payload,
            tuned=tuned,
            retry_count=retry_count,
            resume_from_last=resume_from_last,
            scene_cache_get=scene_cache_get,
            scene_cache_put=scene_cache_put,
            transcription_cache_get=transcription_cache_get,
            transcription_cache_put=transcription_cache_put,
            progress_cb=progress_cb or (lambda _: None),
        )
    except Exception as exc:
        logger.warning("parallel_analysis: unexpected error — %s", exc)
        return ParallelAnalysisResult(
            scene_error=f"unexpected: {exc}",
            transcription_error=f"unexpected: {exc}",
        )


# ── Internal ───────────────────────────────────────────────────────────────────

def _run(
    *,
    source_path: Path,
    full_srt: Path,
    do_scene_detection: bool,
    do_transcription: bool,
    auto_detect_scene: bool,
    payload: Any,
    tuned: dict,
    retry_count: int,
    resume_from_last: bool,
    scene_cache_get: Callable,
    scene_cache_put: Callable,
    transcription_cache_get: Callable,
    transcription_cache_put: Callable,
    progress_cb: Callable[[str], None],
) -> ParallelAnalysisResult:
    both = do_scene_detection and do_transcription

    if both:
        return _run_parallel(
            source_path=source_path,
            full_srt=full_srt,
            auto_detect_scene=auto_detect_scene,
            payload=payload,
            tuned=tuned,
            retry_count=retry_count,
            resume_from_last=resume_from_last,
            scene_cache_get=scene_cache_get,
            scene_cache_put=scene_cache_put,
            transcription_cache_get=transcription_cache_get,
            transcription_cache_put=transcription_cache_put,
            progress_cb=progress_cb,
        )

    result = ParallelAnalysisResult()
    if do_scene_detection:
        sr = _scene_worker(source_path, auto_detect_scene, scene_cache_get, scene_cache_put)
        result.scenes = sr.scenes
        result.scene_ms = sr.scene_ms
        result.scene_cache_hit = sr.scene_cache_hit
        result.scene_error = sr.scene_error
    if do_transcription:
        tr = _transcription_worker(
            source_path, full_srt, payload, tuned, retry_count,
            resume_from_last, transcription_cache_get, transcription_cache_put,
            progress_cb,
        )
        result.full_srt_available = tr.full_srt_available
        result.transcription_ms = tr.transcription_ms
        result.transcription_cache_hit = tr.transcription_cache_hit
        result.transcription_error = tr.transcription_error
    return result


def _run_parallel(
    *,
    source_path: Path,
    full_srt: Path,
    auto_detect_scene: bool,
    payload: Any,
    tuned: dict,
    retry_count: int,
    resume_from_last: bool,
    scene_cache_get: Callable,
    scene_cache_put: Callable,
    transcription_cache_get: Callable,
    transcription_cache_put: Callable,
    progress_cb: Callable[[str], None],
) -> ParallelAnalysisResult:
    result = ParallelAnalysisResult()
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="par_analysis") as pool:
        scene_future: Future = pool.submit(
            _scene_worker,
            source_path, auto_detect_scene, scene_cache_get, scene_cache_put,
        )
        transcription_future: Future = pool.submit(
            _transcription_worker,
            source_path, full_srt, payload, tuned, retry_count,
            resume_from_last, transcription_cache_get, transcription_cache_put,
            progress_cb,
        )

        for future in as_completed(
            [scene_future, transcription_future],
            timeout=_EXECUTOR_TIMEOUT_SEC,
        ):
            try:
                partial: _SceneResult | _TranscriptionResult = future.result()
                if isinstance(partial, _SceneResult):
                    result.scenes = partial.scenes
                    result.scene_ms = partial.scene_ms
                    result.scene_cache_hit = partial.scene_cache_hit
                    result.scene_error = partial.scene_error
                elif isinstance(partial, _TranscriptionResult):
                    result.full_srt_available = partial.full_srt_available
                    result.transcription_ms = partial.transcription_ms
                    result.transcription_cache_hit = partial.transcription_cache_hit
                    result.transcription_error = partial.transcription_error
            except Exception as exc:
                logger.warning("parallel_analysis worker raised: %s", exc)

    elapsed = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "parallel_analysis: done elapsed_ms=%d scene_ms=%d transcription_ms=%d "
        "scenes=%d srt_available=%s cache_hit_scene=%s cache_hit_transcription=%s",
        elapsed,
        result.scene_ms, result.transcription_ms,
        len(result.scenes), result.full_srt_available,
        result.scene_cache_hit, result.transcription_cache_hit,
    )
    return result


# ── Worker result types (internal only) ───────────────────────────────────────

@dataclass
class _SceneResult:
    scenes: list = field(default_factory=list)
    scene_ms: int = 0
    scene_cache_hit: bool = False
    scene_error: Optional[str] = None


@dataclass
class _TranscriptionResult:
    full_srt_available: bool = False
    transcription_ms: int = 0
    transcription_cache_hit: bool = False
    transcription_error: Optional[str] = None


# ── Scene detection worker ─────────────────────────────────────────────────────

def _scene_worker(
    source_path: Path,
    auto_detect_scene: bool,
    cache_get: Callable,
    cache_put: Callable,
) -> _SceneResult:
    result = _SceneResult()
    if not auto_detect_scene:
        return result
    t0 = time.perf_counter()
    try:
        from app.features.render.engine.pipeline.scene_detector import detect_scenes
        cached = cache_get(str(source_path))
        if cached is not None:
            result.scenes = cached
            result.scene_cache_hit = True
        else:
            result.scenes = detect_scenes(str(source_path))
            cache_put(str(source_path), result.scenes)
    except Exception as exc:
        result.scene_error = str(exc)
        logger.warning("parallel_analysis scene_worker failed: %s", exc)
    finally:
        result.scene_ms = int((time.perf_counter() - t0) * 1000)
    return result


# ── Transcription worker ───────────────────────────────────────────────────────

def _transcription_worker(
    source_path: Path,
    full_srt: Path,
    payload: Any,
    tuned: dict,
    retry_count: int,
    resume_from_last: bool,
    cache_get: Callable,
    cache_put: Callable,
    progress_cb: Callable[[str], None],
) -> _TranscriptionResult:
    result = _TranscriptionResult()
    t0 = time.perf_counter()
    try:
        from app.features.render.engine.subtitle.transcription.whisper import has_audio_stream
        from app.features.render.engine.subtitle.transcription.adapters import transcribe_with_adapter

        if not has_audio_stream(str(source_path)):
            result.transcription_error = "no_audio_stream"
            return result

        # Resume: existing SRT already written
        if resume_from_last and full_srt.exists() and full_srt.stat().st_size > 0:
            result.full_srt_available = True
            result.transcription_cache_hit = True
            return result

        model = tuned["whisper_model"]
        engine = getattr(payload, "subtitle_transcription_engine", "default")
        highlight = getattr(payload, "highlight_per_word", False)
        cache_key = f"{engine}_{int(bool(highlight))}"

        # Cache hit: copy cached SRT to full_srt
        cached_path = cache_get(str(source_path), model, cache_key)
        if cached_path is not None:
            try:
                shutil.copy2(str(cached_path), str(full_srt))
                result.full_srt_available = full_srt.exists() and full_srt.stat().st_size > 0
                result.transcription_cache_hit = result.full_srt_available
                return result
            except Exception as copy_exc:
                logger.warning("parallel_analysis copy cache failed: %s", copy_exc)

        # Full transcription
        progress_cb(f"Transcribing with {model}…")
        transcribe_with_adapter(
            str(source_path), str(full_srt),
            engine=engine,
            model_name=model,
            retry_count=retry_count,
            highlight_per_word=highlight,
            logger=logger,
        )
        result.full_srt_available = full_srt.exists() and full_srt.stat().st_size > 0
        if result.full_srt_available:
            cache_put(str(source_path), model, cache_key, full_srt)

    except Exception as exc:
        result.transcription_error = str(exc)
        logger.warning("parallel_analysis transcription_worker failed: %s", exc)
    finally:
        result.transcription_ms = int((time.perf_counter() - t0) * 1000)
    return result
