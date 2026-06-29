"""
timed_narration.py — Synthesize a per-clip narration audio file from a
list of timed segments produced by the rewrite LLM.

For each segment {start, end, text}:
  1. Generate TTS into a temp mp3.
  2. ffprobe the actual duration.
  3. If TTS duration > segment duration, atempo it up (clamped 1.0-1.25)
     so it fits within the slot.
  4. Concat all segments with silence pads at the segment.start offsets,
     producing one mp3 spanning [0, clip_duration_sec].

Sacred Contract #3 — every public entry point returns None on any
failure rather than raising so the caller (part_voice_mix) can fall back
to the original transcript text path.

Falls back gracefully:
  - 0 segments succeeded → returns None (caller treats as TTS failure).
  - some segments succeed → silence pad the failed slots, narration
    keeps going for the rest of the clip.
"""
from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from app.core.config import TEMP_DIR
from app.features.render.engine.audio.tts import generate_narration_audio
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger("app.render.timed_narration")

_PROBE_TIMEOUT_SEC: int = 30
_FFMPEG_TIMEOUT_SEC: int = max(60, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "600")))
_MIN_SEGMENT_SEC: float = 0.3   # below this, skip the segment (TTS would be a stub)
_ATEMPO_MIN: float = 1.0
_ATEMPO_MAX: float = 1.25       # cap speed-up so voice doesn't sound chipmunk

# B1-OPT-1 (2026-06-28): synthesise segments in parallel. Default 3 keeps us
# under Edge-TTS rate caps; raise via env when the user has paid TTS quota or
# is running fully offline (Piper/XTTS). Cap at 8 to avoid disk/thread storms.
_TTS_CONCURRENCY: int = max(1, min(8, int(os.getenv("TIMED_NARRATION_TTS_CONCURRENCY", "3"))))


def _probe_duration_s(path: str) -> float:
    """Return audio duration in seconds. 0.0 on failure."""
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


def _atempo_fit(src_mp3: Path, target_dur: float, out_mp3: Path) -> bool:
    """Speed up src_mp3 to fit target_dur using atempo. Returns True on success."""
    try:
        actual = _probe_duration_s(str(src_mp3))
        if actual <= 0 or target_dur <= 0:
            return False
        if actual <= target_dur:
            # No need to speed up — caller can use src directly.
            return False
        ratio = actual / target_dur
        atempo = max(_ATEMPO_MIN, min(_ATEMPO_MAX, ratio))
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-i", str(src_mp3),
            "-filter:a", f"atempo={atempo:.4f}",
            "-c:a", "libmp3lame", "-q:a", "4",
            str(out_mp3),
        ]
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        return out_mp3.exists() and out_mp3.stat().st_size > 0
    except Exception as exc:
        logger.warning("timed_narration: atempo fit failed: %s", exc)
        return False


def _concat_with_pads(
    segment_mp3s: list[tuple[float, Path]],
    clip_duration_sec: float,
    out_mp3: Path,
) -> bool:
    """Concat segments with silence pads at their start offsets.

    segment_mp3s: list of (start_sec, mp3_path), assumed sorted by start.
    The output mp3 is exactly clip_duration_sec long.
    """
    if not segment_mp3s:
        return False
    try:
        # Build a filter graph that lays each segment at its start time using
        # adelay (in ms), then mixes them all together with amix. Cap to clip
        # duration with -t.
        #
        # 2026-06-28 volume bug fix: amix's default behaviour DIVIDES the
        # output volume by N (number of input streams). With 19 segments
        # the narration ended up at ~5% volume which sounded near-silent.
        # Pin `normalize=0` so each segment plays at its full TTS volume.
        # Since segments don't overlap in time (separated by silence pads
        # from adelay), keeping all inputs at unity gain produces the
        # expected per-segment loudness with no clipping.
        inputs: list[str] = []
        for _, p in segment_mp3s:
            inputs.extend(["-i", str(p)])
        filter_parts: list[str] = []
        for idx, (start_sec, _) in enumerate(segment_mp3s):
            delay_ms = max(0, int(round(start_sec * 1000)))
            # adelay needs per-channel delays; "all=1" applies the same to every channel.
            filter_parts.append(
                f"[{idx}:a]adelay={delay_ms}|{delay_ms},apad[d{idx}]"
            )
        mix_inputs = "".join(f"[d{i}]" for i in range(len(segment_mp3s)))
        filter_parts.append(
            f"{mix_inputs}amix=inputs={len(segment_mp3s)}:duration=longest:dropout_transition=0:normalize=0[aout]"
        )
        filter_graph = ";".join(filter_parts)
        cmd = [
            get_ffmpeg_bin(), "-y",
            *inputs,
            "-filter_complex", filter_graph,
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-q:a", "4",
            "-t", f"{clip_duration_sec:.3f}",
            str(out_mp3),
        ]
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        return out_mp3.exists() and out_mp3.stat().st_size > 0
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("timed_narration: concat failed: %s", detail[:400] or exc)
        return False
    except Exception as exc:
        logger.warning("timed_narration: concat unexpected error: %s", exc)
        return False


