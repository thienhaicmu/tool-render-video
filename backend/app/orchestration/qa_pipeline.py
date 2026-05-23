from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
from app.services.db import list_job_parts


def _resume_output_valid(path: "Path") -> bool:
    """Quick integrity check for a previously-rendered part on the resume path.

    Returns True only when ffprobe reports a positive duration.
    Any probe failure (corrupt container, 0-byte, truncated file) returns False
    so the part is re-rendered rather than silently skipped.
    """
    try:
        cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        val = (out.stdout or "").strip()
        return bool(val) and float(val) > 0.0
    except Exception:
        return False


def _duration_tolerance(expected_duration: float) -> float:
    """Return the acceptable deviation window for output duration validation.

    Very short clips get at least 0.5 s; long clips are capped at 3.0 s.
    """
    if expected_duration > 0:
        return max(0.5, min(expected_duration * 0.15, 3.0))
    return 1.0  # safe fallback for unknown/zero expected duration


def _stall_deadline(encode_start: float, expected_duration: float) -> float:
    """Return the monotonic time beyond which a running render is considered stalled."""
    return encode_start + max(120.0, (expected_duration or 60.0) * 10)


def _failed_part_progress(job_id: str, part_no: int, fallback: int = 95) -> int:
    try:
        for part in list_job_parts(job_id):
            if int(part.get("part_no") or 0) != int(part_no):
                continue
            current = int(part.get("progress_percent") or 0)
            if current >= 100:
                return min(99, fallback)
            return max(0, min(99, current))
    except Exception:
        pass
    return max(0, min(99, fallback))


def _validate_render_output(
    output_path: Path,
    expected_duration: float | None = None,
    expect_audio: bool | None = None,
) -> dict:
    """Validate a rendered output file before marking its part as DONE.

    Returns a dict:
        ok           – True only when all hard checks pass
        warnings     – non-fatal issues (e.g. audio missing when not confirmed required)
        error        – human-readable failure reason when ok=False
        metadata     – {size_bytes, duration, has_video, has_audio}

    Never raises; callers convert a non-ok result into a part failure.
    """
    result: dict = {
        "ok": False,
        "warnings": [],
        "error": None,
        "code": "",
        "phase": "validation",
        "metadata": {"size_bytes": 0, "duration": 0.0, "has_video": False, "has_audio": False},
    }

    # 1. File existence
    if not output_path.exists():
        result["error"] = "output file does not exist"
        result["code"] = "RN001"
        return result

    # 2. Size — 10 KB floor catches zero-byte and near-empty files while
    #    allowing extremely short test clips (~1 s h264 is ~40 KB).
    size = output_path.stat().st_size
    result["metadata"]["size_bytes"] = size
    if size < 10_240:
        result["error"] = f"output file too small: {size} bytes (minimum 10 KB)"
        result["code"] = "RN001"
        return result

    # 3. ffprobe readability — single pass for all stream/format data
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            result["error"] = (
                f"ffprobe could not read output "
                f"(exit {proc.returncode}): {(proc.stderr or '').strip()[:200]}"
            )
            result["code"] = "RN001"
            return result
        probe = json.loads(proc.stdout or "{}")
    except subprocess.TimeoutExpired:
        result["error"] = "ffprobe timed out reading output"
        result["code"] = "RN001"
        return result
    except Exception as exc:
        result["error"] = f"ffprobe error: {exc}"
        result["code"] = "RN001"
        return result

    # 4. Stream presence
    streams = probe.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    result["metadata"]["has_video"] = has_video
    result["metadata"]["has_audio"] = has_audio

    if not has_video:
        result["error"] = "output contains no video stream"
        result["code"] = "RN001"
        return result

    # 5. Duration sanity
    fmt = probe.get("format", {})
    duration = float(fmt.get("duration") or 0)
    result["metadata"]["duration"] = duration

    if duration <= 0:
        result["error"] = "output duration is zero"
        result["code"] = "RN001"
        return result

    if expected_duration and expected_duration > 0:
        tolerance = _duration_tolerance(expected_duration)
        result["metadata"]["expected_duration"] = float(expected_duration)
        result["metadata"]["duration_tolerance"] = float(tolerance)
        if abs(duration - expected_duration) > tolerance:
            result["error"] = (
                f"duration mismatch: output {duration:.2f}s vs "
                f"expected ~{expected_duration:.2f}s "
                f"(tolerance ±{tolerance:.2f}s)"
            )
            result["code"] = "RN001"
            return result

    # 6. Audio stream presence check
    #    - When caller explicitly signals audio is required (expect_audio=True):
    #      warn (non-fatal) — preserves existing behaviour for legacy callers.
    #    - When audio is unknown/unspecified (expect_audio=None/False):
    #      warn — rendered video with no audio stream is almost always a bug;
    #      keep non-fatal so partial/silent clips (e.g. voice-only) are not
    #      hard-blocked, but surface the issue for developer visibility.
    if not has_audio:
        if expect_audio is True:
            result["warnings"].append("audio stream expected but missing from output")
        else:
            result["warnings"].append(
                "output has no audio stream — video may be silent (check source audio or mix settings)"
            )

    result["ok"] = True
    return result


