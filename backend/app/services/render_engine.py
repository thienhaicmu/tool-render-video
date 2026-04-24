
import os
import subprocess
import time
import logging
from functools import lru_cache
from pathlib import Path
from app.services.motion_crop import render_motion_aware_crop, MotionCropConfig
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
from app.services.text_overlay import append_text_layer_filters


logger = logging.getLogger(__name__)


def _run_ffmpeg_with_retry(command: list[str], retry_count: int = 2, wait_sec: float = 0.8):
    attempt = 0
    while True:
        attempt += 1
        try:
            return subprocess.run(command, check=True)
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
    # unsharp: lx:ly:luma_amount:cx:cy:chroma_amount
    # Positive luma_amount = sharpen, positive chroma = slight color pop
    preset = (effect_preset or "slay_soft_01").lower()
    if preset == "slay_pop_01":
        # High-energy TikTok look: punchy color + crisp sharpening
        return "eq=contrast=1.08:saturation=1.18:brightness=0.01:gamma=1.02,unsharp=5:5:1.2:3:3:0.5"
    if preset == "story_clean_01":
        # Clean minimal look: subtle enhancement
        return "eq=contrast=1.03:saturation=1.05:brightness=0.0,unsharp=3:3:0.6:3:3:0.15"
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


def _probe_fps(input_path: str) -> float:
    """Return source video FPS (0.0 on failure)."""
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = (r.stdout or "").strip()
        if "/" in out:
            a, b = out.split("/", 1)
            return float(a) / float(b) if float(b) else 0.0
        return float(out) if out else 0.0
    except Exception:
        return 0.0


def _smart_fps(input_path: str, requested_fps: int) -> int:
    """Return output fps: never upscale beyond source, cap at requested."""
    src_fps = _probe_fps(input_path)
    if src_fps <= 0:
        return max(1, min(60, requested_fps))
    # Don't upscale: if source is 30fps and requested 60, output 30
    src_rounded = int(round(src_fps))
    return max(1, min(src_rounded, requested_fps))


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
        drawtext = f"drawtext=text='{safe_title}':fontcolor=white:fontsize=34:x=(w-text_w)/2:y=50:enable='lt(t\\,3)'"
        if fontfile:
            drawtext += f":fontfile='{_safe_filter_path(fontfile)}'"
        vf_parts.append(drawtext)
    layer_count = len(text_layers or [])
    if layer_count:
        logger.info("Applying %d text overlay layer(s)", layer_count)
    append_text_layer_filters(vf_parts, text_layers)
    speed = _sanitize_speed(playback_speed)
    if abs(speed - 1.0) > 1e-4:
        vf_parts.append(f"setpts=PTS/{speed:.4f}")

    target_fps = _smart_fps(input_path, int(output_fps or 60))
    vf_parts.append(f"fps={target_fps}")

    resolved_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
    resolved_preset = _map_preset_for_encoder(video_preset, resolved_codec)
    bgm_path = str(reup_bgm_path or "").strip()
    bgm_ok = reup_mode and reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
    input_has_audio = _has_audio_stream(input_path)

    vf_chain = ",".join(vf_parts)
    codec_flags = ["-c:v", resolved_codec, "-preset", resolved_preset,
                   *_codec_extra_flags(resolved_codec, int(video_crf), video_preset),
                   "-threads", "0",
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
            af_parts = []
            if reup_mode:
                af_parts.append(_reup_audio_filter())
            if abs(speed - 1.0) > 1e-4:
                af_parts.append(f"atempo={speed:.4f}")
            if af_parts:
                cmd += ["-af", ",".join(af_parts)]
    cmd += [*codec_flags, "-c:a", "aac", "-b:a", audio_bitrate, output_path]
    logger.info("render_part_smart: codec=%s preset=%s crf=%s input=%s output=%s",
                resolved_codec, resolved_preset, video_crf,
                Path(input_path).name, Path(output_path).name)
    try:
        _run_ffmpeg_with_retry(cmd, retry_count=retry_count)
    except Exception as _nvenc_err:
        if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
            logger.warning(
                "NVENC encode failed (%s), falling back to CPU encoder for %s",
                _nvenc_err, Path(output_path).name,
            )
            cpu_codec = "libx265" if str(video_codec).lower() == "h265" else "libx264"
            cpu_preset = _map_preset_for_encoder(video_preset, cpu_codec)
            cpu_flags = ["-c:v", cpu_codec, "-preset", cpu_preset,
                         *_codec_extra_flags(cpu_codec, int(video_crf), video_preset),
                         "-threads", "0",
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
                    af_parts = []
                    if reup_mode:
                        af_parts.append(_reup_audio_filter())
                    if abs(speed - 1.0) > 1e-4:
                        af_parts.append(f"atempo={speed:.4f}")
                    if af_parts:
                        cpu_cmd += ["-af", ",".join(af_parts)]
            cpu_cmd += [*cpu_flags, "-c:a", "aac", "-b:a", audio_bitrate, output_path]
            _run_ffmpeg_with_retry(cpu_cmd, retry_count=retry_count)
            return
        raise



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
):
    if motion_aware_crop:
        try:
            crop_cfg = MotionCropConfig(
                scale_x_percent=float(scale_x),
                scale_y_percent=float(scale_y),
                reframe_mode=reframe_mode,
            )
            return render_motion_aware_crop(
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
                cfg=crop_cfg,
            )
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
    )
