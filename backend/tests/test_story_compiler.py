"""
GĐ1 Story Compiler — 3-call pipeline (Understanding → Writer → Structure).

Pins:
  * prompt builders: writer format contract + style pack + facts block; structure
    prompt embeds the script verbatim + the pinned character table.
  * story_understanding: quote-verification (verified / unverified / tail / order),
    script validators (speakers / missing majors / spoken length).
  * domain: pace/pause LABELS map onto reading_speed/pause_after only when the
    numeric field is absent.
  * director orchestration: compiler path (writer+structure calls), targeted script
    repair, idea length-loop on len(script), fallback to legacy when the writer
    fails or STORY_COMPILER=0, and P2 (base video) staying legacy.
"""
from __future__ import annotations

import json

import pytest

from app.features.render.ai.llm.story_director_v2 import _split_source_chunks, run_super_plan
from app.features.render.ai.llm.story_prompts_v2 import (
    build_understanding_prompt, build_writer_adapt_prompt, build_writer_idea_prompt,
    build_writer_repair_prompt, build_structure_prompt,
)
from app.features.render.ai.llm.story_understanding import (
    parse_understanding, validate_understanding, understanding_block,
    validate_script, script_spoken_chars,
)

_CHAPTER = (
    "Đêm khuya, Hàn Phong ngồi trong Vân Tiêu Các. Ba năm bị phế võ công, hôm nay hắn quyết phá cảnh. "
    "Một luồng nhiệt từ đan điền xông thẳng lên. Ngoài cửa, Tuyết Nhi khẽ gọi sư huynh. "
    "Cuối cùng, Hàn Phong bước ra khỏi đại điện, ánh mắt lạnh như băng nhìn về phía môn phái cũ."
)

_UND_JSON = json.dumps({
    "topic": "Hàn Phong phá cảnh", "genre": "wuxia", "tone": "hào hùng",
    "characters": [
        {"id": "han_phong", "name": "Hàn Phong", "role": "protagonist", "gender": "male", "desc": "kiếm khách trẻ"},
        {"id": "tuyet_nhi", "name": "Tuyết Nhi", "role": "support", "gender": "female", "desc": ""},
    ],
    "locations": [{"id": "van_tieu_cac", "name": "Vân Tiêu Các", "desc": ""}],
    "relationships": [{"a": "tuyet_nhi", "b": "han_phong", "type": "sư muội"}],
    "goals_conflicts": ["Hàn Phong muốn báo thù môn phái"],
    "events": [
        {"id": "e1", "summary": "Hàn Phong quyết phá cảnh sau ba năm bị phế",
         "characters": ["han_phong"], "location": "van_tieu_cac", "time": "đêm",
         "quote": "Ba năm bị phế võ công, hôm nay hắn quyết phá cảnh", "importance": "major"},
        {"id": "e2", "summary": "Tuyết Nhi gọi ngoài cửa",
         "characters": ["tuyet_nhi"], "location": "van_tieu_cac", "time": "",
         "quote": "Ngoài cửa, Tuyết Nhi khẽ gọi sư huynh", "importance": "minor"},
        {"id": "e3", "summary": "Hàn Phong bước ra đại điện nhìn về môn phái cũ",
         "characters": ["han_phong"], "location": "", "time": "",
         "quote": "ánh mắt lạnh như băng nhìn về phía môn phái cũ", "importance": "major"},
    ],
}, ensure_ascii=False)

_SCRIPT = (
    "[SCENE: van_tieu_cac]\n"
    "NARR: Đêm ấy, Hàn Phong ngồi giữa Vân Tiêu Các. Ba năm bị phế võ công, đêm nay hắn quyết phá cảnh.\n"
    'Tuyết Nhi (surprised): "Sư huynh, người đã thành công rồi sao?"\n'
    "NARR: Hắn không đáp. Cuối cùng Hàn Phong bước ra đại điện, ánh mắt lạnh như băng nhìn về phía môn phái cũ.\n"
)

