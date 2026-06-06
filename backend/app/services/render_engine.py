# COMPAT shim — functions now live in features/render/engine/encoder/
from app.features.render.engine.encoder.ffmpeg_helpers import (  # noqa: F401
    NVENC_SEMAPHORE, set_thread_cancel_event,
    probe_video_metadata, extract_thumbnail_frame,
    nvenc_available, _resolve_codec,
    resolve_ffmpeg_threads, resolve_target_dimensions,
    _has_audio_stream, has_audio_stream,
    _run_ffmpeg_with_retry, _probe_duration,
    _sanitize_speed, _resolve_fps, _probe_fps,
    content_type_crf_delta, resolve_effect_preset_with_intensity,
)
from app.features.render.engine.encoder.clip_renderer import (  # noqa: F401
    render_base_clip, render_part, render_part_smart,
    render_part_from_source,
)
from app.features.render.engine.encoder.clip_ops import (  # noqa: F401
    cut_video, detect_silence_trim_offset,
    detect_bad_first_frame, apply_micro_pacing,
)
from app.features.render.engine.encoder.overlay_compositor import (  # noqa: F401
    composite_overlays_on_base_clip,
)
