from app.domain.timeline import TimelineMap
from app.features.render.engine.subtitle.generator.srt import slice_srt_by_time


def slice_srt_to_output_timeline(
    source_srt_path: str,
    output_srt_path: str,
    source_start: float,
    source_end: float,
    timeline: TimelineMap,
) -> dict:
    """Slice a source SRT and re-time entries to output-timeline seconds.

    Output-timeline subtitles are required because base_clip.mp4 has already
    been re-clocked from source time by setpts=PTS/speed in render_base_clip().
    Divides each timestamp by timeline.effective_speed after rebasing to zero,
    so subtitle 10 s at 1.15× speed appears at ≈ 8.70 s in the output clip.

    Returns the same metadata dict as slice_srt_by_time().
    """
    return slice_srt_by_time(
        source_srt_path,
        output_srt_path,
        float(source_start),
        float(source_end),
        rebase_to_zero=True,
        playback_speed=timeline.effective_speed,
        apply_playback_speed=True,
    )

