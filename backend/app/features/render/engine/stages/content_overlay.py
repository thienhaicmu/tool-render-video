"""
content_overlay.py — animated text overlay (title card / lower-third) for a
Content-Mode scene, driven by the AI's ``animation_hint`` + ``scene_title``.

Emitted as a tiny ASS file (NOT ffmpeg drawtext) so fonts, positioning and the
fade animation are handled natively and Windows path escaping is a non-issue —
the scene compose burns it with a second ``ass=`` filter.

Best-effort (Sacred Contract #3 spirit): returns False on any failure so the
caller simply skips the overlay and still renders the scene.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("app.render.content_overlay")

# animation_hint values this module renders. Others (progress_bar / popup /
# highlight) are intentionally not handled yet — the caller skips them.
SUPPORTED_HINTS = ("title", "lower_third")


def _ass_time(sec: float) -> str:
    """Seconds → ASS time H:MM:SS.cc. Never raises."""
    try:
        s = max(0.0, float(sec))
    except (TypeError, ValueError):
        s = 0.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    rem = s % 60
    return f"{h}:{m:02d}:{rem:05.2f}"


def _escape(text: str) -> str:
    """Escape ASS-significant chars in a plain title (no override injection)."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", " ")
        .strip()
    )


def build_overlay_ass(
    scene_title: str, kind: str, width: int, height: int, scene_dur: float, out_ass: str,
) -> bool:
    """Write a title-card / lower-third ASS for ``scene_title``. Returns True on a
    non-empty file, False otherwise (caller skips the overlay). Never raises."""
    try:
        title = _escape(scene_title)
        if not title:
            return False
        k = (kind or "").strip().lower()
        if k not in SUPPORTED_HINTS:
            return False
        w, h = int(width), int(height)
        end = _ass_time(max(0.5, float(scene_dur or 0.0)))

        if k == "lower_third":
            fs = max(28, int(h * 0.040))
            mv = int(h * 0.10)
            # BorderStyle=3 → opaque banner box (OutlineColour), bottom-centre (an2).
            style = (
                f"Style: Ov,Arial,{fs},&H00FFFFFF,&H00FFFFFF,&H80202020,&H80202020,"
                f"-1,0,0,0,100,100,0,0,3,10,0,2,80,80,{mv},1"
            )
            event = f"Dialogue: 0,0:00:00.00,{end},Ov,,0,0,0,,{{\\fad(300,300)}}{title}"
        else:  # title
            fs = max(40, int(h * 0.060))
            mv = int(h * 0.11)
            # Outline text, top-centre (an8), gentle fade.
            style = (
                f"Style: Ov,Arial,{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
                f"-1,0,0,0,100,100,0,0,1,4,2,8,80,80,{mv},1"
            )
            event = f"Dialogue: 0,0:00:00.00,{end},Ov,,0,0,0,,{{\\fad(400,400)}}{title}"

        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\n"
            "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            f"{style}\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        Path(out_ass).write_text(header + event + "\n", encoding="utf-8")
        return Path(out_ass).exists() and Path(out_ass).stat().st_size > 0
    except Exception as exc:
        logger.info("content_overlay: build failed %s", exc)
        return False