_PLAN_JSON = json.dumps({
    "topic": "Hàn Phong phá cảnh", "language": "vi",
    "characters": [{"id": "han_phong", "name": "Hàn Phong"}, {"id": "tuyet_nhi", "name": "Tuyết Nhi"}],
    "settings": [{"id": "van_tieu_cac", "name": "Vân Tiêu Các"}],
    "visuals": [{"id": "v1", "setting_id": "van_tieu_cac", "character_ids": ["han_phong"]}],
    "timeline": [
        {"id": "b1", "visual_id": "v1", "narration": "Đêm ấy, Hàn Phong quyết phá cảnh.",
         "pace": "slow", "pause": "long"},
        {"id": "b2", "visual_id": "v1", "narration": "Hắn bước ra đại điện.", "speaker_id": "han_phong"},
    ],
}, ensure_ascii=False)


# ── Prompt builders ───────────────────────────────────────────────────────────

def test_understanding_prompt_shape():
    sysm, user = build_understanding_prompt(_CHAPTER, "vi")
    assert "literary analyst" in sysm and "VERBATIM" in sysm
    assert "SOURCE ORDER" in user and '"events"' in user and _CHAPTER[:40] in user


def test_writer_adapt_prompt_has_contract_and_style():
    sysm, user = build_writer_adapt_prompt(_CHAPTER, "vi", "kiem-hiep", "FACTS", "")
    assert "audio-drama storyteller" in sysm and "NEVER the events" in sysm
    assert "[SCENE:" in user and "NARR:" in user            # format contract
    assert "wuxia address forms" in user                     # style pack resolved
    assert "STORY FACTS" in user and "BANNED clich" in user  # facts + craft rules


def test_writer_idea_prompt_budget_and_default_style():
    _, user = build_writer_idea_prompt("một ý tưởng", duration_sec=120, language="vi")
    assert "SHORT IS A FAILURE" in user                      # length is the task definition
    assert "1800" in user or "3240" in user                  # char budget (120s × cps × factor)
    assert "MIDPOINT" in user and "[SCENE:" in user


def test_writer_repair_prompt_lists_missing():
    _, user = build_writer_repair_prompt(_SCRIPT, ["Hàn Phong bước ra đại điện"], "vi")
    assert "MISSING EVENTS" in user and "Hàn Phong bước ra đại điện" in user
    assert "CURRENT SCRIPT" in user and "[SCENE: van_tieu_cac]" in user


def test_structure_prompt_pins_ids_and_script(monkeypatch):
    monkeypatch.delenv("STORY_MULTILINE_BEATS", raising=False)
    monkeypatch.delenv("STORY_COMPILER", raising=False)      # compiler default ON
    chars = [{"id": "han_phong", "name": "Hàn Phong", "gender": "male", "desc": "kiếm khách"}]
    sysm, user = build_structure_prompt(_SCRIPT, "vi", characters=chars, genre="wuxia")
    assert "NEVER rewrite" in sysm
    assert "CHARACTER TABLE" in user and "han_phong" in user
    assert "APPROVED SCRIPT" in user and "Tuyết Nhi (surprised)" in user
    assert '"lines"' in user                                  # multiline schema active
    assert '"pace"' in user and '"pause"' in user             # pacing labels asked


def test_structure_prompt_legacy_gate(monkeypatch):
    monkeypatch.delenv("STORY_MULTILINE_BEATS", raising=False)
    monkeypatch.setenv("STORY_COMPILER", "0")
    _, user = build_structure_prompt(_SCRIPT, "vi")
    assert '"pace"' not in user                               # byte-safe legacy schema


# ── Understanding parse + verification ────────────────────────────────────────

def test_parse_and_validate_understanding():
    u = parse_understanding(_UND_JSON)
    assert u is not None and len(u.characters) == 2 and len(u.events) == 3
    rep = validate_understanding(u, _CHAPTER)
    assert rep["total"] == 3 and rep["verified"] == 3
    assert rep["majors_verified"] == 2 and rep["tail_covered"] and rep["order_ok"]
    blk = understanding_block(u)
    assert "[MAJOR]" in blk and "Hàn Phong" in blk and "EVENTS" in blk


def test_validate_understanding_flags_fabricated_quote():
    u = parse_understanding(_UND_JSON)
    u.events[0].quote = "câu này hoàn toàn không có trong chương truyện gốc nhé"
    rep = validate_understanding(u, _CHAPTER)
    assert rep["verified"] == 2 and any("unverified" in w for w in rep["warnings"])


# ── Script validators ─────────────────────────────────────────────────────────