def synthesize_timed_narration(
    *,
    segments: list[dict],
    clip_duration_sec: float,
    voice_language: str,
    voice_gender: str,
    voice_rate: str,
    voice_id: Optional[str],
    content_type: str,
    tts_engine: str,
    job_id: str,
    part_idx: int,
) -> Optional[str]:
    """Synthesize a per-clip narration audio file from a list of timed segments.

    Returns the final mp3 path, or None on any failure (Sacred #3).
    """
    if not segments:
        logger.warning("timed_narration: empty segments")
        return None

    work_dir = TEMP_DIR / job_id / "voice" / f"part_{part_idx:03d}_segs"
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("timed_narration: cannot create work_dir: %s", exc)
        return None

    # B1-OPT-1 (2026-06-28): synthesise each segment in parallel. Each worker
    # is fully self-contained (own raw + fit mp3 paths), Sacred Contract #3
    # preserved (any one segment's TTS failure becomes a None return, the
    # remaining segments still build the narration). Order is restored after
    # the workers complete so silence padding at concat time stays correct.

    def _synth_one_segment(i: int, seg: dict) -> Optional[tuple[float, Path]]:
        """Synthesise segment i in isolation. Returns (start_sec, mp3_path)
        on success, None on failure / skip. Never raises."""
        try:
            # Reaction mode: "original" segments mean the reactor stays SILENT
            # and the source audio plays — no TTS for them. (They also carry no
            # text, so the guard below would skip them anyway; this is explicit.)
            if str(seg.get("kind", "voice") or "voice").strip().lower() == "original":
                return None
            try:
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", 0.0))
                text = str(seg.get("text", "")).strip()
            except (TypeError, ValueError):
                return None
            if not text or end <= start:
                return None
            seg_dur = end - start
            if seg_dur < _MIN_SEGMENT_SEC:
                logger.info(
                    "timed_narration: skipping micro-segment %d dur=%.2fs",
                    i, seg_dur,
                )
                return None
            raw_mp3 = work_dir / f"seg_{i:03d}_raw.mp3"
            try:
                generate_narration_audio(
                    text=text,
                    language=voice_language,
                    gender=voice_gender,
                    rate=voice_rate,
                    job_id=job_id,
                    voice_id=voice_id,
                    output_path=str(raw_mp3),
                    content_type=content_type,
                    tts_engine=tts_engine,
                )
            except Exception as exc:
                logger.warning(
                    "timed_narration: TTS failed for seg %d (%.1f-%.1fs): %s",
                    i, start, end, exc,
                )
                return None
            if not raw_mp3.exists() or raw_mp3.stat().st_size <= 0:
                logger.warning("timed_narration: TTS produced empty file for seg %d", i)
                return None
            fit_mp3 = work_dir / f"seg_{i:03d}_fit.mp3"
            if _atempo_fit(raw_mp3, seg_dur, fit_mp3):
                logger.info(
                    "timed_narration: seg %d atempo-fitted (target=%.2fs)", i, seg_dur,
                )
                return (start, fit_mp3)
            return (start, raw_mp3)
        except Exception as exc:
            # Sacred Contract #3 — worker boundary catches everything.
            logger.warning("timed_narration: worker for seg %d raised: %s", i, exc)
            return None

    workers = min(_TTS_CONCURRENCY, max(1, len(segments)))
    results: list[Optional[tuple[float, Path]]] = [None] * len(segments)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"tts_{job_id[:8]}") as pool:
        futures = {pool.submit(_synth_one_segment, i, seg): i for i, seg in enumerate(segments)}
        for fut in futures:
            results[futures[fut]] = fut.result()  # collect in original index order
    placed: list[tuple[float, Path]] = [r for r in results if r is not None]
    placed.sort(key=lambda x: x[0])

    if not placed:
        logger.warning("timed_narration: no segments synthesised — returning None")
        return None

    final_mp3 = TEMP_DIR / job_id / "voice" / f"part_{part_idx:03d}.mp3"
    final_mp3.parent.mkdir(parents=True, exist_ok=True)
    if not _concat_with_pads(placed, clip_duration_sec, final_mp3):
        logger.warning("timed_narration: concat step failed")
        return None

    logger.info(
        "timed_narration: built %d-segment narration (%.1fs) for part %d at %s",
        len(placed), clip_duration_sec, part_idx, final_mp3,
    )
    return str(final_mp3)
