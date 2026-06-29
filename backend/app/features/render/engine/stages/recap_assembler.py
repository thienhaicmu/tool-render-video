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

from app.services.bin_paths import get_ffmpeg_bin

logger = logging.getLogger("app.render.recap_assembler")

_FFMPEG_TIMEOUT_SEC: int = max(300, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "3600")))


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
                f"[{i}:a]aresample=async=1[a{i}]"
            )
            labels.append(f"[v{i}][a{i}]")
        graph = "".join(parts) + "".join(labels) + f"concat=n={len(clips)}:v=1:a=1[outv][outa]"
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
        return {"ok": False, "method": "none"}
    if len(valid) == 1:
        # Single clip — just copy it to the output path.
        try:
            cmd = [get_ffmpeg_bin(), "-y", "-i", valid[0], "-c", "copy",
                   "-movflags", "+faststart", out_path]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           check=True, timeout=_FFMPEG_TIMEOUT_SEC)
            if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
                return {"ok": True, "method": "copy_single"}
        except Exception as exc:
            logger.info("recap_assembler: single-clip copy failed (will re-encode): %s", exc)
        if _concat_filter(valid, out_path, width, height, fps):
            return {"ok": True, "method": "filter_single"}
        return {"ok": False, "method": "none"}
    if _concat_demuxer(valid, out_path):
        return {"ok": True, "method": "demuxer"}
    if _concat_filter(valid, out_path, width, height, fps):
        return {"ok": True, "method": "filter"}
    return {"ok": False, "method": "none"}
