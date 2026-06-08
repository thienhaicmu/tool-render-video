"""Post-render quality assessor.

assess_rendered_part_quality() — offline, deterministic, fail-safe, non-blocking.

Rules:
- NEVER raises (all exceptions caught internally)
- NEVER auto-regenerates videos
- NEVER changes FFmpeg commands
- Subjective/heuristic checks → WARNING only
- Hard failures (missing file, zero bytes) → already handled by _validate_render_output;
  we duplicate critical checks here so standalone callers also get correct results
- Does NOT make existing QA fail
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from app.features.render.engine.quality.models import QualityIssue, QualityReport
from app.features.render.engine.encoder.ffmpeg_helpers import probe_video_metadata
from app.services.bin_paths import get_ffmpeg_bin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_AI_TRACE_RELEVANT_EVENTS = frozenset({
    "ai.pacing_applied",
    "ai.subtitle_emphasis_applied",
    "ai.visual_intensity_applied",
    "ai.execution_hints",
    "ai.decision_rejected",
    "ai.validation_fixup",
})

# Duration mismatch tolerance: max(10% of expected, 2 seconds)
_DURATION_TOLERANCE_FRACTION = 0.10
_DURATION_TOLERANCE_MIN_SEC = 2.0

# Subtitle density thresholds
_SUBTITLE_MAX_WPS = 3.5          # words per second
_SUBTITLE_MAX_CHARS_PER_LINE = 42
_SUBTITLE_MIN_DISPLAY_SEC = 0.5  # flash threshold
_SUBTITLE_FLASH_RATIO = 0.30     # >30% flash blocks → density_overload error

# Pacing risk thresholds
_PACING_VERY_SHORT_SEC = 3.0
_PACING_VERY_LONG_SEC = 300.0

# Hook risk thresholds
_HOOK_MAX_DELAY_SEC = 5.0
_HOOK_MAX_FIRST_WORDS = 15


def _make_issue(
    code: str,
    severity: str,
    message: str,
    confidence: float,
    part_no: int | None = None,
    evidence: dict | None = None,
    recommended_action: str | None = None,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity=severity,
        message=message,
        confidence=confidence,
        part_no=part_no,
        evidence=evidence or {},
        recommended_action=recommended_action,
    )


def assess_rendered_part_quality(
    video_path: Path,
    part_no: int | None = None,
    job_id: str | None = None,
    srt_path: Path | None = None,
    manifest_path: Path | None = None,
    ai_trace_path: Path | None = None,
) -> QualityReport:
    """Assess quality of a rendered video part.

    Never raises. Returns a QualityReport with score, issues, and metrics.
    All assessment categories are individually wrapped in try/except so a
    failure in one category does not abort the rest.
    """
    report = QualityReport(job_id=job_id, part_no=part_no)

    # ------------------------------------------------------------------
    # 1. FILE INTEGRITY
    # ------------------------------------------------------------------
    try:
        if not video_path.exists():
            report.add_issue(_make_issue(
                code="missing_output",
                severity="critical",
                message=f"Rendered output file does not exist: {video_path}",
                confidence=1.0,
                part_no=part_no,
                recommended_action="Check render pipeline for failures before this step.",
            ))
            return report  # early exit — no point probing

        size = video_path.stat().st_size
        report.metrics["file_size_bytes"] = size

        if size == 0:
            report.add_issue(_make_issue(
                code="zero_byte_output",
                severity="critical",
                message=f"Rendered output file is zero bytes: {video_path}",
                confidence=1.0,
                part_no=part_no,
                evidence={"size_bytes": size},
                recommended_action="Check FFmpeg output and disk space.",
            ))
            return report  # early exit

    except Exception as exc:
        logger.warning("quality_assessor: file integrity check failed: %s", exc)
        report.add_issue(_make_issue(
            code="file_integrity_error",
            severity="error",
            message=f"Could not verify file integrity: {exc}",
            confidence=0.8,
            part_no=part_no,
        ))
        return report

    # ------------------------------------------------------------------
    # 2. VIDEO PROBE
    # ------------------------------------------------------------------
    probe_result: dict | None = None
    actual_duration: float | None = None

    try:
        probe_result = probe_video_metadata(str(video_path))
        actual_duration = probe_result.get("duration")
        if actual_duration is not None:
            report.metrics["actual_duration"] = float(actual_duration)

        if not probe_result.get("has_video") and actual_duration is None:
            # Probe returned empty/failed result
            report.add_issue(_make_issue(
                code="probe_failed",
                severity="error",
                message="ffprobe could not read the rendered output (probe returned no data).",
                confidence=0.7,
                part_no=part_no,
                recommended_action="Verify FFmpeg installation and output file integrity.",
            ))
    except Exception as exc:
        logger.warning("quality_assessor: probe failed: %s", exc)
        report.add_issue(_make_issue(
            code="probe_failed",
            severity="error",
            message=f"ffprobe error during quality assessment: {exc}",
            confidence=0.7,
            part_no=part_no,
        ))

    # ------------------------------------------------------------------
    # 3. AUDIO STREAM
    # ------------------------------------------------------------------
    try:
        if probe_result is not None:
            has_audio = probe_result.get("has_audio", False)
            report.metrics["has_audio"] = bool(has_audio)
            if not has_audio:
                report.add_issue(_make_issue(
                    code="no_audio_stream",
                    severity="warning",
                    message="Rendered output has no audio stream — video may be silent.",
                    confidence=0.95,
                    part_no=part_no,
                    recommended_action="Check source audio and mix settings.",
                ))
    except Exception as exc:
        logger.warning("quality_assessor: audio stream check failed: %s", exc)

    # ------------------------------------------------------------------
    # 4. DURATION CHECK (manifest-based)
    # ------------------------------------------------------------------
    try:
        if manifest_path is not None and manifest_path.exists() and actual_duration is not None:
            raw = manifest_path.read_text(encoding="utf-8")
            manifest_data = json.loads(raw)
            # BaseClipManifest stores source_start/source_end; derive expected duration
            # from the timeline if present, otherwise from source_end - source_start
            expected_duration: float | None = None
            timeline = manifest_data.get("timeline")
            if isinstance(timeline, dict):
                # timeline may have output_duration or total_output_duration
                for key in ("output_duration", "total_output_duration", "duration"):
                    v = timeline.get(key)
                    if v is not None:
                        try:
                            expected_duration = float(v)
                            break
                        except (TypeError, ValueError):
                            pass
            if expected_duration is None:
                src_start = manifest_data.get("source_start")
                src_end = manifest_data.get("source_end")
                if src_start is not None and src_end is not None:
                    speed = float(manifest_data.get("effective_speed") or 1.0)
                    expected_duration = (float(src_end) - float(src_start)) / max(0.1, speed)

            if expected_duration is not None and expected_duration > 0:
                tolerance = max(_DURATION_TOLERANCE_MIN_SEC,
                                expected_duration * _DURATION_TOLERANCE_FRACTION)
                diff = abs(actual_duration - expected_duration)
                report.metrics["expected_duration"] = expected_duration
                report.metrics["duration_diff"] = round(diff, 3)
                report.metrics["duration_tolerance"] = round(tolerance, 3)
                if diff > tolerance:
                    report.add_issue(_make_issue(
                        code="duration_mismatch",
                        severity="error",
                        message=(
                            f"Duration mismatch: actual={actual_duration:.2f}s, "
                            f"expected={expected_duration:.2f}s, "
                            f"diff={diff:.2f}s (tolerance={tolerance:.2f}s)"
                        ),
                        confidence=0.9,
                        part_no=part_no,
                        evidence={
                            "actual_duration": actual_duration,
                            "expected_duration": expected_duration,
                            "tolerance": tolerance,
                        },
                    ))
    except Exception as exc:
        logger.warning("quality_assessor: duration check failed: %s", exc)

    # ------------------------------------------------------------------
    # 5. FIRST FRAME QUALITY
    # ------------------------------------------------------------------
    try:
        if actual_duration is not None and actual_duration < 0.5:
            report.add_issue(_make_issue(
                code="very_short_output",
                severity="warning",
                message=f"Output is extremely short: {actual_duration:.2f}s (<0.5s).",
                confidence=0.95,
                part_no=part_no,
                evidence={"actual_duration": actual_duration},
            ))
    except Exception as exc:
        logger.warning("quality_assessor: very_short check failed: %s", exc)

    # Re-use the dark/blur detection already implemented in qa_pipeline._assess_output_quality.
    # We call ffmpeg blackdetect/blurdetect directly here (same logic, non-fatal).
    try:
        _bdet_cmd = [
            get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-t", "0.5", "-i", str(video_path),
            "-vf", "blackdetect=d=0.0:pix_th=0.10",
            "-an", "-f", "null", "-",
        ]
        _bdet_r = subprocess.run(_bdet_cmd, capture_output=True, text=True, timeout=10)
        _dark_detected = False
        for _line in (_bdet_r.stderr or "").splitlines():
            if "black_start:" not in _line or "black_end:" not in _line:
                continue
            try:
                _b_start = _b_end = None
                for _tok in _line.split():
                    if _tok.startswith("black_start:"):
                        _b_start = float(_tok.split(":", 1)[1])
                    elif _tok.startswith("black_end:"):
                        _b_end = float(_tok.split(":", 1)[1])
                if _b_start is not None and _b_end is not None and _b_start <= 0.08 and _b_end > 0.12:
                    _dark_detected = True
            except (ValueError, IndexError):
                continue
        if _dark_detected:
            report.add_issue(_make_issue(
                code="first_frame_dark",
                severity="warning",
                message="First frame appears dark (blackdetect triggered on first 0.5s).",
                confidence=0.65,
                part_no=part_no,
                recommended_action="Check source clip or intro transition.",
            ))
        report.metrics["first_frame_dark"] = _dark_detected
    except Exception as exc:
        logger.debug("quality_assessor: dark frame check failed (non-fatal): %s", exc)

    try:
        _blur_cmd = [
            get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-t", "0.5", "-i", str(video_path),
            "-vf", "blurdetect=high=0.35:low=0.25",
            "-an", "-f", "null", "-",
        ]
        _blur_r = subprocess.run(_blur_cmd, capture_output=True, text=True, timeout=10)
        _blur_vals: list[float] = []
        for _bl_line in (_blur_r.stderr or "").splitlines():
            if "blur:" not in _bl_line.lower():
                continue
            try:
                _val_str = _bl_line.split("blur:")[-1].strip().split()[0]
                _blur_vals.append(float(_val_str))
            except (ValueError, IndexError):
                continue
        if _blur_vals:
            _avg_blur = sum(_blur_vals) / len(_blur_vals)
            report.metrics["first_frame_blur_score"] = round(_avg_blur, 3)
            if _avg_blur > 0.60:
                report.add_issue(_make_issue(
                    code="first_frame_blurry",
                    severity="warning",
                    message=f"First frames appear blurry (avg_blur={_avg_blur:.2f}).",
                    confidence=0.60,
                    part_no=part_no,
                    evidence={"avg_blur": round(_avg_blur, 3)},
                ))
    except Exception as exc:
        logger.debug("quality_assessor: blur check failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # 6. SUBTITLE DENSITY (if srt_path provided)
    # ------------------------------------------------------------------
    try:
        if srt_path is not None and srt_path.exists():
            _assess_subtitle_density(report, srt_path, part_no)
    except Exception as exc:
        logger.warning("quality_assessor: subtitle density check failed: %s", exc)

    # ------------------------------------------------------------------
    # 7. HOOK RISK (if srt_path provided)
    # ------------------------------------------------------------------
    try:
        if srt_path is not None and srt_path.exists():
            _assess_hook_risk(report, srt_path, part_no)
    except Exception as exc:
        logger.warning("quality_assessor: hook risk check failed: %s", exc)

    # ------------------------------------------------------------------
    # 8. PACING RISK
    # ------------------------------------------------------------------
    try:
        if actual_duration is not None:
            if actual_duration < _PACING_VERY_SHORT_SEC:
                report.add_issue(_make_issue(
                    code="very_short_part",
                    severity="warning",
                    message=f"Part duration is very short: {actual_duration:.2f}s (< {_PACING_VERY_SHORT_SEC}s).",
                    confidence=0.9,
                    part_no=part_no,
                    evidence={"actual_duration": actual_duration},
                ))
            elif actual_duration > _PACING_VERY_LONG_SEC:
                report.add_issue(_make_issue(
                    code="very_long_part",
                    severity="warning",
                    message=f"Part duration is very long: {actual_duration:.2f}s (> {_PACING_VERY_LONG_SEC}s).",
                    confidence=0.85,
                    part_no=part_no,
                    evidence={"actual_duration": actual_duration},
                ))
    except Exception as exc:
        logger.warning("quality_assessor: pacing risk check failed: %s", exc)

    # ------------------------------------------------------------------
    # 9. AI TRACE CORRELATION (if ai_trace_path provided)
    # ------------------------------------------------------------------
    try:
        if ai_trace_path is not None:
            _assess_ai_trace_correlation(report, ai_trace_path)
    except Exception as exc:
        logger.debug("quality_assessor: ai trace correlation failed (non-fatal): %s", exc)

    return report


def _assess_subtitle_density(
    report: QualityReport,
    srt_path: Path,
    part_no: int | None,
) -> None:
    """Analyse subtitle blocks for density issues. Modifies report in place."""
    from app.features.render.engine.subtitle.generator.srt import _parse_srt_blocks

    try:
        blocks = _parse_srt_blocks(str(srt_path))
    except Exception as exc:
        logger.warning("quality_assessor: srt parse failed: %s", exc)
        return

    if not blocks:
        return

    total_blocks = len(blocks)
    flash_count = 0
    too_fast_count = 0
    line_too_long_count = 0

    for b in blocks:
        try:
            start = float(b.get("start", 0))
            end = float(b.get("end", 0))
            text = str(b.get("text", ""))
            display_duration = end - start

            if display_duration <= 0:
                continue

            # words per second
            word_count = len(text.split())
            wps = word_count / display_duration if display_duration > 0 else 0.0

            # max chars per line
            lines = text.split("\n")
            max_chars = max((len(line) for line in lines), default=0)

            # flash block (<0.5s)
            if display_duration < _SUBTITLE_MIN_DISPLAY_SEC:
                flash_count += 1
                report.add_issue(_make_issue(
                    code="subtitle_flash",
                    severity="warning",
                    message=(
                        f"Subtitle block displays for only {display_duration:.2f}s "
                        f"(min {_SUBTITLE_MIN_DISPLAY_SEC}s): \"{text[:40]}\""
                    ),
                    confidence=0.9,
                    part_no=part_no,
                    evidence={"display_duration": display_duration, "text_preview": text[:40]},
                ))

            # too fast speech
            if wps > _SUBTITLE_MAX_WPS:
                too_fast_count += 1
                report.add_issue(_make_issue(
                    code="subtitle_too_fast",
                    severity="warning",
                    message=(
                        f"Subtitle reads at {wps:.1f} wps "
                        f"(max {_SUBTITLE_MAX_WPS}): \"{text[:40]}\""
                    ),
                    confidence=0.85,
                    part_no=part_no,
                    evidence={"wps": round(wps, 2), "display_duration": display_duration},
                ))

            # line too long
            if max_chars > _SUBTITLE_MAX_CHARS_PER_LINE:
                line_too_long_count += 1
                report.add_issue(_make_issue(
                    code="subtitle_line_too_long",
                    severity="warning",
                    message=(
                        f"Subtitle line is {max_chars} chars "
                        f"(max {_SUBTITLE_MAX_CHARS_PER_LINE}): \"{text[:40]}\""
                    ),
                    confidence=0.8,
                    part_no=part_no,
                    evidence={"max_chars_per_line": max_chars},
                ))

        except Exception:
            continue

    # Density overload: >30% of blocks are flash
    if total_blocks > 0:
        flash_ratio = flash_count / total_blocks
        if flash_ratio > _SUBTITLE_FLASH_RATIO:
            report.add_issue(_make_issue(
                code="subtitle_density_overload",
                severity="error",
                message=(
                    f"{flash_count}/{total_blocks} subtitle blocks "
                    f"({flash_ratio:.0%}) are flash duration (<{_SUBTITLE_MIN_DISPLAY_SEC}s). "
                    "Subtitle density is too high."
                ),
                confidence=0.9,
                part_no=part_no,
                evidence={
                    "flash_count": flash_count,
                    "total_blocks": total_blocks,
                    "flash_ratio": round(flash_ratio, 3),
                },
                recommended_action="Resegment subtitles with resegment_srt_for_readability().",
            ))

    # Store density metrics
    report.metrics["subtitle_total_blocks"] = total_blocks
    report.metrics["subtitle_flash_count"] = flash_count
    report.metrics["subtitle_flash_ratio"] = round(flash_count / total_blocks, 3) if total_blocks else 0.0
    report.metrics["subtitle_too_fast_count"] = too_fast_count
    report.metrics["subtitle_line_too_long_count"] = line_too_long_count


def _assess_hook_risk(
    report: QualityReport,
    srt_path: Path,
    part_no: int | None,
) -> None:
    """Assess hook timing and text weight from first subtitle block."""
    from app.features.render.engine.subtitle.generator.srt import _parse_srt_blocks

    try:
        blocks = _parse_srt_blocks(str(srt_path))
    except Exception:
        return

    if not blocks:
        return

    try:
        first = blocks[0]
        first_start = float(first.get("start", 0))
        first_text = str(first.get("text", ""))
        first_word_count = len(first_text.split())

        if first_start > _HOOK_MAX_DELAY_SEC:
            report.add_issue(_make_issue(
                code="hook_delay",
                severity="warning",
                message=(
                    f"First subtitle starts at {first_start:.1f}s "
                    f"(max {_HOOK_MAX_DELAY_SEC}s). Late hook may reduce retention."
                ),
                confidence=0.75,
                part_no=part_no,
                evidence={"first_block_start": first_start},
                recommended_action="Move the first subtitle to within the first 5 seconds.",
            ))

        if first_word_count > _HOOK_MAX_FIRST_WORDS:
            report.add_issue(_make_issue(
                code="hook_text_overload",
                severity="warning",
                message=(
                    f"First subtitle block has {first_word_count} words "
                    f"(max {_HOOK_MAX_FIRST_WORDS}). Too much text at hook position."
                ),
                confidence=0.8,
                part_no=part_no,
                evidence={"first_block_word_count": first_word_count, "text_preview": first_text[:60]},
            ))

        report.metrics["hook_first_block_start"] = first_start
        report.metrics["hook_first_block_words"] = first_word_count

    except Exception as exc:
        logger.warning("quality_assessor: hook risk inner check failed: %s", exc)


def _assess_ai_trace_correlation(
    report: QualityReport,
    ai_trace_path: Path,
) -> None:
    """Read AI trace JSONL and collect relevant event names into report.ai_trace_refs."""
    try:
        if not ai_trace_path.exists():
            return
        with ai_trace_path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    event = obj.get("event")
                    if event and event in _AI_TRACE_RELEVANT_EVENTS:
                        if event not in report.ai_trace_refs:
                            report.ai_trace_refs.append(event)
                except Exception:
                    # Malformed line — skip silently
                    continue
    except Exception:
        # Missing or unreadable file — skip silently
        pass
