
import json
import os
import subprocess
import threading
import time
import logging
from functools import lru_cache
from pathlib import Path
from app.services.motion_crop import render_motion_aware_crop, MotionCropConfig
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import append_text_layer_filters
from app.services.encoder_helpers import (
    ffmpeg_encoders_text as _ffmpeg_encoders_text,
    has_encoder as _has_encoder,
    nvenc_runtime_ready as _nvenc_runtime_ready,
    codec_extra_flags as _codec_extra_flags,
    map_preset_for_encoder as _map_preset_for_encoder,
    reup_video_filters as _reup_video_filters,
    reup_audio_filter as _reup_audio_filter,
    safe_filter_path as _safe_filter_path,
    detect_windows_fontfile as _detect_windows_fontfile,
    detect_windows_fonts_dir as _detect_windows_fonts_dir,
    get_custom_fonts_dir as _get_custom_fonts_dir,
)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource semaphores
# ---------------------------------------------------------------------------
# Consumer NVIDIA GPUs support 3–5 concurrent NVENC sessions. Exceeding the
# limit causes encode failures with "no NVENC capable devices found".
# Override with NVENC_MAX_SESSIONS env var if your GPU supports more.
_NVENC_SEM_VALUE: int = max(1, int(os.getenv("NVENC_MAX_SESSIONS", "3")))
NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)

# Maximum wall-clock seconds a single FFmpeg encode call is allowed to run.
# A hung FFmpeg (codec bug, I/O stall, corrupted input) would otherwise hold a
# JOB_SEMAPHORE slot forever, stalling all further renders.
# Override with FFMPEG_TIMEOUT_SECONDS env var (e.g. for very long source files).
_FFMPEG_TIMEOUT_SEC: int = max(60, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "3600")))

# Thread-local slot for the per-job cancel event.
# render_pipeline sets it at the start of each part so _run_ffmpeg_with_retry can
# kill the FFmpeg Popen when a cancel is requested without needing an extra argument.
_tls = threading.local()


def set_thread_cancel_event(ev) -> None:
    """Register a cancel threading.Event for the current worker thread."""
    _tls.cancel_event = ev

# ---------------------------------------------------------------------------
# ffprobe metadata cache — keyed by (abspath, mtime_ns, size_bytes)
# ---------------------------------------------------------------------------
# Consolidates multiple per-attribute probes into one subprocess call per file.
# Cache is invalidated automatically when file mtime or size changes.
# Failed probes are never cached — they return zero/None defaults and retry.
_PROBE_CACHE: dict[tuple, dict] = {}
_PROBE_CACHE_LOCK = threading.Lock()


def _file_probe_key(path: str) -> "tuple | None":
    """Return (abspath, mtime_ns, size) cache key, or None if stat fails."""
    try:
        st = Path(path).stat()
        return (str(Path(path).resolve()), st.st_mtime_ns, st.st_size)
    except Exception:
        return None


def probe_video_metadata(path: str, timeout: int = 15) -> dict:
    """Return {duration, fps, has_audio, has_video, width, height} for path.

    Runs one ffprobe JSON call and caches by (abspath, mtime, size) so repeated
    probes on the same unmodified file cost zero subprocess calls.
    Failed probes are not cached — zero/None defaults are returned and retried.
    """
    key = _file_probe_key(path)
    if key:
        with _PROBE_CACHE_LOCK:
            cached = _PROBE_CACHE.get(key)
        if cached is not None:
            return cached

    result: dict = {
        "duration": None,
        "fps": 0.0,
        "has_audio": False,
        "has_video": False,
        "width": 0,
        "height": 0,
    }
    try:
        cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,avg_frame_rate,r_frame_rate,width,height",
            "-of", "json", str(path),
        ]
        t0 = time.monotonic()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        _ms = int((time.monotonic() - t0) * 1000)
        if r.returncode == 0:
            data = json.loads(r.stdout or "{}")
            fmt = data.get("format", {})
            try:
                raw_dur = fmt.get("duration")
                if raw_dur:
                    result["duration"] = float(raw_dur)
            except (ValueError, TypeError):
                pass
            for stream in data.get("streams", []):
                ct = stream.get("codec_type", "")
                if ct == "video" and not result["has_video"]:
                    result["has_video"] = True
                    try:
                        result["width"] = int(stream.get("width") or 0)
                        result["height"] = int(stream.get("height") or 0)
                    except (ValueError, TypeError):
                        pass
                    for fps_field in ("avg_frame_rate", "r_frame_rate"):
                        fps_val = _parse_fps_ratio(stream.get(fps_field) or "")
                        if 1.0 <= fps_val <= 120.0:
                            result["fps"] = fps_val
                            break
                elif ct == "audio":
                    result["has_audio"] = True
            logger.debug(
                "ffprobe_metadata_ms=%d path=%s has_video=%s has_audio=%s fps=%.1f dur=%s",
                _ms, Path(path).name, result["has_video"], result["has_audio"],
                result["fps"], result["duration"],
            )
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe_metadata_timeout path=%s timeout=%ds", Path(path).name, timeout)
        return result
    except Exception:
        return result

    # Only store probes where we confirmed video presence — avoids caching garbage.
    if key and result["has_video"]:
        with _PROBE_CACHE_LOCK:
            _PROBE_CACHE[key] = result
    return result


