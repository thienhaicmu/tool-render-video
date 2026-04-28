"""Fast Captions skill adapter — transcribe with faster_whisper or whisper and burn-in."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("app.skills.fast_captions")


def _has_faster_whisper() -> bool:
    try:
        import faster_whisper  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def _has_whisper() -> bool:
    try:
        import whisper  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


class FastCaptionsAdapter:
    skill_id = "fast_captions"
    label = "Fast Captions"
    description = "Generate and burn-in captions using faster_whisper when available."
    status = "available"
    default_options = {
        "engine": "default",
        "language": "auto",
        "translate_subtitle": "off",
    }
    config_schema = {
        "engine": {
            "type": "select", "label": "Engine",
            "options": [
                {"value": "default",        "label": "Default (whisper)"},
                {"value": "faster_whisper", "label": "faster_whisper (if available)"},
            ],
        },
        "language": {
            "type": "select", "label": "Language",
            "options": [
                {"value": "auto", "label": "Auto-detect"},
                {"value": "en",   "label": "English"},
                {"value": "vi",   "label": "Vietnamese"},
                {"value": "ja",   "label": "Japanese"},
                {"value": "fr",   "label": "French"},
                {"value": "de",   "label": "German"},
            ],
        },
        "translate_subtitle": {
            "type": "select", "label": "Translate Subtitles",
            "options": [
                {"value": "off", "label": "Off"},
                {"value": "en",  "label": "English"},
                {"value": "vi",  "label": "Vietnamese"},
                {"value": "ja",  "label": "Japanese"},
                {"value": "fr",  "label": "French"},
                {"value": "de",  "label": "German"},
            ],
        },
    }

    def check(self) -> bool:
        return _has_faster_whisper() or _has_whisper()

    def run(self, input_path: str, output_dir: str, options: dict, context: dict) -> dict:
        from app.services.bin_paths import get_ffmpeg_bin

        inp = Path(input_path)
        out_dir = Path(output_dir) / "skill_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{inp.stem}_captions{inp.suffix}"
        srt_path = out_dir / f"{inp.stem}_captions.srt"

        engine = options.get("engine", "default")
        language = options.get("language", "auto")
        lang_arg = None if language == "auto" else language

        engine_used = "none"
        if engine == "faster_whisper" and _has_faster_whisper():
            segments = _transcribe_faster_whisper(inp, lang_arg)
            engine_used = "faster_whisper"
        elif _has_whisper():
            segments = _transcribe_whisper(inp, lang_arg)
            engine_used = "whisper"
        else:
            raise RuntimeError("No transcription engine available (install whisper or faster_whisper)")

        _write_srt(segments, srt_path)

        # Burn-in subtitles
        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        vf = f"subtitles={srt_escaped}"
        cmd = [get_ffmpeg_bin(), "-y", "-i", str(inp), "-vf", vf, "-c:a", "copy", str(out)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg caption burn-in failed: {(result.stderr or '')[-400:]}")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Fast captions output was not created")

        logger.info("fast_captions applied engine=%s output=%s", engine_used, out)
        return {"output_path": str(out), "applied": True, "engine": engine_used, "segments": len(segments)}


def _transcribe_faster_whisper(video_path: Path, language: str | None) -> list[dict]:
    import faster_whisper  # type: ignore
    model = faster_whisper.WhisperModel("tiny", device="cpu", compute_type="int8")
    kw = {}
    if language:
        kw["language"] = language
    segments_gen, _ = model.transcribe(str(video_path), **kw)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments_gen if s.text.strip()]


def _transcribe_whisper(video_path: Path, language: str | None) -> list[dict]:
    import whisper  # type: ignore
    model = whisper.load_model("tiny")
    kw: dict = {"fp16": False, "verbose": False}
    if language:
        kw["language"] = language
    result = model.transcribe(str(video_path), **kw)
    return [{"start": float(s["start"]), "end": float(s["end"]), "text": str(s.get("text", "")).strip()}
            for s in result.get("segments", []) if str(s.get("text", "")).strip()]


def _write_srt(segments: list, path: Path) -> None:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _fmt_ts(float(seg.get("start", 0)))
        end   = _fmt_ts(float(seg.get("end", 0)))
        text  = seg.get("text", "").strip()
        if text:
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


ADAPTER = FastCaptionsAdapter()
