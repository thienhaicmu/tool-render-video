"""
s08_render_parts.py — Parallel FFmpeg render cho từng segment.

Input:  FilterResult, PlanResult, ValidateResult, TranscribeResult, RenderRequest
Output: RenderPartsResult(parts: list[PartResult])

Per-part pipeline (sequential trong mỗi worker):
  CUT → SLICE_SRT → SRT_TO_ASS → RENDER_SMART → QA_CHECK

Parts chạy song song qua ThreadPoolExecutor (MAX_CONCURRENT_PARTS workers).
Partial success được giữ nguyên — không convert thành full fail.
Cancel: check giữa các future completions + giữa steps trong worker.

Delegates sang v1:
  cut_video()             app.services.render.clip_ops
  slice_srt_by_time()     app.services.subtitles.srt_core
  SRT→ASS conversion      app.services.subtitle_engine (best-effort, fallback skip)
  render_part_smart()     app.services.render.legacy_renderer
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from v2.core.constants import MAX_CONCURRENT_PARTS
from v2.core.exceptions import CancelledError
from v2.core.types import PartResult, PipelineContext, Segment
from v2.domain.render.models import RenderRequest
from v2.domain.render.stages.s01_validate import ValidateResult
from v2.domain.render.stages.s02_transcribe import TranscribeResult
from v2.domain.render.stages.s06_score_filter import FilterResult
from v2.domain.render.stages.s07_plan import PlanResult, SegmentPlan

logger = logging.getLogger("v2.render.s08_render_parts")

# Minimum output file size — smaller = truncated / corrupt
_MIN_OUTPUT_BYTES = 10_000

# Playback speed per pacing style
_PACING_SPEED = {"fast": 1.15, "medium": 1.07, "slow": 1.01, "default": 1.07}


@dataclass(frozen=True)
class RenderPartsResult:
    parts: list[PartResult]

    @property
    def success_count(self) -> int:
        return sum(1 for p in self.parts if p.is_success)

    @property
    def failed_count(self) -> int:
        return sum(1 for p in self.parts if not p.is_success)


def run(
    ctx: PipelineContext,
    filter_result: FilterResult,
    plan_result: PlanResult,
    validate_result: ValidateResult,
    transcribe_result: TranscribeResult,
    request: RenderRequest,
) -> RenderPartsResult:
    """
    Render tất cả parts song song. Partial success không bị convert thành fail.
    Raise CancelledError nếu cancel detected giữa các future completions.
    """
    ctx.check_cancel()
    segments = filter_result.ranked_segments
    logger.info(
        "s08_render_parts job_id=%s total_parts=%d workers=%d",
        ctx.job_id, len(segments), MAX_CONCURRENT_PARTS,
    )

    if not segments:
        return RenderPartsResult(parts=[])

    ctx.emit("render_parts.start", {
        "total": len(segments),
        "workers": MAX_CONCURRENT_PARTS,
    })

    request.output_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Optional[PartResult]] = [None] * len(segments)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PARTS) as executor:
        future_to_idx = {
            executor.submit(
                _render_one_part,
                ctx,
                i,
                seg,
                plan_result.per_segment.get(i),
                validate_result,
                transcribe_result,
                request,
            ): i
            for i, seg in enumerate(segments)
        }

        for future in as_completed(future_to_idx):
            # Check cancel between completions — raises CancelledError if set
            if ctx.cancel_event.is_set():
                # Cancel queued futures (running ones self-check cancel_event)
                for f in future_to_idx:
                    f.cancel()
                raise CancelledError(f"Job {ctx.job_id} cancelled during render")

            idx = future_to_idx[future]
            try:
                result = future.result()
            except Exception as exc:
                logger.warning(
                    "s08_render_parts part[%d] unexpected exception: %s", idx, exc
                )
                result = PartResult(
                    part_index=idx,
                    segment=segments[idx],
                    output_path=None,
                    is_success=False,
                    error=str(exc),
                )

            parts[idx] = result
            ctx.emit("render_parts.part_done", {
                "part_index": idx,
                "success": result.is_success,
                "error": result.error,
                "file_size": result.file_size,
            })
            logger.info(
                "s08_render_parts part[%d] %s%s",
                idx,
                "OK" if result.is_success else "FAIL",
                f" — {result.error}" if result.error else "",
            )

    # Fill any None slots (shouldn't happen, but safety)
    for i, seg in enumerate(segments):
        if parts[i] is None:
            parts[i] = PartResult(
                part_index=i, segment=seg,
                output_path=None, is_success=False, error="future missing",
            )

    final_parts: list[PartResult] = [p for p in parts if p is not None]  # type: ignore[misc]
    ctx.emit("render_parts.done", {
        "total": len(final_parts),
        "success": sum(1 for p in final_parts if p.is_success),
        "failed": sum(1 for p in final_parts if not p.is_success),
    })

    return RenderPartsResult(parts=final_parts)


# ── Per-part worker ───────────────────────────────────────────────────────────

def _render_one_part(
    ctx: PipelineContext,
    part_index: int,
    segment: Segment,
    plan: Optional[SegmentPlan],
    validate_result: ValidateResult,
    transcribe_result: TranscribeResult,
    request: RenderRequest,
) -> PartResult:
    """
    Render 1 part: CUT → SLICE_SRT → ASS → RENDER_SMART → QA.
    Không raise — luôn trả về PartResult.
    """
    t0 = time.monotonic()
    part_dir = ctx.work_dir / f"part_{part_index:02d}"
    part_dir.mkdir(parents=True, exist_ok=True)

    cut_path    = part_dir / "cut.mp4"
    part_srt    = part_dir / "part.srt"
    part_ass    = part_dir / "part.ass"
    output_path = request.output_dir / f"{ctx.job_id}_clip_{part_index:02d}.mp4"

    speed = _PACING_SPEED.get(plan.pacing.pacing_style if plan else "default", 1.07)

    try:
        # ── Step 1: Cut clip ─────────────────────────────────────────────────
        if ctx.cancel_event.is_set():
            raise CancelledError("cancelled before cut")
        _cut_clip(validate_result.source.path, cut_path, segment.start, segment.end)

        # ── Step 2: Slice SRT ────────────────────────────────────────────────
        if ctx.cancel_event.is_set():
            raise CancelledError("cancelled before srt slice")
        _slice_srt(transcribe_result.srt_path, part_srt, segment.start, segment.end, speed)

        # ── Step 3: SRT → ASS ────────────────────────────────────────────────
        ass_path: Optional[str] = None
        if request.subtitle_enabled and part_srt.exists() and part_srt.stat().st_size > 0:
            if ctx.cancel_event.is_set():
                raise CancelledError("cancelled before ass convert")
            style = plan.subtitle.style_preset if plan else "viral_bold"
            ass_path = _try_srt_to_ass(part_srt, part_ass, style)

        # ── Step 4: Render ───────────────────────────────────────────────────
        if ctx.cancel_event.is_set():
            raise CancelledError("cancelled before render")
        _render_smart(
            cut_path=cut_path,
            output_path=output_path,
            ass_path=ass_path,
            segment=segment,
            plan=plan,
            request=request,
            speed=speed,
        )

        # ── Step 5: QA check ────────────────────────────────────────────────
        if not output_path.exists():
            return PartResult(
                part_index=part_index, segment=segment,
                output_path=None, is_success=False, error="output missing",
            )
        file_size = output_path.stat().st_size
        if file_size < _MIN_OUTPUT_BYTES:
            return PartResult(
                part_index=part_index, segment=segment,
                output_path=None, is_success=False,
                error=f"output too small: {file_size} bytes",
            )

        elapsed = time.monotonic() - t0
        logger.info(
            "s08 part[%d] OK output=%s size=%d elapsed=%.1fs",
            part_index, output_path.name, file_size, elapsed,
        )
        return PartResult(
            part_index=part_index,
            segment=segment,
            output_path=output_path,
            is_success=True,
            error=None,
            duration=segment.duration,
            file_size=file_size,
        )

    except CancelledError:
        raise   # propagate cancel — caller handles it
    except Exception as exc:
        logger.warning("s08 part[%d] failed: %s", part_index, exc, exc_info=True)
        return PartResult(
            part_index=part_index, segment=segment,
            output_path=None, is_success=False, error=str(exc),
        )


# ── Step implementations ──────────────────────────────────────────────────────

def _cut_clip(source: Path, output: Path, start: float, end: float) -> None:
    """Trim source video to [start, end]. Delegates to v1 cut_video."""
    try:
        from app.services.render.clip_ops import cut_video
        cut_video(
            input_path=str(source),
            output_path=str(output),
            start_time=start,
            end_time=end,
            retry_count=1,
        )
    except ImportError:
        # Fallback: FFmpeg direct
        from v2.services.ffmpeg import execute_ffmpeg
        execute_ffmpeg([
            "-ss", str(start),
            "-to", str(end),
            "-i", str(source),
            "-c", "copy",
            "-avoid_negative_ts", "1",
            str(output),
        ])

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"cut_video produced empty output: {output}")


def _slice_srt(
    full_srt: Path,
    part_srt: Path,
    start: float,
    end: float,
    speed: float,
) -> None:
    """Extract SRT lines in [start, end], rebase to 0, adjust for playback speed."""
    try:
        from app.services.subtitles.srt_core import slice_srt_by_time
        slice_srt_by_time(
            source_srt_path=str(full_srt),
            output_srt_path=str(part_srt),
            start_sec=start,
            end_sec=end,
            rebase_to_zero=True,
            playback_speed=speed,
            apply_playback_speed=True,
        )
    except Exception as exc:
        logger.warning("s08 slice_srt thất bại: %s", exc)
        # Graceful: empty SRT — subtitles will be skipped downstream


def _try_srt_to_ass(srt_path: Path, ass_path: Path, style_preset: str) -> Optional[str]:
    """
    Convert SRT → ASS. Thử nhiều v1 entry points. Trả về path str hoặc None.
    Subtitle là optional — failure ở đây không crash render.
    """
    # Thử subtitle_engine (most likely entry point)
    for module_path, fn_name in [
        ("app.services.subtitle_engine", "generate_ass_from_srt"),
        ("app.services.subtitle_engine", "srt_to_ass"),
        ("app.services.subtitle_engine", "generate_subtitles"),
        ("app.services.subtitles.ass_core", "srt_to_ass"),
        ("app.services.subtitles.ass_builder", "build_ass_from_srt"),
    ]:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name, None)
            if fn is None:
                continue
            fn(str(srt_path), str(ass_path), style_preset=style_preset)
            if ass_path.exists() and ass_path.stat().st_size > 0:
                return str(ass_path)
        except Exception:
            continue

    logger.debug("s08 SRT→ASS conversion không khả dụng — bỏ qua subtitle")
    return None


def _render_smart(
    cut_path: Path,
    output_path: Path,
    ass_path: Optional[str],
    segment: Segment,
    plan: Optional[SegmentPlan],
    request: RenderRequest,
    speed: float,
) -> None:
    """
    Gọi v1 render_part_smart() với config từ plan. Fallback sang render_part().
    """
    cam = plan.camera if plan else None
    sub = plan.subtitle if plan else None

    motion_aware = cam is not None and cam.behavior != "none"
    reframe_mode = "subject"   # motion_crop default

    # Aspect ratio → scale
    aspect_to_scale = {"9:16": (100, 178), "3:4": (100, 133), "1:1": (100, 100)}
    scale_x, scale_y = aspect_to_scale.get(request.aspect_ratio, (100, 178))

    common_kwargs = dict(
        input_path=str(cut_path),
        output_path=str(output_path),
        subtitle_ass=ass_path,
        title_text=segment.title or None,
        aspect_ratio=request.aspect_ratio,
        scale_x=scale_x,
        scale_y=scale_y,
        add_subtitle=ass_path is not None,
        add_title_overlay=bool(segment.title),
        video_codec=request.video_codec,
        playback_speed=speed,
        retry_count=1,
    )

    try:
        from app.services.render.legacy_renderer import render_part_smart
        render_part_smart(
            **common_kwargs,
            motion_aware_crop=motion_aware,
            reframe_mode=reframe_mode,
        )
        return
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("s08 render_part_smart thất bại: %s — thử render_part", exc)

    # Fallback: render_part (no motion crop)
    try:
        from app.services.render.legacy_renderer import render_part
        render_part(**common_kwargs)
        return
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("s08 render_part thất bại: %s — thử FFmpeg direct", exc)

    # Last resort: FFmpeg direct cut (no effects, no subtitles)
    _render_ffmpeg_direct(cut_path, output_path, request.video_codec)


def _render_ffmpeg_direct(
    input_path: Path,
    output_path: Path,
    codec: str,
) -> None:
    """
    Minimal FFmpeg encode — không có effect, không subtitle.
    Chỉ dùng khi cả render_part_smart lẫn render_part đều không chạy được.
    """
    from v2.services.ffmpeg import execute_ffmpeg
    vcodec = "libx264" if codec == "h264" else codec
    execute_ffmpeg([
        "-i", str(input_path),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v", vcodec,
        "-crf", "22",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ])
