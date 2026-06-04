"""
groq_stage.py — Compatibility shim. Renamed to llm_stage.py.
Import from app.orchestration.llm_stage instead.
"""
from app.orchestration.llm_stage import (  # noqa: F401
    run_llm_segment_selection as run_groq_segment_selection,
    _build_editorial_hint,
    _resolve_api_key,
    _to_scored_dict,
)
