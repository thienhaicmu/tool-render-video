"""L2 — AI analysis layer: AI selects best segments (Groq / local / hybrid).

This layer bridges the AI Director into the pipeline.
The actual AI logic lives in app.ai.director.ai_director.
"""
from app.ai.director.ai_director import AIDirector  # noqa: F401
