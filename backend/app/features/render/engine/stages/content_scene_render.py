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

# CS-C — word-by-word ("chữ động") subtitle. Transcribe the scene's TTS audio
# with Whisper word timestamps → a CapCut word-level ASS. Default ON with a
# graceful fallback to the sentence-level SRT when Whisper is unavailable or
# fails. Whisper models are LRU-cached across scenes, so only the first scene
# pays the model-load cost. CONTENT_WHISPER_MODEL picks the model (base = a good
# speed/accuracy trade-off for short TTS clips).
_CONTENT_WORD_BY_WORD: bool = os.getenv("CONTENT_WORD_BY_WORD", "1") == "1"
# E1: animated text overlay (title card / lower-third) from the AI's
# animation_hint + scene_title. Default ON; a build failure just skips it.
_CONTENT_TEXT_OVERLAY: bool = os.getenv("CONTENT_TEXT_OVERLAY", "1") == "1"
_CONTENT_WHISPER_MODEL: str = (os.getenv("CONTENT_WHISPER_MODEL", "base").strip() or "base")

_SRT_TIME_LINE_RE = re.compile(r"(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…。！？])\s+")
# W5-5: split an over-long sentence caption at a clause boundary (comma etc.) so
# a long single sentence doesn't sit on screen as one wall of text for the whole
# scene. Readability target ≈ one caption line. Timing stays char-proportional
# (consistent with the plan's ~15 chars/sec model).
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:—–])\s+")
_CAPTION_CHAR_TARGET: int = max(16, int(os.getenv("CONTENT_CAPTION_CHARS", "42")))


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


def _apply_tempo(audio_path: str, speed: float) -> Optional[str]:
    """W5-1 — change an audio file's TEMPO by ``speed`` (pitch-preserving ffmpeg
    ``atempo``) to enforce a scene's reading_speed on TTS engines that DON'T apply
    the ``rate`` knob (xtts / piper ignore it; gemini only soft-hints it). Edge
    applies rate natively, so it never reaches here. ``speed`` > 1 → faster/shorter.

    Overwrites ``audio_path`` in place; returns it on success, or None on failure
    (the caller then keeps the natural-pace audio). reading_speed is clamped
    0.5–2.0 so a single atempo (its supported range) always covers it. Never
    raises (Sacred Contract #3 spirit)."""
    try:
        spd = max(0.5, min(2.0, float(speed or 1.0)))
        if abs(spd - 1.0) <= 1e-3:
            return audio_path
        tmp = str(Path(audio_path).with_suffix(".tempo.mp3"))
        subprocess.run(
            [get_ffmpeg_bin(), "-y", "-i", str(audio_path),
             "-filter:a", f"atempo={spd:.4f}", "-c:a", "libmp3lame", tmp],
            capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        if Path(tmp).exists() and Path(tmp).stat().st_size > 0:
            os.replace(tmp, audio_path)
            return audio_path
        return None
    except Exception as exc:
        logger.info("content_scene_render: atempo failed (%s) — keeping natural pace", exc)
        try:
            Path(str(Path(audio_path).with_suffix(".tempo.mp3"))).unlink(missing_ok=True)
        except Exception:
            pass
        return None


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
        # W5-1: only Edge applies `rate` precisely. For other engines pass a
        # NEUTRAL rate and enforce reading_speed with a post-TTS atempo below, so
        # the plan's fitted duration actually holds regardless of engine (edge
        # stays byte-identical).
        _is_edge = (tts_engine or "edge").strip().lower() == "edge"
        _spd = float(getattr(scene, "reading_speed", 1.0) or 1.0)
        rate = _reading_speed_to_rate(_spd) if _is_edge else "+0%"
        path = generate_narration_audio(
            text=text, language=language, gender=gender, rate=rate,
            job_id=job_id, voice_id=voice_id, output_path=out_path,
            content_type=content_type, tts_engine=tts_engine,
            emotion=str(getattr(scene, "emotion", "") or ""),   # D1
        )
        if not path or not Path(path).exists() or Path(path).stat().st_size <= 0:
            logger.warning("content_scene_render: TTS produced no audio (scene idx=%s)",
                           getattr(scene, "index", "?"))
            return None
        # W5-1: enforce reading_speed on engines that ignore/only-hint `rate`.
        # Note: an Edge request that silently fell back to piper/xtts offline is
        # not corrected here (we can't observe the fallback) — a known edge case.
        if not _is_edge and abs(_spd - 1.0) > 0.02:
            _tempo = _apply_tempo(path, _spd)
            if _tempo:
                path = _tempo
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


def _refine_long_cues(parts: list[str], max_cues: int) -> list[str]:
    """W5-5 — while under ``max_cues``, sub-split the longest over-target caption
    at its clause boundary nearest the middle (comma/semicolon/…), so a long
    sentence becomes a few readable lines instead of one wall of text. A cue with
    no clause boundary is left whole (can't split cleanly without word timings).
    Preserves chronological order. Never raises."""
    out = list(parts)
    try:
        while len(out) < max_cues:
            idx, longest = -1, _CAPTION_CHAR_TARGET
            for k, c in enumerate(out):
                if len(c) > longest and _CLAUSE_SPLIT_RE.search(c):
                    idx, longest = k, len(c)
            if idx < 0:
                break
            c = out[idx]
            cuts = [m.end() for m in _CLAUSE_SPLIT_RE.finditer(c)]
            mid = len(c) / 2.0
            cut = min(cuts, key=lambda p: abs(p - mid))
            a, b = c[:cut].strip(), c[cut:].strip()
            if not a or not b:
                break
            out[idx:idx + 1] = [a, b]
        return out
    except Exception:
        return parts


def _split_cues(text: str, max_cues: int) -> list[str]:
    """Split narration into up to ``max_cues`` caption chunks by sentence, then
    sub-split over-long sentences at clause boundaries (W5-5) if there is headroom,
    and finally merge if there are too many. Never raises."""
    t = " ".join((text or "").split())
    if not t:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(t) if p.strip()]
    if not parts:
        parts = [t]
    # W5-5: improve readability of long sentences before the merge step.
    if len(parts) < max_cues:
        parts = _refine_long_cues(parts, max_cues)
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


