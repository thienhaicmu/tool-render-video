"""
s05_scene_detect.py — Scene detection CHỈ trên segments đã chọn.

Input:  GroqSelectResult (segments), ValidateResult (source path)
Output: SceneResult(per_segment_cuts: dict[int, list[float]], from_detector: bool)

Strategy:
  Chạy detect_scenes() 1 lần trên toàn video (OpenCV, lightweight),
  sau đó filter scene cuts theo time window của từng segment.

  Lý do không extract clip trước: detect_scenes() là OpenCV frame diff,
  nhanh hơn FFmpeg extraction + re-encode overhead cho clip ngắn.

  Nếu v1 detect_scenes không khả dụng → trả về per_segment_cuts rỗng,
  pipeline tiếp tục bình thường (scene data là optional).

Local only — không gọi cloud API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from v2.core.types import PipelineContext, Segment
from v2.domain.render.stages.s01_validate import ValidateResult
from v2.domain.render.stages.s03_groq_select import GroqSelectResult

logger = logging.getLogger("v2.render.s05_scene_detect")

# detect_scenes trên video dài có thể mất vài giây — log nếu vượt ngưỡng này
_SLOW_THRESHOLD_SEC = 30.0


@dataclass(frozen=True)
class SceneResult:
    """
    Scene cuts (timestamps tính từ đầu video gốc) trong time window của từng segment.
    Key = index trong segments list của GroqSelectResult.
    all_cuts: raw output của detect_scenes() — dùng cho local scorer ở s06 khi Groq disabled.
    """
    per_segment_cuts: dict[int, list[float]]
    all_cuts:         list[dict] = field(default_factory=list)
    from_detector:    bool = False   # False = v1 detect_scenes không chạy được


def run(
    ctx: PipelineContext,
    groq_result: GroqSelectResult,
    validate_result: ValidateResult,
) -> SceneResult:
    """
    Detect scene cuts rồi map về từng segment. Không raise — trả về empty nếu thất bại.
    """
    ctx.check_cancel()
    segments = groq_result.segments
    logger.info("s05_scene_detect job_id=%s segments=%d", ctx.job_id, len(segments))

    if not segments:
        return SceneResult(per_segment_cuts={})

    ctx.emit("scene_detect.start", {
        "segments": len(segments),
        "source": validate_result.source.path.name,
    })

    # Chạy detect_scenes 1 lần trên toàn video
    all_cuts = _run_detect_scenes(validate_result.source.path)
    if all_cuts is None:
        logger.info("s05_scene_detect: detect_scenes không khả dụng — bỏ qua")
        return SceneResult(per_segment_cuts={seg_idx: [] for seg_idx in range(len(segments))})

    # Filter cuts về từng segment time window
    per_segment_cuts: dict[int, list[float]] = {}
    for i, seg in enumerate(segments):
        ctx.check_cancel()
        cuts_in_window = [
            cut["start"]
            for cut in all_cuts
            if seg.start <= cut["start"] <= seg.end
        ]
        per_segment_cuts[i] = cuts_in_window
        logger.debug(
            "s05_scene_detect seg[%d] %.1f–%.1f → %d cuts",
            i, seg.start, seg.end, len(cuts_in_window),
        )

    total_cuts = sum(len(v) for v in per_segment_cuts.values())
    ctx.emit("scene_detect.done", {
        "total_scene_cuts": len(all_cuts),
        "cuts_in_segments": total_cuts,
        "segments": len(segments),
    })
    logger.info(
        "s05_scene_detect done job_id=%s total_cuts=%d in_segments=%d",
        ctx.job_id, len(all_cuts), total_cuts,
    )

    return SceneResult(per_segment_cuts=per_segment_cuts, all_cuts=all_cuts, from_detector=True)


# ── Internal ──────────────────────────────────────────────────────────────────

def _run_detect_scenes(source_path: Path) -> list[dict] | None:
    """
    Import lazy và gọi v1 detect_scenes(). Trả về list[{start, end, transition_score}]
    hoặc None nếu module không khả dụng / lỗi.
    """
    try:
        from app.services.scene_detector import detect_scenes
    except ImportError:
        logger.debug("s05_scene_detect: scene_detector module không khả dụng")
        return None

    import time
    t0 = time.monotonic()

    try:
        result = detect_scenes(video_path=str(source_path))
    except Exception as exc:
        logger.warning("s05_scene_detect: detect_scenes thất bại: %s", exc)
        return None

    elapsed = time.monotonic() - t0
    if elapsed > _SLOW_THRESHOLD_SEC:
        logger.warning(
            "s05_scene_detect: detect_scenes mất %.1fs (> %.0fs threshold)",
            elapsed, _SLOW_THRESHOLD_SEC,
        )
    else:
        logger.debug("s05_scene_detect: detect_scenes %.1fs → %d cuts", elapsed, len(result))

    return result or []
