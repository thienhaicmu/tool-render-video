# COMPAT shim — canonical: app.features.render.engine.subtitle.processing.readability
from app.features.render.engine.subtitle.processing.readability import *  # noqa: F401, F403
from app.features.render.engine.subtitle.processing.readability import (  # noqa: F401
    _HOOK_EMPHASIS_WORDS,
    _is_cjk,
    _emphasis_level,
    _should_emphasize,
    _semantic_wrap_block,
    _break_by_visual_width,
    _approx_visual_width,
)