def extract_thumbnail_frame(
    path: str,
    offset_sec: float = 0.5,
    width: int = 320,
    timeout: int = 10,
) -> "bytes | None":
    """Extract one JPEG frame at offset_sec from path. Returns raw JPEG bytes or None."""
    try:
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-ss", str(max(0.0, offset_sec)),
            "-i", str(path),
            "-frames:v", "1",
            "-vf", f"scale={max(32, width)}:-2",
            "-f", "image2",
            "-vcodec", "mjpeg",
            "pipe:1",
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if r.returncode == 0 and len(r.stdout) > 100:
            return bytes(r.stdout)
    except Exception:
        pass
    return None


def _run_ffmpeg_with_retry(command: list[str], retry_count: int = 2, wait_sec: float = 0.8):
    # Pick up the cancel event registered by render_pipeline for this worker thread.
    cancel_event = getattr(_tls, 'cancel_event', None)
    attempt = 0
    while True:
        attempt += 1
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Run communicate in a daemon thread so the main loop can poll for
            # cancel/timeout without risking pipe-buffer deadlock.
            _done = threading.Event()
            _result: list = [None, None, None]  # [stdout, stderr, returncode]

            def _communicate(_p=proc, _d=_done, _r=_result):
                out, err = _p.communicate()
                _r[0] = out
                _r[1] = err
                _r[2] = _p.returncode
                _d.set()

            threading.Thread(target=_communicate, daemon=True).start()

            deadline = time.monotonic() + _FFMPEG_TIMEOUT_SEC
            while not _done.wait(timeout=1.0):
                if cancel_event is not None and cancel_event.is_set():
                    proc.terminate()
                    if not _done.wait(timeout=5):
                        proc.kill()
                        _done.wait(timeout=2)
                    raise RuntimeError("FFmpeg cancelled")
                if time.monotonic() > deadline:
                    proc.terminate()
                    if not _done.wait(timeout=5):
                        proc.kill()
                        _done.wait(timeout=2)
                    raise RuntimeError(
                        f"FFmpeg timed out after {_FFMPEG_TIMEOUT_SEC}s and was killed. "
                        "Increase FFMPEG_TIMEOUT_SECONDS env var for very long source files."
                    )

            stdout = _result[0] or ""
            stderr = _result[1] or ""
            if _result[2] != 0:
                raise subprocess.CalledProcessError(_result[2], command, stdout, stderr)
            return subprocess.CompletedProcess(command, _result[2], stdout, stderr)
        except RuntimeError:
            raise
        except subprocess.CalledProcessError as exc:
            if attempt > retry_count:
                stderr_text = exc.stderr or ""
                diag = _summarize_ffmpeg_stderr(stderr_text)
                stderr_tail = stderr_text[-2000:].strip()
                raise RuntimeError(
                    f"FFmpeg render failed: {diag} (exit={exc.returncode})"
                    + (f"\n{stderr_tail}" if stderr_tail else "")
                ) from exc
            time.sleep(wait_sec * attempt)
        except Exception:
            if attempt > retry_count:
                raise
            time.sleep(wait_sec * attempt)


# ---------------------------------------------------------------------------
# nvenc_available — cached GPU-readiness check exported to render_pipeline
# _resolve_codec — kept as a proper function so tests can patch _has_encoder
#                  and _nvenc_runtime_ready at the render_engine module level
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    """Return True if at least one NVENC encoder is present and runtime-ready.

    Cached at module level so the GPU probe runs at most once per process.
    Importable by other modules (e.g. render_pipeline) to inform worker
    count decisions before any encoding actually starts.
    """
    for codec_name in ("h264_nvenc", "hevc_nvenc"):
        if _has_encoder(codec_name) and _nvenc_runtime_ready(codec_name):
            return True
    return False


