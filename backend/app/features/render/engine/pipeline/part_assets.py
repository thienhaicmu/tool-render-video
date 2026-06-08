from dataclasses import dataclass, field


@dataclass
class PartAssets:
    """Captures all Layer 7 (Overlay Asset Prep) outputs for one part.

    Produced after subtitle slicing, ASS conversion, translation, hook
    formatting, and text-layer assembly — before FFmpeg render execution.
    Passed conceptually as the Layer 7 → Layer 8 contract.
    """
    # Subtitle
    subtitle_enabled: bool = False
    srt_path: str | None = None
    ass_path: str | None = None
    subtitle_count: int = 0
    subtitle_style: str = ""
    hook_subtitle_formatted: bool = False
    # Hook overlay
    hook_overlay_applied: bool = False
    # Text layers (legacy path and overlay-composite path)
    text_layers: list = field(default_factory=list)
    text_layers_overlay: list = field(default_factory=list)
