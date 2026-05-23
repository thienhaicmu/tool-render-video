import logging
from pathlib import Path

from app.services.motion_crop import render_motion_aware_crop, MotionCropConfig
from app.services.bin_paths import get_ffmpeg_bin
from app.services.text_overlay import append_text_layer_filters
from app.services.encoder_helpers import (
    codec_extra_flags as _codec_extra_flags,
    map_preset_for_encoder as _map_preset_for_encoder,
    reup_video_filters as _reup_video_filters,
    safe_filter_path as _safe_filter_path,
    detect_windows_fontfile as _detect_windows_fontfile,
    detect_windows_fonts_dir as _detect_windows_fonts_dir,
    get_custom_fonts_dir as _get_custom_fonts_dir,
)
from app.services.render.ffmpeg_helpers import (
    NVENC_SEMAPHORE,
    probe_video_metadata,
    _run_ffmpeg_with_retry,
    _resolve_codec,
    _effect_filter,
    _cinematic_color_filter,
    _cinematic_sharpen_filter,
    _smart_denoise_filter,
    _build_audio_mix_filter,
    _build_audio_filter,
    _resolve_fps,
    _sanitize_speed,
    _has_audio_stream,
    resolve_ffmpeg_threads,
    resolve_target_dimensions,
    resolve_effect_preset_with_intensity,
)

logger = logging.getLogger(__name__)


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
    visual_intensity_hint: str | None = None,
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
        # Floor at 0.03 s (≈ 1 frame at 30fps) prevents pure hard cuts.
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
    playback_speed: float = 1.07,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    crop_cfg_override: MotionCropConfig | None = None,
    content_type: str = "vlog",
    _motion_cache_key: str | None = None,
    _fallback_flag: list | None = None,
    visual_intensity_hint: str | None = None,
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
    )
