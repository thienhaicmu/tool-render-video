
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


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource semaphores
# ---------------------------------------------------------------------------
# Consumer NVIDIA GPUs support 3–5 concurrent NVENC sessions. Exceeding the
# limit causes encode failures with "no NVENC capable devices found".
# Override with NVENC_MAX_SESSIONS env var if your GPU supports more.
_NVENC_SEM_VALUE: int = max(1, int(os.getenv("NVENC_MAX_SESSIONS", "3")))
NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)


def _run_ffmpeg_with_retry(command: list[str], retry_count: int = 2, wait_sec: float = 0.8):
    attempt = 0
    while True:
        attempt += 1
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            if attempt > retry_count:
                stderr = exc.stderr or ""
                diag = _summarize_ffmpeg_stderr(stderr)
                stderr_tail = stderr[-2000:].strip()
                raise RuntimeError(
                    f"FFmpeg render failed: {diag} (exit={exc.returncode})"
                    + (f"\n{stderr_tail}" if stderr_tail else "")
                ) from exc
            time.sleep(wait_sec * attempt)
        except Exception:
            if attempt > retry_count:
                raise
            time.sleep(wait_sec * attempt)


@lru_cache(maxsize=1)
def _ffmpeg_encoders_text() -> str:
    try:
        ffmpeg_bin = get_ffmpeg_bin()
        r = subprocess.run([ffmpeg_bin, "-hide_banner", "-encoders"], capture_output=True, text=True, check=True)
        return (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        return ""


def _has_encoder(name: str) -> bool:
    return name in _ffmpeg_encoders_text()


@lru_cache(maxsize=2)
def _nvenc_runtime_ready(codec_name: str) -> bool:
    try:
        ffmpeg_bin = get_ffmpeg_bin()
        probe_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", "color=c=black:s=256x256:d=0.1",
            "-an",
            "-c:v", codec_name,
            "-f", "null",
            "-",
        ]
        proc = subprocess.run(probe_cmd, capture_output=True, text=True)
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).lower()
        if proc.returncode == 0:
            return True
        blockers = (
            "cannot load nvcuda.dll",
            "no nvenc capable devices found",
            "cannot init cuda",
            "operation not permitted",
        )
        return not any(b in text for b in blockers)
    except Exception:
        return False


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


def _codec_extra_flags(resolved_codec: str, video_crf: int, video_preset: str = "slow"):
    c = (resolved_codec or "").lower()
    p = (video_preset or "slow").lower()
    if c == "hevc_nvenc":
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "4",
        ]
    if c == "h264_nvenc":
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "3",
        ]
    if c == "libx265":
        if p in ("veryslow", "slower"):
            x265p = "aq-mode=3:aq-strength=1.0:deblock=-1,-1:rc-lookahead=60:ref=5:bframes=4:psy-rdoq=1.0:rdoq-level=2"
        elif p == "slow":
            x265p = "aq-mode=3:aq-strength=0.8:deblock=-1,-1:rc-lookahead=40:ref=4:bframes=4"
        else:
            x265p = "aq-mode=2:rc-lookahead=20:ref=3:bframes=3"
        return ["-crf", str(video_crf), "-tag:v", "hvc1", "-x265-params", x265p]

    # libx264 — tiered by preset
    if p in ("veryslow", "slower"):
        x264p = "ref=5:bframes=3:me=umh:subme=9:analyse=all:trellis=2:deblock=-1,-1:aq-mode=3:aq-strength=0.8:psy-rd=1.0:psy-rdoq=0.0"
    elif p == "slow":
        x264p = "ref=4:bframes=3:me=hex:subme=7:trellis=1:deblock=-1,-1:aq-mode=3:aq-strength=0.8:psy-rd=1.0"
    else:
        x264p = "ref=3:bframes=2:me=hex:subme=6:trellis=0:aq-mode=2"
    return [
        "-crf", str(video_crf),
        "-profile:v", "high", "-level:v", "5.1",
        "-tune", "film",
        "-x264-params", x264p,
    ]


def _map_preset_for_encoder(video_preset: str, resolved_codec: str):
    c = (resolved_codec or "").lower()
    p = (video_preset or "slow").lower()
    if c in ("h264_nvenc", "hevc_nvenc"):
        mapping = {
            "ultrafast": "p2",
            "superfast": "p3",
            "veryfast": "p4",
            "faster": "p4",
            "fast": "p4",
            "medium": "p5",
            "slow": "p6",
            "slower": "p7",
            "veryslow": "p7",
        }
        return mapping.get(p, "p6")
    return p


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


