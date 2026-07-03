"""
content_scene_render.py — Render ONE Content-Mode scene into a self-contained
clip: a user-chosen background + burned narration subtitle + the TTS voice-over.

Content Mode (render_format="content") has no source footage, so a "part" is not
cut from a video — it is COMPOSED here:

    1. synthesize_scene_narration(scene)  → narration .mp3 + measured duration
    2. content_background.build_background_clip(...) → video-only background at the
       scene duration (= pause_before + narration_dur + pause_after)
    3. _build_scene_srt(...)              → a simple timed SRT from the narration
    4. one ffmpeg pass: burn the subtitle (-vf) + delay/pad the narration (-af)
       + mux → scene .mp4 at the target A/V spec

The A/V spec (W×H / fps / sample-rate / stereo AAC) is forced so the downstream
concat (recap_assembler.concat_clips, reused by content_pipeline) can join scenes
without a per-boundary re-encode.

Subtitle handling is deliberately simple in this phase: the narration is split
into a few sequential cues spanning its spoken window. Word-by-word / CapCut
timing (which needs per-word timestamps from a Whisper pass over the TTS audio)
is a later phase; the ``subtitle_style`` hint is carried on the plan for then.

Sacred Contract #3 spirit: every entry point returns None / False on any failure
(never raises) so the pipeline skips the scene or fails the job cleanly.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
from app.features.render.engine.encoder.encoder_helpers import safe_filter_path
from app.features.render.engine.stages.content_background import build_background_clip

logger = logging.getLogger("app.render.content_scene_render")

_FFMPEG_TIMEOUT_SEC: int = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))
_PROBE_TIMEOUT_SEC: int = 30

# Max subtitle cues per scene — keeps captions readable (no 1-cue wall of text,
# no 1-cue-per-word storm before we have real word timings).
_MAX_CUES_PER_SCENE: int = max(1, int(os.getenv("CONTENT_MAX_CUES_PER_SCENE", "6")))
_MIN_CUE_SEC: float = 0.6

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…。！？])\s+")


def probe_audio_duration(path: str) -> float:
    """Return audio duration in seconds via ffprobe, or 0.0 on any error."""
    try:
        out = subprocess.run(
            [get_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=_PROBE_TIMEOUT_SEC,
        )
        raw = (out.stdout or "").strip()
        return max(0.0, float(raw)) if raw else 0.0
    except Exception:
        return 0.0


def _reading_speed_to_rate(reading_speed: float) -> str:
    """Map a ContentScene.reading_speed multiplier (≈0.9–1.15) to an Edge-TTS
    rate string ("+10%", "-5%", "+0%"). Clamped defensively."""
    try:
        spd = float(reading_speed or 1.0)
    except (TypeError, ValueError):
        spd = 1.0
    spd = max(0.5, min(2.0, spd))
    pct = int(round((spd - 1.0) * 100))
    return f"+{pct}%" if pct >= 0 else f"{pct}%"


def synthesize_scene_narration(
    *,
    scene,
    job_id: str,
    language: str = "vi-VN",
    gender: str = "female",
    voice_id: Optional[str] = None,
    tts_engine: str = "edge",
    content_type: str = "vlog",
    out_path: str,
) -> Optional[tuple[str, float]]:
    """Synthesize the narration audio for one ContentScene. Returns
    ``(audio_path, duration_sec)`` or None on any failure (Sacred Contract #3).

    Kept separate from ``render_content_scene`` so the ffmpeg composition path is
    testable offline with a synthetic audio track (no network TTS)."""
    try:
        text = str(getattr(scene, "narration", "") or "").strip()
        if not text:
            return None
        from app.features.render.engine.audio.tts import generate_narration_audio
        rate = _reading_speed_to_rate(getattr(scene, "reading_speed", 1.0))
        path = generate_narration_audio(
            text=text, language=language, gender=gender, rate=rate,
            job_id=job_id, voice_id=voice_id, output_path=out_path,
            content_type=content_type, tts_engine=tts_engine,
        )
        if not path or not Path(path).exists() or Path(path).stat().st_size <= 0:
            logger.warning("content_scene_render: TTS produced no audio (scene idx=%s)",
                           getattr(scene, "index", "?"))
            return None
        dur = probe_audio_duration(path)
        if dur <= 0:
            logger.warning("content_scene_render: TTS audio has zero duration")
            return None
        return path, dur
    except Exception as exc:
        logger.warning("content_scene_render: synthesize_scene_narration error %s", exc)
        return None


def _srt_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int(round((s - int(s)) * 1000))
    if ms == 1000:  # rounding guard
        ms = 999
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _split_cues(text: str, max_cues: int) -> list[str]:
    """Split narration into up to ``max_cues`` caption chunks by sentence, then by
    length if there are too few. Never raises."""
    t = " ".join((text or "").split())
    if not t:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(t) if p.strip()]
    if not parts:
        parts = [t]
    if len(parts) > max_cues:
        # Merge neighbours until we're within the cap (keeps chronological order).
        while len(parts) > max_cues:
            merged: list[str] = []
            it = iter(parts)
            for a in it:
                b = next(it, None)
                merged.append(a if b is None else f"{a} {b}")
            parts = merged
    return parts


def _build_scene_srt(narration: str, start_sec: float, dur_sec: float, out_srt: str) -> bool:
    """Write a simple timed SRT covering ``narration`` across
    [start_sec, start_sec+dur_sec], one cue per chunk with time proportional to
    chunk length. Returns True on success, False on any failure (never raises)."""
    try:
        cues = _split_cues(narration, _MAX_CUES_PER_SCENE)
        if not cues:
            return False
        total_chars = sum(len(c) for c in cues) or 1
        lines: list[str] = []
        t = max(0.0, float(start_sec))
        span = max(_MIN_CUE_SEC, float(dur_sec))
        for i, cue in enumerate(cues, start=1):
            share = (len(cue) / total_chars) * span
            cue_dur = max(_MIN_CUE_SEC, share)
            begin = t
            end = min(start_sec + span, begin + cue_dur)
            if end <= begin:
                end = begin + _MIN_CUE_SEC
            lines.append(str(i))
            lines.append(f"{_srt_time(begin)} --> {_srt_time(end)}")
            lines.append(cue)
            lines.append("")
            t = end
        Path(out_srt).write_text("\n".join(lines), encoding="utf-8")
        return Path(out_srt).exists() and Path(out_srt).stat().st_size > 0
    except Exception as exc:
        logger.warning("content_scene_render: _build_scene_srt error %s", exc)
        return False


def render_content_scene(
    *,
    scene,
    background_kind: str,
    background_value: str,
    narration_audio_path: str,
    narration_dur: float,
    width: int,
    height: int,
    fps: float,
    sample_rate: int,
    out_path: str,
    work_dir: str,
    subtitle_enabled: bool = True,
) -> bool:
    """Compose one Content-Mode scene → ``out_path``. Returns True on success.

    Given a pre-synthesized narration audio (path + measured duration), builds the
    background, burns a simple subtitle, and muxes the delayed/padded narration.
    The scene runs for pause_before + narration_dur + pause_after seconds.
    Returns False on any failure (never raises — Sacred Contract #3)."""
    bg_path = ""
    srt_path = ""
    try:
        pause_before = max(0.0, float(getattr(scene, "pause_before", 0.0) or 0.0))
        pause_after = max(0.0, float(getattr(scene, "pause_after", 0.0) or 0.0))
        ndur = max(0.1, float(narration_dur or 0.0))
        scene_dur = pause_before + ndur + pause_after
        r = float(fps) if fps and fps > 0 else 30.0
        sr = int(sample_rate) if sample_rate and sample_rate > 0 else 48000
        idx = getattr(scene, "index", 0)

        if not narration_audio_path or not Path(narration_audio_path).exists():
            logger.warning("content_scene_render: narration audio missing (scene idx=%s)", idx)
            return False

        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        bg_path = str(work / f"content_bg_{idx:03d}.mp4")
        srt_path = str(work / f"content_sub_{idx:03d}.srt")

        # 1. Background video (scene-length, no audio).
        if not build_background_clip(
            kind=background_kind, value=background_value,
            width=int(width), height=int(height), fps=r,
            duration_sec=scene_dur, out_path=bg_path,
        ):
            logger.warning("content_scene_render: background build failed (scene idx=%s)", idx)
            return False

        # 2. Subtitle (optional) — spans the narration window inside the scene.
        want_subtitle = bool(subtitle_enabled) and _build_scene_srt(
            str(getattr(scene, "narration", "") or ""), pause_before, ndur, srt_path,
        )

        # 3. Compose: burn subtitle (-vf) + delay/pad narration (-af) + mux.
        pb_ms = int(round(pause_before * 1000))
        af = f"adelay={pb_ms}:all=1,apad,atrim=0:{scene_dur:.3f},aresample={sr}"
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-i", bg_path,
            "-i", str(narration_audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
        ]
        if want_subtitle:
            cmd += ["-vf", f"subtitles='{safe_filter_path(srt_path)}'"]
            cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-bf", "0"]
        else:
            # No burn needed — the background is already at spec; copy the video.
            cmd += ["-c:v", "copy"]
        cmd += [
            "-af", af,
            "-r", f"{r:.3f}",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(sr), "-ac", "2",
            "-t", f"{scene_dur:.3f}",
            str(out_path),
        ]
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        ok = Path(out_path).exists() and Path(out_path).stat().st_size > 0
        if not ok:
            logger.warning("content_scene_render: output missing/empty (scene idx=%s)", idx)
        return ok
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("content_scene_render: ffmpeg failed (non-fatal): %s", detail[:400] or exc)
        _cleanup(out_path)
        return False
    except Exception as exc:
        logger.warning("content_scene_render: unexpected error (non-fatal): %s", exc)
        _cleanup(out_path)
        return False
    finally:
        _cleanup(bg_path)
        _cleanup(srt_path)


def _cleanup(path: str) -> None:
    try:
        if path and Path(path).exists():
            Path(path).unlink()
    except Exception:
        pass
