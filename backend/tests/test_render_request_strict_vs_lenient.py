"""Tests for the RenderRequest Strict/Lenient split (audit FINDING-C04).

Closes the silent-drop hazard at the API boundary.

The parent ``RenderRequest`` keeps ``extra="ignore"`` so stored payloads
with deprecated keys (groq_*, ai_director_enabled, ai_use_rag_memory, ...)
can replay cleanly — Sacred Contract #2.

The new ``RenderRequestStrict`` overrides the policy to ``extra="forbid"``
and is wired on POST /api/render/process. An unknown field on a fresh
submission now raises a 422 Unprocessable Entity error, so phased FE
rollouts learn about the mismatch immediately instead of after hours
of confused debugging.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import RenderRequest, RenderRequestStrict


def _minimum_valid() -> dict:
    return {
        "source_mode": "local",
        "source_video_path": "/tmp/in.mp4",
        "output_dir": "/tmp/out",
    }


# ---------------------------------------------------------------------------
# Configuration introspection — the contract is encoded in model_config
# ---------------------------------------------------------------------------

def test_lenient_ignores_unknown_fields_by_design():
    """RenderRequest must remain Lenient — stored payloads with legacy keys
    (Sacred Contract #2) must deserialize cleanly.
    """
    assert RenderRequest.model_config.get("extra") == "ignore"


def test_strict_forbids_unknown_fields():
    """RenderRequestStrict must use extra=forbid so unknowns become 422."""
    assert RenderRequestStrict.model_config.get("extra") == "forbid"


def test_strict_is_subclass_of_lenient():
    """Strict inherits every field, validator, and model_validator from
    the Lenient parent — no separate field list to maintain.
    """
    assert issubclass(RenderRequestStrict, RenderRequest)


def test_strict_field_set_matches_lenient():
    """Sanity: the inheritance must NOT add or remove fields."""
    assert RenderRequestStrict.model_fields.keys() == RenderRequest.model_fields.keys()


# ---------------------------------------------------------------------------
# Lenient behaviour — stored payloads with unknown / deprecated keys
# ---------------------------------------------------------------------------

def test_lenient_accepts_unknown_field():
    """An unknown field on the Lenient model is silently dropped — Sacred
    Contract #2 backward-compat for replay of historical jobs.
    """
    payload = _minimum_valid()
    payload["definitely_not_a_real_field"] = "ignored"
    req = RenderRequest(**payload)
    assert not hasattr(req, "definitely_not_a_real_field")


def test_lenient_accepts_deprecated_groq_keys():
    """Migration 0002 stripped groq_* aliases from stored payloads, but
    Sacred Contract #2 promises any future re-add must not crash the
    replay path. Pin the property.
    """
    payload = _minimum_valid()
    payload.update({
        "groq_analysis_enabled": True,
        "groq_model": "llama-3.1-8b-instant",
        "groq_min_quality_score": 0.7,
    })
    # Must not raise; unknown extras silently dropped.
    RenderRequest(**payload)


def test_lenient_accepts_deprecated_ai_director_keys():
    """Phase G removed ai_director / RAG memory; legacy stored payloads
    may still carry them. Replay must not break.
    """
    payload = _minimum_valid()
    payload.update({
        "ai_director_enabled": True,
        "ai_use_rag_memory": True,
        "ai_mode": "auto",
    })
    RenderRequest(**payload)


# ---------------------------------------------------------------------------
# Strict behaviour — POST /api/render/process now rejects typos
# ---------------------------------------------------------------------------

def test_strict_accepts_known_fields_only():
    payload = _minimum_valid()
    payload["min_part_sec"] = 15
    payload["max_part_sec"] = 60
    req = RenderRequestStrict(**payload)
    assert req.min_part_sec == 15


def test_strict_rejects_typo_field():
    """The whole point of Strict: a FE typo surfaces as 422 immediately."""
    payload = _minimum_valid()
    payload["mim_part_sec"] = 15  # typo of min_part_sec
    with pytest.raises(ValidationError) as exc_info:
        RenderRequestStrict(**payload)
    err = str(exc_info.value)
    assert "mim_part_sec" in err
    # Pydantic v2 vocabulary for unknown extras
    assert "extra" in err.lower() or "Extra inputs are not permitted" in err


def test_strict_rejects_deprecated_groq_keys():
    """Strict refuses a fresh submission carrying obsolete fields — the
    FE shouldn't be sending them anymore. Stored-payload replay still
    uses the Lenient parent so historical jobs are unaffected.
    """
    payload = _minimum_valid()
    payload["groq_analysis_enabled"] = True
    with pytest.raises(ValidationError):
        RenderRequestStrict(**payload)


def test_strict_validators_inherited():
    """Field validators from the Lenient parent must still run on Strict.

    Coerce-on-write validators (e.g. part_order falls back to 'viral')
    are part of the contract; the Strict subclass must inherit them.
    """
    payload = _minimum_valid()
    payload["part_order"] = "nonsense_unknown_mode"
    req = RenderRequestStrict(**payload)
    # The part_order validator coerces unknowns to 'viral'.
    assert req.part_order == "viral"


def test_strict_strips_api_keys_like_lenient():
    """The Batch 3 *_api_key stripping validator must apply on Strict too."""
    payload = _minimum_valid()
    payload["gemini_api_key"] = "sk-real-secret"
    req = RenderRequestStrict(**payload)
    assert req.gemini_api_key is None


# ---------------------------------------------------------------------------
# Field count sanity — guards a future "I forgot to add the new field to
# both classes" trap (impossible thanks to inheritance, but pin it anyway).
# ---------------------------------------------------------------------------

def test_strict_has_all_lenient_fields():
    missing = set(RenderRequest.model_fields) - set(RenderRequestStrict.model_fields)
    assert missing == set(), f"Strict missing fields: {sorted(missing)}"


def test_both_models_have_render_essentials():
    """Pin a handful of high-traffic fields so a refactor of the parent
    can't silently remove them.
    """
    essentials = {
        "source_mode", "source_video_path", "output_dir",
        "min_part_sec", "max_part_sec",
        "add_subtitle", "subtitle_style",
        "target_platform", "render_profile",
        "ai_provider", "llm_enabled",
    }
    for model in (RenderRequest, RenderRequestStrict):
        missing = essentials - set(model.model_fields)
        assert missing == set(), f"{model.__name__} missing essentials: {sorted(missing)}"
