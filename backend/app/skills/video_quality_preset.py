"""Video Quality Preset skill adapter — color-grade re-encode with quality presets."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("app.skills.video_quality_preset")

# FFmpeg video filter chains for each preset
_PRESET_FILTERS: dict[str, str] = {
    "none":            "",
    "social bright":   "eq=brightness=0.05:contrast=1.1:saturation=1.2,unsharp=5:5:0.8:5:5:0",
    "cinematic soft":  "eq=brightness=-0.03:contrast=0.95:saturation=0.85,gblur=sigma=0.5",
    "high contrast":   "eq=contrast=1.25:saturation=1.1,curves=all='0/0 0.25/0.2 0.75/0.85 1/1'",
    "clean business":  "eq=brightness=0.02:contrast=1.05:saturation=0.9",
}

_QUALITY_CRF: dict[str, int] = {"balanced": 22, "high": 18, "max": 14}


class VideoQualityPresetAdapter:
    skill_id = "video_quality_preset"
    label = "Video Quality Preset"
    description = "Apply a color grade and re-encode at a selected quality level."
    status = "available"
    default_options = {
        "preset": "none",
        "quality_level": "balanced",
    }
    config_schema = {
        "preset": {
            "type": "select", "label": "Preset",
            "options": [
                {"value": "none",           "label": "None"},
                {"value": "social bright",  "label": "Social Bright"},
                {"value": "cinematic soft", "label": "Cinematic Soft"},
                {"value": "high contrast",  "label": "High Contrast"},
                {"value": "clean business", "label": "Clean Business"},
            ],
        },
        "quality_level": {
            "type": "select", "label": "Quality Level",
            "options": [
                {"value": "balanced", "label": "Balanced"},
                {"value": "high",     "label": "High"},
                {"value": "max",      "label": "Max"},
            ],
        },
    }

    def check(self) -> bool:
        try:
            from app.services.bin_paths import get_ffmpeg_bin
            return bool(get_ffmpeg_bin())
        except Exception:
            return False

    def run(self, input_path: str, output_dir: str, options: dict, context: dict) -> dict:
        from app.services.bin_paths import get_ffmpeg_bin

        inp = Path(input_path)
        out_dir = Path(output_dir) / "skill_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{inp.stem}_vqp{inp.suffix}"

        preset = options.get("preset", "none")
        quality = options.get("quality_level", "balanced")
        crf = _QUALITY_CRF.get(quality, 22)
        vf = _PRESET_FILTERS.get(preset, "")

        cmd = [get_ffmpeg_bin(), "-y", "-i", str(inp)]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                "-c:a", "copy", str(out)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg quality preset failed: {(result.stderr or '')[-400:]}")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Quality preset output was not created")

        logger.info("video_quality_preset applied preset=%s crf=%d output=%s", preset, crf, out)
        return {"output_path": str(out), "applied": True, "preset": preset, "crf": crf}


ADAPTER = VideoQualityPresetAdapter()
