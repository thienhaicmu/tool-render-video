"""Story Mode v2 — B0 wire fields: default inert (Sacred #2) + FE-facing + validator."""
from __future__ import annotations

from app.models.schemas import RenderRequest
from app.models.render_public import FE_FACING_FIELDS, BE_ONLY_FIELDS, RenderRequestPublic

_NEW = ("story_source", "story_idea", "story_duration_sec", "story_genre")


def test_defaults_inert():
    r = RenderRequest(output_dir="")
    assert r.story_source == ""       # "" = paste path (unchanged behaviour)
    assert r.story_idea == ""
    assert r.story_duration_sec == 0
    assert r.story_genre == ""


def test_story_source_validator_normalises():
    assert RenderRequest(story_source="idea", output_dir="").story_source == "idea"
    assert RenderRequest(story_source="PASTE", output_dir="").story_source == "paste"
    assert RenderRequest(story_source=" Idea ", output_dir="").story_source == "idea"
    assert RenderRequest(story_source="bogus", output_dir="").story_source == ""   # unknown → paste
    assert RenderRequest(story_source=None, output_dir="").story_source == ""


def test_fields_are_fe_facing():
    for f in _NEW:
        assert f in FE_FACING_FIELDS
        assert f not in BE_ONLY_FIELDS       # partition — never both
        assert f in RenderRequestPublic.model_fields


def test_fields_grouped():
    from app.models.render_field_groups import group_of
    for f in _NEW:
        assert group_of(f) == "story"


def test_public_accepts_idea_payload():
    p = RenderRequestPublic(
        render_format="story", story_source="idea",
        story_idea="A fallen sect disciple awakens a forbidden power.",
        story_duration_sec=300, story_genre="wuxia",
    )
    assert p.story_source == "idea"
    assert p.story_duration_sec == 300
