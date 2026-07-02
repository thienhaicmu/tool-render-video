"""Recap assembler (Phase R2) — concat title cards + scene clips → 1 video.

Two strategies:
  • concat demuxer (fast, stream-copy, no quality loss) — works when every
    input shares the same codec/params. The recap scenes are all rendered by
    the same part_renderer (same payload) and the title cards are forced to the
    same spec, so this is the primary path.
  • concat filter (re-encode) — robust fallback when the demuxer rejects a
    spec mismatch. Normalises everything to one target WxH/fps and re-encodes.

Sacred Contract #3 spirit: returns {"ok": False} on any failure (never raises);
the caller decides how to degrade. qa_pipeline still validates the final output.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger("app.render.recap_assembler")

_FFMPEG_TIMEOUT_SEC: int = max(300, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "3600")))


def _probe_duration(path: str) -> float:
    """Container duration in seconds via ffprobe. 0.0 on any failure."""
    try:
        out = subprocess.run(
            [get_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        return max(0.0, float((out.stdout or "").strip() or 0.0))
    except Exception:
        return 0.0


def _demuxer_output_sane(out_path: str, expected_sec: float) -> bool:
    """Stream-copy concat exits 0 even when input specs differ (NVENC scene
    clips + libx264 caption-burned clips + title cards), silently emitting
    broken PTS: a container duration wildly off the sum of the inputs
    (observed 2026-07-02: 15,134s for a ~295s episode, frozen video, audio
    desync). Verify the duration before trusting the demuxer result."""
    if expected_sec <= 0:
        return True  # nothing to compare against
    actual = _probe_duration(out_path)
    if actual <= 0:
        return False
    tolerance = max(3.0, expected_sec * 0.02)
    if abs(actual - expected_sec) > tolerance:
        logger.warning(
            "recap_assembler: demuxer output duration %.1fs deviates from expected "
            "%.1fs (tol %.1fs) — discarding, falling back to re-encode concat",
            actual, expected_sec, tolerance,
        )
        return False
    return True


def _concat_demuxer(clips: list[str], out_path: str) -> bool:
    """Stream-copy concat via the demuxer. Requires uniform input specs."""
    listfile = None
    try:
        # Build a temp concat list file (ffmpeg concat demuxer format).
        fd, listfile = tempfile.mkstemp(suffix=".txt", prefix="recap_concat_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for c in clips:
                p = str(Path(c).resolve()).replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{p}'\n")
        cmd = [
            get_ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
            "-i", listfile, "-c", "copy", "-movflags", "+faststart", out_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       check=True, timeout=_FFMPEG_TIMEOUT_SEC)
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.info("recap_assembler: demuxer concat failed (will try filter): %s", detail[:300] or exc)
        return False
    except Exception as exc:
        logger.info("recap_assembler: demuxer concat error (will try filter): %s", exc)
        return False
    finally:
        if listfile:
            try:
                os.unlink(listfile)
            except Exception:
                pass


def _concat_filter(clips: list[str], out_path: str, width: int, height: int, fps: float) -> bool:
    """Re-encode concat — normalises every input to width×height/fps. Robust."""
    try:
        inputs: list[str] = []
        for c in clips:
            inputs += ["-i", str(c)]
        parts: list[str] = []
        labels: list[str] = []
        for i in range(len(clips)):
            parts.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.3f}[v{i}];"
                # aformat: the concat filter requires uniform audio specs, and the
                # inputs mix NVENC scenes (mixer aac), caption-burned clips
                # (audio copy) and 48 kHz title cards. Normalise every input the
                # same way remotion_adapter's proven intro-concat does, so the
                # fallback works regardless of ffmpeg version / input rates.
                f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"aresample=async=1[a{i}]"
            )
            labels.append(f"[v{i}][a{i}]")
        # 2026-07-02: filter chains MUST be ';'-separated. The previous
        # "".join(parts) glued "[a0][1:v]..." together into an invalid graph,
        # so this fallback had never actually run — every spec-mismatched
        # episode silently shipped the broken demuxer output instead.
        graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(clips)}:v=1:a=1[outv][outa]"
        cmd = [
            get_ffmpeg_bin(), "-y", *inputs,
            "-filter_complex", graph, "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       check=True, timeout=_FFMPEG_TIMEOUT_SEC)
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("recap_assembler: filter concat failed: %s", detail[:400] or exc)
        return False
    except Exception as exc:
        logger.warning("recap_assembler: filter concat error: %s", exc)
        return False


def concat_clips(
    clips: list[str],
    out_path: str,
    *,
    width: int,
    height: int,
    fps: float = 30.0,
) -> dict:
    """Concat clips (in order) → out_path. Tries stream-copy demuxer first,
    falls back to a re-encode filter. Returns {"ok": bool, "method": str}."""
    valid = [c for c in clips if c and Path(c).exists() and Path(c).stat().st_size > 0]
    if not valid:
        return {"ok": False, "method": "none", "expected_duration": 0.0}
    # Sum of input durations — the ground truth the assembled output must
    # match. Also returned to the caller so episode-level QA can enforce it
    # (Sacred Contract #8: _validate_render_output expected_duration).
    expected_sec = sum(_probe_duration(c) for c in valid)
    if len(valid) == 1:
        # Single clip — just copy it to the output path.
        try:
            cmd = [get_ffmpeg_bin(), "-y", "-i", valid[0], "-c", "copy",
                   "-movflags", "+faststart", out_path]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           check=True, timeout=_FFMPEG_TIMEOUT_SEC)
            if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
                return {"ok": True, "method": "copy_single", "expected_duration": expected_sec}
        except Exception as exc:
            logger.info("recap_assembler: single-clip copy failed (will re-encode): %s", exc)
        if _concat_filter(valid, out_path, width, height, fps):
            return {"ok": True, "method": "filter_single", "expected_duration": expected_sec}
        return {"ok": False, "method": "none", "expected_duration": expected_sec}
    if _concat_demuxer(valid, out_path):
        if _demuxer_output_sane(out_path, expected_sec):
            return {"ok": True, "method": "demuxer", "expected_duration": expected_sec}
        # Broken stream-copy output — remove it so a filter failure below
        # can't leave the corrupt file behind as the "delivered" episode.
        try:
            Path(out_path).unlink()
        except Exception:
            pass
    if _concat_filter(valid, out_path, width, height, fps):
        return {"ok": True, "method": "filter", "expected_duration": expected_sec}
    return {"ok": False, "method": "none", "expected_duration": expected_sec}
