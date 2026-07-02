import subprocess
import logging
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.ffmpeg_helpers import (
    _probe_duration,
    _run_ffmpeg_with_retry,
    _has_audio_stream,
    _tls,
)

logger = logging.getLogger(__name__)


def cut_video(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    retry_count: int = 2,
    force_accurate_cut: bool = False,
):
    """Cut a segment from input_path.

    force_accurate_cut=True skips the stream-copy attempt and goes straight to
    a full re-encode, guaranteeing frame-accurate output at the cost of speed.
    Use this whenever a visual first-frame correction has been applied so that
    the seek cannot land on the wrong keyframe.
    """
    intended_duration = max(0.0, float(end_time) - float(start_time))
    duration_tolerance = max(0.35, intended_duration * 0.03) if intended_duration > 0 else 0.35
    base = [
        get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-y", "-ss", str(start_time), "-t", str(intended_duration), "-i", input_path,
    ]

    def _probe_cut_duration() -> float | None:
        return _probe_duration(output_path)

    def _duration_ok(duration: float | None) -> bool:
        return duration is not None and abs(float(duration) - intended_duration) <= duration_tolerance

    copy_error: str | None = None

    if not force_accurate_cut:
        # Stream-copy first: fastest, lossless, no re-encode
        copy_cmd = [
            *base,
            "-map", "0:v:0", "-map", "0:a?",
            "-c", "copy", "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            _run_ffmpeg_with_retry(copy_cmd, retry_count=retry_count)
            raw_duration = _probe_cut_duration()
            if _duration_ok(raw_duration):
                # Keyframe-drift guard: stream-copy seeks to the nearest keyframe
                # before start_time.  If the output is >0.1 s longer than intended
                # it means extra pre-cut content was captured (drift).  Force an
                # accurate re-encode so subtitles and first-frame are both clean.
                _drift = float(raw_duration or 0.0) - intended_duration
                if _drift > 0.1:
                    copy_error = (
                        f"keyframe_drift intended={intended_duration:.3f}s "
                        f"raw={float(raw_duration or 0.0):.3f}s drift={_drift:.3f}s"
                    )
                    logger.warning(
                        "cut_video: keyframe_drift_detected output=%s "
                        "intended=%.3f raw=%.3f drift=%.3f → retrying with accurate cut",
                        Path(output_path).name, intended_duration,
                        float(raw_duration or 0.0), _drift,
                    )
                else:
                    logger.info(
                        "cut_video: cut_mode=copy intended_duration=%.3f raw_duration=%.3f tolerance=%.3f output=%s",
                        intended_duration, float(raw_duration or 0.0), duration_tolerance, Path(output_path).name,
                    )
                    return
            else:
                copy_error = (
                    f"duration_mismatch intended={intended_duration:.3f}s "
                    f"raw={float(raw_duration or 0.0):.3f}s tolerance={duration_tolerance:.3f}s"
                )
        except Exception as exc:
            copy_error = str(exc)
    else:
        copy_error = "force_accurate_cut=True"

    # Re-encode path: frame-accurate, handles corrupted keyframes / forced cuts
    fallback_cmd = [
        get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-y", "-i", input_path, "-ss", str(start_time), "-t", str(intended_duration),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k",
        "-movflags", "+faststart",
        output_path,
    ]
    logger.warning(
        "cut_video: cut_mode=accurate intended_duration=%.3f fallback_reason=%s output=%s",
        intended_duration, copy_error or "copy_failed", Path(output_path).name,
    )
    _run_ffmpeg_with_retry(fallback_cmd, retry_count=retry_count)
    raw_duration = _probe_cut_duration()
    logger.info(
        "cut_video: cut_mode=accurate intended_duration=%.3f raw_duration=%.3f tolerance=%.3f output=%s",
        intended_duration, float(raw_duration or 0.0), duration_tolerance, Path(output_path).name,
    )


def detect_silence_trim_offset(
    input_path: str,
    start_sec: float,
    end_sec: float,
    max_trim: float = 1.5,
    min_trim: float = 0.2,
    noise_db: float = -30.0,
    silence_min_dur: float = 0.1,
) -> float:
    """Return the seconds of leading silence at the start of a clip.

    Probes a short window at the clip start using ffmpeg silencedetect.
    Returns 0.0 when detection fails, no silence is found, or the
    silence_end falls outside [min_trim, max_trim].
    """
    clip_dur = end_sec - start_sec
    probe_dur = min(max_trim + 0.5, clip_dur)
    if probe_dur <= 0:
        return 0.0
    cmd = [
        get_ffmpeg_bin(), "-hide_banner",
        "-ss", str(start_sec),
        "-t", str(probe_dur),
        "-i", input_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={silence_min_dur}",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=20)
        for line in result.stderr.splitlines():
            if "silence_end:" in line:
                # "silence_end: 0.858333 | silence_duration: 0.858333"
                raw = line.split("silence_end:", 1)[1].split("|")[0].strip()
                silence_end = float(raw)
                offset = min(silence_end, max_trim)
                return offset if offset >= min_trim else 0.0
    except Exception:
        pass
    return 0.0


def detect_bad_first_frame(
    input_path: str,
    start_sec: float,
    end_sec: float,
    max_scan_sec: float = 1.5,
    max_shift_sec: float = 1.0,
    black_pix_threshold: float = 0.06,
) -> float:
    """Return seconds to skip past leading dark/black frames at the clip start.

    Runs a lightweight ffmpeg blackdetect probe on the first max_scan_sec of the
    clip.  Returns 0.0 when the opening frame is clean or on any detection error.

    The returned shift is always in the range (0.0, max_shift_sec].
    A minimum of 3 s of content is always preserved after the shift.

    pix_th=0.06 catches near-black frames (≤6% average brightness) that a
    10% threshold would miss (e.g. very dark intros or fade-from-black sequences).
    """
    clip_dur = max(0.0, float(end_sec) - float(start_sec))
    # Leave at least 0.5 s of content after any shift
    scan_dur = min(float(max_scan_sec), clip_dur - 0.5)
    if scan_dur < 0.08:
        return 0.0

    cmd = [
        get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-ss", str(start_sec),
        "-t", str(scan_dur),
        "-i", input_path,
        "-vf", f"blackdetect=d=0.0:pix_th={black_pix_threshold}",
        "-an", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
        # blackdetect writes to stderr:
        # [blackdetect @ 0x...] black_start:0 black_end:0.458 black_duration:0.458
        for line in (result.stderr or "").splitlines():
            if "black_start:" not in line or "black_end:" not in line:
                continue
            try:
                b_start = b_end = None
                for token in line.split():
                    if token.startswith("black_start:"):
                        b_start = float(token.split(":", 1)[1])
                    elif token.startswith("black_end:"):
                        b_end = float(token.split(":", 1)[1])
                if b_start is None or b_end is None:
                    continue
                # Only shift when the dark region starts at the very beginning
                if b_start > 0.08:
                    continue
                if b_end <= 0.08:
                    continue
                shift = min(b_end, float(max_shift_sec))
                # Don't shift if it would leave fewer than 3 s of content
                if clip_dur - shift < 3.0:
                    shift = max(0.0, clip_dur - 3.0)
                return shift if shift > 0.08 else 0.0
            except (ValueError, IndexError):
                continue
    except Exception:
        pass
    return 0.0


def _detect_silence_segments(
    input_path: str,
    noise_db: float = -30.0,
    min_dur: float = 0.3,
) -> list[tuple[float, float]]:
    """Return (start, end) pairs of silence regions detected inside input_path."""
    cmd = [
        get_ffmpeg_bin(), "-hide_banner",
        "-i", input_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ]
    try:
        cancel_ev = getattr(_tls, 'cancel_event', None)
        if cancel_ev is not None and cancel_ev.is_set():
            return []
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
        segments: list[tuple[float, float]] = []
        pending_start: float | None = None
        for line in result.stderr.splitlines():
            if "silence_start:" in line:
                try:
                    pending_start = float(line.split("silence_start:", 1)[1].strip())
                except ValueError:
                    pass
            elif "silence_end:" in line and pending_start is not None:
                try:
                    end = float(line.split("silence_end:", 1)[1].split("|")[0].strip())
                    segments.append((pending_start, end))
                    pending_start = None
                except ValueError:
                    pass
        return segments
    except Exception:
        return []


_PACING_LEGACY_FLAGS: list[str] = ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]


def _pacing_encode_flags(video_codec: str, encoder_mode: str) -> tuple[list[str], bool]:
    """Cờ encoder cho pass re-encode của micro-pacing → (flags, used_gpu).

    Mặc định giữ nguyên libx264 medium crf17 — hành vi legacy bit-identical.
    Khi ``MICRO_PACING_GPU=1`` và job resolve ra GPU encoder: encode pass này
    trên GPU với cùng mục tiêu chất lượng (bộ cờ chuẩn từ
    ``encoder_helpers.gpu_pacing_flags`` — literal codec GPU sống ở đó để
    file này giữ đúng phân loại false-positive của
    tests/test_nvenc_semaphore_external_acquire.py). Lý do: pass này trước
    đây luôn chạy libx264 trên CPU (90-110s cho clip 60s theo log
    production) trong khi GPU ngồi không sau lần encode chính.
    ``_run_ffmpeg_with_retry`` tự acquire NVENC_SEMAPHORE khi argv chứa
    codec GPU nên không cần khoá thủ công. Mọi lỗi resolve → rơi về cờ
    legacy, không bao giờ raise.
    """
    import os as _os
    if _os.getenv("MICRO_PACING_GPU", "0") != "1":
        return list(_PACING_LEGACY_FLAGS), False
    try:
        from app.features.render.engine.encoder.encoder_helpers import gpu_pacing_flags
        _gpu = gpu_pacing_flags(video_codec, encoder_mode)
        if _gpu is None:
            return list(_PACING_LEGACY_FLAGS), False
        return _gpu, True
    except Exception:
        return list(_PACING_LEGACY_FLAGS), False


def apply_micro_pacing(
    input_path: str,
    output_path: str,
    noise_db: float = -30.0,
    min_silence_dur: float = 0.4,
    max_total_trim: float = 2.0,
    min_clip_dur: float = 5.0,
    content_type: str = "vlog",
    video_codec: str = "",
    encoder_mode: str = "auto",
) -> dict:
    """Compress mid-clip silences with human-feeling rhythm.

    Silence thresholds, kept durations, and max trim budget are adjusted per
    content type (interview / commentary / vlog / tutorial / montage). Short
    breath pauses are preserved; genuine dead air is trimmed. The last 2s of
    each clip (payoff zone) receive gentler trimming to protect reactions and
    reveals. Splices saving less than 100ms are skipped to prevent over-cutting.

    Returns {"applied": bool, "segments_trimmed": int, "total_trim_ms": int, "method": str}.
    Raises on FFmpeg error so the caller can fall back to the original file.
    """
    _NO_OP: dict = {"applied": False, "segments_trimmed": 0, "total_trim_ms": 0, "method": "audio"}

    clip_dur = _probe_duration(input_path)
    if clip_dur is None or clip_dur < min_clip_dur:
        return _NO_OP

    # Content-aware pacing parameters (PART D)
    _type_params: dict[str, dict] = {
        "interview":  {"db_adj": -5.0, "dur_adj":  0.10, "target_mul": 1.50, "max_trim": 1.5},
        "commentary": {"db_adj": -3.0, "dur_adj":  0.05, "target_mul": 1.25, "max_trim": 1.8},
        "vlog":       {"db_adj":  0.0, "dur_adj":  0.00, "target_mul": 1.00, "max_trim": 2.0},
        "tutorial":   {"db_adj": -4.0, "dur_adj":  0.10, "target_mul": 1.40, "max_trim": 1.5},
        "montage":    {"db_adj":  2.0, "dur_adj": -0.10, "target_mul": 0.80, "max_trim": 2.5},
    }
    _p = _type_params.get(content_type, _type_params["vlog"])
    effective_noise_db = noise_db + _p["db_adj"]
    effective_min_dur = max(0.25, min_silence_dur + _p["dur_adj"])
    target_multiplier: float = _p["target_mul"]
    effective_max_trim: float = _p["max_trim"]

    silences = _detect_silence_segments(input_path, noise_db=effective_noise_db, min_dur=effective_min_dur)
    # PART A: protect clip boundaries — 0.6s start buffer (was 0.5s), 0.3s end buffer
    silences = [(s, e) for s, e in silences if s >= 0.6 and e <= clip_dur - 0.3]
    if not silences:
        return _NO_OP

    # PART E: payoff zone — last 2s may contain a reaction/reveal; trim more gently there
    _payoff_zone_start = max(0.0, clip_dur - 2.0)

    def _target_dur(dur: float, mul: float = 1.0) -> float:
        # PART A+B: preserve more of medium/long silences — they are more likely intentional.
        # Short (≤0.5s): breath pause     → keep 0.20s  (was 0.15s for ≤0.7s)
        # Medium (≤0.9s): rhythm pause    → keep 0.30s  (was 0.25s for ≤1.2s)
        # Long (≤1.5s): emphasis/sentence → keep 0.45s  (was 0.40s for >1.2s)
        # Dead air (>1.5s): genuine gap   → keep 0.50s
        if dur <= 0.5:
            base = 0.20
        elif dur <= 0.9:
            base = 0.30
        elif dur <= 1.5:
            base = 0.45
        else:
            base = 0.50
        return min(dur - 0.05, base * mul)

    # Build a list of (keep_start, keep_end) timeline segments
    keeps: list[tuple[float, float]] = []
    prev_end = 0.0
    total_trim = 0.0
    segments_trimmed = 0
    _MIN_TRIM = 0.10  # PART C: skip splice if saving < 100ms (over-cut prevention)

    for s_start, s_end in silences:
        s_dur = s_end - s_start
        # PART E: apply gentler multiplier inside the payoff zone
        _eff_mul = target_multiplier * (1.5 if s_start >= _payoff_zone_start else 1.0)
        trim = s_dur - _target_dur(s_dur, _eff_mul)
        remaining = effective_max_trim - total_trim
        if remaining <= 0 or trim < _MIN_TRIM:  # PART C: skip tiny trims
            continue
        trim = min(trim, remaining)
        # Keep speech up to the silence, plus the kept portion of the silence
        keep_end = s_start + (s_dur - trim)
        if keep_end > prev_end:
            keeps.append((prev_end, keep_end))
        prev_end = s_end
        total_trim += trim
        segments_trimmed += 1

    if prev_end < clip_dur:
        keeps.append((prev_end, clip_dur))

    if segments_trimmed == 0 or len(keeps) <= 1:
        return _NO_OP

    # B1-OPT-2 (2026-06-28): skip the full libx264 re-encode when the total
    # trim is below MICRO_PACING_MIN_TRIM_MS (default 500 ms). Re-encoding a
    # 60s clip with preset=medium crf=17 costs 90-110 seconds in production
    # logs — paying that to remove <0.5s of silence is a bad trade. The
    # output is essentially indistinguishable (humans can't notice <0.2s
    # rhythm shifts on most clips). Override via env when tighter pacing
    # matters more than render time (set to "0" to disable the skip entirely).
    import os as _os
    _min_trim_ms = max(0, int(_os.getenv("MICRO_PACING_MIN_TRIM_MS", "500")))
    _total_trim_ms = int(total_trim * 1000)
    if _total_trim_ms < _min_trim_ms:
        logger.info(
            "micro_pacing: skipped re-encode total_trim_ms=%d threshold_ms=%d "
            "segments_trimmed=%d (saving ~90-110s)",
            _total_trim_ms, _min_trim_ms, segments_trimmed,
        )
        return {
            "applied": False,
            "segments_trimmed": segments_trimmed,
            "total_trim_ms": _total_trim_ms,
            "method": "skipped_low_trim",
        }

    has_audio = _has_audio_stream(input_path)
    n = len(keeps)

    # Build a filter_complex that splices the keeps together
    fc: list[str] = []
    fc.append(f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n)))
    if has_audio:
        fc.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)))

    for i, (seg_s, seg_e) in enumerate(keeps):
        fc.append(
            f"[vs{i}]trim=start={seg_s:.6f}:end={seg_e:.6f},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
        if has_audio:
            fc.append(
                f"[as{i}]atrim=start={seg_s:.6f}:end={seg_e:.6f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )

    v_cat = "".join(f"[v{i}]" for i in range(n))
    fc.append(f"{v_cat}concat=n={n}:v=1:a=0[vout]")
    if has_audio:
        a_cat = "".join(f"[a{i}]" for i in range(n))
        fc.append(f"{a_cat}concat=n={n}:v=0:a=1[aout]")

    filter_complex = ";".join(fc)
    map_args = ["-map", "[vout]", "-map", "[aout]"] if has_audio else ["-map", "[vout]"]
    audio_args = ["-c:a", "aac", "-b:a", "192k"] if has_audio else []

    _encode_flags, _gpu_pacing_used = _pacing_encode_flags(video_codec, encoder_mode)

    def _pacing_cmd(flags: list[str]) -> list[str]:
        return [
            get_ffmpeg_bin(), "-hide_banner", "-y",
            "-i", input_path,
            "-filter_complex", filter_complex,
            *map_args,
            *flags,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            *audio_args,
            output_path,
        ]

    try:
        _run_ffmpeg_with_retry(_pacing_cmd(_encode_flags), retry_count=0)
    except Exception:
        # GPU encode lỗi (hết phiên, driver, ...) → thử lại bằng cờ legacy
        # CPU để tính năng pacing không mất; đường legacy lỗi thì raise như
        # cũ cho caller giữ nguyên file chưa pacing.
        if _gpu_pacing_used:
            logger.warning("micro_pacing: GPU encode failed — retrying on libx264")
            _run_ffmpeg_with_retry(_pacing_cmd(list(_PACING_LEGACY_FLAGS)), retry_count=0)
        else:
            raise

    return {
        "applied": True,
        "segments_trimmed": segments_trimmed,
        "total_trim_ms": int(total_trim * 1000),
        "method": "audio",
    }

