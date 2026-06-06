import logging
from pathlib import Path

from app.domain.timeline import TimelineMap
from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.encoder_helpers import (
    codec_extra_flags as _codec_extra_flags,
    map_preset_for_encoder as _map_preset_for_encoder,
    safe_filter_path as _safe_filter_path,
    detect_windows_fontfile as _detect_windows_fontfile,
    detect_windows_fonts_dir as _detect_windows_fonts_dir,
    get_custom_fonts_dir as _get_custom_fonts_dir,
)
from app.features.render.engine.overlay.text_overlay import append_text_layer_filters
from app.features.render.engine.encoder.ffmpeg_helpers import (
    NVENC_SEMAPHORE,
    probe_video_metadata,
    _run_ffmpeg_with_retry,
    _resolve_codec,
    resolve_ffmpeg_threads,
)

logger = logging.getLogger(__name__)


def composite_overlays_on_base_clip(
    base_clip_path: str,
    output_path: str,
    timeline: TimelineMap,
    subtitle_ass: str | None = None,
    text_layers: "list[dict] | None" = None,
    title_text: "str | None" = None,
    video_codec: str = "h264",
    video_crf: int = 18,
    video_preset: str = "slow",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    ffmpeg_threads: int | None = None,
) -> dict:
    """Burn output-timeline subtitle and text overlays onto a pre-processed base clip.

    The base clip is already speed-adjusted, cropped, color-processed, and
    audio-adjusted by render_base_clip(). This compositor applies only overlays:
    subtitle burn-in, title drawtext, and text_layer drawtext filters.

    All start_time / end_time values in text_layers must be output-timeline seconds.
    On base_clip.mp4 the frame PTS is already output-timeline; no speed conversion
    is applied here â€” the caller builds output-timeline layers before calling.

    Invariants: no setpts, no atempo, no crop, no scale, no color/effect filters.
    Audio is always copied; the base_clip audio is already speed-adjusted and
    loudnorm-applied from render_base_clip().

    When no overlays are present (all three sources None/empty), both streams are
    copied without re-encode.

    Returns a metadata dict: path, duration, fps, width, height, has_audio.
    """
    _has_subtitle = bool(subtitle_ass)
    _has_title = bool(title_text and str(title_text).strip())
    _has_text_layers = bool(text_layers)
    _needs_encode = _has_subtitle or _has_title or _has_text_layers

    if not _needs_encode:
        # No overlay â€” stream copy preserves all base_clip quality.
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-i", base_clip_path,
            "-c:v", "copy",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        _run_ffmpeg_with_retry(cmd, retry_count=retry_count)
    else:
        # Build vf_chain: overlays in order, fps= always last.
        # fps is probed from base_clip (which render_base_clip() guaranteed to be CFR);
        # re-applying ensures CFR output regardless of any container quirks.
        _base_fps = int(probe_video_metadata(base_clip_path).get("fps") or 60)
        vf_parts: list = []

        # 1. Subtitle burn-in â€” output-timeline ASS; base_clip PTS already matches.
        if _has_subtitle:
            safe_ass = _safe_filter_path(str(Path(subtitle_ass).resolve()))
            fonts_dir = _get_custom_fonts_dir() or _detect_windows_fonts_dir()
            if fonts_dir:
                vf_parts.append(f"ass='{safe_ass}':fontsdir='{_safe_filter_path(fonts_dir)}'")
            else:
                vf_parts.append(f"ass='{safe_ass}'")

        # 2. Title drawtext â€” enable='lt(t,3)' means first 3 output seconds on base_clip PTS.
        if _has_title:
            fontfile = _detect_windows_fontfile()
            safe_title = str(title_text).replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")[:120]
            drawtext = f"drawtext=text='{safe_title}':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=50:enable='lt(t\\,3)'"
            if fontfile:
                drawtext += f":fontfile='{_safe_filter_path(fontfile)}'"
            vf_parts.append(drawtext)

        # 3. User/hook text_layers â€” start_time/end_time are output-timeline seconds (caller contract).
        if _has_text_layers:
            append_text_layer_filters(vf_parts, text_layers)

        # 4. fps= always last â€” guarantees CFR output for platform compatibility.
        vf_parts.append(f"fps={_base_fps}")

        vf_chain = ",".join(vf_parts)

        resolved_codec = _resolve_codec(video_codec, encoder_mode=encoder_mode)
        resolved_preset = _map_preset_for_encoder(video_preset, resolved_codec)
        _threads = ffmpeg_threads if ffmpeg_threads is not None else resolve_ffmpeg_threads()

        codec_flags = [
            "-c:v", resolved_codec, "-preset", resolved_preset,
            *_codec_extra_flags(resolved_codec, int(video_crf), video_preset),
            "-threads", str(_threads),
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-movflags", "+faststart",
        ]
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-i", base_clip_path,
            "-vf", vf_chain,
            *codec_flags,
            "-c:a", "copy",
            output_path,
        ]

        if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
            try:
                with NVENC_SEMAPHORE:
                    # nvenc_externally_held=True â€” see Sprint 4.2 note in
                    # base_clip_renderer; avoids semaphore double-acquire.
                    _run_ffmpeg_with_retry(cmd, retry_count=retry_count, nvenc_externally_held=True)
            except Exception as _nvenc_err:
                logger.warning(
                    "NVENC overlay composite failed (%s), falling back to CPU for %s",
                    _nvenc_err, Path(output_path).name,
                )
                cpu_codec = "libx265" if str(video_codec).lower() == "h265" else "libx264"
                cpu_preset = _map_preset_for_encoder(video_preset, cpu_codec)
                cpu_flags = [
                    "-c:v", cpu_codec, "-preset", cpu_preset,
                    *_codec_extra_flags(cpu_codec, int(video_crf), video_preset),
                    "-threads", str(_threads),
                    "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-movflags", "+faststart",
                ]
                cpu_cmd = [
                    get_ffmpeg_bin(), "-y",
                    "-i", base_clip_path,
                    "-vf", vf_chain,
                    *cpu_flags,
                    "-c:a", "copy",
                    output_path,
                ]
                _run_ffmpeg_with_retry(cpu_cmd, retry_count=retry_count)
        else:
            _run_ffmpeg_with_retry(cmd, retry_count=retry_count)

    meta = probe_video_metadata(output_path)
    return {
        "path": output_path,
        "duration": meta.get("duration"),
        "fps": meta.get("fps"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "has_audio": bool(meta.get("has_audio", False)),
    }

