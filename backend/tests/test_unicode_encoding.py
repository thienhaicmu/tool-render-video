# -*- coding: utf-8 -*-
"""Regression tests for Unicode/encoding correctness across the render pipeline.

These tests verify that Vietnamese, CJK, Arabic, emoji, and smart-quote text
survives intact through every layer that reads or writes text: SRT round-trips,
ASS subtitle generation, JSON serialisation, and subprocess argument encoding.

Root cause summary (2026-06-08): 55 source files had mojibake in comments
(UTF-8 bytes re-read as CP1252), and subprocess.run(text=True) calls lacked
encoding="utf-8", risking CP1252 decode of ffmpeg/git stderr on Windows.
All 55 files and all subprocess call sites have been fixed.
"""
from __future__ import annotations

import ast
import json
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------

VIETNAMESE = "Nguyễn Hải nói: 'Xin chào Việt Nam'"
VIETNAMESE_DIACRITICS = "Tiếng Việt có dấu"
SMART_QUOTES = "“Hello” and ‘world’"
EM_DASH = "before—after"
EN_DASH = "2024–2025"
ELLIPSIS = "wait…"
RIGHT_ARROW = "input → output"
EMOJI = "\U0001f600\U0001f680\U0001f1fb\U0001f1f3"
CJK_CHINESE = "中文测试"
CJK_JAPANESE = "日本語テスト"
CJK_KOREAN = "한국어 테스트"
ARABIC = "مرحبا"

ALL_UNICODE_SAMPLES = [
    VIETNAMESE,
    VIETNAMESE_DIACRITICS,
    SMART_QUOTES,
    EM_DASH,
    EN_DASH,
    ELLIPSIS,
    RIGHT_ARROW,
    EMOJI,
    CJK_CHINESE,
    CJK_JAPANESE,
    CJK_KOREAN,
    ARABIC,
]

# Mojibake indicators: these sequences must NOT appear in any Python source file.
# They are the mojibake equivalents of common punctuation encoded as CP1252 reread as UTF-8.
MOJIBAKE_CLASS_A = [
    bytes([0xE2, 0x80, 0x94]).decode("cp1252"),   # em-dash mojibake
    bytes([0xE2, 0x80, 0x93]).decode("cp1252"),   # en-dash mojibake
    bytes([0xE2, 0x80, 0xA6]).decode("cp1252"),   # ellipsis mojibake
    bytes([0xE2, 0x86, 0x92]).decode("cp1252"),   # right-arrow mojibake
    bytes([0xE2, 0x80, 0x98]).decode("cp1252"),   # left-single-quote mojibake
    bytes([0xE2, 0x80, 0x99]).decode("cp1252"),   # right-single-quote mojibake
    bytes([0xE2, 0x80, 0x9C]).decode("cp1252"),   # left-double-quote mojibake
]

# CLASS-B mojibake: math/symbol characters affected by the UTF-8 -> CP1252 re-read bug.
MOJIBAKE_CLASS_B: list[str] = [
    bytes([0xE2, 0x89, 0x88]).decode("cp1252"),   # approx-equal sign U+2248 (approx=)
    bytes([0xE2, 0x89, 0xA4]).decode("cp1252"),   # less-or-equal sign U+2264 (<=)
    bytes([0xE2, 0x89, 0xA5]).decode("cp1252"),   # greater-or-equal sign U+2265 (>=)
    bytes([0xC3, 0x97]).decode("cp1252"),          # multiplication sign U+00D7 (x)
    bytes([0xE2, 0x86, 0x94]).decode("cp1252"),   # left-right arrow U+2194 (<->)
    bytes([0xC2, 0xA7]).decode("cp1252"),          # section sign U+00A7 (section)
]


