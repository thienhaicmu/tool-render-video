"""Reaction freeze-frame post-pass (narration_mode="reaction", Phase B).

Inserts suspense freeze-frames into a rendered per-part clip. In reaction
mode the AI marks a few "voice" lead-in segments with ``freeze_after`` —
after the reactor's line, the video holds on the current frame for a beat
(with an on-screen caption) before releasing into the original-audio payoff.

This runs as a self-contained post-pass on the FINAL per-part mp4 (after the
voice/BGM mix, before the finalize/qa stage). It re-times BOTH video and the
already-mixed audio together so everything after each freeze shifts by the
hold duration. Audio during a hold is silent — the "(im lặng 1-2s)" beat.

Design choices:
  • One FFmpeg filter_complex, single re-encode. Spans of the source are
    trimmed and concatenated; each freeze holds the span's last frame via
    ``tpad=stop_mode=clone`` and pads the audio with silence (``apad``).
  • CPU libx264 encode — NO NVENC, so it never touches NVENC_SEMAPHORE
    (a one-off post-pass must not contend for GPU encoder sessions).
  • Sacred Contract #3 spirit: any failure returns added_sec=0 / applied=
    False and leaves the input clip untouched — the caller keeps the
    unfrozen clip. NEVER raises.

Caps (env-overridable) keep the clip from ballooning past its target:
  REACTION_FREEZE_ENABLED            (default 1) — master switch.
  REACTION_FREEZE_MAX_PER_POINT_SEC  (default 2.0) — clamp each hold.
  REACTION_FREEZE_MAX_TOTAL_SEC      (default 6.0) — clamp total added time.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
from app.features.render.engine.encoder.encoder_helpers import (
    detect_windows_fontfile,
    safe_filter_path,
)

logger = logging.getLogger("app.render.reaction_freeze")

_FREEZE_ENABLED: bool = os.getenv("REACTION_FREEZE_ENABLED", "1") == "1"
_MAX_PER_POINT_SEC: float = max(0.3, min(5.0, float(os.getenv("REACTION_FREEZE_MAX_PER_POINT_SEC", "2.0"))))
_MAX_TOTAL_SEC: float = max(0.0, min(20.0, float(os.getenv("REACTION_FREEZE_MAX_TOTAL_SEC", "6.0"))))
_FFMPEG_TIMEOUT_SEC: int = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))
_PROBE_TIMEOUT_SEC: int = 30


def _probe_duration_s(path: str) -> float:
    try:
        result = subprocess.run(
            [
                get_ffprobe_bin(), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, encoding="utf-8", timeout=_PROBE_TIMEOUT_SEC,
        )
        return float((result.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _escape_drawtext(text: str) -> str:
    """Escape a caption for an FFmpeg drawtext ``text=`` value."""
    s = (text or "").strip()
    # Order matters: backslash first.
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "’")   # curly apostrophe — avoids quote-balancing pain
    s = s.replace("%", "\\%")
    return s


def plan_freeze_points(
    segments: list[dict],
    *,
    render_speed: float,
    clip_final_duration: float,
) -> list[dict]:
    """Map reaction ``freeze_after`` markers to final-timeline freeze points.

    Returns a sorted list of {at: <final sec>, hold: <sec>, text: <caption>}
    after applying the per-point and per-clip caps. Empty when freezes are
    disabled or none are requested. Never raises.
    """
    if not _FREEZE_ENABLED or not segments:
        return []
    try:
        speed = render_speed if render_speed and render_speed > 0 else 1.0
        raw: list[dict] = []
        for seg in segments:
            try:
                if str(seg.get("kind", "voice") or "voice").strip().lower() != "voice":
                    continue
                hold = float(seg.get("freeze_after", 0) or 0)
            except (TypeError, ValueError):
                continue
            if hold <= 0:
                continue
            hold = min(hold, _MAX_PER_POINT_SEC)
            # Source clip time → final (speed-adjusted) time. The freeze lands
            # at the end of the reactor's lead-in line.
            at_final = float(seg.get("end", 0) or 0) / speed
            # Keep a margin from the very end so there's payoff video left.
            if at_final <= 0.1 or at_final >= max(0.2, clip_final_duration - 0.2):
                continue
            text = str(seg.get("freeze_text", "") or "").strip() or str(seg.get("text", "") or "").strip()
            raw.append({"at": round(at_final, 3), "hold": round(hold, 3), "text": text})
        raw.sort(key=lambda x: x["at"])
        # Enforce total cap — keep earliest points until the budget is spent.
        out: list[dict] = []
        total = 0.0
        for p in raw:
            if _MAX_TOTAL_SEC and total + p["hold"] > _MAX_TOTAL_SEC:
                remaining = _MAX_TOTAL_SEC - total
                if remaining < 0.3:
                    break
                p = {**p, "hold": round(remaining, 3)}
            out.append(p)
            total += p["hold"]
            if _MAX_TOTAL_SEC and total >= _MAX_TOTAL_SEC:
                break
        return out
    except Exception as exc:
        logger.warning("reaction_freeze: plan failed (non-fatal): %s", exc)
        return []


def apply_reaction_freezes(
    *,
    video_path: str,
    output_path: str,
    freeze_points: list[dict],
    video_crf: int = 18,
) -> dict:
    """Insert freeze-frames into video_path → output_path.

    Returns {"applied": bool, "added_sec": float, "points": int}. On any
    failure returns applied=False / added_sec=0 and does NOT create a
    partial output (caller keeps the original). Never raises.
    """
    result = {"applied": False, "added_sec": 0.0, "points": 0}
    if not freeze_points:
        return result
    src = Path(video_path)
    out = Path(output_path)
    if not src.exists() or src.stat().st_size <= 0:
        return result
    try:
        dur = _probe_duration_s(str(src))
        if dur <= 0:
            return result
        pts = [p for p in freeze_points if 0.1 < float(p["at"]) < dur - 0.1 and float(p["hold"]) > 0]
        if not pts:
            return result

        fontfile = detect_windows_fontfile()
        boundaries = [0.0] + [float(p["at"]) for p in pts]  # span starts
        ends = [float(p["at"]) for p in pts] + [dur]         # span ends
        holds = [float(p["hold"]) for p in pts] + [0.0]      # hold after each span (last=0)
        texts = [p.get("text", "") for p in pts] + [""]

        vparts: list[str] = []
        aparts: list[str] = []
        labels: list[str] = []
        n = len(boundaries)
        for i in range(n):
            a, b, hold = boundaries[i], ends[i], holds[i]
            span_len = max(0.0, b - a)
            # Video span + optional clone-hold tail + caption during the hold.
            v = f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS"
            if hold > 0:
                v += f",tpad=stop_mode=clone:stop_duration={hold:.3f}"
                cap = _escape_drawtext(texts[i])
                if cap and fontfile:
                    _ff = safe_filter_path(fontfile)
                    v += (
                        f",drawtext=fontfile='{_ff}':text='{cap}'"
                        f":fontcolor=white:fontsize=h/18:box=1:boxcolor=black@0.55:boxborderw=24"
                        f":x=(w-text_w)/2:y=h*0.78"
                        f":enable='gte(t,{span_len:.3f})'"
                    )
            v += f"[v{i}]"
            vparts.append(v)
            # Audio span + silence pad during the hold.
            a_f = f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS"
            if hold > 0:
                a_f += f",apad=pad_dur={hold:.3f}"
            a_f += f"[a{i}]"
            aparts.append(a_f)
            labels.append(f"[v{i}][a{i}]")

        concat = "".join(labels) + f"concat=n={n}:v=1:a=1[outv][outa]"
        filter_complex = ";".join(vparts + aparts + [concat])

        cmd = [
            get_ffmpeg_bin(), "-y", "-i", str(src),
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(int(video_crf)),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(out),
        ]
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        if not out.exists() or out.stat().st_size <= 0:
            return result
        added = sum(float(p["hold"]) for p in pts)
        result.update({"applied": True, "added_sec": round(added, 3), "points": len(pts)})
        return result
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("reaction_freeze: ffmpeg failed (non-fatal): %s", detail[:400] or exc)
        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return result
    except Exception as exc:
        logger.warning("reaction_freeze: unexpected error (non-fatal): %s", exc)
        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return result
