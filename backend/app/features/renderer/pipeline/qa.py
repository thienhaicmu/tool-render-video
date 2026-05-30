"""L7 — QA layer: output validation (never bypass).

Re-exports from the canonical orchestration module.
Contract 8: qa_pipeline validation must never be bypassed.
"""
from app.orchestration.qa_pipeline import *  # noqa: F401, F403
