from enum import Enum


class JobStage(str, Enum):
    """Pipeline stage recorded in jobs.stage column and current_stage variable."""
    QUEUED             = "queued"
    STARTING           = "starting"
    RUNNING            = "running"            # batch job lifecycle
    ANALYZING          = "analyzing"          # local video analysis (replaces download stage)
    DOWNLOADING        = "downloading"        # kept for backward compat with stored records
    SCENE_DETECTION    = "scene_detection"
    SEGMENT_BUILDING   = "segment_building"
    TRANSCRIBING_FULL  = "transcribing_full"
    RENDERING          = "rendering"
    RENDERING_PARALLEL = "rendering_parallel"
    WRITING_REPORT     = "writing_report"
    DONE               = "done"
    FAILED             = "failed"
    # Audit 2026-06-02 P3-B1 follow-up — was written as the raw string
    # "cancelled" at routes/render.py:557 because the enum value was missing.
    # Sacred Contract 4 lists CANCELLED as a frozen terminal job stage.
    CANCELLED          = "cancelled"


class JobPartStage(str, Enum):
    """Per-part status recorded in job_parts.status column."""
    QUEUED       = "queued"
    WAITING      = "waiting"      # worker thread claimed the part, work not started yet
    CUTTING      = "cutting"
    TRANSCRIBING = "transcribing"
    RENDERING    = "rendering"
    DONE         = "done"
    FAILED       = "failed"
    SKIPPED      = "skipped"


# Maps JobStage → structured event name used by _emit_render_event().
# Replaces the inline _event_from_stage() string-matching logic.
STAGE_TO_EVENT: dict[str, str] = {
    JobStage.QUEUED:             "render.start",
    JobStage.STARTING:           "render.start",
    JobStage.RUNNING:            "render.start",
    JobStage.ANALYZING:          "render.analyze.start",
    JobStage.DOWNLOADING:        "render.download.start",
    JobStage.SCENE_DETECTION:    "render.scene.detect.start",
    JobStage.SEGMENT_BUILDING:   "render.segment.build.start",
    JobStage.TRANSCRIBING_FULL:  "render.transcribe.start",
    JobStage.RENDERING:          "render.ffmpeg.start",
    JobStage.RENDERING_PARALLEL: "render.ffmpeg.start",
    JobStage.WRITING_REPORT:     "render.report.start",
    JobStage.DONE:               "render.complete",
    JobStage.FAILED:             "render.error",
}