def _resolve_codec(codec: str, encoder_mode: str = "auto"):
    c = (codec or "h264").lower()
    mode = (encoder_mode or "auto").lower()

    if mode in ("auto", "nvenc"):
        if c == "h265" and _has_encoder("hevc_nvenc") and _nvenc_runtime_ready("hevc_nvenc"):
            return "hevc_nvenc"
        if c != "h265" and _has_encoder("h264_nvenc") and _nvenc_runtime_ready("h264_nvenc"):
            return "h264_nvenc"
        if mode == "nvenc":
            # Requested nvenc but unavailable: fallback CPU.
            pass

    if c == "h265":
        return "libx265"
    return "libx264"


def _effect_filter(effect_preset: str):
    preset = (effect_preset or "slay_soft_01").lower()
    if preset == "slay_pop_01":
        return "eq=contrast=1.08:saturation=1.18:brightness=0.01:gamma=1.02,unsharp=5:5:1.2:3:3:0.5"
    if preset == "story_clean_01":
        return "eq=contrast=1.03:saturation=1.05:brightness=0.0,unsharp=3:3:0.6:3:3:0.15"
    if preset == "social_bright":
        return "eq=contrast=1.06:saturation=1.22:brightness=0.02:gamma=0.98,unsharp=5:5:1.0:3:3:0.4"
    if preset == "cinematic_soft":
        return "eq=contrast=1.04:saturation=0.92:brightness=-0.01:gamma=1.04,unsharp=3:3:0.5:3:3:0.1,hqdn3d=1.5:1.5:6:6"
    if preset == "high_contrast":
        return "eq=contrast=1.15:saturation=1.10:brightness=-0.02:gamma=1.0,unsharp=7:7:1.5:5:5:0.6"
    # slay_soft_01 (default): natural cinematic look with light sharpening
    return "eq=contrast=1.05:saturation=1.10:brightness=0.0:gamma=1.01,unsharp=5:5:0.9:3:3:0.35"


def _cinematic_color_filter(src_h: int, content_type: str = "vlog") -> "str | None":
    """Content-type-aware contrast/saturation lift after recompression.

    tutorial/interview: near-neutral — preserve screen and face authenticity.
    montage: slightly richer for energy feel.
    commentary/vlog: balanced lift (original behaviour).
    Disabled for sources below 480p.
    """
    if 0 < src_h < 480:
        return None
    if content_type in ("tutorial", "interview"):
        return "eq=contrast=1.01:saturation=1.01"
    if content_type == "montage":
        return "eq=contrast=1.03:saturation=1.06"
    return "eq=contrast=1.02:saturation=1.03"


def _cinematic_sharpen_filter(src_h: int, content_type: str = "vlog") -> "str | None":
    """Content-type-aware luma-only edge sharpening.

    tutorial/interview: slightly stronger for text and screen clarity.
    montage: reduced to avoid halos on fast motion.
    commentary/vlog: standard (original behaviour).
    Disabled for sources below 480p — halos appear on noisy/low-res content.
    """
    if 0 < src_h < 480:
        return None
    if content_type in ("tutorial", "interview"):
        return "unsharp=5:5:0.5:5:5:0.0"
    if content_type == "montage":
        return "unsharp=3:3:0.25:3:3:0.0"
    return "unsharp=5:5:0.4:5:5:0.0"


def _smart_denoise_filter(content_type: str, preset: str, src_h: int) -> "str | None":
    """Return an hqdn3d denoise filter string, or None when denoise should be skipped.

    montage: skipped — motion smearing risk outweighs benefit.
    slower/veryslow preset: full denoise (quality mode, no change to existing behaviour).
    slow preset + interview/tutorial: lite denoise for static talking-head / screen content.
    low-res source (<720p, any non-montage type): lite denoise — compressed noise amplified by upscale.
    """
    if content_type == "montage":
        return None
    if preset in ("slower", "veryslow"):
        return "hqdn3d=1.5:1.5:6:6"
    if preset == "slow" and content_type in ("interview", "tutorial"):
        return "hqdn3d=1.0:1.0:4:4"
    if 0 < src_h < 720:
        return "hqdn3d=0.8:0.8:3:3"
    return None


def content_type_crf_delta(content_type: str) -> int:
    """Return a CRF adjustment for content-type-aware encode sharpness.

    tutorial/interview: -2 — fine text and screen detail benefit from tighter quantisation.
    montage: +1 — fast motion benefits more from AQ than marginal CRF improvement.
    Others: 0 (no change from profile default).
    """
    return {"tutorial": -2, "interview": -2, "montage": 1}.get(content_type or "", 0)