def _srt_to_sec(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _shift_srt(srt_path: str, offset_sec: float) -> None:
    """Add ``offset_sec`` to every cue time in an SRT in place. Used to shift the
    Whisper word timings (0-based on the TTS audio) by the scene's pause_before so
    the burned captions stay in sync with the ``adelay``-delayed narration."""
    lines = Path(srt_path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for ln in lines:
        m = _SRT_TIME_LINE_RE.match(ln.strip())
        if m:
            a = _srt_to_sec(m.group(1)) + offset_sec
            b = _srt_to_sec(m.group(2)) + offset_sec
            out.append(f"{_srt_time(a)} --> {_srt_time(b)}")
        else:
            out.append(ln)
    Path(srt_path).write_text("\n".join(out), encoding="utf-8")


def _word_srt_to_ass(
    word_srt: str, out_ass: str, width: int, height: int,
    style: str, offset_sec: float, emphasis=None,
) -> bool:
    """Render a 0-based word-level SRT to a CapCut word-by-word ASS, shifted by
    ``offset_sec`` (the scene's pause_before) so it syncs with the adelay'd
    narration. Copies the input to a scratch file so the caller's SRT is not
    mutated. Returns False on any failure. Never raises (Sacred Contract #3)."""
    scratch = str(Path(out_ass).with_suffix(".word.srt"))
    try:
        import shutil as _sh
        from app.features.render.engine.subtitle.generator.ass_capcut import srt_to_ass_capcut
        _sh.copyfile(word_srt, scratch)
        if not Path(scratch).exists() or Path(scratch).stat().st_size <= 0:
            return False
        if offset_sec and offset_sec > 0:
            _shift_srt(scratch, float(offset_sec))
        srt_to_ass_capcut(
            scratch, out_ass, style=(style or ""),
            play_res_x=int(width), play_res_y=int(height),
            emphasis=emphasis,   # D2
        )
        return Path(out_ass).exists() and Path(out_ass).stat().st_size > 0
    except Exception as exc:
        logger.info("content_scene_render: word-srt→ass failed (%s) — sentence SRT fallback", exc)
        return False
    finally:
        try:
            Path(scratch).unlink(missing_ok=True)
        except Exception:
            pass


def _build_word_ass(
    audio_path: str, out_ass: str, width: int, height: int,
    style: str, model_name: str, offset_sec: float,
    emphasis=None,
) -> bool:
    """Transcribe ONE narration clip with Whisper word timestamps → CapCut ASS.
    The per-scene fallback when W5-6's shared one-shot transcription isn't
    available (word timings not pre-computed for this scene). Returns False on any
    failure so the caller falls back to the sentence SRT. Never raises."""
    tmp_srt = str(Path(out_ass).with_suffix(".tx.srt"))
    try:
        from app.features.render.engine.subtitle.transcription.whisper import transcribe_to_srt
        transcribe_to_srt(str(audio_path), tmp_srt, model_name=model_name, highlight_per_word=True)
        if not Path(tmp_srt).exists() or Path(tmp_srt).stat().st_size <= 0:
            return False
        return _word_srt_to_ass(tmp_srt, out_ass, width, height, style, offset_sec, emphasis)
    except Exception as exc:
        logger.info(
            "content_scene_render: word-by-word subtitle unavailable (%s) — sentence SRT fallback",
            exc,
        )
        return False
    finally:
        try:
            Path(tmp_srt).unlink(missing_ok=True)
        except Exception:
            pass


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
    subtitle_style: str = "",
    ken_burns: bool = False,
    camera: str = "",
    word_by_word: bool = True,
    word_srt: Optional[str] = None,
) -> bool:
    """Compose one Content-Mode scene → ``out_path``. Returns True on success.

    Given a pre-synthesized narration audio (path + measured duration), builds the
    background, burns the subtitle, and muxes the delayed/padded narration. The
    subtitle is word-by-word (CapCut ASS via Whisper alignment on the TTS) when
    CONTENT_WORD_BY_WORD is on, falling back to a sentence-level SRT otherwise.
    The scene runs for pause_before + narration_dur + pause_after seconds.
    Returns False on any failure (never raises — Sacred Contract #3)."""
    bg_path = ""
    srt_path = ""
    ass_path = ""
    overlay_path = ""
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
        ass_path = str(work / f"content_sub_{idx:03d}.ass")

        # 1. Background video (scene-length, no audio).
        if not build_background_clip(
            kind=background_kind, value=background_value,
            width=int(width), height=int(height), fps=r,
            duration_sec=scene_dur, out_path=bg_path,
            ken_burns=bool(ken_burns), camera=(camera or ""),
        ):
            logger.warning("content_scene_render: background build failed (scene idx=%s)", idx)
            return False

        # 2. Subtitle (optional). Prefer word-by-word CapCut ASS (Whisper aligned
        #    on the TTS); fall back to the sentence SRT if that is off/unavailable.
        want_ass = False
        want_srt = False
        if subtitle_enabled:
            if word_by_word and _CONTENT_WORD_BY_WORD:
                # W5-6: prefer the pre-computed word SRT (one shared transcription
                # for the whole video) over a per-scene Whisper pass.
                if word_srt and Path(word_srt).exists() and Path(word_srt).stat().st_size > 0:
                    want_ass = _word_srt_to_ass(
                        word_srt, ass_path, int(width), int(height),
                        subtitle_style, pause_before,
                        emphasis=getattr(scene, "emphasis", None),   # D2
                    )
                if not want_ass:
                    want_ass = _build_word_ass(
                        narration_audio_path, ass_path, int(width), int(height),
                        subtitle_style, _CONTENT_WHISPER_MODEL, pause_before,
                        emphasis=getattr(scene, "emphasis", None),   # D2
                    )
            if not want_ass:
                want_srt = _build_scene_srt(
                    str(getattr(scene, "narration", "") or ""), pause_before, ndur, srt_path,
                )

        # E1: optional animated text overlay (title card / lower-third) from the
        # AI's animation_hint + scene_title. Best-effort — a failure skips it.
        overlay_path = ""
        if _CONTENT_TEXT_OVERLAY:
            _anim = (getattr(scene, "animation_hint", "") or "").strip().lower()
            _title = (getattr(scene, "scene_title", "") or "").strip()
            if _anim in ("title", "lower_third") and _title:
                from app.features.render.engine.stages.content_overlay import build_overlay_ass
                _ov = str(work / f"content_ov_{idx:03d}.ass")
                if build_overlay_ass(_title, _anim, int(width), int(height), scene_dur, _ov):
                    overlay_path = _ov

        # 3. Compose: burn subtitle + optional overlay (-vf) + delay/pad narration
        #    (-af) + mux.
        pb_ms = int(round(pause_before * 1000))
        af = f"adelay={pb_ms}:all=1,apad,atrim=0:{scene_dur:.3f},aresample={sr}"
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-i", bg_path,
            "-i", str(narration_audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
        ]
        _vf: list[str] = []
        if want_ass:
            _vf.append(f"ass='{safe_filter_path(ass_path)}'")
        elif want_srt:
            _vf.append(f"subtitles='{safe_filter_path(srt_path)}'")
        if overlay_path:
            _vf.append(f"ass='{safe_filter_path(overlay_path)}'")
        if _vf:
            cmd += ["-vf", ",".join(_vf)]
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
        _cleanup(ass_path)
        _cleanup(overlay_path)


def _cleanup(path: str) -> None:
    try:
        if path and Path(path).exists():
            Path(path).unlink()
    except Exception:
        pass
