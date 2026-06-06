from dataclasses import dataclass, field


@dataclass
class CameraStrategy:
    """Captures the per-part camera/framing decision before FFmpeg execution.

    Produced after PartExecutionPlan — represents the focused camera concern
    (reframe mode, motion tracking, aspect/scale) as an explicit Layer 6.5 artifact.
    """
    aspect_ratio: str = "9:16"
    frame_scale_x: int = 1080
    frame_scale_y: int = 1920
    motion_aware_crop: bool = False
    reframe_mode: str = "subject"
    content_type: str = "vlog"
    camera_mode: str = ""

    def __post_init__(self):
        if not self.camera_mode:
            if self.motion_aware_crop:
                self.camera_mode = "motion_track"
            elif self.reframe_mode == "subject":
                self.camera_mode = "static_subject"
            else:
                self.camera_mode = "static_default"
