import time
import logging
from pathlib import Path

from app.domain.timeline import TimelineMap
from app.features.render.engine.motion import render_motion_aware_crop, MotionCropConfig
from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.overlay.text_overlay import append_text_layer_filters
from app.features.render.engine.encoder.encoder_helpers import (
    codec_extra_flags as _codec_extra_flags,
    map_preset_for_encoder as _map_preset_for_encoder,
    reup_video_filters as _reup_video_filters,
    safe_filter_path as _safe_filter_path,
    detect_windows_fontfile as _detect_windows_fontfile,
    detect_windows_fonts_dir as _detect_windows_fonts_dir,
    get_custom_fonts_dir as _get_custom_fonts_dir,
)
from app.features.render.engine.encoder.ffmpeg_helpers import (
    NVENC_SEMAPHORE,
    probe_video_metadata,
    _run_ffmpeg_with_retry,
    _resolve_codec,
    _sanitize_speed,
    _has_audio_stream,
    _smart_denoise_filter,
    _effect_filter,
    _zoom_burst_filter,
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
    playback_speed: float = 1.0,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    content_type: str = "vlog",
    visual_intensity_hint: str | None = None,
    zoom_burst: bool = False,
    # Sprint 7.4 (2026-06-05) — fuse mode: when both _source_seek_start and
    # _source_seek_duration are provided, input_path is treated as a full
    # source (not a pre-cut raw_part). The seek args are prepended (input-
    # side, fast) before -i for speed, or appended (output-side, frame-
    # accurate) after -i when _source_seek_force_accurate=True. Defaults
    # preserve the pre-Sprint-7.4 contract: when None, no seek is applied
    # and input_path is treated as a t=0 pre-cut clip. See
    # docs/review/SPRINT_7_4_RAW_PART_FUSE_2026-06-05.md.
    _source_seek_start: float | None = None,
    _source_seek_duration: float | None = None,
    _source_seek_force_accurate: bool = False,
):
    # Sprint 7.4 — pre-build input args once so both the NVENC main cmd
    # and the CPU fallback cmd use the same shape.
    if _source_seek_start is not None and _source_seek_duration is not None:
        if _source_seek_force_accurate:
            # Output-side seek (slower, frame-accurate): -i input -ss start -t dur
            _input_args = ["-i", input_path, "-ss", str(_source_seek_start), "-t", str(_source_seek_duration)]
        else:
            # Input-side seek (fast keyframe seek): -ss start -t dur -i input
            _input_args = ["-ss", str(_source_seek_start), "-t", str(_source_seek_duration), "-i", input_path]
    else:
        _input_args = ["-i", input_path]

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
    if zoom_burst:
        vf_parts.append(_zoom_burst_filter(target_w=target_w, target_h=target_h))
    # Phase 5.7: Resolve effective effect preset from AI visual intensity hint.
    # Renderer OWNS the mapping; AI only passes None/"low"/"medium"/"high".
    # User explicit effect_preset (non-default) always wins over AI hint.
    _user_effect_explicit = (
        (effect_preset or "slay_soft_01").strip() != "slay_soft_01"
    )
    _effective_effect_preset = resolve_effect_preset_with_intensity(
        effect_preset, visual_intensity_hint, _user_effect_explicit
    )
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
        # _effective_effect_preset is either the user's preset (when explicit) or
        # the AI-intensity-mapped preset (when AI hint is valid and not overridden).
        # Original effect_preset is preserved for logging below.
        vf_parts.append(_effect_filter(_effective_effect_preset))
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
        # Content-type-aware fade cap.
        # Montage/vlog: keep 0.08 s — hard cuts are intentional in fast-paced content.
        # Speech-heavy (interview/commentary/tutorial): allow up to 0.20 s so the
        # edit feels less jarring when the subject is talking continuously.
        # Floor at 0.03 s (â‰ˆ 1 frame at 30fps) prevents pure hard cuts.
        _FADE_CAP_BY_TYPE: dict[str, float] = {
            "interview": 0.20, "commentary": 0.20, "tutorial": 0.20,
        }
        _fade_cap = _FADE_CAP_BY_TYPE.get(content_type, 0.08)
        _fade_d = round(max(0.03, min(_fade_cap, transition_sec)), 4)
        vf_parts.append(f"fade=t=in:st=0:d={_fade_d}")
        logger.info(
            "transition_fade_duration part=%s content_type=%s fade_in=%.4f fade_out=0.0000 cap=%.4f",
            Path(output_path).stem, content_type, _fade_d, _fade_cap,
        )
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
    logger.debug(
        "render_part vf_chain part=%s chain=%s",
        Path(output_path).name, vf_chain,
    )
    _threads = ffmpeg_threads if ffmpeg_threads is not None else resolve_ffmpeg_threads()
    codec_flags = ["-c:v", resolved_codec, "-preset", resolved_preset,
                   *_codec_extra_flags(resolved_codec, int(video_crf), video_preset,
                                       maxrate_m=_mr_m, bufsize_m=_bs_m),
                   "-threads", str(_threads),
                   "-pix_fmt", "yuv420p",
                   "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                   "-movflags", "+faststart"]

    cmd = [get_ffmpeg_bin(), "-y", *_input_args]
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
                  f"{_build_audio_mix_filter('a0', 'a1', 'aout')}")
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
                logger.debug(
                    "render_part audio_filter=%s speed=%.4f part=%s",
                    af, speed, Path(output_path).name,
                )
                cmd += ["-af", af]
    cmd += [*codec_flags, "-c:a", "aac", "-b:a", audio_bitrate, output_path]
    logger.debug("render_part ffmpeg_cmd=%s", " ".join(str(a) for a in cmd))
    logger.info(
        "render_part: codec=%s preset=%s crf=%s effect=%s effective_effect=%s "
        "visual_intensity_hint=%s loudnorm=%s input=%s output=%s",
        resolved_codec, resolved_preset, video_crf,
        effect_preset, _effective_effect_preset,
        visual_intensity_hint, loudnorm_enabled,
        Path(input_path).name, Path(output_path).name,
    )
    if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
        # GPU encode: hold one NVENC session slot for the duration of the subprocess.
        # NVENC_SEMAPHORE is released on any exit (success OR exception) before the
        # CPU fallback runs — so the fallback never competes with other GPU sessions.
        try:
            with NVENC_SEMAPHORE:
                # nvenc_externally_held=True — see Sprint 4.2 note in
                # render_base_clip above; avoids semaphore double-acquire.
                _run_ffmpeg_with_retry(cmd, retry_count=retry_count, nvenc_externally_held=True)
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
        cpu_cmd = [get_ffmpeg_bin(), "-y", *_input_args]
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
                      f"{_build_audio_mix_filter('a0', 'a1', 'aout')}")
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
    playback_speed: float = 1.0,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    crop_cfg_override: MotionCropConfig | None = None,
    content_type: str = "vlog",
    _motion_cache_key: str | None = None,
    _fallback_flag: list | None = None,
    visual_intensity_hint: str | None = None,
    zoom_burst: bool = False,
):
    # Phase 5.7: Resolve effective effect preset from AI visual intensity hint.
    # Renderer OWNS the mapping; AI only passes None/"low"/"medium"/"high".
    # User explicit effect_preset (non-default) always wins over AI hint.
    _smart_user_explicit = (
        (effect_preset or "slay_soft_01").strip() != "slay_soft_01"
    )
    _smart_effective_preset = resolve_effect_preset_with_intensity(
        effect_preset, visual_intensity_hint, _smart_user_explicit
    )

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
                    effect_preset=_smart_effective_preset,
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
                    _cache_key=_motion_cache_key,
                )
            finally:
                if _crop_ctx is not None:
                    _crop_ctx.release()
            return result
        except Exception as exc:
            logger.warning("Motion-aware crop failed, fallback to standard render: %s", exc)
            logger.info("recovery_attempted strategy=fallback_standard_crop reason=%s output=%s", exc, Path(output_path).name)
            if _fallback_flag is not None:
                _fallback_flag.append(str(exc))
            # Fallback to standard ffmpeg render path if motion-aware branch fails.
            # Pass visual_intensity_hint so render_part() can re-resolve correctly.
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
                visual_intensity_hint=visual_intensity_hint,
                zoom_burst=zoom_burst,
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
        visual_intensity_hint=visual_intensity_hint,
        zoom_burst=zoom_burst,
    )


