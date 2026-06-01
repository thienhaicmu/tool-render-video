"""
app/ai/quality_gate/ — Quality-gated influence (Phase 59D).

Public API:
    apply_quality_gate(payload, edit_plan, job_id) -> dict
    apply_segment_quality_gate(payload, edit_plan, job_id) -> dict
"""
try:
    from app.ai.quality_gate.quality_gate_engine import (
        apply_quality_gate,
        apply_segment_quality_gate,
    )
    _QUALITY_GATE_AVAILABLE = True
except ImportError:
    _QUALITY_GATE_AVAILABLE = False

__all__ = ["apply_quality_gate", "apply_segment_quality_gate"]
