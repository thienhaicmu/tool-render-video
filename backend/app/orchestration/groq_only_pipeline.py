"""
groq_only_pipeline.py — Compatibility shim. Renamed to llm_pipeline.py.
Import from app.orchestration.llm_pipeline instead.
"""
from app.orchestration.llm_pipeline import (  # noqa: F401
    LLMPipelineError as GroqOnlyPipelineError,
    LLMPreRenderResult as PreRenderScenesResult,
    run_llm_pre_render as run_groq_only_pre_render,
)