def _build_audio_filter(loudnorm_enabled: bool, reup_mode: bool, speed: float) -> str | None:
    """Return a comma-joined -af filter string, or None when no audio processing is needed."""
    parts = []
    if loudnorm_enabled and not reup_mode:
        # Creator-grade audio polish: rumble removal → loudness target → gentle compression → limiter.
        # acompressor ratio=2 at -18dB threshold: natural dynamic control without pumping.
        parts.append("highpass=f=80")
        parts.append("loudnorm=I=-14:LRA=11:TP=-1.0")
        parts.append("acompressor=threshold=-18dB:ratio=2:attack=40:release=300:makeup=1.5")
        parts.append("alimiter=limit=0.95")
    if reup_mode:
        parts.append(_reup_audio_filter())
    if abs(speed - 1.0) > 1e-4:
        parts.append(f"atempo={speed:.4f}")
    return ",".join(parts) if parts else None


_FPS_CAP = 60  # hard ceiling — prevents encode overhead for HFR sources


def _parse_fps_ratio(s: str) -> float:
    """Parse a fraction string like '60/1' or '60000/1001' to a float. Returns 0.0 on failure."""
    s = (s or "").strip()
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return float(a) / float(b) if float(b) else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _probe_fps(input_path: str) -> float:
    """Return source video fps via cached ffprobe. Returns 0.0 on any failure."""
    return probe_video_metadata(input_path)["fps"]


def _resolve_fps(input_path: str, output_fps: int) -> tuple[int, str]:
    """Determine output frame rate and return a log string.

    Policy
    ------
    output_fps == 0  (auto / not set):
        Preserve source fps, capped at _FPS_CAP.
    output_fps  > 0  (user-specified):
        Use min(user_fps, source_fps, _FPS_CAP).
        Never upscale beyond source — avoids judder without minterpolate.

    Returns (target_fps, policy_str).  Caller should log policy_str.
    """
    src_fps = _probe_fps(input_path)

    if src_fps <= 0:
        target = max(1, min(_FPS_CAP, output_fps or _FPS_CAP))
        return target, f"fps_policy=fallback(probe_failed) target={target}"

    src_int = int(round(src_fps))

    if not output_fps:
        target = max(1, min(src_int, _FPS_CAP))
        return target, f"fps_policy=auto src={src_fps:.3f} target={target}"

    target = max(1, min(src_int, output_fps, _FPS_CAP))
    return target, f"fps_policy=user({output_fps}) src={src_fps:.3f} target={target}"


def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))


def _has_audio_stream(input_path: str) -> bool:
    """Return True if the file has at least one audio stream (cached ffprobe)."""
    return probe_video_metadata(input_path)["has_audio"]


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
                logger.info(
                    "cut_video: cut_mode=copy intended_duration=%.3f raw_duration=%.3f tolerance=%.3f output=%s",
                    intended_duration, float(raw_duration or 0.0), duration_tolerance, Path(output_path).name,
                )
                return
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
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
    black_pix_threshold: float = 0.10,
) -> float:
    """Return seconds to skip past leading dark/black frames at the clip start.

    Runs a lightweight ffmpeg blackdetect probe on the first max_scan_sec of the
    clip.  Returns 0.0 when the opening frame is clean or on any detection error.

    The returned shift is always in the range (0.0, max_shift_sec].
    A minimum of 3 s of content is always preserved after the shift.
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
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


def _probe_duration(input_path: str) -> "float | None":
    """Return video duration in seconds via cached ffprobe, or None on error."""
    return probe_video_metadata(input_path)["duration"]


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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
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


def apply_micro_pacing(
    input_path: str,
    output_path: str,
    noise_db: float = -30.0,
    min_silence_dur: float = 0.4,
    max_total_trim: float = 2.0,
    min_clip_dur: float = 5.0,
    content_type: str = "vlog",
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

    cmd = [
        get_ffmpeg_bin(), "-hide_banner", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        *map_args,
        "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        *audio_args,
        output_path,
    ]
    _run_ffmpeg_with_retry(cmd, retry_count=0)

    return {
        "applied": True,
        "segments_trimmed": segments_trimmed,
        "total_trim_ms": int(total_trim * 1000),
        "method": "audio",
    }


def resolve_ffmpeg_threads(max_parallel_parts: int | None = None) -> int:
    cpu_total = os.cpu_count() or 4
    workers = max(1, int(max_parallel_parts or 2))
    return max(1, min(8, cpu_total // workers))


def resolve_target_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Return (width, height) output canvas for the given aspect_ratio string.

    Supported values: "1:1", "9:16", "16:9", "3:4", "4:5".
    Unknown values fall through to the portrait default (1080×1440).
    """
    ar = (aspect_ratio or "").strip()
    if ar == "1:1":
        return 1080, 1080
    if ar == "9:16":
        return 1080, 1920
    if ar == "16:9":
        return 1920, 1080
    return 1080, 1440  # 3:4, 4:5, and any unrecognised value


