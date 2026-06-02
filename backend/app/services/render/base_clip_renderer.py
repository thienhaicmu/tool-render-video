import time
import logging
from pathlib import Path

from app.domain.timeline import TimelineMap
from app.services.motion_crop import render_motion_aware_crop
from app.services.bin_paths import get_ffmpeg_bin
from app.services.encoder_helpers import (
    codec_extra_flags as _codec_extra_flags,
    map_preset_for_encoder as _map_preset_for_encoder,
)
from app.services.render.ffmpeg_helpers import (
    NVENC_SEMAPHORE,
    probe_video_metadata,
    _run_ffmpeg_with_retry,
    _resolve_codec,
    _sanitize_speed,
    _has_audio_stream,
    _smart_denoise_filter,
    _effect_filter,
    _cinematic_color_filter,
    _cinematic_sharpen_filter,
    resolve_target_dimensions,
    _resolve_fps,
    resolve_ffmpeg_threads,
    _build_audio_mix_filter,
    _build_audio_filter,
    resolve_effect_preset_with_intensity,
)

logger = logging.getLogger(__name__)


def render_base_clip(
    input_path: str,
    output_path: str,
    timeline: TimelineMap,
    aspect_ratio: str = "3:4",
    scale_x: int = 100,
    scale_y: int = 106,
    motion_aware_crop: bool = True,
    reframe_mode: str = "subject",
    effect_preset: str = "slay_soft_01",
    transition_sec: float = 0.06,
    video_codec: str = "h264",
    video_crf: int = 18,
    video_preset: str = "slow",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    output_fps: int = 60,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    content_type: str = "vlog",
    _motion_cache_key: str | None = None,
    reup_bgm_enable: bool = False,
    reup_bgm_path: str | None = None,
    reup_bgm_gain: float = 0.18,
    visual_intensity_hint: str | None = None,
) -> dict:
    """Render a base clip with no subtitle, title, or text overlay filters.

    Uses timeline.effective_speed for setpts/atempo — no speed re-derivation.
    Returns a metadata dict: path, duration, fps, width, height, has_audio, created_at.

    When FEATURE_BASE_CLIP_FIRST=1 only: base_clip.mp4 is a parallel validation artifact;
    render_part_smart() still produces the final output.

    When both FEATURE_BASE_CLIP_FIRST=1 and FEATURE_OVERLAY_AFTER_BASE_CLIP=1:
    base_clip.mp4 feeds composite_overlays_on_base_clip() which produces the final output.

    BGM: when reup_bgm_enable=True and reup_bgm_path points to a valid file, BGM is
    baked into base_clip.mp4 via filter_complex. The composite streams audio via -c:a copy
    so BGM flows through to the final output without re-encoding.
    """
    speed = _sanitize_speed(timeline.effective_speed)

    # Phase 5.7: Resolve effective effect preset from AI visual intensity hint.
    # Renderer OWNS the mapping; AI only passes None/"low"/"medium"/"high".
    # User explicit effect_preset (non-default) always wins over AI hint.
    _bc_user_explicit = (
        (effect_preset or "slay_soft_01").strip() != "slay_soft_01"
    )
    _bc_effective_preset = resolve_effect_preset_with_intensity(
        effect_preset, visual_intensity_hint, _bc_user_explicit
    )

    if motion_aware_crop:
        _crop_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
        _use_nvenc = _crop_codec in ("h264_nvenc", "hevc_nvenc")
        if _use_nvenc:
            NVENC_SEMAPHORE.acquire()
        try:
            render_motion_aware_crop(
                input_path=input_path,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                scale_x_percent=float(scale_x),
                scale_y_percent=float(scale_y),
                subtitle_file=None,
                title_text=None,
                effect_preset=_bc_effective_preset,
                transition_sec=transition_sec,
                video_codec=video_codec,
                video_crf=video_crf,
                video_preset=video_preset,
                audio_bitrate=audio_bitrate,
                retry_count=retry_count,
                encoder_mode=encoder_mode,
                output_fps=output_fps,
                playback_speed=speed,
                text_layers=None,
                loudnorm_enabled=loudnorm_enabled,
                ffmpeg_threads=ffmpeg_threads,
                content_type=content_type,
                _cache_key=_motion_cache_key,
            )
        finally:
            if _use_nvenc:
                NVENC_SEMAPHORE.release()
    else:
        _src_meta = probe_video_metadata(input_path)
        _src_h = _src_meta.get("height", 0)
        preset_low = (video_preset or "").lower()
        _mr_m, _bs_m = {"montage": (25, 50), "interview": (15, 30), "tutorial": (15, 30)}.get(
            content_type, (20, 40)
        )
        sws = "lanczos" if preset_low in ("slower", "veryslow") else "bicubic"
        target_w, target_h = resolve_target_dimensions(aspect_ratio)
        scale_crop = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags={sws},"
            f"crop={target_w}:{target_h}"
        )
        zoom_scale = f"scale=trunc(iw*{scale_x}/100/2)*2:trunc(ih*{scale_y}/100/2)*2:flags={sws}"
        fixed_canvas = (
            f"pad=w=max(iw\\,{target_w}):h=max(ih\\,{target_h}):"
            f"x=(ow-iw)/2:y=(oh-ih)/2,"
            f"crop={target_w}:{target_h}"
        )
        vf_parts = [scale_crop, zoom_scale, fixed_canvas]
        _denoise = _smart_denoise_filter(content_type, preset_low, _src_h)
        if _denoise:
            vf_parts.append(_denoise)
        # _bc_effective_preset is either user's preset (when explicit) or
        # the AI-intensity-mapped preset (when AI hint valid and not overridden).
        vf_parts.append(_effect_filter(_bc_effective_preset))
        _color_filter = _cinematic_color_filter(_src_h, content_type)
        _sharpen_filter = _cinematic_sharpen_filter(_src_h, content_type)
        if _color_filter:
            vf_parts.append(_color_filter)
        if _sharpen_filter:
            vf_parts.append(_sharpen_filter)
        vf_parts.append("format=yuv420p")
        if transition_sec and transition_sec > 0:
            _FADE_CAP_BY_TYPE: dict[str, float] = {
                "interview": 0.20, "commentary": 0.20, "tutorial": 0.20,
            }
            _fade_cap = _FADE_CAP_BY_TYPE.get(content_type, 0.08)
            _fade_d = round(max(0.03, min(_fade_cap, transition_sec)), 4)
            vf_parts.append(f"fade=t=in:st=0:d={_fade_d}")
        # Overlay filters (ass=, drawtext=, text_layers) are intentionally absent.
        # Base clip is a clean encode: crop + color + speed only.
        if abs(speed - 1.0) > 1e-4:
            vf_parts.append(f"setpts=PTS/{speed:.4f}")
        target_fps, _ = _resolve_fps(input_path, int(output_fps or 0))
        vf_parts.append(f"fps={target_fps}")

        resolved_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
        resolved_preset = _map_preset_for_encoder(video_preset, resolved_codec)
        input_has_audio = _has_audio_stream(input_path)
        vf_chain = ",".join(vf_parts)
        _threads = ffmpeg_threads if ffmpeg_threads is not None else resolve_ffmpeg_threads()
        codec_flags = [
            "-c:v", resolved_codec, "-preset", resolved_preset,
            *_codec_extra_flags(resolved_codec, int(video_crf), video_preset,
                                maxrate_m=_mr_m, bufsize_m=_bs_m),
            "-threads", str(_threads),
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-movflags", "+faststart",
        ]

        _bgm_path = str(reup_bgm_path or "").strip()
        _bgm_ok = reup_bgm_enable and _bgm_path and Path(_bgm_path).is_file()

        def _build_base_clip_cmd(enc_flags: list) -> list:
            c = [get_ffmpeg_bin(), "-y", "-i", input_path]
            if _bgm_ok:
                c += ["-stream_loop", "-1", "-i", _bgm_path]
                gain = max(0.01, min(1.0, float(reup_bgm_gain or 0.18)))
                if input_has_audio:
                    a0_chain = "volume=1.0"
                    a1_chain = f"volume={gain}"
                    if abs(speed - 1.0) > 1e-4:
                        a0_chain += f",atempo={speed:.4f}"
                        a1_chain += f",atempo={speed:.4f}"
                    fc = (
                        f"[0:v]{vf_chain}[vout];"
                        f"[0:a]{a0_chain}[a0];[1:a]{a1_chain}[a1];"
                        f"{_build_audio_mix_filter('a0', 'a1', 'aout')}"
                    )
                    c += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]"]
                else:
                    fc = f"[0:v]{vf_chain}[vout]"
                    af = f"volume={gain}"
                    if abs(speed - 1.0) > 1e-4:
                        af += f",atempo={speed:.4f}"
                    c += ["-filter_complex", fc, "-map", "[vout]", "-map", "1:a:0",
                          "-filter:a", af, "-shortest"]
            else:
                c += ["-vf", vf_chain]
                if input_has_audio:
                    af = _build_audio_filter(loudnorm_enabled, False, speed)
                    if af:
                        c += ["-af", af]
            c += [*enc_flags, "-c:a", "aac", "-b:a", audio_bitrate, output_path]
            return c

        cmd = _build_base_clip_cmd(codec_flags)
        logger.debug("render_base_clip vf_chain=%s bgm=%s output=%s", vf_chain, _bgm_ok, Path(output_path).name)

        if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
            try:
                with NVENC_SEMAPHORE:
                    # nvenc_externally_held=True: the `with` block above already
                    # holds NVENC_SEMAPHORE. Skip the internal acquire in
                    # _run_ffmpeg_with_retry to avoid double-counting against
                    # the GPU session limit (Sprint 4.2, audit 2026-06-02 P2-B1).
                    _run_ffmpeg_with_retry(cmd, retry_count=retry_count, nvenc_externally_held=True)
            except Exception as _nvenc_err:
                logger.warning(
                    "NVENC encode failed (%s), falling back to CPU for base_clip %s",
                    _nvenc_err, Path(output_path).name,
                )
                cpu_codec = "libx265" if str(video_codec).lower() == "h265" else "libx264"
                cpu_preset = _map_preset_for_encoder(video_preset, cpu_codec)
                cpu_flags = [
                    "-c:v", cpu_codec, "-preset", cpu_preset,
                    *_codec_extra_flags(cpu_codec, int(video_crf), video_preset,
                                        maxrate_m=_mr_m, bufsize_m=_bs_m),
                    "-threads", str(_threads),
                    "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-movflags", "+faststart",
                ]
                cpu_cmd = _build_base_clip_cmd(cpu_flags)
                _run_ffmpeg_with_retry(cpu_cmd, retry_count=retry_count)
        else:
            _run_ffmpeg_with_retry(cmd, retry_count=retry_count)

    meta = probe_video_metadata(output_path)
    return {
        "path": output_path,
        "duration": float(meta.get("duration") or 0.0),
        "fps": float(meta.get("fps") or 0.0),
        "width": int(meta.get("width") or 0),
        "height": int(meta.get("height") or 0),
        "has_audio": bool(meta.get("has_audio", False)),
        "created_at": time.time(),
    }