def _write_srt(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _make_srt_content(text: str) -> str:
    return f"1\n00:00:01,000 --> 00:00:03,000\n{text}\n\n"


# ---------------------------------------------------------------------------
# SRT round-trip: Unicode must survive read -> write -> read
# ---------------------------------------------------------------------------

class TestSrtUnicodeRoundTrip:

    def test_vietnamese_survives_srt_roundtrip(self, tmp_path):
        from app.features.render.engine.subtitle.generator.srt import (
            parse_srt_blocks, write_srt_blocks,
        )
        srt_in = tmp_path / "in.srt"
        srt_out = tmp_path / "out.srt"
        srt_in.write_text(_make_srt_content(VIETNAMESE), encoding="utf-8")

        blocks = parse_srt_blocks(str(srt_in))
        assert blocks, "SRT parser returned no blocks"
        assert blocks[0]["text"] == VIETNAMESE, f"Expected {VIETNAMESE!r}, got {blocks[0]['text']!r}"

        write_srt_blocks(blocks, str(srt_out))
        blocks2 = parse_srt_blocks(str(srt_out))
        assert blocks2[0]["text"] == VIETNAMESE

    def test_emoji_survives_srt_roundtrip(self, tmp_path):
        from app.features.render.engine.subtitle.generator.srt import (
            parse_srt_blocks, write_srt_blocks,
        )
        srt_in = tmp_path / "in.srt"
        srt_out = tmp_path / "out.srt"
        srt_in.write_text(_make_srt_content(EMOJI), encoding="utf-8")

        blocks = parse_srt_blocks(str(srt_in))
        write_srt_blocks(blocks, str(srt_out))
        blocks2 = parse_srt_blocks(str(srt_out))
        assert blocks2[0]["text"] == EMOJI

    def test_smart_quotes_survive_srt_roundtrip(self, tmp_path):
        from app.features.render.engine.subtitle.generator.srt import (
            parse_srt_blocks, write_srt_blocks,
        )
        srt_in = tmp_path / "in.srt"
        srt_out = tmp_path / "out.srt"
        srt_in.write_text(_make_srt_content(SMART_QUOTES), encoding="utf-8")

        blocks = parse_srt_blocks(str(srt_in))
        write_srt_blocks(blocks, str(srt_out))
        raw = srt_out.read_text(encoding="utf-8")
        assert SMART_QUOTES in raw

    @pytest.mark.parametrize("sample", ALL_UNICODE_SAMPLES)
    def test_all_unicode_samples_survive_srt_roundtrip(self, tmp_path, sample):
        from app.features.render.engine.subtitle.generator.srt import (
            parse_srt_blocks, write_srt_blocks,
        )
        srt_in = tmp_path / "in.srt"
        srt_out = tmp_path / "out.srt"
        srt_in.write_text(_make_srt_content(sample), encoding="utf-8")

        blocks = parse_srt_blocks(str(srt_in))
        assert blocks, f"No blocks parsed for sample: {sample!r}"
        write_srt_blocks(blocks, str(srt_out))
        out_text = srt_out.read_text(encoding="utf-8")
        assert sample in out_text, f"Sample lost after SRT round-trip: {sample!r}"

    def test_srt_file_written_as_utf8(self, tmp_path):
        from app.features.render.engine.subtitle.generator.srt import write_srt_blocks
        srt_out = tmp_path / "out.srt"
        blocks = [{"start": 1.0, "end": 3.0, "text": VIETNAMESE}]
        write_srt_blocks(blocks, str(srt_out))
        raw_bytes = srt_out.read_bytes()
        decoded = raw_bytes.decode("utf-8")
        assert VIETNAMESE in decoded

    def test_slice_srt_to_text_preserves_unicode(self, tmp_path):
        from app.features.render.engine.subtitle.generator.srt import slice_srt_to_text
        srt_path = tmp_path / "in.srt"
        srt_path.write_text(_make_srt_content(VIETNAMESE), encoding="utf-8")
        result = slice_srt_to_text(str(srt_path), 0.0, 5.0)
        assert VIETNAMESE in result


# ---------------------------------------------------------------------------
# JSON serialisation: ensure_ascii=False preserves Unicode
# ---------------------------------------------------------------------------

class TestJsonUnicodePreservation:

    def test_json_dumps_vietnamese_without_escaping(self):
        data = {"text": VIETNAMESE, "lang": "vi"}
        serialised = json.dumps(data, ensure_ascii=False)
        assert VIETNAMESE in serialised
        assert "\\u" not in serialised

    def test_json_dumps_emoji_without_escaping(self):
        data = {"emoji": EMOJI}
        serialised = json.dumps(data, ensure_ascii=False)
        assert EMOJI in serialised

    def test_render_plan_to_json_preserves_unicode(self):
        from app.domain.render_plan import RenderPlan, ClipPlan
        plan = RenderPlan(
            clips=[ClipPlan(title=VIETNAMESE, reason=SMART_QUOTES)],
        )
        blob = plan.to_json()
        parsed = json.loads(blob)
        assert parsed["clips"][0]["title"] == VIETNAMESE
        assert parsed["clips"][0]["reason"] == SMART_QUOTES

    def test_render_plan_from_json_preserves_unicode(self):
        from app.domain.render_plan import RenderPlan, ClipPlan
        original = RenderPlan(
            clips=[ClipPlan(title=VIETNAMESE, reason=CJK_CHINESE)],
        )
        blob = original.to_json()
        restored = RenderPlan.from_json(blob)
        assert restored.clips[0].title == VIETNAMESE
        assert restored.clips[0].reason == CJK_CHINESE

    def test_json_roundtrip_all_unicode_samples(self):
        for sample in ALL_UNICODE_SAMPLES:
            data = {"text": sample}
            blob = json.dumps(data, ensure_ascii=False)
            parsed = json.loads(blob)
            assert parsed["text"] == sample, f"JSON round-trip lost: {sample!r}"

    def test_creator_context_to_json_preserves_unicode(self):
        from app.domain.creator_context import CreatorContext
        ctx = CreatorContext(channel_name=VIETNAMESE, notes=CJK_JAPANESE)
        blob = ctx.to_json()
        parsed = json.loads(blob)
        assert parsed.get("channel_name") == VIETNAMESE
        assert parsed.get("notes") == CJK_JAPANESE


# ---------------------------------------------------------------------------
# Source file encoding: no mojibake in Python source files
# ---------------------------------------------------------------------------

class TestSourceFileMojibake:

    def _iter_python_files(self) -> list[Path]:
        backend_dir = Path(__file__).resolve().parents[1] / "app"
        return list(backend_dir.rglob("*.py"))

    def test_no_mojibake_class_a_in_source_files(self):
        """Verify no CLASS-A mojibake sequences in any .py source file under app/."""
        found: list[tuple[Path, str, int]] = []
        for py_file in self._iter_python_files():
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pytest.fail(f"Non-UTF-8 file detected: {py_file}")
            for pattern in MOJIBAKE_CLASS_A:
                for lineno, line in enumerate(content.splitlines(), start=1):
                    if pattern in line:
                        found.append((py_file, pattern, lineno))

        if found:
            details = "\n".join(
                f"  {f.relative_to(Path(__file__).resolve().parents[1])}:{ln} -- {pat!r}"
                for f, pat, ln in found[:20]
            )
            pytest.fail(
                f"Mojibake (CLASS A) found in {len(found)} location(s):\n{details}"
            )

    def test_no_mojibake_class_b_in_source_files(self):
        """Verify no CLASS-B mojibake sequences (math/symbol) in any .py source file under app/."""
        found: list[tuple[Path, str, int]] = []
        for py_file in self._iter_python_files():
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pytest.fail(f"Non-UTF-8 file detected: {py_file}")
            for pattern in MOJIBAKE_CLASS_B:
                for lineno, line in enumerate(content.splitlines(), start=1):
                    if pattern in line:
                        found.append((py_file, pattern, lineno))

        if found:
            details = "\n".join(
                f"  {f.relative_to(Path(__file__).resolve().parents[1])}:{ln} -- {pat!r}"
                for f, pat, ln in found[:20]
            )
            pytest.fail(
                f"Mojibake (CLASS B) found in {len(found)} location(s):\n{details}"
            )

    def test_all_source_files_are_utf8(self):
        """Every .py file under app/ must be decodable as UTF-8."""
        non_utf8: list[Path] = []
        for py_file in self._iter_python_files():
            try:
                py_file.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                non_utf8.append(py_file)
        if non_utf8:
            names = "\n  ".join(str(p) for p in non_utf8[:10])
            pytest.fail(f"Non-UTF-8 Python source files detected:\n  {names}")


# ---------------------------------------------------------------------------
# subprocess encoding: text=True calls must include encoding="utf-8"
# ---------------------------------------------------------------------------

class TestSubprocessEncoding:
    """Parse source files with AST to detect subprocess.run/Popen(text=True) calls
    that are missing encoding='utf-8', which on Windows defaults to CP1252."""

    _SUBPROCESS_CALLS = {"run", "Popen", "check_output", "check_call"}
    _IGNORELIST = {
        # subprocess calls legitimately handled by the platform (e.g. tests)
    }

    def _collect_violations(self) -> list[tuple[Path, int]]:
        backend_dir = Path(__file__).resolve().parents[1] / "app"
        violations: list[tuple[Path, int]] = []
        for py_file in backend_dir.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except (UnicodeDecodeError, SyntaxError):
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                func_name = None
                if isinstance(func, ast.Attribute):
                    func_name = func.attr
                elif isinstance(func, ast.Name):
                    func_name = func.id
                if func_name not in self._SUBPROCESS_CALLS:
                    continue

                kw_names = {kw.arg for kw in node.keywords}
                if "text" not in kw_names:
                    continue

                # text=True is present; encoding= must also be present.
                if "encoding" not in kw_names:
                    violations.append((py_file, node.lineno))

        return violations

    def test_subprocess_text_mode_always_has_encoding(self):
        violations = self._collect_violations()
        if violations:
            details = "\n".join(
                f"  {f.relative_to(Path(__file__).resolve().parents[1])}:{ln}"
                for f, ln in violations[:30]
            )
            pytest.fail(
                f"subprocess text=True without encoding='utf-8' found in {len(violations)} location(s):\n{details}"
            )


# ---------------------------------------------------------------------------
# SRT timestamp: ASCII-only, no Unicode corruption
# ---------------------------------------------------------------------------

class TestSrtTimestampFormat:

    def test_format_srt_timestamp_is_ascii(self):
        from app.features.render.engine.subtitle.generator.srt import format_srt_timestamp
        ts = format_srt_timestamp(3661.5)
        assert ts.isascii(), f"Timestamp contains non-ASCII: {ts!r}"
        assert ts == "01:01:01,500"

    def test_parse_srt_timestamp_roundtrip(self):
        from app.features.render.engine.subtitle.generator.srt import (
            format_srt_timestamp, parse_srt_timestamp,
        )
        for seconds in [0.0, 1.5, 90.123, 3661.0, 7322.999]:
            ts = format_srt_timestamp(seconds)
            parsed = parse_srt_timestamp(ts)
            assert abs(parsed - seconds) < 0.002, f"Roundtrip lost precision at {seconds}s: {ts!r} -> {parsed}"


# ---------------------------------------------------------------------------
# ASS escape: Unicode text must pass through without corruption
# ---------------------------------------------------------------------------

class TestAssEscapeUnicode:

    def test_ass_escape_preserves_vietnamese(self):
        from app.features.render.engine.subtitle.generator.ass import _ass_escape_text
        result = _ass_escape_text(VIETNAMESE)
        assert result == VIETNAMESE

    def test_ass_escape_preserves_emoji(self):
        from app.features.render.engine.subtitle.generator.ass import _ass_escape_text
        result = _ass_escape_text(EMOJI)
        assert result == EMOJI

    @pytest.mark.parametrize("sample", ALL_UNICODE_SAMPLES)
    def test_ass_escape_preserves_all_unicode_samples(self, sample):
        from app.features.render.engine.subtitle.generator.ass import _ass_escape_text
        result = _ass_escape_text(sample)
        assert result == sample, f"_ass_escape_text corrupted: {sample!r} -> {result!r}"
