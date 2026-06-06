# COMPAT shim — canonical: app.features.render.ai.dependencies
from app.features.render.ai.dependencies import *  # noqa: F401, F403
from app.features.render.ai.dependencies import (  # noqa: F401
    has_sentence_transformers,
    has_faiss,
    has_librosa,
    has_mediapipe,
    has_faster_whisper,
    has_whisperx,
    has_deepfilternet,
    has_xtts,
    get_ai_dependency_status,
)
