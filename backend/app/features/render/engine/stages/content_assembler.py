"""
content_assembler.py — join Content scene clips with CROSSFADE transitions.

Deliberately separate from ``recap_assembler.concat_clips`` (which is shared with
recap and MUST remain a plain concat). Builds an ``xfade`` (video) +
``acrossfade`` (audio) filtergraph so consecutive scenes blend per the AI's
``transition_hint``. Re-encode only (xfade can't stream-copy).

Never raises: returns ``{"ok": bool, "method": str, "expected_duration": float}``
so the caller falls back to the plain concat on any failure. Scene clips are
already uniform (same WxH/fps/pix_fmt/SAR + an aac track), which xfade requires.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger("app.render.content_assembler")

_FFMPEG_TIMEOUT_SEC = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))
# Default crossfade length per boundary. Override via CONTENT_XFADE_SEC.
_XFADE_SEC = max(0.05, float(os.getenv("CONTENT_XFADE_SEC", "0.4") or 0.4))
# A "cut" hint → a near-instant blend (keeps the graph uniform without a visible
# dissolve). Everything else gets the full _XFADE_SEC.
_CUT_DUR = 0.08

# AI transition_hint → ffmpeg xfade transition name.
_XFADE_MAP = {
    "fade": "fade", "slide": "slideleft", "flash": "fadewhite",
    "zoom": "zoomin", "cut": "fade", "": "fade",
}


def _xtype(hint: str) -> str:
    return _XFADE_MAP.get((hint or "").strip().lower(), "fade")


def _gpu_encode() -> bool:
    """W5-7 — whether the xfade re-encode may use NVENC (h264_nvenc).

    OPT-IN, default CPU (see content_scene_render._content_gpu_encode for the
    measured rationale — NVENC gave no speedup for content and steals a scarce
    shared GPU session). NVENC only engages when ``CONTENT_ENCODER`` is
    ``auto``/``nvenc`` AND the GPU is ready; the default keeps the byte-identical
    libx264 path. Gated on the canonical cached ``nvenc_available()`` check
    (reused — no divergent resolver). The ``NVENC_SEMAPHORE`` acquire is
    delegated to ``_run_ffmpeg_with_retry`` (auto-locks on an h264_nvenc argv).
    Never raises."""
    if os.getenv("CONTENT_ENCODER", "cpu").strip().lower() not in ("auto", "nvenc", "gpu"):
        return False
    try:
        from app.features.render.engine.encoder.ffmpeg_helpers import nvenc_available
        return bool(nvenc_available())
    except Exception:
        return False


def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            [get_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", path],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        return max(0.0, float((r.stdout or "0").strip() or 0.0))
    except Exception:
        return 0.0


def concat_with_transitions(
    clips: list[str], out_path: str, *,
    transitions: list[str], width: int, height: int, fps: float = 30.0,
) -> dict:
    """Join ``clips`` (in order) with a per-boundary xfade/acrossfade.

    ``transitions[i]`` is the AI transition_hint for the boundary BEFORE
    ``clips[i+1]`` (i.e. ideally len == len(clips)-1; padded defensively with
    "fade"). Returns ``{ok, method, expected_duration}`` where expected_duration
    accounts for the crossfade overlaps (Σdur − Σd) so QA (Sacred Contract #8)
    matches. Never raises."""
    valid = [c for c in clips if c and Path(c).exists() and Path(c).stat().st_size > 0]
    if len(valid) < 2:
        return {"ok": False, "method": "need>=2", "expected_duration": 0.0}
    try:
        durs = [_probe_duration(c) for c in valid]
        if any(d <= 0 for d in durs):
            return {"ok": False, "method": "bad_duration", "expected_duration": 0.0}
        n = len(valid)

        # Per-boundary (xfade type, duration). Never let a crossfade exceed either
        # neighbour's length (leave a 0.05s guard) so a very short scene is safe.
        bounds: list[tuple[str, float]] = []
        for i in range(n - 1):
            hint = transitions[i] if i < len(transitions) else ""
            d = _CUT_DUR if (hint or "").strip().lower() == "cut" else _XFADE_SEC
            d = min(d, max(0.05, durs[i] - 0.05), max(0.05, durs[i + 1] - 0.05))
            bounds.append((_xtype(hint), d))

        inputs: list[str] = []
        for c in valid:
            inputs += ["-i", c]

        # Video xfade chain: [0:v][1:v]xfade→[vx0]; [vx0][2:v]xfade→[vx1]; …
        vparts: list[str] = []
        prev_v = "[0:v]"
        running = durs[0]
        for i in range(n - 1):
            xt, d = bounds[i]
            offset = max(0.0, running - d)
            out_lbl = f"[vx{i}]"
            vparts.append(
                f"{prev_v}[{i + 1}:v]xfade=transition={xt}:duration={d:.3f}:offset={offset:.3f}{out_lbl}"
            )
            prev_v = out_lbl
            running = running + durs[i + 1] - d

        # Audio acrossfade chain (acrossfade overlaps by d internally — no offset).
        aparts: list[str] = []
        prev_a = "[0:a]"
        for i in range(n - 1):
            _, d = bounds[i]
            out_lbl = f"[ax{i}]"
            aparts.append(f"{prev_a}[{i + 1}:a]acrossfade=d={d:.3f}:c1=tri:c2=tri{out_lbl}")
            prev_a = out_lbl

        graph = ";".join(vparts + aparts)
        if _gpu_encode():
            # W5-7: NVENC when GPU-ready; _run_ffmpeg_with_retry auto-acquires
            # NVENC_SEMAPHORE for the h264_nvenc argv.
            _vargs = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20", "-pix_fmt", "yuv420p"]
        else:
            _vargs = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
        cmd = [
            get_ffmpeg_bin(), "-y", *inputs,
            "-filter_complex", graph,
            "-map", prev_v, "-map", prev_a,
            *_vargs,
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-r", f"{float(fps):.3f}", out_path,
        ]
        from app.features.render.engine.encoder.ffmpeg_helpers import _run_ffmpeg_with_retry
        _run_ffmpeg_with_retry(cmd)
        if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
            return {"ok": True, "method": "xfade", "expected_duration": round(running, 3)}
        return {"ok": False, "method": "empty", "expected_duration": round(running, 3)}
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.info("content_assembler: xfade concat failed (fallback to plain): %s", detail[:300] or exc)
        return {"ok": False, "method": "error", "expected_duration": 0.0}
    except Exception as exc:
        logger.info("content_assembler: xfade concat error (fallback to plain): %s", exc)
        return {"ok": False, "method": "error", "expected_duration": 0.0}
