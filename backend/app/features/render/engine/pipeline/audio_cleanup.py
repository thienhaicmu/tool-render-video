from __future__ import annotations

import logging
import os
from pathlib import Path

from app.models.schemas import RenderRequest
from app.features.render.engine.pipeline.render_events import _job_log, _safe_unlink
from app.features.render.engine.audio.cleanup_adapters import cleanup_audio_with_adapter

logger = logging.getLogger("app.render")


def _maybe_cleanup_narration_audio(
    narration_audio_path: str,
    payload: RenderRequest,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int | None = None,
    source: str = "manual",
) -> str:
    engine = str(getattr(payload, "audio_cleanup_engine", "none") or "none").strip().lower()

    # OQ-2.1: Auto-upgrade "none" â†’ "deepfilternet" when package is installed.
    # AUDIO_CLEANUP_AUTO=0 opts out. Explicit payload value always wins (including "none").
    if engine == "none" and os.environ.get("AUDIO_CLEANUP_AUTO", "1") == "1":
        from app.features.render.ai.dependencies import has_deepfilternet as _has_dfn
        if _has_dfn():
            engine = "deepfilternet"

    if engine == "none":
        return narration_audio_path

    input_path = Path(narration_audio_path)
    cleaned_path = input_path.with_name(f"{input_path.stem}.cleaned{input_path.suffix}")
    context = f"part_no={part_no} " if part_no is not None else ""
    _job_log(
        effective_channel,
        job_id,
        f"audio_cleanup_requested {context}source={source} audio_cleanup_engine={engine}",
    )
    try:
        result = cleanup_audio_with_adapter(
            str(input_path),
            str(cleaned_path),
            engine=engine,
            logger=logger,
        )
    except Exception as exc:
        _job_log(
            effective_channel,
            job_id,
            f"audio_cleanup_failed {context}source={source} audio_cleanup_engine={engine} "
            f"audio_cleanup_warning={type(exc).__name__}",
            kind="warning",
        )
        _safe_unlink(cleaned_path)
        return narration_audio_path

    candidate = Path(result.output_path) if result.applied and result.output_path else None
    if candidate and candidate.exists() and candidate.stat().st_size > 0:
        _job_log(
            effective_channel,
            job_id,
            f"audio_cleanup_applied {context}source={source} audio_cleanup_engine={engine} "
            f"elapsed_ms={result.elapsed_ms}",
        )
        return str(candidate)

    warning = ",".join(result.warnings) if result.warnings else "audio_cleanup_not_applied"
    _job_log(
        effective_channel,
        job_id,
        f"audio_cleanup_failed {context}source={source} audio_cleanup_engine={engine} "
        f"audio_cleanup_warning={warning}",
        kind="warning",
    )
    if cleaned_path != input_path:
        _safe_unlink(cleaned_path)
    return narration_audio_path
