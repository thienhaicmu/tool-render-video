"""
P1 · BE-A — multi-line dialogue beats (Beat.lines[]).

A beat = one shot (khung hình) that may hold several spoken lines, each with its own
speaker/emotion. Additive + backward-safe: a beat with no `lines` behaves exactly as
before (its legacy narration/speaker_id = one implicit line).
"""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, Beat, Line, CharacterDef, Visual, SettingDef


def _plan(beat):
    return StoryPlan(
        language="vi",
        characters=[CharacterDef(id="a"), CharacterDef(id="b")],
        settings=[SettingDef(id="s1")],
        visuals=[Visual(id="v1", setting_id="s1")],
        timeline=[beat],
    )


def test_effective_lines_multiline():
    b = Beat(id="b1", visual_id="v1", lines=[
        Line("", "Ngày xưa..."), Line("a", "Ta là A", "angry"), Line("b", "Còn ta B", "sad")])
    lines = b.effective_lines()
    assert [ln.speaker_id for ln in lines] == ["", "a", "b"]
    assert lines[1].emotion == "angry"


def test_effective_lines_legacy_fallback():
    # No `lines` → the legacy narration/speaker_id is the single implicit line.
    b = Beat(id="b1", visual_id="v1", narration="Xin chào", speaker_id="a", emotion="happy")
    lines = b.effective_lines()
    assert len(lines) == 1 and lines[0].text == "Xin chào"
    assert lines[0].speaker_id == "a" and lines[0].emotion == "happy"


def test_effective_lines_drops_blank_and_silent_hold():
    assert Beat(id="b1", visual_id="v1", lines=[Line("a", "  "), Line("b", "hi")]).effective_lines() \
        == [Line("b", "hi")]
    assert Beat(id="b1", visual_id="v1", hold_sec=2.0).effective_lines() == []   # silent hold


def test_primary_speaker():
    assert Beat(lines=[Line("", "narr"), Line("a", "hi")]).primary_speaker() == "a"
    assert Beat(narration="x", speaker_id="b").primary_speaker() == "b"
    assert Beat(narration="x").primary_speaker() == ""              # narrator


def test_json_round_trip_preserves_lines():
    b = Beat(id="b1", visual_id="v1", lines=[Line("a", "Alpha", "angry", "point"), Line("b", "Beta")])
    p2 = StoryPlan.from_json(_plan(b).to_json())
    got = p2.timeline[0].lines
    assert len(got) == 2 and got[0].text == "Alpha" and got[0].pose == "point"


def test_parses_lines_from_ai_json():
    p = StoryPlan.from_json(
        '{"visuals":[{"id":"v1"}],"characters":[{"id":"a"}],'
        '"timeline":[{"id":"b1","visual_id":"v1","lines":['
        '{"speaker_id":"","text":"Mở đầu"},{"speaker_id":"a","text":"Thoại","emotion":"happy"}]}]}'
    )
    assert p is not None
    assert [ln.text for ln in p.timeline[0].effective_lines()] == ["Mở đầu", "Thoại"]


def test_validate_refs_scrubs_unknown_line_speaker():
    b = Beat(id="b1", visual_id="v1", lines=[Line("a", "ok"), Line("ghost", "bad", "boom")])
    p = _plan(b)
    p.validate_refs()
    ln = p.timeline[0].lines
    assert ln[0].speaker_id == "a"          # known → kept
    assert ln[1].speaker_id == ""           # unknown → narrator
    assert ln[1].emotion == "normal"        # invalid emotion coerced


def test_est_sec_sums_lines():
    short = _plan(Beat(id="b1", visual_id="v1", lines=[Line("a", "x" * 15)]))
    long = _plan(Beat(id="b1", visual_id="v1", lines=[Line("a", "x" * 15), Line("b", "y" * 15)]))
    assert long.beat_est_sec(long.timeline[0]) > short.beat_est_sec(short.timeline[0])


def test_derive_char_anchor_uses_primary_line_speaker():
    # Beat-level speaker_id empty, but a line has speaker "a" → overlay must anchor.
    b = Beat(id="b1", visual_id="v1", lines=[Line("", "narr"), Line("a", "hi")])
    p = _plan(b)
    p.derive_beat_styling()
    assert p.timeline[0].char_anchor != "none"


# ── BE-B: STORY_MULTILINE_BEATS toggles schema + prompt (default off) ─────────

def test_strict_schema_multiline_toggle(monkeypatch):
    from app.features.render.ai.llm.story_schema_v2 import build_story_plan_schema
    # OFF (default) → single-line beat (narration on the beat, no lines).
    beat = build_story_plan_schema()["properties"]["timeline"]["items"]["properties"]
    assert "lines" not in beat and "narration" in beat
    # ON → beat holds a lines[] array; who-says-what moves into each line.
    monkeypatch.setenv("STORY_MULTILINE_BEATS", "1")
    beat = build_story_plan_schema()["properties"]["timeline"]["items"]["properties"]
    assert "lines" in beat and "narration" not in beat and "speaker_id" not in beat
    line = beat["lines"]["items"]["properties"]
    assert set(line) == {"speaker_id", "text", "emotion", "pose"}
    # strict-mode invariant still holds (every property required, both objects).
    obj = build_story_plan_schema()["properties"]["timeline"]["items"]
    assert set(obj["required"]) == set(obj["properties"].keys())


def test_prose_prompt_multiline_toggle(monkeypatch):
    from app.features.render.ai.llm.story_prompts_v2 import build_super_idea_prompt
    _, off = build_super_idea_prompt("x", duration_sec=60, language="vi")
    assert '"lines"' not in off and "narration" in off
    monkeypatch.setenv("STORY_MULTILINE_BEATS", "1")
    _, on = build_super_idea_prompt("x", duration_sec=60, language="vi")
    assert '"lines"' in on and "spoken turns" in on          # dialogue guidance present
