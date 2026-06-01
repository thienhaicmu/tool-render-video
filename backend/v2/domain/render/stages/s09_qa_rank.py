"""
s09_qa_rank.py — QA validation + ranking + result_json.

Input:  RenderPartsResult, RenderRequest
Output: QaRankResult

QA kiểm tra từng output:
  1. File tồn tại và size >= MIN_OUTPUT_FILE_BYTES (1 MB)
  2. Có video stream (ffprobe)
  3. Có audio stream (ffprobe)
  4. Duration >= MIN_OUTPUT_DURATION_SEC (3.0s)

QA validation dùng v2's own probe_video() — không bypass, không swallow.
Mọi file fail QA bị loại khỏi success_parts.

Ranking (0–100):
  60 pts — segment.score (Groq/local confidence)
  15 pts — file quality (size-based proxy)
  15 pts — duration sweet spot (25–45s optimal for short-form)
  10 pts — QA passed bonus

Sacred Contract (CLAUDE.md Contract 1):
  output_rank_score, is_best_output, is_best_clip PHẢI có trong mỗi RankedOutput.
  is_best_output: True cho 1 output duy nhất có score cao nhất và QA passed.
  is_best_clip:   True cho cùng output (v2 không có cross-job tracking).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from v2.core.constants import MIN_OUTPUT_FILE_BYTES, MIN_OUTPUT_DURATION_SEC
from v2.core.types import PartResult, PipelineContext
from v2.domain.render.models import RenderRequest
from v2.domain.render.stages.s08_render_parts import RenderPartsResult
from v2.services.ffmpeg import probe_video

logger = logging.getLogger("v2.render.s09_qa_rank")

# File size thresholds for quality score
_SIZE_FULL_SCORE_MB = 3.0    # >= 3 MB → full quality score
_SIZE_QUALITY_PTS   = 15.0

# Duration sweet spot (giây)
_DUR_SWEET_MIN = 25.0
_DUR_SWEET_MAX = 45.0
_DUR_PTS       = 15.0

_SCORE_PTS     = 60.0
_QA_BONUS_PTS  = 10.0


@dataclass(frozen=True)
class RankedOutput:
    """
    Kết quả QA + rank của 1 part. Sacred Contract: 3 field bắt buộc phải tồn tại.
    """
    part:              PartResult
    output_rank_score: float        # 0.0–100.0
    is_best_output:    bool         # Sacred Contract field 1
    is_best_clip:      bool         # Sacred Contract field 2
    qa_passed:         bool
    qa_reason:         str = ""     # lý do fail QA (rỗng nếu passed)


@dataclass(frozen=True)
class QaRankResult:
    ranked_outputs:  list[RankedOutput]
    best_output:     Optional[Path]
    total_parts:     int
    success_parts:   int     # QA passed
    failed_parts:    int     # render fail + QA fail
    qa_failed_parts: int     # subset of failed: rendered OK nhưng fail QA probe


def run(
    ctx: PipelineContext,
    parts_result: RenderPartsResult,
    request: RenderRequest,
) -> QaRankResult:
    """
    Validate và rank tất cả outputs. Không raise.

    Không bao giờ bypass QA gate — CLAUDE.md Contract 8.
    Corrupt / missing outputs được mark failed, không được deliver as success.
    """
    ctx.check_cancel()
    parts = parts_result.parts
    logger.info(
        "s09_qa_rank job_id=%s total=%d success=%d failed=%d",
        ctx.job_id, len(parts), parts_result.success_count, parts_result.failed_count,
    )

    ctx.emit("qa_rank.start", {"total": len(parts)})

    # ── QA validate từng part ──────────────────────────────────────────────────
    scored: list[tuple[float, RankedOutput]] = []   # (score, output) — trước khi mark best
    qa_failed_count = 0

    for part in parts:
        if not part.is_success or part.output_path is None:
            # Render đã fail ở s08 — không cần QA probe
            output = RankedOutput(
                part=part,
                output_rank_score=0.0,
                is_best_output=False,
                is_best_clip=False,
                qa_passed=False,
                qa_reason=part.error or "render_failed",
            )
            scored.append((0.0, output))
            continue

        ctx.check_cancel()
        qa_passed, qa_reason, probe = _qa_probe(part.output_path)

        if not qa_passed:
            qa_failed_count += 1
            logger.warning(
                "s09_qa_rank part[%d] QA FAIL: %s path=%s",
                part.part_index, qa_reason, part.output_path,
            )
            output = RankedOutput(
                part=part,
                output_rank_score=0.0,
                is_best_output=False,
                is_best_clip=False,
                qa_passed=False,
                qa_reason=qa_reason,
            )
            scored.append((0.0, output))
            continue

        rank_score = _compute_rank_score(part, probe)
        logger.debug(
            "s09_qa_rank part[%d] QA OK rank_score=%.1f",
            part.part_index, rank_score,
        )
        output = RankedOutput(
            part=part,
            output_rank_score=rank_score,
            is_best_output=False,    # set below after sorting
            is_best_clip=False,
            qa_passed=True,
            qa_reason="",
        )
        scored.append((rank_score, output))

    # ── Mark best output (highest score, QA passed) ────────────────────────────
    passed = [(s, o) for s, o in scored if o.qa_passed]
    best_path: Optional[Path] = None

    if passed:
        best_score, best_out = max(passed, key=lambda x: x[0])
        best_path = best_out.part.output_path

        # Rebuild with is_best_output=True, is_best_clip=True for the winner
        scored = [
            (s, _set_best(o, o is best_out))
            for s, o in scored
        ]
        logger.info(
            "s09_qa_rank best_output part[%d] score=%.1f path=%s",
            best_out.part.part_index, best_score, best_path,
        )

    # ── Sort by rank score descending (QA passed first, then failed) ───────────
    scored.sort(key=lambda x: (x[1].qa_passed, x[0]), reverse=True)
    ranked_outputs = [o for _, o in scored]

    success_parts = sum(1 for o in ranked_outputs if o.qa_passed)
    failed_parts  = len(ranked_outputs) - success_parts

    ctx.emit("qa_rank.done", {
        "total": len(ranked_outputs),
        "success": success_parts,
        "failed": failed_parts,
        "qa_failed": qa_failed_count,
        "best_score": max((o.output_rank_score for o in ranked_outputs), default=0.0),
    })
    logger.info(
        "s09_qa_rank done job_id=%s success=%d failed=%d qa_failed=%d",
        ctx.job_id, success_parts, failed_parts, qa_failed_count,
    )

    return QaRankResult(
        ranked_outputs=ranked_outputs,
        best_output=best_path,
        total_parts=len(ranked_outputs),
        success_parts=success_parts,
        failed_parts=failed_parts,
        qa_failed_parts=qa_failed_count,
    )


# ── QA probe ──────────────────────────────────────────────────────────────────

def _qa_probe(output_path: Path) -> tuple[bool, str, object]:
    """
    Kiểm tra output file bằng ffprobe. Trả về (passed, reason, probe_result).
    Không bypass: mọi fail đều được report thật.
    """
    # 1. File tồn tại
    if not output_path.exists():
        return False, "file_missing", None

    # 2. File size >= 1 MB
    size = output_path.stat().st_size
    if size < MIN_OUTPUT_FILE_BYTES:
        return False, f"file_too_small:{size}bytes", None

    # 3. Probe với ffprobe
    try:
        probe = probe_video(output_path)
    except Exception as exc:
        return False, f"probe_failed:{exc}", None

    # 4. Có video stream
    if not probe.has_video:
        return False, "no_video_stream", probe

    # 5. Có audio stream
    if not probe.has_audio:
        return False, "no_audio_stream", probe

    # 6. Duration >= 3.0s
    if probe.duration < MIN_OUTPUT_DURATION_SEC:
        return False, f"duration_too_short:{probe.duration:.2f}s", probe

    return True, "", probe


# ── Ranking ───────────────────────────────────────────────────────────────────

def _compute_rank_score(part: PartResult, probe) -> float:
    """
    Tính output_rank_score (0–100).
    Probe có thể là None nếu ffprobe thất bại nhưng file vẫn pass basic checks.
    """
    score = 0.0

    # 60 pts — segment confidence score
    score += part.segment.score * _SCORE_PTS

    # 15 pts — file quality (size proxy)
    size_mb = (part.file_size or 0) / 1_000_000
    score += min(_SIZE_QUALITY_PTS, (size_mb / _SIZE_FULL_SCORE_MB) * _SIZE_QUALITY_PTS)

    # 15 pts — duration sweet spot
    dur = probe.duration if probe else part.segment.duration
    if _DUR_SWEET_MIN <= dur <= _DUR_SWEET_MAX:
        score += _DUR_PTS
    elif dur < _DUR_SWEET_MIN and _DUR_SWEET_MIN > 0:
        score += _DUR_PTS * (dur / _DUR_SWEET_MIN)
    else:  # dur > _DUR_SWEET_MAX
        excess = dur - _DUR_SWEET_MAX
        score += _DUR_PTS * max(0.0, 1.0 - excess / 60.0)

    # 10 pts — QA passed bonus (always True here, called only on passed parts)
    score += _QA_BONUS_PTS

    return round(min(100.0, score), 2)


def _set_best(output: RankedOutput, is_best: bool) -> RankedOutput:
    """Return new RankedOutput với is_best_output/is_best_clip set."""
    return RankedOutput(
        part=output.part,
        output_rank_score=output.output_rank_score,
        is_best_output=is_best,
        is_best_clip=is_best,   # v2: same as is_best_output
        qa_passed=output.qa_passed,
        qa_reason=output.qa_reason,
    )
