"""
memory_writer.py — Write render results into the persistent AI memory store.

Called after render finalization. Never raises — failures are logged and
rendering continues normally.

Public API:
    write_render_memory(result_json, context=None) -> bool
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger("app.ai.rag.memory_writer")

# Statuses worth storing (both successes and errors provide learning signal).
_STORE_STATUSES = {"completed", "completed_with_errors"}


def write_render_memory(
    result_json: dict,
    context: Optional[dict] = None,
) -> bool:
    """Summarize and persist a render result into the AI memory store.

    Returns True if saved, False on any failure. Never raises.
    """
    try:
        return _write(result_json, dict(context or {}))
    except Exception as exc:
        logger.warning("memory_writer_unexpected_error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _write(result_json: dict, context: dict) -> bool:
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    from app.ai.rag.memory_schema import RenderMemory
    from app.ai.rag.embeddings import embed_text, is_embedding_available

    ai_plan = result_json.get("ai_director") or {}
    status = _resolve_status(result_json)
    market = _clean_str(context.get("market"))
    mode = _clean_str(ai_plan.get("mode") or context.get("mode")) or "unknown"
    duration = _safe_float(context.get("duration") or result_json.get("duration"))
    output_score = _resolve_output_score(result_json)
    subtitle_tone = _clean_str((ai_plan.get("subtitle") or {}).get("tone"))
    camera_behavior = _clean_str((ai_plan.get("camera") or {}).get("behavior"))

    text = _build_summary_text(
        market=market,
        mode=mode,
        status=status,
        output_score=output_score,
        subtitle_tone=subtitle_tone,
        camera_behavior=camera_behavior,
        duration=duration,
    )

    memory = RenderMemory(
        id=f"render-{uuid.uuid4().hex[:12]}",
        text=text,
        market=market or None,
        mode=mode,
        duration=duration,
        score=output_score,
        subtitle_tone=subtitle_tone or None,
        camera_behavior=camera_behavior or None,
        status=status,
        metadata={
            "successful_outputs": int(result_json.get("successful_outputs_count") or 0),
            "failed_outputs": int(result_json.get("failed_outputs_count") or 0),
            "is_partial_success": bool(result_json.get("is_partial_success")),
        },
    )

    vector: Optional[list[float]] = None
    if is_embedding_available():
        vector = embed_text(text)

    store = SQLiteMemoryStore()
    if not store.initialize():
        logger.debug("memory_writer_sqlite_unavailable: skipping persist")
        return False

    saved = store.add_memory(memory, vector=vector)
    if saved:
        logger.info(
            "memory_writer_saved id=%s status=%s mode=%s score=%s",
            memory.id, status, mode, output_score,
        )
    return saved


def _resolve_status(result_json: dict) -> str:
    if int(result_json.get("failed_outputs_count") or 0) > 0:
        return "completed_with_errors"
    if int(result_json.get("successful_outputs_count") or 0) > 0:
        return "completed"
    return "unknown"


def _resolve_output_score(result_json: dict) -> Optional[float]:
    try:
        best = result_json.get("best_clip") or {}
        if best:
            s = best.get("output_score") or best.get("viral_score")
            if s is not None:
                return float(s)
        for entry in list(result_json.get("output_ranking") or []):
            s = entry.get("output_score") or entry.get("score")
            if s is not None:
                return float(s)
    except Exception:
        pass
    return None


def _build_summary_text(
    market: Optional[str],
    mode: str,
    status: str,
    output_score: Optional[float],
    subtitle_tone: Optional[str],
    camera_behavior: Optional[str],
    duration: Optional[float],
) -> str:
    parts: list[str] = []

    if market:
        parts.append(market)
    if mode and mode != "unknown":
        parts.append(mode)
    parts.append("render")

    if subtitle_tone:
        parts.append(f"with {subtitle_tone} subtitles")

    if status == "completed":
        parts.append("completed successfully")
    elif status == "completed_with_errors":
        parts.append("completed with errors")

    if output_score is not None:
        parts.append(f"scored {output_score:.1f}")

    if duration:
        parts.append(f"duration {int(duration)}s")

    if camera_behavior:
        parts.append(f"camera {camera_behavior}")

    return " ".join(parts) + "."


def _clean_str(val: Any) -> Optional[str]:
    s = str(val).strip() if val is not None else ""
    return s or None


def _safe_float(val: Any) -> Optional[float]:
    try:
        v = float(val)
        return v if v > 0 else None
    except Exception:
        return None
