"""Audio Pro Mix skill adapter — EBU R128 loudnorm + voice clarity EQ + limiter."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("app.skills.audio_pro_mix")

_LUFS_MAP = {"-14 LUFS": -14.0, "-16 LUFS": -16.0, "-18 LUFS": -18.0}


class AudioProMixAdapter:
    skill_id = "audio_pro_mix"
    label = "Audio Pro Mix"
    description = "Balance and normalize audio for consistent loudness across all clips."
    status = "available"
    default_options = {
        "loudness_target": "-16 LUFS",
        "background_ducking": "off",
        "voice_clarity": "off",
        "limiter": True,
    }
    config_schema = {
        "loudness_target": {
            "type": "select", "label": "Loudness Target",
            "options": [
                {"value": "-14 LUFS", "label": "-14 LUFS"},
                {"value": "-16 LUFS", "label": "-16 LUFS (default)"},
                {"value": "-18 LUFS", "label": "-18 LUFS"},
            ],
        },
        "background_ducking": {
            "type": "select", "label": "Background Ducking",
            "options": [
                {"value": "off",    "label": "Off"},
                {"value": "light",  "label": "Light"},
                {"value": "medium", "label": "Medium"},
                {"value": "strong", "label": "Strong"},
            ],
        },
        "voice_clarity": {
            "type": "select", "label": "Voice Clarity",
            "options": [
                {"value": "off",      "label": "Off"},
                {"value": "standard", "label": "Standard"},
                {"value": "strong",   "label": "Strong"},
            ],
        },
        "limiter": {"type": "bool", "label": "Limiter"},
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
        out = out_dir / f"{inp.stem}_audiomix{inp.suffix}"

        lufs = _LUFS_MAP.get(options.get("loudness_target", "-16 LUFS"), -16.0)
        voice_clarity = options.get("voice_clarity", "off")
        limiter = bool(options.get("limiter", True))

        af_parts = [f"loudnorm=I={lufs}:TP=-1.5:LRA=11"]

        if voice_clarity == "standard":
            af_parts.append("equalizer=f=3000:width_type=o:width=2:g=2")
        elif voice_clarity == "strong":
            af_parts.append("equalizer=f=3000:width_type=o:width=2:g=4")

        if limiter:
            af_parts.append("alimiter=level_in=1:level_out=1:limit=0.9:attack=5:release=50")

        cmd = [
            get_ffmpeg_bin(), "-y", "-i", str(inp),
            "-af", ",".join(af_parts),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio mix failed: {(result.stderr or '')[-400:]}")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Audio mix output was not created")

        logger.info("audio_pro_mix applied lufs=%s output=%s", lufs, out)
        return {"output_path": str(out), "applied": True, "lufs": lufs}


ADAPTER = AudioProMixAdapter()