def test_validate_script_ok_and_spoken_chars():
    u = parse_understanding(_UND_JSON)
    validate_understanding(u, _CHAPTER)
    rep = validate_script(_SCRIPT, u, language="vi")
    assert rep["ok"] and not rep["missing_events"] and not rep["unknown_speakers"]
    assert rep["spoken_chars"] > 100
    assert script_spoken_chars("[SCENE: x]\nNARR: abc def") == len("abc def")


def test_validate_script_detects_missing_major_and_unknown_speaker():
    u = parse_understanding(_UND_JSON)
    validate_understanding(u, _CHAPTER)
    bad = '[SCENE: a]\nNARR: Một đoạn khác hẳn.\nNgười Lạ (angry): "Ta là ai?"\n'
    rep = validate_script(bad, u, language="vi")
    assert rep["ok"] is False and len(rep["missing_events"]) >= 1
    assert rep["unknown_speakers"]


# ── Domain pacing labels ──────────────────────────────────────────────────────

def test_pace_pause_labels_map_to_numeric():
    from app.domain.story_plan_v2 import StoryPlan
    p = StoryPlan.from_json(_PLAN_JSON)
    assert p is not None
    b1, b2 = p.timeline[0], p.timeline[1]
    assert b1.reading_speed == pytest.approx(0.88) and b1.pause_after == pytest.approx(1.6)
    assert b2.reading_speed == 1.0 and b2.pause_after == 0.0      # defaults
    # explicit numbers always win over labels
    raw = json.loads(_PLAN_JSON)
    raw["timeline"][0]["reading_speed"] = 1.3
    raw["timeline"][0]["pause_after"] = 0.2
    p2 = StoryPlan.from_json(json.dumps(raw, ensure_ascii=False))
    assert p2.timeline[0].reading_speed == pytest.approx(1.3)
    assert p2.timeline[0].pause_after == pytest.approx(0.2)


# ── Director orchestration ────────────────────────────────────────────────────

def _covered_plan_json() -> str:
    """A Structure response that actually preserves the approved Writer script."""
    raw = json.loads(_PLAN_JSON)
    raw["timeline"][0]["narration"] = _SCRIPT
    raw["timeline"][0]["hook"] = True
    return json.dumps(raw, ensure_ascii=False)


def _fns():
    """(calls, call_fn, writer_fn, json_fn) — happy-path fakes with call logging."""
    calls = []

    def call_fn(sysm, usr):
        calls.append(("structure", sysm, usr))
        return _covered_plan_json()

    def writer_fn(sysm, usr):
        calls.append(("writer", sysm, usr))
        return _SCRIPT

    def json_fn(sysm, usr):
        calls.append(("understand", sysm, usr))
        return _UND_JSON

    return calls, call_fn, writer_fn, json_fn


