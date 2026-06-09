"""Sprint F-2 — whisper_model allow-list validator on RenderRequest.

1. Known model string → accepted, value preserved.
2. None (omitted) → accepted (uses pipeline default).
3. Empty string → accepted (treated as "use pipeline default").
4. Unknown model name → ValidationError.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_known_whisper_model_accepted():
    from app.models.render import RenderRequest
    rr = RenderRequest(whisper_model="large-v3")
    assert rr.whisper_model == "large-v3"


def test_whisper_model_none_accepted():
    from app.models.render import RenderRequest
    rr = RenderRequest(whisper_model=None)
    assert rr.whisper_model is None


def test_whisper_model_empty_string_accepted():
    from app.models.render import RenderRequest
    rr = RenderRequest(whisper_model="")
    assert rr.whisper_model == ""


def test_unknown_whisper_model_raises():
    from app.models.render import RenderRequest
    with pytest.raises((ValidationError, ValueError)):
        RenderRequest(whisper_model="large-v4")