def render_part(
    input_path: str,
    output_path: str,
    subtitle_ass: str | None,
    title_text: str | None,
    aspect_ratio: str = "3:4",
    scale_x: int = 100,
    scale_y: int = 106,
    add_subtitle: bool = True,
    add_title_overlay: bool = True,
    effect_preset: str = "slay_soft_01",
    transition_sec: float = 0.06,
    video_codec: str = "h264",
    video_crf: int = 18,
    video_preset: str = "slow",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    output_fps: int = 60,
    reup_mode: bool = False,
    reup_overlay_enable: bool = True,
    reup_overlay_opacity: float = 0.08,
    reup_bgm_enable: bool = False,
    reup_bgm_path: str | None = None,
    reup_bgm_gain: float = 0.18,
    playback_speed: float = 1.07,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    content_type: str = "vlog",
):
    preset_low = (video_preset or "").lower()
    _src_meta = probe_video_metadata(input_path)
    _src_h = _src_meta.get("height", 0)
    _src_w = _src_meta.get("width", 0)
    _low_quality_source = 0 < _src_h < 480
    logger.info("source_quality_detected src=%dx%d low_quality=%s", _src_w, _src_h, _low_quality_source)
    if _low_quality_source:
        logger.info("cinematic_pass_reduced_for_low_quality_source src=%dx%d", _src_w, _src_h)
    if loudnorm_enabled and not reup_mode:
        logger.info("audio_polish_enabled audio_loudnorm_applied=True")
    # Part E: content-type bitrate profile — montage needs more budget; interview/tutorial less
    _mr_m, _bs_m = {"montage": (25, 50), "interview": (15, 30), "tutorial": (15, 30)}.get(
        content_type, (20, 40)
    )
    sws = "lanczos" if preset_low in ("slower", "veryslow") else "bicubic"
    target_w, target_h = resolve_target_dimensions(aspect_ratio)
    scale_crop = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags={sws},"
        f"crop={target_w}:{target_h}"
    )
    zoom_scale = (
        f"scale=trunc(iw*{scale_x}/100/2)*2:trunc(ih*{scale_y}/100/2)*2:flags={sws}"
    )
    fixed_canvas = (
        f"pad=w=max(iw\\,{target_w}):h=max(ih\\,{target_h}):"
        f"x=(ow-iw)/2:y=(oh-ih)/2,"
        f"crop={target_w}:{target_h}"
    )

    vf_parts = [
        scale_crop,
        zoom_scale,
        fixed_canvas,
    ]
    # Part C: smart denoise — content-type and source-quality gated (replaces preset-only gate)
    _denoise = _smart_denoise_filter(content_type, preset_low, _src_h)
    if _denoise:
        vf_parts.append(_denoise)
    if reup_mode:
        # Reup mode: use dedicated reup filters (already includes eq+unsharp+hqdn3d)
        vf_parts.extend(_reup_video_filters())
        if reup_overlay_enable:
            opacity = max(0.01, min(0.20, float(reup_overlay_opacity or 0.08)))
            vf_parts.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{opacity}:t=fill")
    else:
        # Normal mode: creative effect filter then cinematic finishing passes
        vf_parts.append(_effect_filter(effect_preset))
        # Part D: content-type-aware color polish
        _color_filter = _cinematic_color_filter(_src_h, content_type)
        # Part B: content-type-aware clarity pass
        _sharpen_filter = _cinematic_sharpen_filter(_src_h, content_type)
        if _color_filter:
            vf_parts.append(_color_filter)
            logger.debug("cinematic_color_pass_enabled src=%dx%d", _src_w, _src_h)
        else:
            logger.debug("cinematic_color_pass_skipped reason=low_quality_source src=%dx%d", _src_w, _src_h)
        if _sharpen_filter:
            vf_parts.append(_sharpen_filter)
            logger.debug("subtle_sharpen_enabled src=%dx%d", _src_w, _src_h)
        else:
            logger.debug("subtle_sharpen_skipped reason=low_quality_source src=%dx%d", _src_w, _src_h)
    vf_parts.append("format=yuv420p")
    if transition_sec and transition_sec > 0:
        # Cap at 0.08 s — long fades look cheap on short-form content.
        # Floor at 0.03 s keeps at least 1 frame of softening to avoid a hard cut.
        vf_parts.append(f"fade=t=in:st=0:d={max(0.03, min(0.08, transition_sec))}")
    if add_subtitle and subtitle_ass:
        ass_safe = _safe_filter_path(subtitle_ass)
        fonts_dir = _get_custom_fonts_dir() or _detect_windows_fonts_dir()
        if fonts_dir:
            vf_parts.append(f"ass='{ass_safe}':fontsdir='{_safe_filter_path(fonts_dir)}'")
        else:
            vf_parts.append(f"ass='{ass_safe}'")
    if add_title_overlay and title_text:
        fontfile = _detect_windows_fontfile()
        safe_title = title_text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")[:120]
        # Escape comma in ffmpeg expression to avoid splitting into another filter.
        drawtext = f"drawtext=text='{safe_title}':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=50:enable='lt(t\\,3)'"
        if fontfile:
            drawtext += f":fontfile='{_safe_filter_path(fontfile)}'"
        vf_parts.append(drawtext)
    layer_count = len(text_layers or [])
    if layer_count:
        logger.info("Applying %d text overlay layer(s)", layer_count)
    append_text_layer_filters(vf_parts, text_layers)
    speed = _sanitize_speed(playback_speed)
    if abs(speed - 1.0) > 1e-4:
        # setpts must come BEFORE fps so the fps filter receives speed-adjusted
        # timestamps and outputs a constant cadence at exactly target_fps.
        vf_parts.append(f"setpts=PTS/{speed:.4f}")

    # fps filter is always the last video filter — it guarantees CFR output
    # regardless of what setpts or upstream filters did to the timestamps.
    target_fps, fps_policy = _resolve_fps(input_path, int(output_fps or 0))
    logger.info("render_part: %s | input=%s", fps_policy, Path(input_path).name)
    vf_parts.append(f"fps={target_fps}")

    resolved_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
    resolved_preset = _map_preset_for_encoder(video_preset, resolved_codec)
    logger.info(
        "encoder_profile_selected codec=%s preset=%s encoder_quality_mode=%s encoder_crf_or_cq=%d",
        resolved_codec, resolved_preset,
        "nvenc" if resolved_codec in ("h264_nvenc", "hevc_nvenc") else "cpu",
        video_crf,
    )
    bgm_path = str(reup_bgm_path or "").strip()
    bgm_ok = reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
    input_has_audio = _has_audio_stream(input_path)

    vf_chain = ",".join(vf_parts)
    _threads = ffmpeg_threads if ffmpeg_threads is not None else resolve_ffmpeg_threads()
    codec_flags = ["-c:v", resolved_codec, "-preset", resolved_preset,
                   *_codec_extra_flags(resolved_codec, int(video_crf), video_preset,
                                       maxrate_m=_mr_m, bufsize_m=_bs_m),
                   "-threads", str(_threads),
                   "-pix_fmt", "yuv420p",
                   "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                   "-movflags", "+faststart"]

    cmd = [get_ffmpeg_bin(), "-y", "-i", input_path]
    if bgm_ok:
        cmd += ["-stream_loop", "-1", "-i", bgm_path]
        gain = max(0.01, min(1.0, float(reup_bgm_gain or 0.18)))
        if input_has_audio:
            # Merge video filters + audio mix into one -filter_complex graph
            a0_chain = "volume=1.0"
            a1_chain = f"volume={gain}"
            if abs(speed - 1.0) > 1e-4:
                a0_chain += f",atempo={speed:.4f}"
                a1_chain += f",atempo={speed:.4f}"
            fc = (f"[0:v]{vf_chain}[vout];"
                  f"[0:a]{a0_chain}[a0];[1:a]{a1_chain}[a1];"
                  f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]")
            cmd += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]"]
        else:
            # No source audio — use video filter_complex + map BGM directly
            fc = f"[0:v]{vf_chain}[vout]"
            af = f"volume={gain}"
            if abs(speed - 1.0) > 1e-4:
                af += f",atempo={speed:.4f}"
            cmd += ["-filter_complex", fc,
                    "-map", "[vout]", "-map", "1:a:0",
                    "-filter:a", af, "-shortest"]
    else:
        cmd += ["-vf", vf_chain]
        if input_has_audio:
            af = _build_audio_filter(loudnorm_enabled, reup_mode, speed)
            if af:
                cmd += ["-af", af]
    cmd += [*codec_flags, "-c:a", "aac", "-b:a", audio_bitrate, output_path]
    logger.info("render_part: codec=%s preset=%s crf=%s effect=%s loudnorm=%s input=%s output=%s",
                resolved_codec, resolved_preset, video_crf, effect_preset, loudnorm_enabled,
                Path(input_path).name, Path(output_path).name)
    if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
        # GPU encode: hold one NVENC session slot for the duration of the subprocess.
        # NVENC_SEMAPHORE is released on any exit (success OR exception) before the
        # CPU fallback runs — so the fallback never competes with other GPU sessions.
        try:
            with NVENC_SEMAPHORE:
                _run_ffmpeg_with_retry(cmd, retry_count=retry_count)
            return
        except Exception as _nvenc_err:
            logger.warning(
                "NVENC encode failed (%s), falling back to CPU encoder for %s",
                _nvenc_err, Path(output_path).name,
            )
            logger.info("recovery_attempted strategy=cpu_encoder reason=%s output=%s", _nvenc_err, Path(output_path).name)
        # CPU fallback — NVENC_SEMAPHORE already released by the `with` block above.
        cpu_codec = "libx265" if str(video_codec).lower() == "h265" else "libx264"
        cpu_preset = _map_preset_for_encoder(video_preset, cpu_codec)
        cpu_flags = ["-c:v", cpu_codec, "-preset", cpu_preset,
                     *_codec_extra_flags(cpu_codec, int(video_crf), video_preset,
                                         maxrate_m=_mr_m, bufsize_m=_bs_m),
                     "-threads", str(_threads),
                     "-pix_fmt", "yuv420p",
                     "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                     "-movflags", "+faststart"]
        cpu_cmd = [get_ffmpeg_bin(), "-y", "-i", input_path]
        if bgm_ok:
            cpu_cmd += ["-stream_loop", "-1", "-i", bgm_path]
            if input_has_audio:
                a0_chain = "volume=1.0"
                a1_chain = f"volume={gain}"
                if abs(speed - 1.0) > 1e-4:
                    a0_chain += f",atempo={speed:.4f}"
                    a1_chain += f",atempo={speed:.4f}"
                fc = (f"[0:v]{vf_chain}[vout];"
                      f"[0:a]{a0_chain}[a0];[1:a]{a1_chain}[a1];"
                      f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]")
                cpu_cmd += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]"]
            else:
                fc = f"[0:v]{vf_chain}[vout]"
                af = f"volume={gain}"
                if abs(speed - 1.0) > 1e-4:
                    af += f",atempo={speed:.4f}"
                cpu_cmd += ["-filter_complex", fc,
                            "-map", "[vout]", "-map", "1:a:0",
                            "-filter:a", af, "-shortest"]
        else:
            cpu_cmd += ["-vf", vf_chain]
            if input_has_audio:
                af = _build_audio_filter(loudnorm_enabled, reup_mode, speed)
                if af:
                    cpu_cmd += ["-af", af]
        cpu_cmd += [*cpu_flags, "-c:a", "aac", "-b:a", audio_bitrate, output_path]
        _run_ffmpeg_with_retry(cpu_cmd, retry_count=retry_count)
        logger.info("recovery_success strategy=cpu_encoder output=%s", Path(output_path).name)
    else:
        # CPU-only encode — no GPU semaphore needed.
        _run_ffmpeg_with_retry(cmd, retry_count=retry_count)