def test_compiler_paste_runs_three_calls(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    calls, call_fn, writer_fn, json_fn = _fns()
    plan = run_super_plan(call_fn=call_fn, source="paste", chapter=_CHAPTER, language="vi",
                          writer_call_fn=writer_fn, json_call_fn=json_fn)
    assert plan is not None and plan.beat_count() == 2
    kinds = [c[0] for c in calls]
    assert kinds == ["understand", "writer", "structure"]
    # the structure call received the SCRIPT, not the raw chapter
    assert "[SCENE: van_tieu_cac]" in calls[-1][2]


def test_compiler_idea_skips_understanding(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "0")
    calls, call_fn, writer_fn, json_fn = _fns()
    plan = run_super_plan(call_fn=call_fn, source="idea", idea="ý tưởng", duration_sec=0,
                          language="vi", writer_call_fn=writer_fn, json_call_fn=json_fn)
    assert plan is not None
    assert [c[0] for c in calls] == ["writer", "structure"]


def test_compiler_fallback_when_writer_fails(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    seen = []

    def call_fn(sysm, usr):
        seen.append(sysm)
        return _PLAN_JSON

    plan = run_super_plan(call_fn=call_fn, source="paste", chapter="truyện " * 40,
                          language="vi", writer_call_fn=lambda s, u: None, json_call_fn=None)
    assert plan is not None
    # legacy single-pass prompt was used (P1 adapt role)
    assert any("adapting an EXISTING written story" in s for s in seen)


def test_compiler_disabled_env_uses_legacy(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "0")
    calls, call_fn, writer_fn, json_fn = _fns()
    plan = run_super_plan(call_fn=call_fn, source="paste", chapter="truyện " * 40,
                          language="vi", writer_call_fn=writer_fn, json_call_fn=json_fn)
    assert plan is not None
    assert all(k == "structure" for k, *_ in calls)          # only the legacy plan call ran


def test_compiler_base_video_stays_legacy(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    calls, call_fn, writer_fn, json_fn = _fns()
    plan = run_super_plan(call_fn=call_fn, source="paste", chapter="truyện " * 40,
                          language="vi", has_base_video=True, base_video_dur=60,
                          writer_call_fn=writer_fn, json_call_fn=json_fn)
    assert plan is not None
    assert [c[0] for c in calls] == ["structure"]            # P2 path, no writer call
    assert "BACKGROUND VIDEO" in calls[0][1]


def test_compiler_script_repair_round(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    monkeypatch.setenv("STORY_SCRIPT_REPAIR", "1")
    calls = []
    bad_script = '[SCENE: a]\nNARR: chỉ nói về Tuyết Nhi ngoài cửa khẽ gọi.\n'

    def writer_fn(sysm, usr):
        calls.append(("writer", sysm))
        if "MISSING EVENTS" in usr:
            calls.append(("repair", sysm))
            return _SCRIPT                                   # repaired script covers majors
        return bad_script

    def call_fn(sysm, usr):
        calls.append(("structure", sysm))
        return _covered_plan_json()

    plan = run_super_plan(call_fn=call_fn, source="paste", chapter=_CHAPTER, language="vi",
                          writer_call_fn=writer_fn, json_call_fn=lambda s, u: _UND_JSON)
    assert plan is not None
    kinds = [k for k, *_ in calls]
    assert "repair" in kinds and kinds[-1] == "structure"


def test_estimate_cost_reports_calls(monkeypatch):
    from app.features.render.ai.llm.story_director_v2 import estimate_super_plan_cost
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    c3 = estimate_super_plan_cost(source_chars=10000, ceiling=10)
    assert c3["llm_calls"] == 3 and c3["cost_usd"] > 0
    c2 = estimate_super_plan_cost(source_chars=10000, ceiling=10, source="idea")
    assert c2["llm_calls"] == 2 and c2["input_tokens"] < c3["input_tokens"]
    monkeypatch.setenv("STORY_COMPILER", "0")
    c1 = estimate_super_plan_cost(source_chars=10000, ceiling=10)
    assert c1["llm_calls"] == 1 and c1["input_tokens"] < c3["input_tokens"]


def test_understanding_block_preserves_relationships_and_quotes():
    u = parse_understanding(_UND_JSON)
    validate_understanding(u, _CHAPTER)
    block = understanding_block(u)
    assert "RELATIONSHIPS" in block
    assert "source quote:" in block
    assert "TOPIC:" in block and "TONE:" in block


def test_compiler_trace_reports_physical_calls_and_selected_mode(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "0")
    calls, call_fn, writer_fn, json_fn = _fns()
    events = []
    plan = run_super_plan(
        call_fn=call_fn, source="idea", idea="idea", language="vi",
        writer_call_fn=writer_fn, json_call_fn=json_fn, observer=events.append,
    )
    assert plan is not None
    assert [e["stage"] for e in events if e["event"] == "call_started"] == ["writer", "structure"]
    assert any(e["event"] == "authoring_selected" and e["mode"] == "compiler" for e in events)


def test_compiler_rejects_structure_that_drops_script(monkeypatch):
    monkeypatch.delenv("STORY_COMPILER", raising=False)
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "0")
    calls = []

    def structure(sysm, user):
        calls.append("structure")
        return _PLAN_JSON

    events = []
    plan = run_super_plan(
        call_fn=structure, source="idea", idea="idea", language="vi",
        writer_call_fn=lambda s, u: _SCRIPT, json_call_fn=lambda s, u: _UND_JSON,
        observer=events.append,
    )
    assert plan is not None
    assert calls == ["structure", "structure"]
    assert any(e["event"] == "validation" and e.get("stage") == "structure"
               and not e.get("passed") for e in events)
    assert any(e["event"] == "compiler_fallback" for e in events)


def test_source_chunker_preserves_tail_without_oversized_parts():
    source = "first paragraph\n\n" + "x" * 120 + "\n\nlast ending"
    parts = _split_source_chunks(source, limit=80)
    assert len(parts) >= 2
    assert all(len(part) <= 80 for part in parts)
    assert "".join(parts).replace("\n", "") == source.replace("\n", "")
    assert parts[-1].endswith("last ending")
