from dataclasses import dataclass


@dataclass
class VisualAnalysisResult:
    """Captures all Layer 4 (Visual Analysis) outputs.

    Produced after detect_scenes() completes — before segment building.
    Passed conceptually as the Layer 4 → Layer 5 contract.
    """
    scene_count: int = 0
    detection_ms: int = 0
    cache_hit: bool = False
    clip_score_applied: bool = False
    clip_score_ms: int = 0
