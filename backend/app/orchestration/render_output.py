from dataclasses import dataclass


@dataclass
class RenderOutputResult:
    """Captures the Layer 8 (FFmpeg Render Execution) output before validation.

    Produced after FFmpeg encode + voice/narration mix — before _validate_render_output.
    Passed conceptually as the Layer 8 → Layer 9 contract.
    """
    output_path: str = ""
    render_ms: int = 0
    codec: str = ""
    crop_fallback: bool = False
    overlay_composite_used: bool = False
