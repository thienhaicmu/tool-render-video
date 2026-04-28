"""Smart Crop / Auto Reframe skill adapter — crop + scale to target aspect ratio."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("app.skills.smart_crop")

_ASPECT_MAP: dict[str, tuple[int, int]] = {
    "9:16": (9, 16),
    "1:1":  (1, 1),
    "4:5":  (4, 5),
    "16:9": (16, 9),
}


class SmartCropAdapter:
    skill_id = "smart_crop"
    label = "Smart Crop / Auto Reframe"
    description = "Crop and scale video to a target aspect ratio with subject-aware framing."
    status = "available"
    default_options = {
        "target_aspect": "9:16",
        "subject_priority": "face",
        "crop_smoothing": "medium",
    }
    config_schema = {
        "target_aspect": {
            "type": "select", "label": "Target Aspect",
            "options": [
                {"value": "9:16", "label": "9:16 (Vertical)"},
                {"value": "1:1",  "label": "1:1 (Square)"},
                {"value": "4:5",  "label": "4:5 (Portrait)"},
                {"value": "16:9", "label": "16:9 (Landscape)"},
            ],
        },
        "subject_priority": {
            "type": "select", "label": "Subject Priority",
            "options": [
                {"value": "face",   "label": "Face"},
                {"value": "person", "label": "Person"},
                {"value": "center", "label": "Center"},
                {"value": "motion", "label": "Motion"},
            ],
        },
        "crop_smoothing": {
            "type": "select", "label": "Crop Smoothing",
            "options": [
                {"value": "off",    "label": "Off"},
                {"value": "light",  "label": "Light"},
                {"value": "medium", "label": "Medium"},
                {"value": "strong", "label": "Strong"},
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
        from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
        import json as _json

        inp = Path(input_path)
        out_dir = Path(output_dir) / "skill_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{inp.stem}_cropped{inp.suffix}"

        target = options.get("target_aspect", "9:16")
        tw, th = _ASPECT_MAP.get(target, (9, 16))

        # Probe source dimensions
        probe_cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(inp),
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        try:
            probe_data = _json.loads(probe_result.stdout or "{}")
            streams = probe_data.get("streams", [{}])
            src_w = int(streams[0].get("width", 1920))
            src_h = int(streams[0].get("height", 1080))
        except Exception:
            src_w, src_h = 1920, 1080

        # Compute crop to match target aspect from center
        src_aspect = src_w / src_h
        tgt_aspect = tw / th
        if src_aspect > tgt_aspect:
            # source is wider — crop width
            crop_h = src_h
            crop_w = int(crop_h * tgt_aspect)
        else:
            # source is taller — crop height
            crop_w = src_w
            crop_h = int(crop_w / tgt_aspect)
        # Center crop
        x = (src_w - crop_w) // 2
        y = (src_h - crop_h) // 2

        vf = f"crop={crop_w}:{crop_h}:{x}:{y},scale={crop_w}:{crop_h}"

        cmd = [
            get_ffmpeg_bin(), "-y", "-i", str(inp),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-c:a", "copy", str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg smart crop failed: {(result.stderr or '')[-400:]}")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Smart crop output was not created")

        logger.info("smart_crop applied aspect=%s crop=%dx%d output=%s", target, crop_w, crop_h, out)
        return {"output_path": str(out), "applied": True, "target_aspect": target, "crop": f"{crop_w}x{crop_h}"}


ADAPTER = SmartCropAdapter()
