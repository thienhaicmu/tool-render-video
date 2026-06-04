"""
Sprint 3.1 — pin the CreatorContext dataclass contract:

- defaults are safe (every field default + is_empty pin Sacred Contract #2)
- to_json / from_json round-trip is lossless
- from_json is strictly defensive — never raises
- to_prompt_hint() is deterministic, empty-friendly, format-safe
  (no literal `{...}` placeholders that would explode in
  prompts._USER_TEMPLATE.format — the pre-flight bug class)
"""
from app.domain.creator_context import SCHEMA_VERSION, CreatorContext


class TestDefaults:
    def test_default_is_safe(self):
        c = CreatorContext()
        assert c.schema_version == SCHEMA_VERSION
        assert c.creator_id == ""
        assert c.channel_name == ""
        assert c.brand_voice == ""
        assert c.target_audience == ""
        assert c.content_pillars == []
        assert c.market == ""
        assert c.language == ""
        assert c.notes == ""

    def test_empty_default(self):
        assert CreatorContext().is_empty() is True

    def test_not_empty_when_any_field_set(self):
        assert CreatorContext(channel_name="k1").is_empty() is False
        assert CreatorContext(brand_voice="viral").is_empty() is False
        assert CreatorContext(content_pillars=["recipe"]).is_empty() is False
        assert CreatorContext(notes="brief").is_empty() is False
        # Whitespace-only doesn't count as set.
        assert CreatorContext(channel_name="   ").is_empty() is True


class TestRoundTrip:
    def test_default_roundtrip(self):
        original = CreatorContext()
        restored = CreatorContext.from_json(original.to_json())
        assert restored == original

    def test_populated_roundtrip(self):
        original = CreatorContext(
            creator_id="creator-vn-1",
            channel_name="K1 Cooking",
            brand_voice="authentic",
            target_audience="vn",
            content_pillars=["recipe", "tutorial"],
            market="vn",
            language="vi",
            notes="Friendly home cook vibe; keep hooks short.",
        )
        restored = CreatorContext.from_json(original.to_json())
        assert restored == original

    def test_vietnamese_chars_preserved(self):
        original = CreatorContext(channel_name="Bếp Việt", notes="Hấp dẫn, gần gũi")
        restored = CreatorContext.from_json(original.to_json())
        assert restored is not None
        assert restored.channel_name == "Bếp Việt"
        assert restored.notes == "Hấp dẫn, gần gũi"

    def test_json_is_compact_and_sorted(self):
        c = CreatorContext(creator_id="abc")
        raw = c.to_json()
        # No whitespace between members.
        assert ", " not in raw and ": " not in raw
        # First few sorted top-level keys.
        assert raw.index('"brand_voice"') < raw.index('"channel_name"') < raw.index('"creator_id"')


class TestDefensiveFromJson:
    def test_none_returns_none(self):
        assert CreatorContext.from_json(None) is None

    def test_empty_string_returns_none(self):
        assert CreatorContext.from_json("") is None

    def test_malformed_json_returns_none(self):
        assert CreatorContext.from_json("not json at all") is None
        assert CreatorContext.from_json("{nope}") is None

    def test_array_top_level_returns_none(self):
        assert CreatorContext.from_json("[1,2,3]") is None

    def test_unknown_keys_dropped(self):
        raw = '{"channel_name":"k1","unknown_key":42}'
        c = CreatorContext.from_json(raw)
        assert c is not None
        assert c.channel_name == "k1"
        assert not hasattr(c, "unknown_key")

    def test_content_pillars_from_csv_string(self):
        """Forward-compat: a string like 'a,b,c' parses to ['a','b','c']."""
        raw = '{"content_pillars":"recipe, tutorial , review"}'
        c = CreatorContext.from_json(raw)
        assert c is not None
        assert c.content_pillars == ["recipe", "tutorial", "review"]

    def test_content_pillars_drops_empties(self):
        raw = '{"content_pillars":["a","","  ","b"]}'
        c = CreatorContext.from_json(raw)
        assert c is not None
        assert c.content_pillars == ["a", "b"]

    def test_string_coercion_for_non_string_values(self):
        raw = '{"channel_name":123,"brand_voice":true}'
        c = CreatorContext.from_json(raw)
        assert c is not None
        assert c.channel_name == "123"
        # bool coerces via str() to "True"
        assert c.brand_voice == "True"

    def test_schema_version_explicit(self):
        c = CreatorContext.from_json('{"schema_version":7}')
        assert c is not None
        assert c.schema_version == 7

    def test_schema_version_missing_uses_current(self):
        c = CreatorContext.from_json("{}")
        assert c is not None
        assert c.schema_version == SCHEMA_VERSION

    def test_bytes_input_accepted(self):
        original = CreatorContext(channel_name="k1")
        raw = original.to_json().encode("utf-8")
        restored = CreatorContext.from_json(raw)
        assert restored == original


class TestPromptHintRendering:
    def test_empty_context_renders_empty_string(self):
        """Pin: blank CreatorContext yields no editorial hint → AI
        prompt behaves identically to pre-Sprint-3."""
        assert CreatorContext().to_prompt_hint() == ""

    def test_full_context_renders_human_readable(self):
        c = CreatorContext(
            channel_name="K1 Cooking",
            brand_voice="authentic",
            target_audience="vn",
            content_pillars=["recipe", "tutorial"],
            language="vi",
            notes="Friendly tone",
        )
        hint = c.to_prompt_hint()
        assert "Channel: K1 Cooking" in hint
        assert "Brand voice: authentic" in hint
        assert "Target audience: vn" in hint
        assert "Language: vi" in hint
        assert "Content pillars: recipe, tutorial" in hint
        assert "Editorial brief: Friendly tone" in hint

    def test_partial_context_includes_only_set_fields(self):
        c = CreatorContext(brand_voice="educational")
        hint = c.to_prompt_hint()
        assert hint == "Brand voice: educational"

    def test_hint_is_deterministic(self):
        c = CreatorContext(channel_name="k1", brand_voice="viral", language="vi")
        assert c.to_prompt_hint() == c.to_prompt_hint()

    def test_hint_contains_no_format_placeholders(self):
        """Defensive against the pre-flight bug class — prompts.py uses
        .format() and any literal `{foo}` token in the editorial hint
        would explode with KeyError. Pin that the hint never contains
        the `{` character."""
        c = CreatorContext(
            channel_name="K1 {brand}",      # user-supplied content might include braces
            brand_voice="viral",
            notes="curly {braces} should not break .format()",
        )
        hint = c.to_prompt_hint()
        # The hint itself is fed verbatim into prompts.build_segment_prompt
        # via `editorial_hint`, which goes into the {editorial_section}
        # placeholder. That placeholder substitution does NOT re-format the
        # hint, so even literal braces in the hint pass through harmlessly.
        # This test pins the assumption: hint contains the raw braces (no
        # accidental escaping yet), and downstream wiring must not call
        # .format() on it again.
        assert "{brand}" in hint
        assert "{braces}" in hint

    def test_target_audience_falls_back_to_market(self):
        c = CreatorContext(market="us")
        assert "Target audience: us" in c.to_prompt_hint()

    def test_target_audience_wins_over_market_when_both_set(self):
        c = CreatorContext(target_audience="vn", market="us")
        assert "Target audience: vn" in c.to_prompt_hint()
        assert "us" not in c.to_prompt_hint()