def render_part_from_source(
    source_path: str,
    output_path: str,
    source_start: float,
    source_duration: float,
    subtitle_ass: str | None,
    title_text: str | None,
    *,
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
    playback_speed: float = 1.0,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    content_type: str = "vlog",
    visual_intensity_hint: str | None = None,
    zoom_burst: bool = False,
    force_accurate_cut: bool = False,
    # Sprint 7.8 (2026-06-05) — motion-aware fused cut+render branch.
    # When motion_aware_crop=True, delegates to render_motion_aware_crop
    # with source_start_sec/source_duration_sec window kwargs instead of
    # passing through render_part. Defaults preserve Sprint 7.4 behaviour.
    motion_aware_crop: bool = False,
    reframe_mode: str = "subject",
    _motion_cache_key: str | None = None,
    _fallback_flag: list | None = None,
) -> None:
    """Sprint 7.4 (2026-06-05) — fused cut+render for the raw_part skip path.

    Combines the cut_video stream-copy + render_part_smart final encode into
    a single FFmpeg invocation by passing source_start / source_duration
    through to render_part's new ``_source_seek_*`` kwargs (input-side seek
    by default, output-side when ``force_accurate_cut=True``).

    Sprint 7.8 (2026-06-05) added the motion-aware-crop branch. When
    ``motion_aware_crop=True``, delegates to ``render_motion_aware_crop``
    with ``source_start_sec``/``source_duration_sec`` so the OpenCV read
    loop pulls only the window. Force-OFF fallback: leave the kwarg False.

    Eliminates the raw_part.mp4 intermediate when:
      - part_subtitle_enabled = False           (no per-part Whisper consumer)
      - base_clip will not render                (Sprint 6 P0 HIGH gate inactive)
      - motion_aware_crop = False (Sprint 7.4) OR True (Sprint 7.8)

    See docs/review/SPRINT_7_4_RAW_PART_FUSE_2026-06-05.md and
    docs/review/SPRINT_7_8_MOTION_AWARE_FUSE_PLAN_2026-06-05.md.
    """
    if motion_aware_crop:
        # Sprint 7.8 — fused cut + motion-aware-crop. NVENC semaphore
        # acquired here (same pattern as render_part_smart lines 633-640)
        # so total acquires per part stays at 1.
        from app.features.render.engine.motion import render_motion_aware_crop
        _crop_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
        _crop_ctx = NVENC_SEMAPHORE if _crop_codec in ("h264_nvenc", "hevc_nvenc") else None
        if _crop_ctx is not None:
            _crop_ctx.acquire()
        try:
            try:
                return render_motion_aware_crop(
                    input_path=source_path,
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
                    content_type=content_type,
                    _cache_key=_motion_cache_key,
                    source_start_sec=float(source_start),
                    source_duration_sec=float(source_duration),
                    source_seek_force_accurate=force_accurate_cut,
                )
            except Exception as exc:
                logger.warning("Motion-aware fused crop failed, fallback to render_part: %s", exc)
                if _fallback_flag is not None:
                    _fallback_flag.append(str(exc))
                # Fall through to the standard render_part path below (no
                # motion crop, but window-cut + final encode still fused).
        finally:
            if _crop_ctx is not None:
                _crop_ctx.release()

    # Sprint 7.4 path (non-motion-aware) or Sprint 7.8 motion-crop fallback.
    return render_part(
        input_path=source_path,
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
        visual_intensity_hint=visual_intensity_hint,
        zoom_burst=zoom_burst,
        _source_seek_start=float(source_start),
        _source_seek_duration=float(source_duration),
        _source_seek_force_accurate=force_accurate_cut,
    )


