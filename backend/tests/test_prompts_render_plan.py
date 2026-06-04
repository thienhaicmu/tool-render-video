"""
Sprint 4.B — pin the build_render_plan_prompt contract.

This is the additive dual-mode prompt builder. Sprint 4.C will hook it
into providers; Sprint 4.D will gate the orchestrator behind a feature
flag; Sprint 4.H will retire build_segment_prompt. For now the function
lives alongside build_segment_prompt and the tests anchor:

- format() never raises (the pre-flight {end}/{start} bug class)
- placeholder substitution works for every named slot
- the JSON example inside the prompt is itself valid JSON and matches
  the native shape parse_render_plan_response accepts
- SRT truncation respects MAX_SRT_CHARS / max_srt_chars
- editorial_hint flows into both system and user prompts
- build_segment_prompt is unchanged (regression guard)
"""
import json
import re

import pytest

from app.ai.llm.prompts import (
    MAX_SRT_CHARS,
    build_render_plan_prompt,
    build_segment_prompt,
)


_SAMPLE_SRT = (
    "1\n00:00:10,000 --> 00:00:13,000\nThis is the hook.\n"
    "\n2\n00:00:42,000 --> 00:00:55,000\nThis is the payoff.\n"
)


def _extract_json_example(user_prompt: str) -> dict:
    """Pull the JSON example block out of the rendered user prompt.

    The prompt embeds one concrete JSON literal inside the
    `━━━ OUTPUT JSON SHAPE ━━━` section. After .format() substitution
    every literal { and } is unescaped, so a non-greedy braces grab
    works. We use the outermost { ... } block in that section.
    """
    marker = "━━━ OUTPUT JSON SHAPE ━━━"
    idx = user_prompt.find(marker)
    assert idx >= 0, "user prompt missing the JSON SHAPE marker"
    body = user_prompt[idx:]
    # Match the first balanced top-level object after the marker.
    # The outer { is the FIRST '{' that appears after the marker.
    open_idx = body.find("{")
    assert open_idx >= 0
    depth = 0
    end_idx = -1
    for i in range(open_idx, len(body)):
        ch = body[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break
    assert end_idx >= 0
    raw = body[open_idx : end_idx + 1]
    return json.loads(raw)


# ── Format safety (pre-flight regression guard) ──────────────────────────


class TestFormatSafety:
    def test_default_render_returns_two_strings(self):
        system, user = build_render_plan_prompt(
            _SAMPLE_SRT,
            output_count=3,
            min_sec=15,
            max_sec=60,
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert system and user

    def test_format_does_not_raise_on_curly_braces_in_editorial_hint(self):
        """If editorial_hint carries literal { ... } from a creator's
        notes (Sprint 3 has a pin for this on the dataclass), the
        downstream .format() chain MUST NOT KeyError on them. The
        hint is fed verbatim into the {editorial_section} placeholder
        which becomes a literal substring."""
        system, user = build_render_plan_prompt(
            _SAMPLE_SRT,
            output_count=3,
            min_sec=15,
            max_sec=60,
            editorial_hint="Channel: K1 {brand_x} | Brief: {start} {end} stay literal",
        )
        assert "{brand_x}" in user
        assert "{start}" in user and "{end}" in user

    def test_no_unsubstituted_named_placeholders_remain(self):
        """The named placeholders the template uses
        ({language}, {output_count}, {min_sec}, {max_sec},
        {srt_content}, {example_end}, {editorial_section}) must ALL
        be substituted by the time the function returns. A surviving
        literal would mean we forgot to escape something or
        misspelled a substitution kwarg."""
        system, user = build_render_plan_prompt(
            _SAMPLE_SRT,
            output_count=3,
            min_sec=15,
            max_sec=60,
            language="vi",
        )
        for placeholder in (
            "{language}",
            "{output_count}",
            "{min_sec}",
            "{max_sec}",
            "{srt_content}",
            "{example_end}",
            "{editorial_section}",
        ):
            assert placeholder not in user, f"left-over placeholder {placeholder} in user prompt"


# ── Placeholder substitution ─────────────────────────────────────────────


class TestSubstitution:
    def test_language_substituted(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60, language="vi-VN",
        )
        assert "vi-VN" in user

    def test_output_count_substituted(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=7, min_sec=15, max_sec=60,
        )
        # output_count appears at least twice: once near the top, once
        # in the closing instruction. We just confirm presence.
        assert "7" in user

    def test_min_max_substituted_as_integers(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=20.0, max_sec=45.0,
        )
        # Floats are cast to int() to keep the prompt readable.
        assert "20" in user and "45" in user
        # Float artefacts like "20.0" should NOT appear.
        assert "20.0" not in user.split("━━━")[2]  # first numeric section

    def test_srt_content_present(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60,
        )
        # The SRT is converted to seconds-format before substitution —
        # the spoken text survives verbatim.
        assert "This is the hook." in user
        assert "This is the payoff." in user

    def test_example_end_inside_clip_duration_bounds(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=20, max_sec=50,
        )
        example = _extract_json_example(user)
        # The JSON example's clip must satisfy (end - start) in [min, max].
        first = example["clips"][0]
        duration = float(first["end"]) - float(first["start"])
        assert 20 <= duration <= 50

    def test_editorial_section_when_hint_set(self):
        system, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60,
            editorial_hint="Bias toward suspense",
        )
        assert "Bias toward suspense" in system
        assert "EDITORIAL GUIDANCE" in user
        assert "Bias toward suspense" in user

    def test_no_editorial_section_when_hint_empty(self):
        system, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60, editorial_hint="",
        )
        assert "EDITORIAL GUIDANCE" not in user
        # System prompt is the bare baseline.
        assert not system.endswith(" ")


