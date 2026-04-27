"""
QA: Market-aware subtitle line breaking — test_market_subtitle_linebreak.py

Covers the 5 spec test cases without modifying any production code.
Run with: python -m pytest tests/test_market_subtitle_linebreak.py -v
Or standalone: python tests/test_market_subtitle_linebreak.py
"""
import sys
import os
import tempfile
import textwrap
from pathlib import Path

# Allow running from repo root or tests/ dir
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub heavy optional deps so subtitle_engine can import without GPU/model setup
import types
for _mod in ("whisper", "torch", "torchvision", "torchaudio"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

from app.services.market_subtitle_policy import (
    get_market_subtitle_policy,
    break_text_by_words,
)
from app.services.subtitle_engine import (
    apply_market_line_break_to_srt,
    _parse_srt_blocks,
    format_srt_timestamp,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

SAMPLE_SRT = textwrap.dedent("""\
    1
    00:00:00,000 --> 00:00:02,500
    This is the first subtitle block with several words in it

    2
    00:00:02,600 --> 00:00:05,000
    Here comes a second block that also has quite a few words

    3
    00:00:05,100 --> 00:00:07,800
    And a third one with punctuation, like commas and periods.

    4
    00:00:07,900 --> 00:00:10,000
    Short block.

""")

RESULTS = []


def _write_tmp_srt(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".srt")
    os.close(fd)
    Path(path).write_text(content, encoding="utf-8")
    return path


def _collect_lines_per_block(srt_path: str) -> list[list[str]]:
    """Return list of text lines per block (split on \\n)."""
    content = Path(srt_path).read_text(encoding="utf-8")
    result = []
    for block in content.split("\n\n"):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        text_lines = lines[2:]  # everything after index and timestamp
        result.append(text_lines)
    return result


def _collect_all_words(srt_path: str) -> list[str]:
    blocks = _parse_srt_blocks(srt_path)
    words = []
    for b in blocks:
        words.extend(b["text"].split())
    return words


def _original_words() -> list[str]:
    path = _write_tmp_srt(SAMPLE_SRT)
    words = _collect_all_words(path)
    os.unlink(path)
    return words


ORIGINAL_WORDS = _original_words()


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((name, status, detail))
    marker = "+" if passed else "x"
    print(f"  {marker} [{status}] {name}" + (f" — {detail}" if detail else ""))


# -----------------------------------------------------------------------------
# Case 1 — No market (baseline)
# -----------------------------------------------------------------------------

def test_case1_no_market():
    print("\n-- Case 1: No market_viral (baseline) --")
    path = _write_tmp_srt(SAMPLE_SRT)
    original_content = Path(path).read_text(encoding="utf-8")

    # Simulate: _mv_cfg is empty / falsy
    result_path = apply_market_line_break_to_srt(path, {})
    after_content = Path(path).read_text(encoding="utf-8")

    record("Returns original path unchanged", result_path == path)
    record("File content not modified", original_content == after_content,
           "content was altered" if original_content != after_content else "")

    result_path2 = apply_market_line_break_to_srt(path, None)
    record("Returns path for None payload", result_path2 == path)

    os.unlink(path)


# -----------------------------------------------------------------------------
# Case 2 — US market, clean tone → max 4 words/line
# -----------------------------------------------------------------------------

def test_case2_us_clean():
    print("\n-- Case 2: US / clean (max 4 words/line) --")
    policy = get_market_subtitle_policy("US", "clean")
    max_w = policy["max_words_per_line"]
    record("Policy max_words_per_line == 4", max_w == 4, f"got {max_w}")

    path = _write_tmp_srt(SAMPLE_SRT)
    apply_market_line_break_to_srt(path, {"target_market": "US", "subtitle_tone": "clean"})

    lines_per_block = _collect_lines_per_block(path)
    all_over = [
        (bi, line, len(line.split()))
        for bi, block in enumerate(lines_per_block)
        for line in block
        if len(line.split()) > max_w
    ]
    record("No line exceeds max_words_per_line", len(all_over) == 0,
           f"{len(all_over)} violations: {all_over[:3]}" if all_over else "")

    after_words = _collect_all_words(path)
    record("No words lost", sorted(after_words) == sorted(ORIGINAL_WORDS),
           f"before={len(ORIGINAL_WORDS)} after={len(after_words)}")

    # Spot-check punctuation: period/comma should survive
    raw = Path(path).read_text(encoding="utf-8")
    record("Punctuation preserved (comma)", "," in raw)
    record("Punctuation preserved (period)", "." in raw)

    os.unlink(path)


# -----------------------------------------------------------------------------
# Case 3 — EU market, clean tone → max 6 words/line
# -----------------------------------------------------------------------------

def test_case3_eu_clean():
    print("\n-- Case 3: EU / clean (max 6 words/line) --")
    policy = get_market_subtitle_policy("EU", "clean")
    max_w = policy["max_words_per_line"]
    record("Policy max_words_per_line == 6", max_w == 6, f"got {max_w}")

    path = _write_tmp_srt(SAMPLE_SRT)
    apply_market_line_break_to_srt(path, {"target_market": "EU", "subtitle_tone": "clean"})

    lines_per_block = _collect_lines_per_block(path)
    all_over = [
        (bi, line, len(line.split()))
        for bi, block in enumerate(lines_per_block)
        for line in block
        if len(line.split()) > max_w
    ]
    record("No line exceeds max_words_per_line", len(all_over) == 0,
           f"{len(all_over)} violations: {all_over[:3]}" if all_over else "")

    after_words = _collect_all_words(path)
    record("No words lost", sorted(after_words) == sorted(ORIGINAL_WORDS),
           f"before={len(ORIGINAL_WORDS)} after={len(after_words)}")

    # EU should produce fewer line breaks than US (longer lines)
    eu_line_count = sum(len(b) for b in lines_per_block)
    path2 = _write_tmp_srt(SAMPLE_SRT)
    apply_market_line_break_to_srt(path2, {"target_market": "US", "subtitle_tone": "clean"})
    us_line_count = sum(len(b) for b in _collect_lines_per_block(path2))
    record("EU produces fewer or equal lines than US", eu_line_count <= us_line_count,
           f"EU={eu_line_count} US={us_line_count}")
    os.unlink(path2)

    os.unlink(path)


# -----------------------------------------------------------------------------
# Case 4 — JP market, clean tone → max 2 words/line
# -----------------------------------------------------------------------------

def test_case4_jp_clean():
    print("\n-- Case 4: JP / clean (max 2 words/line) --")
    policy = get_market_subtitle_policy("JP", "clean")
    max_w = policy["max_words_per_line"]
    record("Policy max_words_per_line == 2", max_w == 2, f"got {max_w}")

    path = _write_tmp_srt(SAMPLE_SRT)
    apply_market_line_break_to_srt(path, {"target_market": "JP", "subtitle_tone": "clean"})

    lines_per_block = _collect_lines_per_block(path)
    all_over = [
        (bi, line, len(line.split()))
        for bi, block in enumerate(lines_per_block)
        for line in block
        if len(line.split()) > max_w
    ]
    record("No line exceeds 2 words", len(all_over) == 0,
           f"{len(all_over)} violations: {all_over[:3]}" if all_over else "")

    after_words = _collect_all_words(path)
    record("No words lost", sorted(after_words) == sorted(ORIGINAL_WORDS),
           f"before={len(ORIGINAL_WORDS)} after={len(after_words)}")

    # JP should produce more lines than EU
    jp_line_count = sum(len(b) for b in lines_per_block)
    path_eu = _write_tmp_srt(SAMPLE_SRT)
    apply_market_line_break_to_srt(path_eu, {"target_market": "EU", "subtitle_tone": "clean"})
    eu_line_count = sum(len(b) for b in _collect_lines_per_block(path_eu))
    record("JP produces more lines than EU (shorter)", jp_line_count >= eu_line_count,
           f"JP={jp_line_count} EU={eu_line_count}")
    os.unlink(path_eu)

    os.unlink(path)


# -----------------------------------------------------------------------------
# Case 5 — Error safety
# -----------------------------------------------------------------------------

def test_case5_error_safety():
    print("\n-- Case 5: Error safety --")

    # 5a — empty file
    path_empty = _write_tmp_srt("")
    try:
        result = apply_market_line_break_to_srt(
            path_empty, {"target_market": "US", "subtitle_tone": "clean"}
        )
        record("Empty file: no crash", True)
        record("Empty file: returns path", result == path_empty)
    except Exception as exc:
        record("Empty file: no crash", False, str(exc))
    os.unlink(path_empty)

    # 5b — garbage / invalid SRT
    path_garbage = _write_tmp_srt("this is not valid srt content at all!!! ###\n\nrandom text here")
    original = Path(path_garbage).read_text(encoding="utf-8")
    try:
        result = apply_market_line_break_to_srt(
            path_garbage, {"target_market": "US", "subtitle_tone": "clean"}
        )
        after = Path(path_garbage).read_text(encoding="utf-8")
        record("Invalid SRT: no crash", True)
        record("Invalid SRT: returns path", result == path_garbage)
        record("Invalid SRT: file untouched (no parseable blocks)", original == after,
               "file was modified unexpectedly" if original != after else "")
    except Exception as exc:
        record("Invalid SRT: no crash", False, str(exc))
    os.unlink(path_garbage)

    # 5c — file does not exist
    fake_path = "/tmp/nonexistent_subtitle_qa_test.srt"
    try:
        result = apply_market_line_break_to_srt(
            fake_path, {"target_market": "US", "subtitle_tone": "clean"}
        )
        record("Non-existent file: no crash", True)
        record("Non-existent file: returns path", result == fake_path)
    except Exception as exc:
        record("Non-existent file: no crash", False, str(exc))

    # 5d — malformed timestamps (partial SRT)
    partial_srt = "1\n00:00:00,000 --> \nsome text\n\n"
    path_partial = _write_tmp_srt(partial_srt)
    original_partial = Path(path_partial).read_text(encoding="utf-8")
    try:
        result = apply_market_line_break_to_srt(
            path_partial, {"target_market": "JP", "subtitle_tone": "clean"}
        )
        record("Malformed timestamp: no crash", True)
    except Exception as exc:
        record("Malformed timestamp: no crash", False, str(exc))
    os.unlink(path_partial)


# -----------------------------------------------------------------------------
# Bonus — Idempotency (apply twice = same result as once)
# -----------------------------------------------------------------------------

def test_bonus_idempotency():
    print("\n-- Bonus: Idempotency --")
    path = _write_tmp_srt(SAMPLE_SRT)
    payload = {"target_market": "US", "subtitle_tone": "clean"}
    apply_market_line_break_to_srt(path, payload)
    after_once = Path(path).read_text(encoding="utf-8")
    apply_market_line_break_to_srt(path, payload)
    after_twice = Path(path).read_text(encoding="utf-8")
    record("Applying twice produces same result as once", after_once == after_twice,
           "double-application altered content" if after_once != after_twice else "")
    os.unlink(path)


# -----------------------------------------------------------------------------
# Bonus — Timing & order preserved
# -----------------------------------------------------------------------------

def test_bonus_timing_and_order():
    print("\n-- Bonus: Timing & block order preserved --")
    path = _write_tmp_srt(SAMPLE_SRT)
    original_blocks = _parse_srt_blocks(path)

    apply_market_line_break_to_srt(path, {"target_market": "JP", "subtitle_tone": "bold"})
    after_blocks = _parse_srt_blocks(path)

    record("Block count unchanged",
           len(original_blocks) == len(after_blocks),
           f"before={len(original_blocks)} after={len(after_blocks)}")

    timing_ok = all(
        abs(o["start"] - a["start"]) < 0.001 and abs(o["end"] - a["end"]) < 0.001
        for o, a in zip(original_blocks, after_blocks)
    )
    record("All timestamps identical (< 1ms drift)", timing_ok)

    order_ok = all(
        sorted(o["text"].split()) == sorted(a["text"].split())
        for o, a in zip(original_blocks, after_blocks)
    )
    record("Word sets identical per block (no cross-block mixing)", order_ok)

    os.unlink(path)


# -----------------------------------------------------------------------------
# Bonus — break_text_by_words unit coverage
# -----------------------------------------------------------------------------

def test_bonus_break_text_edge_cases():
    print("\n-- Bonus: break_text_by_words edge cases --")

    record("Empty string returns empty", break_text_by_words("", 4) == "")
    record("None-ish input returns original", break_text_by_words(None, 4) == "")
    record("max_words=0 returns original", break_text_by_words("hello world", 0) == "hello world")
    record("Exact fit (4 words, max=4) → 1 line",
           "\n" not in break_text_by_words("one two three four", 4))
    record("5 words max=4 → 2 lines",
           break_text_by_words("one two three four five", 4) == "one two three four\nfive")
    record("Single word max=1 → each word on own line",
           break_text_by_words("a b c", 1) == "a\nb\nc")
    record("Preserves punctuation in token",
           break_text_by_words("Hello, world. How are you?", 2) == "Hello, world.\nHow are\nyou?")


# -----------------------------------------------------------------------------
# Bonus — Policy fallbacks
# -----------------------------------------------------------------------------

def test_bonus_policy_fallbacks():
    print("\n-- Bonus: Policy fallbacks --")

    p = get_market_subtitle_policy("XX", "clean")   # unknown market
    record("Unknown market falls back to US", p["market"] == "US", f"got {p['market']}")

    p2 = get_market_subtitle_policy("US", "disco")  # unknown tone
    record("Unknown tone falls back to clean", p2["style_hint"] == "clean-punch", f"got {p2['style_hint']}")

    p3 = get_market_subtitle_policy("", "")
    record("Empty strings fall back gracefully", p3["market"] == "US")

    p4 = get_market_subtitle_policy(None, None)
    record("None inputs fall back gracefully", p4["market"] == "US")


# -----------------------------------------------------------------------------
# All tone variants
# -----------------------------------------------------------------------------

def test_bonus_all_tones():
    print("\n-- Bonus: All tone variants --")

    expected = {
        ("US", "clean"):   4,
        ("US", "bold"):    3,
        ("US", "karaoke"): 5,
        ("EU", "clean"):   6,
        ("EU", "bold"):    5,
        ("EU", "karaoke"): 8,
        ("JP", "clean"):   2,
        ("JP", "bold"):    3,
        ("JP", "karaoke"): 4,
    }
    for (market, tone), expected_max in expected.items():
        p = get_market_subtitle_policy(market, tone)
        actual = p["max_words_per_line"]
        record(f"{market}/{tone} → max_words={expected_max}", actual == expected_max,
               f"got {actual}")


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("QA: Market-aware subtitle line breaking")
    print("=" * 65)

    test_case1_no_market()
    test_case2_us_clean()
    test_case3_eu_clean()
    test_case4_jp_clean()
    test_case5_error_safety()
    test_bonus_idempotency()
    test_bonus_timing_and_order()
    test_bonus_break_text_edge_cases()
    test_bonus_policy_fallbacks()
    test_bonus_all_tones()

    print("\n" + "=" * 65)
    total  = len(RESULTS)
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = total - passed
    print(f"TOTAL: {total}  PASSED: {passed}  FAILED: {failed}")
    if failed:
        print("\nFAILED TESTS:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  x {name}" + (f" — {detail}" if detail else ""))
    print("=" * 65)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