def render_part_smart(
    input_path: str,
    output_path: str,
    subtitle_ass: str,
    title_text: str,
    aspect_ratio: str = "3:4",
    scale_x: int = 100,
    scale_y: int = 106,
    motion_aware_crop: bool = True,
    reframe_mode: str = "subject",
    add_subtitle: bool = True,
    add_title_overlay: bool = True,
    effect_preset: str = "slay_soft_01",
    transition_sec: float = 0.06,
    video_codec: str = "h264",
    video_crf: int = 18,
    video_preset: str = "slow",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    output_fps: int = 60,
    reup_mode: bool = False,
    reup_overlay_enable: bool = True,
    reup_overlay_opacity: float = 0.08,
    reup_bgm_enable: bool = False,
    reup_bgm_path: str | None = None,
    reup_bgm_gain: float = 0.18,
    playback_speed: float = 1.07,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    crop_cfg_override: MotionCropConfig | None = None,
    content_type: str = "vlog",
):
    if motion_aware_crop:
        try:
            if crop_cfg_override is not None:
                crop_cfg = crop_cfg_override
            else:
                crop_cfg = MotionCropConfig(
                    scale_x_percent=float(scale_x),
                    scale_y_percent=float(scale_y),
                    reframe_mode=reframe_mode,
                )
            # motion_crop.py has its own NVENC resolve logic; acquire the semaphore
            # here (one level up) so the session slot is held for the full encode.
            _crop_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
            _crop_ctx = NVENC_SEMAPHORE if _crop_codec in ("h264_nvenc", "hevc_nvenc") else None
            if _crop_ctx is not None:
                _crop_ctx.acquire()
            try:
                result = render_motion_aware_crop(
                    input_path=input_path,
                    output_path=output_path,
                    aspect_ratio=aspect_ratio,
                    scale_x_percent=float(scale_x),
                    scale_y_percent=float(scale_y),
                    subtitle_file=subtitle_ass if add_subtitle and subtitle_ass and Path(subtitle_ass).exists() else None,
                    title_text=title_text if add_title_overlay else None,
                    effect_preset=effect_preset,
                    transition_sec=transition_sec,
                    video_codec=video_codec,
                    video_crf=video_crf,
                    video_preset=video_preset,
                    audio_bitrate=audio_bitrate,
                    retry_count=retry_count,
                    encoder_mode=encoder_mode,
                    output_fps=output_fps,
                    reup_mode=reup_mode,
                    reup_overlay_enable=reup_overlay_enable,
                    reup_overlay_opacity=reup_overlay_opacity,
                    reup_bgm_enable=reup_bgm_enable,
                    reup_bgm_path=reup_bgm_path,
                    reup_bgm_gain=reup_bgm_gain,
                    playback_speed=playback_speed,
                    text_layers=text_layers,
                    loudnorm_enabled=loudnorm_enabled,
                    ffmpeg_threads=ffmpeg_threads,
                    cfg=crop_cfg,
                    content_type=content_type,
                )
            finally:
                if _crop_ctx is not None:
                    _crop_ctx.release()
            return result
        except Exception as exc:
            logger.warning("Motion-aware crop failed, fallback to standard render: %s", exc)
            logger.info("recovery_attempted strategy=fallback_standard_crop reason=%s output=%s", exc, Path(output_path).name)
            # Fallback to standard ffmpeg render path if motion-aware branch fails.
            _fb = render_part(
                input_path=input_path,
                output_path=output_path,
                subtitle_ass=subtitle_ass,
                title_text=title_text,
                aspect_ratio=aspect_ratio,
                scale_x=scale_x,
                scale_y=scale_y,
                add_subtitle=add_subtitle,
                add_title_overlay=add_title_overlay,
                effect_preset=effect_preset,
                transition_sec=transition_sec,
                video_codec=video_codec,
                video_crf=video_crf,
                video_preset=video_preset,
                audio_bitrate=audio_bitrate,
                retry_count=retry_count,
                encoder_mode=encoder_mode,
                output_fps=output_fps,
                reup_mode=reup_mode,
                reup_overlay_enable=reup_overlay_enable,
                reup_overlay_opacity=reup_overlay_opacity,
                reup_bgm_enable=reup_bgm_enable,
                reup_bgm_path=reup_bgm_path,
                reup_bgm_gain=reup_bgm_gain,
                playback_speed=playback_speed,
                text_layers=text_layers,
                loudnorm_enabled=loudnorm_enabled,
                ffmpeg_threads=ffmpeg_threads,
                content_type=content_type,
            )
            logger.info("recovery_success strategy=fallback_standard_crop output=%s", Path(output_path).name)
            return _fb

    return render_part(
        input_path=input_path,
        output_path=output_path,
        subtitle_ass=subtitle_ass,
        title_text=title_text,
        aspect_ratio=aspect_ratio,
        scale_x=scale_x,
        scale_y=scale_y,
        add_subtitle=add_subtitle,
        add_title_overlay=add_title_overlay,
        effect_preset=effect_preset,
        transition_sec=transition_sec,
        video_codec=video_codec,
        video_crf=video_crf,
        video_preset=video_preset,
        audio_bitrate=audio_bitrate,
        retry_count=retry_count,
        encoder_mode=encoder_mode,
        output_fps=output_fps,
        reup_mode=reup_mode,
        reup_overlay_enable=reup_overlay_enable,
        reup_overlay_opacity=reup_overlay_opacity,
        reup_bgm_enable=reup_bgm_enable,
        reup_bgm_path=reup_bgm_path,
        reup_bgm_gain=reup_bgm_gain,
        playback_speed=playback_speed,
        text_layers=text_layers,
        loudnorm_enabled=loudnorm_enabled,
        content_type=content_type,
    )