# ── JSON example shape parity with parser ────────────────────────────────


class TestExampleJsonShape:
    def test_example_is_valid_json(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60,
        )
        example = _extract_json_example(user)
        assert isinstance(example, dict)

    def test_example_carries_all_native_renderplan_keys(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60,
        )
        example = _extract_json_example(user)
        required = {
            "clips", "subtitle_policy", "camera_strategy", "audio_plan", "overlays",
        }
        assert required.issubset(example.keys()), (
            f"missing keys: {required - set(example.keys())}"
        )

    def test_example_parses_through_parse_render_plan_response(self):
        """End-to-end pin: the JSON the prompt SHOWS the AI as a
        target shape must itself be acceptable to the parser the
        AI's answer will land in. This is the single strongest
        regression guard against prompt/parser drift."""
        from app.ai.llm.parser import parse_render_plan_response
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60,
        )
        example = _extract_json_example(user)
        raw = json.dumps(example)
        plan = parse_render_plan_response(
            raw,
            output_count=3,
            min_sec=15,
            max_sec=60,
            video_duration=120.0,
        )
        assert plan is not None
        assert len(plan.clips) == 1
        # Sub-plans should round-trip the example values.
        assert plan.subtitle_policy.style == "viral"
        assert plan.camera_strategy.reframe_mode == "center"
        assert plan.audio_plan.voice_enabled is False
        assert plan.overlays == []


# ── SRT truncation ───────────────────────────────────────────────────────


class TestSrtTruncation:
    def test_default_cap_applies(self):
        large_srt = _SAMPLE_SRT + ("a" * (MAX_SRT_CHARS + 100))
        _, user = build_render_plan_prompt(
            large_srt, output_count=3, min_sec=15, max_sec=60,
        )
        assert "[transcript truncated]" in user

    def test_max_srt_chars_override(self):
        srt = "x" * 500
        _, user = build_render_plan_prompt(
            srt, output_count=3, min_sec=15, max_sec=60, max_srt_chars=100,
        )
        assert "[transcript truncated]" in user

    def test_no_truncation_when_under_cap(self):
        _, user = build_render_plan_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60, max_srt_chars=10_000,
        )
        assert "[transcript truncated]" not in user


# ── Legacy build_segment_prompt unchanged ────────────────────────────────


class TestLegacyPromptUntouched:
    def test_build_segment_prompt_still_renders(self):
        """Sprint 4.B is additive — the legacy entry point must
        continue to return the byte-shaped output it used to. We
        just sanity-check it produces two non-empty strings without
        raising."""
        system, user = build_segment_prompt(
            _SAMPLE_SRT, output_count=3, min_sec=15, max_sec=60,
        )
        assert isinstance(system, str) and isinstance(user, str)
        assert system and user
        # The legacy prompt says "segments", not "clips".
        assert "segments" in user
