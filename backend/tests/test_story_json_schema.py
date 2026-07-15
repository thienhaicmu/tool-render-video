"""
F-05 — native OpenAI structured output (strict JSON Schema) for the Story super-plan.

  * build_story_plan_schema is a valid STRICT schema (additionalProperties=false +
    every key required on every object) derived from the domain enums, using only
    the OpenAI-supported keyword subset.
  * _call_openai_story_plan_once uses json_schema when enabled and auto-degrades to
    json_object on a schema error (so an unsupported model never fails the render).
"""
from __future__ import annotations

from app.features.render.ai.llm.story_schema_v2 import build_story_plan_schema
from app.features.render.ai.llm.providers import openai as oai

_UNSUPPORTED = {"minLength", "maxLength", "pattern", "minimum", "maximum",
                "minItems", "maxItems", "format", "default"}


def _walk_objects(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk_objects(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk_objects(v, fn)


def test_schema_is_strict_and_supported():
    s = build_story_plan_schema()

    def _check(o):
        assert not (set(o) & _UNSUPPORTED), f"unsupported keyword: {set(o) & _UNSUPPORTED}"
        if o.get("type") == "object":
            assert o.get("additionalProperties") is False
            # strict mode: every property must be listed in required.
            assert set(o.get("required", [])) == set(o.get("properties", {}).keys())

    _walk_objects(s, _check)


def test_schema_enums_derived_from_domain(monkeypatch):
    from app.domain.story_plan_v2 import FOCUS, EMOTION, POSE, BGM_MOODS
    # Hermetic: a dev .env may set STORY_MULTILINE_BEATS=1 (injected session-wide by
    # config.load_dotenv), whose lines[] branch removes emotion/pose from the beat.
    # GĐ1: UNSET multiline now follows the compiler (default ON) — pin the LEGACY
    # single-line lean beat via STORY_COMPILER=0 so this asserts that contract.
    monkeypatch.delenv("STORY_MULTILINE_BEATS", raising=False)
    monkeypatch.delenv("STORY_LEAN_CONTRACT", raising=False)
    monkeypatch.setenv("STORY_COMPILER", "0")
    # Default = LEAN contract (Phase 3): the model emits only the CREATIVE per-beat
    # fields; the mechanical style labels are derived by StoryPlan.derive_beat_styling.
    beat = build_story_plan_schema()["properties"]["timeline"]["items"]["properties"]
    assert beat["focus"]["enum"] == list(FOCUS)
    assert beat["emotion"]["enum"] == list(EMOTION)
    assert beat["pose"]["enum"] == list(POSE)
    # bgm_mood drops the "default" fallback folder (AI-facing vocab).
    assert "default" not in beat["bgm_mood"]["enum"]
    assert set(beat["bgm_mood"]["enum"]) == {m for m in BGM_MOODS if m != "default"}
    vis = build_story_plan_schema()["properties"]["visuals"]["items"]["properties"]
    chars = build_story_plan_schema()["properties"]["characters"]["items"]["properties"]
    # P-A (s11): dead image-gen fields are NOT exposed to the model (SVG-only).
    assert "prompt" not in vis and "tier" not in vis and "negative_prompt" not in vis
    assert "voice_style" not in chars
    # Pipeline-derived timing fields are never exposed either.
    assert "reading_speed" not in beat and "hold_sec" not in beat
    # Phase 3: the 9 mechanical style labels are NOT asked of the model under lean.
    for f in ("motion", "transition_in", "bgm_cue", "bgm_intensity", "source_audio",
              "char_anchor", "char_scale", "char_motion", "text_anchor"):
        assert f not in beat, f"lean contract must not expose {f!r}"


def test_lean_contract_toggle(monkeypatch):
    from app.domain.story_plan_v2 import MOTION
    # Multiline (dev .env) takes precedence over lean in build_story_plan_schema —
    # pin it off so LEAN=0 actually yields the full 19-field beat under test.
    # GĐ1: unset multiline follows the compiler → pin the legacy branch explicitly.
    monkeypatch.delenv("STORY_MULTILINE_BEATS", raising=False)
    monkeypatch.setenv("STORY_COMPILER", "0")
    # Kill-switch: STORY_LEAN_CONTRACT=0 restores the full 19-field beat (pre-Phase-3).
    monkeypatch.setenv("STORY_LEAN_CONTRACT", "0")
    beat = build_story_plan_schema()["properties"]["timeline"]["items"]["properties"]
    assert beat["motion"]["enum"] == list(MOTION)
    for f in ("bgm_cue", "char_anchor", "text_anchor", "source_audio"):
        assert f in beat
    # strict-mode invariant holds in both modes (every property required).
    obj = build_story_plan_schema()["properties"]["timeline"]["items"]
    assert set(obj["required"]) == set(obj["properties"].keys())


def test_once_uses_json_schema_when_enabled(monkeypatch):
    monkeypatch.setattr(oai, "_STORY_JSON_SCHEMA", True)
    seen = {"use_schema": None, "n": 0}

    def _fake_create(api_key, model, sysm, usr, use_schema):
        seen["use_schema"] = use_schema
        seen["n"] += 1
        return '{"ok": 1}'

    monkeypatch.setattr(oai, "_story_plan_create", _fake_create)
    out = oai._call_openai_story_plan_once("k", "gpt-4o", "s", "u")
    assert out == '{"ok": 1}'
    assert seen["use_schema"] is True and seen["n"] == 1


def test_once_degrades_to_json_object_on_schema_error(monkeypatch):
    monkeypatch.setattr(oai, "_STORY_JSON_SCHEMA", True)
    calls = []

    def _fake_create(api_key, model, sysm, usr, use_schema):
        calls.append(use_schema)
        if use_schema:
            raise RuntimeError("400 response_format.json_schema not supported")
        return '{"ok": 1}'

    monkeypatch.setattr(oai, "_story_plan_create", _fake_create)
    out = oai._call_openai_story_plan_once("k", "gpt-4o", "s", "u")
    assert out == '{"ok": 1}'
    assert calls == [True, False]        # schema attempt → degrade to json_object


def test_json_schema_kill_switch(monkeypatch):
    monkeypatch.setattr(oai, "_STORY_JSON_SCHEMA", False)
    calls = []
    monkeypatch.setattr(oai, "_story_plan_create",
                        lambda *a: (calls.append(a[-1]) or '{"ok": 1}'))
    oai._call_openai_story_plan_once("k", "gpt-4o", "s", "u")
    assert calls == [False]              # never attempts schema when disabled


def test_response_format_shapes():
    rf = oai._story_response_format(True)
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert oai._story_response_format(False) == {"type": "json_object"}
