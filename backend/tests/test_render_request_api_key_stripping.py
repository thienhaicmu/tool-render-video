"""Tests for the RenderRequest API-key stripping validator
(audit FINDING-F07 / C02).

Closes the contract: cloud LLM API keys must NOT travel in the
RenderRequest payload, must NOT be persisted to jobs.payload_json,
and must NOT reach per-job log files.

Verified properties:
1. Any non-empty *_api_key field is stripped to None at validation time.
2. A WARN log is emitted to the "app.api.security" logger so the
   policy violation is auditable.
3. The fields remain in the model (Sacred Contract #2 backwards-compat
   for stored payloads with legacy keys).
4. Stored payloads with legacy keys deserialize cleanly (no exception).
"""
from __future__ import annotations

import logging

import pytest

from app.models.schemas import RenderRequest


_KEY_FIELDS = (
    "ai_cloud_api_key",
    "gemini_api_key",
    "openai_api_key",
    "claude_api_key",
    "groq_api_key",
)


def _make_valid_render_request(**overrides) -> dict:
    """Minimum valid RenderRequest dict — only set fields we care about."""
    base = {
        "source_mode": "local",
        "source_video_path": "/tmp/in.mp4",
        "output_dir": "/tmp/out",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Stripping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", _KEY_FIELDS)
def test_api_key_field_stripped_to_none(field: str):
    payload = _make_valid_render_request(**{field: "sk-real-secret-1234"})
    req = RenderRequest(**payload)
    assert getattr(req, field) is None


@pytest.mark.parametrize("field", _KEY_FIELDS)
def test_api_key_whitespace_stripped_to_none(field: str):
    # An "all-whitespace" key is silently dropped (it's still a non-secret).
    payload = _make_valid_render_request(**{field: "   "})
    req = RenderRequest(**payload)
    assert getattr(req, field) is None


@pytest.mark.parametrize("field", _KEY_FIELDS)
def test_api_key_empty_string_stripped_silently(field: str, caplog):
    caplog.set_level(logging.WARNING, logger="app.api.security")
    payload = _make_valid_render_request(**{field: ""})
    req = RenderRequest(**payload)
    assert getattr(req, field) is None
    warnings = [r for r in caplog.records if r.name == "app.api.security"]
    assert warnings == [], "empty/missing keys must NOT warn"


@pytest.mark.parametrize("field", _KEY_FIELDS)
def test_api_key_missing_does_not_warn(field: str, caplog):
    """When the FE simply omits the key, no warning is generated."""
    caplog.set_level(logging.WARNING, logger="app.api.security")
    payload = _make_valid_render_request()
    req = RenderRequest(**payload)
    assert getattr(req, field) is None
    warnings = [r for r in caplog.records if r.name == "app.api.security"]
    assert warnings == []


# ---------------------------------------------------------------------------
# WARN signal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", _KEY_FIELDS)
def test_real_key_logs_security_warning(field: str, caplog):
    caplog.set_level(logging.WARNING, logger="app.api.security")
    payload = _make_valid_render_request(**{field: "sk-this-is-a-real-secret"})
    RenderRequest(**payload)
    warnings = [r for r in caplog.records if r.name == "app.api.security" and r.levelname == "WARNING"]
    assert len(warnings) >= 1
    # The warning mentions the audit ID + policy reference so the
    # operator can find the closure note.
    full = "\n".join(r.getMessage() for r in warnings)
    assert "F07" in full or "C02" in full
    assert "stripping" in full.lower()


def test_secret_value_never_appears_in_warning(caplog):
    """Sanity: the WARN log must not echo the actual key value (or we'd
    be defeating our own purpose by writing it back to logs).
    """
    caplog.set_level(logging.WARNING, logger="app.api.security")
    secret = "sk-ultra-secret-VALUE-1234567890"
    payload = _make_valid_render_request(ai_cloud_api_key=secret)
    RenderRequest(**payload)
    for r in caplog.records:
        if r.name == "app.api.security":
            assert secret not in r.getMessage(), (
                "WARN log leaked the secret value back into logs"
            )


# ---------------------------------------------------------------------------
# Sacred Contract #2 — stored payload replay
# ---------------------------------------------------------------------------

def test_stored_payload_with_keys_replays_cleanly():
    """A legacy stored payload (e.g. from before Batch 3) that carries
    a real key must still deserialize without raising. The keys get
    stripped on the way in; the rest of the render proceeds.
    """
    legacy = _make_valid_render_request(
        ai_cloud_api_key="legacy-key",
        gemini_api_key="legacy-gemini-key",
        openai_api_key="legacy-openai-key",
    )
    req = RenderRequest(**legacy)
    # All stripped — Sacred Contract #2 preserved (no exception, no breakage).
    assert req.ai_cloud_api_key is None
    assert req.gemini_api_key is None
    assert req.openai_api_key is None


# ---------------------------------------------------------------------------
# The fields still exist in the model (for backward compat introspection)
# ---------------------------------------------------------------------------

def test_fields_still_declared_on_model():
    """The audit pinning ensures we don't delete the fields outright —
    Sacred Contract #2 wants stored payloads to deserialize cleanly.
    Verify the fields are still members of the model.
    """
    fields = RenderRequest.model_fields
    for f in _KEY_FIELDS:
        assert f in fields, f"{f!r} disappeared from RenderRequest"
