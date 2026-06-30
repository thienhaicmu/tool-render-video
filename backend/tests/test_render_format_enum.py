"""Architecture-review Batch A — RenderFormat Literal contract.

Pins that the ``render_format`` field is a closed-set Literal at the
schema layer while the validator continues to normalise legacy payloads
(uppercase, padded whitespace, None, unknown strings).
"""
from __future__ import annotations

import typing

import pytest

from app.models.render import RenderFormat, RenderRequest


def test_render_format_literal_args():
    """The Literal carries exactly the two supported modes."""
    args = typing.get_args(RenderFormat)
    assert set(args) == {"clips", "recap"}


def test_default_is_clips():
    """Sacred Contract #2: default is the conservative legacy mode."""
    assert RenderRequest().render_format == "clips"


@pytest.mark.parametrize("raw", ["clips", "recap"])
def test_canonical_values_pass_through(raw):
    assert RenderRequest(render_format=raw).render_format == raw


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("RECAP", "recap"),
        ("Recap", "recap"),
        (" recap ", "recap"),
        ("CLIPS", "clips"),
        (" CLIPS ", "clips"),
    ],
)
def test_legacy_casing_and_whitespace_normalised(raw, expected):
    """Stored payloads with non-canonical casing still deserialise — the
    validator runs in mode='before' so it precedes the Literal check."""
    assert RenderRequest(render_format=raw).render_format == expected


@pytest.mark.parametrize("raw", [None, "", "garbage", "highlight", "podcast"])
def test_unknown_values_fall_back_to_clips(raw):
    """An unknown legacy value (e.g. removed render mode) falls back to the
    conservative default, never raises."""
    assert RenderRequest(render_format=raw).render_format == "clips"


def test_schema_lists_closed_set():
    """The OpenAPI / JSON schema exposes the closed set explicitly."""
    schema = RenderRequest.model_json_schema()
    # Pydantic represents Literal as an enum at the field level.
    field_schema = schema["properties"]["render_format"]
    # Resolve via $ref or inline enum, depending on Pydantic version.
    enum_values = field_schema.get("enum")
    if enum_values is None:
        # Pydantic may inline as anyOf / allOf — walk one level.
        defs = schema.get("$defs", {})
        ref = field_schema.get("$ref") or field_schema.get("allOf", [{}])[0].get("$ref")
        if ref:
            name = ref.split("/")[-1]
            enum_values = defs.get(name, {}).get("enum")
    assert enum_values is not None, (
        f"render_format schema does not expose enum values: {field_schema}"
    )
    assert set(enum_values) == {"clips", "recap"}