def _assess_output_quality(
    output_path: Path,
    output_dir: Path,
    *,
    expect_subtitle: bool = False,
    subtitle_file: "Path | None" = None,
    expect_hook: bool = False,
    hook_applied: bool = False,
) -> dict:
    """Non-blocking perceptual quality checks run after hard validation passes.

    Returns a report dict:
        passed         – True when no hard failures (currently all checks are warn-only)
        hard_failures  – list of blocking error strings (reserved; currently always empty)
        warnings       – list of non-fatal issue strings
        checks         – per-check boolean/float results
        score_penalty  – total points to deduct from output_score (clamped by caller)

    Never raises — all exceptions produce a None check value rather than propagating.
    """
    hard_failures: list[str] = []
    warnings: list[str] = []
    checks: dict = {}
    penalty = 0

    # 1. Output path safety: must resolve inside output_dir
    try:
        is_inside = output_path.resolve().is_relative_to(output_dir.resolve())
        checks["output_path_safe"] = is_inside
        if not is_inside:
            warnings.append(f"output file is outside the selected output folder: {output_path}")
    except Exception:
        checks["output_path_safe"] = None

    # 2. First-frame darkness — blackdetect on first 0.5 s of the rendered output
    checks["first_frame_dark"] = False
    try:
        _bdet_cmd = [
            get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-t", "0.5", "-i", str(output_path),
            "-vf", "blackdetect=d=0.0:pix_th=0.10",
            "-an", "-f", "null", "-",
        ]
        _bdet_r = subprocess.run(_bdet_cmd, capture_output=True, text=True, timeout=10)
        for _bd_line in (_bdet_r.stderr or "").splitlines():
            if "black_start:" not in _bd_line or "black_end:" not in _bd_line:
                continue
            try:
                _b_start = _b_end = None
                for _tok in _bd_line.split():
                    if _tok.startswith("black_start:"):
                        _b_start = float(_tok.split(":", 1)[1])
                    elif _tok.startswith("black_end:"):
                        _b_end = float(_tok.split(":", 1)[1])
                if _b_start is not None and _b_end is not None and _b_start <= 0.08 and _b_end > 0.12:
                    checks["first_frame_dark"] = True
                    warnings.append(f"first frame appears dark (black_end={_b_end:.2f}s)")
                    penalty += 8
            except (ValueError, IndexError):
                continue
    except Exception:
        checks["first_frame_dark"] = None

    # 3. First-frame blur — blurdetect on first 0.5 s
    checks["first_frame_blur"] = False
    checks["first_frame_blur_score"] = None
    try:
        _blur_cmd = [
            get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-t", "0.5", "-i", str(output_path),
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
            checks["first_frame_blur_score"] = round(_avg_blur, 3)
            if _avg_blur > 0.60:
                checks["first_frame_blur"] = True
                warnings.append(f"first frames appear blurry (avg_blur={_avg_blur:.2f})")
                penalty += 6
    except Exception:
        checks["first_frame_blur"] = None

    # 4. Subtitle file present when subtitles were requested for this part
    if expect_subtitle:
        _sub_ok = (
            subtitle_file is not None
            and subtitle_file.exists()
            and subtitle_file.stat().st_size > 0
        )
        checks["subtitle_file_present"] = _sub_ok
        if not _sub_ok:
            warnings.append("subtitle file missing or empty (subtitles were requested for this part)")
            penalty += 10
    else:
        checks["subtitle_file_present"] = None  # not applicable

    # 5. Hook overlay confirmed when hook overlay was expected
    if expect_hook:
        checks["hook_overlay_applied"] = hook_applied
        if not hook_applied:
            warnings.append("hook overlay was enabled but no suitable text was found to apply")
            penalty += 6
    else:
        checks["hook_overlay_applied"] = None  # not applicable

    return {
        "passed": len(hard_failures) == 0,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "checks": checks,
        "score_penalty": penalty,
    }


def _render_part_failure_detail(part_no: int, error: Exception | str) -> dict:
    message = str(error)
    is_validation = "output_validation_failed" in message or "duration mismatch" in message
    return {
        "part_no": int(part_no),
        "error": message,
        "code": "RN001" if is_validation else "RN004",
        "phase": "validation" if is_validation else "render",
    }