def _reup_video_filters() -> list[str]:
    # Lightweight enhancement pack for reup mode.
    return [
        "eq=contrast=1.04:saturation=1.10:brightness=0.01",
        "unsharp=5:5:0.45:3:3:0.0",
        "hqdn3d=1.2:1.2:6:6",
    ]


def _reup_audio_filter() -> str:
    # Voice clarity + peak control.
    return (
        "highpass=f=120,"
        "lowpass=f=11000,"
        "acompressor=threshold=-16dB:ratio=2.2:attack=20:release=200:makeup=2,"
        "alimiter=limit=0.95"
    )


def _build_audio_filter(loudnorm_enabled: bool, reup_mode: bool, speed: float) -> str | None:
    """Return a comma-joined -af filter string, or None when no audio processing is needed."""
    parts = []
    if loudnorm_enabled and not reup_mode:
        parts.append("loudnorm=I=-16:LRA=11:TP=-1.5")
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
    """Return source video fps via ffprobe. Returns 0.0 on any failure.

    Probes both avg_frame_rate and r_frame_rate in one pass.
    avg_frame_rate is preferred: it reflects the actual frame cadence and is
    more accurate for VFR content and YouTube downloads.  r_frame_rate is the
    container-declared max and can be an unrealistically high rational for
    some encoders.  We use whichever lands in the sane range [1, 120] first.
    """
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate,r_frame_rate",
            "-of", "csv=p=0",
            str(input_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts = (r.stdout or "").strip().split(",")
        avg_fps = _parse_fps_ratio(parts[0]) if parts else 0.0
        r_fps   = _parse_fps_ratio(parts[1]) if len(parts) > 1 else 0.0
        for fps in (avg_fps, r_fps):
            if 1.0 <= fps <= 120.0:
                return fps
        return 0.0
    except Exception:
        return 0.0


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
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(input_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return bool((r.stdout or "").strip())
    except Exception:
        return False


def _safe_filter_path(path: str) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _detect_windows_fontfile() -> str | None:
    windir = os.environ.get("WINDIR")
    if not windir:
        return None
    fonts_dir = Path(windir) / "Fonts"
    candidates = [
        fonts_dir / "arial.ttf",
        fonts_dir / "segoeui.ttf",
        fonts_dir / "tahoma.ttf",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _detect_windows_fonts_dir() -> str | None:
    windir = os.environ.get("WINDIR")
    if not windir:
        return None
    fonts_dir = Path(windir) / "Fonts"
    if fonts_dir.exists():
        return str(fonts_dir)
    return None


def _get_custom_fonts_dir() -> str | None:
    """Return path to bundled fonts directory."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "fonts",  # backend/fonts (current project layout)
        here.parents[3] / "fonts",  # legacy: repo/fonts
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def cut_video(input_path: str, output_path: str, start_time: float, end_time: float, retry_count: int = 2):
    base = [
        get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-y", "-ss", str(start_time), "-to", str(end_time), "-i", input_path,
    ]
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
        return
    except Exception:
        pass

    # Re-encode fallback: handles corrupted keyframes or muxing issues
    fallback_cmd = [
        *base,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k",
        "-movflags", "+faststart",
        output_path,
    ]
    _run_ffmpeg_with_retry(fallback_cmd, retry_count=retry_count)


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


def _probe_duration(input_path: str) -> float | None:
    """Return video duration in seconds via ffprobe, or None on error."""
    try:
        cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return None


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
    min_silence_dur: float = 0.3,
    max_total_trim: float = 2.0,
    min_clip_dur: float = 5.0,
) -> dict:
    """Compress mid-clip silences to improve pacing without altering speech.

    Detects silence regions inside the clip (ignoring the first/last 0.5s),
    trims each region down to a minimal breathing pause, and stitches the
    result via a single FFmpeg filter_complex pass.

    Returns {"applied": bool, "segments_trimmed": int, "total_trim_ms": int, "method": str}.
    Raises on FFmpeg error so the caller can fall back to the original file.
    """
    _NO_OP: dict = {"applied": False, "segments_trimmed": 0, "total_trim_ms": 0, "method": "audio"}

    clip_dur = _probe_duration(input_path)
    if clip_dur is None or clip_dur < min_clip_dur:
        return _NO_OP

    silences = _detect_silence_segments(input_path, noise_db=noise_db, min_dur=min_silence_dur)
    # Only consider mid-clip silences — leave boundaries intact
    silences = [(s, e) for s, e in silences if s >= 0.5 and e <= clip_dur - 0.3]
    if not silences:
        return _NO_OP

    def _target_dur(dur: float) -> float:
        if dur <= 0.7:
            return 0.15
        elif dur <= 1.2:
            return 0.25
        return 0.4

    # Build a list of (keep_start, keep_end) timeline segments
    keeps: list[tuple[float, float]] = []
    prev_end = 0.0
    total_trim = 0.0
    segments_trimmed = 0

    for s_start, s_end in silences:
        s_dur = s_end - s_start
        trim = s_dur - _target_dur(s_dur)
        remaining = max_total_trim - total_trim
        if remaining <= 0 or trim <= 0:
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
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        *audio_args,
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)

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
    transition_sec: float = 0.25,
    video_codec: str = "h264",
    video_crf: int = 20,
    video_preset: str = "medium",
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
):
    preset_low = (video_preset or "").lower()
    sws = "lanczos" if preset_low in ("slower", "veryslow") else "bicubic"
    if aspect_ratio == "1:1":
        scale_crop = f"scale=1080:1080:force_original_aspect_ratio=increase:flags={sws},crop=1080:1080"
    elif aspect_ratio == "9:16":
        scale_crop = f"scale=1080:1920:force_original_aspect_ratio=increase:flags={sws},crop=1080:1920"
    else:
        scale_crop = f"scale=1080:1440:force_original_aspect_ratio=increase:flags={sws},crop=1080:1440"

    vf_parts = [
        scale_crop,
        f"scale=trunc(iw*{scale_x}/100/2)*2:trunc(ih*{scale_y}/100/2)*2:flags={sws}",
        "crop=iw:ih",
    ]
    # hqdn3d denoiser only for slower/veryslow (quality mode)
    if preset_low in ("slower", "veryslow"):
        vf_parts.append("hqdn3d=1.5:1.5:6:6")
    if reup_mode:
        # Reup mode: use dedicated reup filters (already includes eq+unsharp+hqdn3d)
        vf_parts.extend(_reup_video_filters())
        if reup_overlay_enable:
            opacity = max(0.01, min(0.20, float(reup_overlay_opacity or 0.08)))
            vf_parts.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{opacity}:t=fill")
    else:
        # Normal mode: apply creative effect filter
        vf_parts.append(_effect_filter(effect_preset))
    vf_parts.append("format=yuv420p")
    if transition_sec and transition_sec > 0:
        vf_parts.append(f"fade=t=in:st=0:d={max(0.05, min(0.8, transition_sec))}")
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
    bgm_path = str(reup_bgm_path or "").strip()
    bgm_ok = reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
    input_has_audio = _has_audio_stream(input_path)

    vf_chain = ",".join(vf_parts)
    _threads = ffmpeg_threads if ffmpeg_threads is not None else resolve_ffmpeg_threads()
    codec_flags = ["-c:v", resolved_codec, "-preset", resolved_preset,
                   *_codec_extra_flags(resolved_codec, int(video_crf), video_preset),
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
        # CPU fallback — NVENC_SEMAPHORE already released by the `with` block above.
        cpu_codec = "libx265" if str(video_codec).lower() == "h265" else "libx264"
        cpu_preset = _map_preset_for_encoder(video_preset, cpu_codec)
        cpu_flags = ["-c:v", cpu_codec, "-preset", cpu_preset,
                     *_codec_extra_flags(cpu_codec, int(video_crf), video_preset),
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
    transition_sec: float = 0.25,
    video_codec: str = "h264",
    video_crf: int = 20,
    video_preset: str = "medium",
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
):
    if motion_aware_crop:
        try:
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
                )
            finally:
                if _crop_ctx is not None:
                    _crop_ctx.release()
            return result
        except Exception as exc:
            logger.warning("Motion-aware crop failed, fallback to standard render: %s", exc)
            # Fallback to standard ffmpeg render path if motion-aware branch fails.
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
                ffmpeg_threads=ffmpeg_threads,
            )

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
    )
