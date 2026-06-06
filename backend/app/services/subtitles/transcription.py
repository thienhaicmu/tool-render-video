# COMPAT shim — canonical: app.features.render.engine.subtitle.transcription.whisper
from app.features.render.engine.subtitle.transcription.whisper import *  # noqa: F401, F403
from app.features.render.engine.subtitle.transcription.whisper import (  # noqa: F401
    _MODEL_CACHE,
    _MODEL_CACHE_LOCK,
    _MODEL_TRANSCRIBE_LOCKS,
    _get_transcribe_lock,
)
