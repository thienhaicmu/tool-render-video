"""
scene_map_stage.py — deterministic shot-boundary detection pipeline stage.

Architecture-review Batch D-2-thin (2026-06-30). Promotes
``scene_detector.detect_scenes()`` (PySceneDetect + TransNetV2) from
dead code (no caller, flagged in the review) into a named pipeline stage
that:

  1. Both Recap and Clip pipelines CAN call (D-2-thin wires Recap only;
     D-2-snap / D-2-motion / C.1 wire downstream consumers).
  2. Produces a ``SceneMap`` — the domain object representing the source
     video's shot list.
  3. Persists the SceneMap to ``jobs.scene_map_json`` (migration 0014).
  4. Caches the raw detector output on disk via the existing
     ``_scene_cache_get/put`` helpers in ``pipeline_cache.py`` — those
     helpers were dead code (no caller) until this stage. Same key:
     ``(source_path | mtime | size)`` → re-detecting the SAME video is
     a fast no-op.
  5. Emits Sacred Contract #6-additive WS events
     (``scene_map.start`` and ``scene_map.done``).

Guarantees (Sacred Contract #3):
  - Every public entry point catches all exceptions and returns ``None``.
  - A failing detection call NEVER crashes a live render — the recap
    pipeline simply proceeds without a SceneMap (the consumer-wired
    stages D-2-snap / D-2-motion treat missing as legacy behaviour).
  - ``scenedetect`` package missing → auto-degrade: log + emit
    ``source="missing-dep"`` event + return None. No crash.

Kill switches:
  ``SCENE_MAP_ENABLED=0`` → run_scene_map returns None immediately.
  The Recap pipeline then proceeds with no SceneMap — identical to
  legacy behaviour from any pre-D-2 consumer's perspective.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from app.domain.scene_map import SceneMap, scene_map_from_detector_result

logger = logging.getLogger("app.render.scene_map")


def is_scene_map_enabled() -> bool:
    """Public form of the kill switch — called once by recap_pipeline to decide
    whether to invoke the stage. Read on every call (not at module load) so
    an operator can flip the env var without restarting the worker process."""
    return os.getenv("SCENE_MAP_ENABLED", "1") == "1"


# Internal alias kept for symmetry with comprehension_stage.
_is_scene_map_enabled = is_scene_map_enabled


def _safe_emit(emit_fn: Optional[Callable[..., None]], **kwargs) -> None:
    """Invoke the WS emit callback, swallowing every exception. Pure
    observation — never breaks the stage (Sacred Contract #6 spirit)."""
    if emit_fn is None:
        return
    try:
        emit_fn(**kwargs)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("scene_map: emit callback raised %s — ignored", exc)


def _try_import_detect_scenes() -> Optional[Callable]:
    """Late-import ``detect_scenes`` from the scene_detector module so this
    stage can be imported (and unit-tested) on a venv that lacks the
    optional ``scenedetect`` package. Returns None on import failure.
    """
    try:
        from app.features.render.engine.pipeline.scene_detector import detect_scenes
        return detect_scenes
    except Exception as exc:
        logger.warning("scene_map: scene_detector import failed (%s) — degraded mode", exc)
        return None


def run_scene_map(
    *,
    job_id: str,
    channel_code: str,
    video_path: str,
    persist: bool = True,
    emit_fn: Optional[Callable[..., None]] = None,
    detect_scenes_fn: Optional[Callable[..., list]] = None,
    cache_get_fn: Optional[Callable[[str], Optional[list]]] = None,
    cache_put_fn: Optional[Callable[[str, list], None]] = None,
    update_scene_map_fn: Optional[Callable[[str, str], None]] = None,
    probe_metadata_fn: Optional[Callable[[str], dict]] = None,
) -> Optional[SceneMap]:
    """Run the scene_map stage end-to-end.

    Returns the produced ``SceneMap`` or ``None``. ``None`` means the
    caller (recap_pipeline) proceeds without a SceneMap — D-2-thin's
    downstream is observation-only so this signal is informational.

    All collaborators are injectable for testability — production callers
    pass none of the ``*_fn`` arguments and the defaults late-import the
    real implementations.

    Parameters
    ----------
    job_id, channel_code : str
        Identify the WS event stream.
    video_path : str
        Absolute path to the source video file (the one Whisper transcribed).
    persist : bool
        When True, write the produced SceneMap to ``jobs.scene_map_json``
        on success. Set False in tests / dry runs.
    emit_fn : Optional[Callable]
        ``_emit_render_event`` from render_events.py — injected so this
        module avoids a circular import. The stage emits
        ``scene_map.start`` and ``scene_map.done``.
    detect_scenes_fn : Optional[Callable]
        Inject the detector for testability. Defaults to a late import of
        ``scene_detector.detect_scenes``.
    cache_get_fn / cache_put_fn : Optional[Callable]
        Inject the cache layer for testability. Defaults reuse the
        existing ``_scene_cache_get`` / ``_scene_cache_put`` helpers in
        ``pipeline_cache.py`` (previously dead code).
    update_scene_map_fn : Optional[Callable]
        Inject the persistence helper for testability. Defaults to
        ``jobs_repo.update_scene_map``.
    probe_metadata_fn : Optional[Callable]
        Inject ``probe_video_metadata`` for fps + duration. Default lazy
        import. Failure to probe is non-fatal — SceneMap carries 0.0.
    """
    # Kill switch — single env var = recap proceeds without a SceneMap.
    if not is_scene_map_enabled():
        logger.info(
            "scene_map: SCENE_MAP_ENABLED=0 — stage skipped for job_id=%s",
            job_id,
        )
        return None

    # PySceneDetect open_video() yêu cầu str (nó check '"://" in path' để
    # nhận diện URL) — truyền WindowsPath nổ "argument of type 'WindowsPath'
    # is not iterable" và stage âm thầm trả None từ ngày đầu trên Windows.
    # Ép str tại cửa vào để che mọi caller (quan sát live 2026-07 phát hiện).
    video_path = os.fspath(video_path)

    try:
        _safe_emit(
            emit_fn,
            channel_code=channel_code, job_id=job_id,
            event="scene_map.start",
            level="INFO",
            message="SceneMap: detecting shot boundaries",
            step="render.scene_map",
            context={"video_path": video_path},
        )

        # 1. Cache lookup. Reuses the existing scene_cache (was dead code
        # before D-2-thin — keyed on path|mtime|size which is exactly what
        # we need for a deterministic detector).
        if cache_get_fn is None:
            from app.features.render.engine.pipeline.pipeline_cache import (
                _scene_cache_get as _cg,
            )
            cache_get_fn = _cg
        cached_shots = None
        try:
            cached_shots = cache_get_fn(video_path)
        except Exception as exc:
            logger.warning("scene_map: cache_get raised %s — treating as miss", exc)
            cached_shots = None

        if cached_shots is not None:
            logger.info("scene_map: cache hit for job_id=%s", job_id)
            return _finalise_and_emit(
                raw_shots=cached_shots, source="cache",
                job_id=job_id, channel_code=channel_code,
                video_path=video_path, persist=persist,
                emit_fn=emit_fn,
                update_scene_map_fn=update_scene_map_fn,
                probe_metadata_fn=probe_metadata_fn,
            )

        # 2. Detector call.
        if detect_scenes_fn is None:
            detect_scenes_fn = _try_import_detect_scenes()
            if detect_scenes_fn is None:
                # PySceneDetect / TransNetV2 missing — auto-degrade.
                _emit_done(
                    emit_fn,
                    channel_code=channel_code, job_id=job_id,
                    ok=False, source="missing-dep",
                    scene_map=None,
                    message="SceneMap: detector dependencies missing — skipped",
                )
                return None

        raw_shots = None
        try:
            raw_shots = detect_scenes_fn(video_path)
        except Exception as exc:
            logger.warning("scene_map: detect_scenes raised %s", exc)
            raw_shots = None

        if not raw_shots:
            _emit_done(
                emit_fn,
                channel_code=channel_code, job_id=job_id,
                ok=False, source="failed",
                scene_map=None,
                message="SceneMap: detector returned no shots",
            )
            return None

        # 3. Cache write (best-effort).
        if cache_put_fn is None:
            from app.features.render.engine.pipeline.pipeline_cache import (
                _scene_cache_put as _cp,
            )
            cache_put_fn = _cp
        try:
            cache_put_fn(video_path, raw_shots)
        except Exception as exc:
            logger.debug("scene_map: cache_put raised %s — ignored", exc)

        return _finalise_and_emit(
            raw_shots=raw_shots, source="detect",
            job_id=job_id, channel_code=channel_code,
            video_path=video_path, persist=persist,
            emit_fn=emit_fn,
            update_scene_map_fn=update_scene_map_fn,
            probe_metadata_fn=probe_metadata_fn,
        )
    except Exception as exc:
        # Last-line catch — Sacred Contract #3.
        logger.warning("scene_map: unhandled error for job_id=%s — %s", job_id, exc)
        return None


def _finalise_and_emit(
    *,
    raw_shots: list,
    source: str,
    job_id: str,
    channel_code: str,
    video_path: str,
    persist: bool,
    emit_fn: Optional[Callable[..., None]],
    update_scene_map_fn: Optional[Callable[[str, str], None]],
    probe_metadata_fn: Optional[Callable[[str], dict]],
) -> Optional[SceneMap]:
    """Build the SceneMap dataclass, persist it (if requested), emit done."""
    # Probe fps + duration so the persisted blob records the source state
    # consumers can sanity-check against. Probe failure is non-fatal —
    # SceneMap carries 0.0 in those fields.
    fps = 0.0
    duration = 0.0
    try:
        if probe_metadata_fn is None:
            from app.features.render.engine.encoder.ffmpeg_helpers import (
                probe_video_metadata as _probe,
            )
            probe_metadata_fn = _probe
        meta = probe_metadata_fn(video_path) or {}
        fps = float(meta.get("fps") or 0.0)
        duration = float(meta.get("duration") or 0.0)
    except Exception as exc:
        logger.debug("scene_map: probe_video_metadata raised %s — defaults to 0.0", exc)

    sm = scene_map_from_detector_result(
        raw_shots, source_fps=fps, total_duration_sec=duration,
    )
    if sm.is_empty():
        _emit_done(
            emit_fn, channel_code=channel_code, job_id=job_id,
            ok=False, source="failed",
            scene_map=None,
            message="SceneMap: detector produced no usable shots",
        )
        return None

    if persist:
        if update_scene_map_fn is None:
            from app.db.jobs_repo import update_scene_map as _impl
            update_scene_map_fn = _impl
        try:
            update_scene_map_fn(job_id, sm.to_json())
        except Exception as exc:
            logger.warning("scene_map: persist failed for job_id=%s — %s", job_id, exc)

    _emit_done(
        emit_fn, channel_code=channel_code, job_id=job_id,
        ok=True, source=source,
        scene_map=sm,
        message=f"SceneMap: {sm.shot_count()} shots ({source})",
    )
    return sm


def _emit_done(
    emit_fn: Optional[Callable[..., None]],
    *,
    channel_code: str,
    job_id: str,
    ok: bool,
    source: str,
    scene_map: Optional[SceneMap],
    message: str,
) -> None:
    """Common done-event emission. Pure best-effort."""
    _safe_emit(
        emit_fn,
        channel_code=channel_code, job_id=job_id,
        event="scene_map.done",
        level=("INFO" if ok else "WARNING"),
        message=message,
        step="render.scene_map",
        context={
            "ok": ok,
            "source": source,
            "shot_count": scene_map.shot_count() if scene_map is not None else 0,
            "total_duration_sec": scene_map.total_duration_sec if scene_map is not None else 0.0,
            # Public projection of the SceneMap (entities → dicts) for UI.
            "scene_map": scene_map.to_public_dict() if scene_map is not None else None,
        },
    )
