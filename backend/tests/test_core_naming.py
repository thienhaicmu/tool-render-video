"""Tests for ``app.core.naming.slugify`` (audit A08).

The helper moved from ``app.features.download.engine.downloader`` to
``app.core.naming`` so the render feature no longer reaches into the
downloader feature for a generic filesystem-safe name builder. These
tests pin the canonical behaviour at the new home and verify the
backward-compat re-export at the old location still resolves.
"""
from __future__ import annotations

import pytest

from app.core.naming import slugify


# ---------------------------------------------------------------------------
# Canonical behaviour
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("inp", "want"),
    [
        ("Hello World",                "hello-world"),
        ("  HELLO   WORLD  ",          "hello-world"),
        ("Người 123 chạy đua",         "ng-i-123-ch-y-ua"),  # diacritics dropped
        ("My Video!@#$%^&*().mp4",      "my-video-mp4"),
        ("multiple---dashes",          "multiple-dashes"),
        ("UPPERCASE_With_Underscores", "uppercase-with-underscores"),
        ("1234567890",                 "1234567890"),
        ("---",                        "video"),
        ("",                           "video"),
        ("@@@@",                       "video"),
    ],
)
def test_slug_canonical_outputs(inp: str, want: str):
    assert slugify(inp) == want


def test_slug_truncates_to_80_chars():
    long = "a" * 200
    out = slugify(long)
    assert len(out) <= 80
    assert out == "a" * 80


def test_slug_truncates_long_input_with_separators():
    # If the slug would otherwise contain a trailing hyphen at exactly 80
    # characters, the truncation must still produce a valid slug.
    long = ("hello world " * 30).strip()
    out = slugify(long)
    assert len(out) <= 80
    assert not out.startswith("-")
    assert not out.endswith("-")


# ---------------------------------------------------------------------------
# Backward-compat re-export
# ---------------------------------------------------------------------------

def test_legacy_import_still_resolves():
    """The downloader's ``slugify`` re-export must still point at the same
    function so any existing internal callers don't break.
    """
    from app.features.download.engine.downloader import slugify as legacy_slugify
    assert legacy_slugify is slugify


# ---------------------------------------------------------------------------
# Cross-feature import was severed
# ---------------------------------------------------------------------------

def test_render_lifecycle_imports_from_core():
    """Closes the asymmetric import: render must reach into core, not
    into the downloader feature.
    """
    src = (
        __import__(
            "app.features.render.routers.lifecycle", fromlist=["slugify"],
        ).slugify
    )
    assert src is slugify


def test_pipeline_source_prep_imports_from_core():
    src = (
        __import__(
            "app.features.render.engine.pipeline.pipeline_source_prep",
            fromlist=["slugify"],
        ).slugify
    )
    assert src is slugify
