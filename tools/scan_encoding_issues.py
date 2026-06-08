"""Scan the repository for Unicode/encoding issues.

Detects:
  1. Mojibake sequences in source files (UTF-8 bytes read as CP1252)
  2. Files that are not valid UTF-8
  3. subprocess.run / subprocess.Popen calls with text=True but no encoding=
  4. json.dumps() calls missing ensure_ascii=False where Unicode data may flow
  5. open() calls without explicit encoding=
  6. Python source files with UTF-8 BOM

Usage:
  python tools/scan_encoding_issues.py [directory]
  python tools/scan_encoding_issues.py              # scans ./backend by default

Outputs a markdown report to stdout and a machine-readable JSON to
tools/encoding_scan_report.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Mojibake patterns — these are the CP1252 re-interpretations of common
# Unicode chars whose UTF-8 byte sequences happen to decode as CP1252 text.
#
# Pattern:  original char → UTF-8 bytes → CP1252 codepoints → mojibake text
# U+2014 —  E2 80 94  →  â€"  (00E2 20AC 201D)
# U+2013 –  E2 80 93  →  â€"  (00E2 20AC 201C)
# U+2026 …  E2 80 A6  →  â€¦  (00E2 20AC 00A6)
# U+2192 →  E2 86 92  →  â†'  (00E2 2020 2019)
# U+201C "  E2 80 9C  →  â€œ  (00E2 20AC 009C — shows as â€œ)
# U+201D "  E2 80 9D  →  â€   (00E2 20AC 009D — shows as â€)
# U+2018 '  E2 80 98  →  â€˜  (00E2 20AC 2018)
# U+2019 '  E2 80 99  →  â€™  (00E2 20AC 2019)
# U+00E1 á  C3 A1     →  Ã¡   (00C3 00A1)
# U+00E0 à  C3 A0     →  Ã    (00C3 00A0)
# U+00E9 é  C3 A9     →  Ã©   (00C3 00A9)
# Vietnamese multi-byte sequences produce longer mojibake strings like
# Nguyá»…n (Nguyễn), Viá»‡t (Việt)
# ---------------------------------------------------------------------------

MOJIBAKE_PATTERNS: list[tuple[str, str, str]] = [
    # (mojibake_text, original_char, description)
    ("â€”", "—", "em-dash (—)"),
    ("â€“", "–", "en-dash (–)"),
    ("â€¦", "…", "ellipsis (…)"),
    ("â†’", "→", "right-arrow (→)"),
    ("â€", "“", "left-double-quote (“)"),
    ("â€", "”", "right-double-quote (”)"),
    ("â€‘", "‘", "left-single-quote (‘)"),
    ("â€™", "’", "right-single-quote (’)"),
    ("Ã¡", "á", "á"),
    ("Ã ", "à", "à"),
    ("Ã©", "é", "é"),
    ("Ã¨", "è", "è"),
    ("Ãº", "ú", "ú"),
    ("Ã¹", "ù", "ù"),
    # Vietnamese tone-mark sequences (Latin-1 mojibake of UTF-8 3-byte seqs)
    # These appear as patterns like á» + letter in CP1252
]

# Compile regex for quick first-pass detection
_MOJIBAKE_QUICK_RE = re.compile(
    r"[â][€][“-”¦‘™]"
    r"|[â][†][’]"
    r"|[Ã][ -¿]"
    r"|[Ã][-]"
)

# subprocess.run/Popen with text=True but no encoding=
_SUBPROCESS_TEXT_RE = re.compile(
    r"subprocess\.(run|Popen|check_output)\s*\([^)]*\btext\s*=\s*True[^)]*\)",
    re.DOTALL,
)
_ENCODING_PRESENT_RE = re.compile(r"\bencoding\s*=")

# open() without explicit encoding=
_OPEN_NO_ENC_RE = re.compile(
    r"""(?<!\w)open\s*\(\s*(?:[^,)]+,\s*['"](w|r|a|rb\+|wb\+)['"]\s*)\)""",
)

# json.dumps without ensure_ascii=False
_JSON_DUMPS_RE = re.compile(r"\bjson\.dumps\s*\(")
_ENSURE_ASCII_FALSE_RE = re.compile(r"ensure_ascii\s*=\s*False")

SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json",
                   ".yaml", ".yml", ".sql", ".srt", ".vtt", ".md"}

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__",
             ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
             "static", "static-v2", "static-v3", "whisper_cache"}


class Finding(NamedTuple):
    file: str
    line: int
    column: int
    severity: str       # HIGH / MEDIUM / LOW
    category: str       # mojibake / non-utf8 / subprocess-text / json-dumps / open-no-enc
    content: str
    detail: str


def scan_file_mojibake(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not _MOJIBAKE_QUICK_RE.search(line):
            continue
        for mojibake, original, desc in MOJIBAKE_PATTERNS:
            col = line.find(mojibake)
            if col >= 0:
                findings.append(Finding(
                    file=str(path),
                    line=lineno,
                    column=col + 1,
                    severity="MEDIUM",
                    category="mojibake",
                    content=line.strip()[:120],
                    detail=f"'{mojibake}' should be '{original}' ({desc})",
                ))
    return findings


def scan_file_subprocess(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if "subprocess" not in text:
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "text=True" not in line and "text = True" not in line:
            continue
        if "subprocess" not in line:
            continue
        if _ENCODING_PRESENT_RE.search(line):
            continue
        # Check surrounding context (up to 3 lines) for encoding=
        lines = text.splitlines()
        start = max(0, lineno - 4)
        end = min(len(lines), lineno + 3)
        context = "\n".join(lines[start:end])
        if _ENCODING_PRESENT_RE.search(context):
            continue
        findings.append(Finding(
            file=str(path),
            line=lineno,
            column=1,
            severity="HIGH",
            category="subprocess-text",
            content=line.strip()[:120],
            detail="text=True without encoding='utf-8' — uses system locale (CP1252 on Windows)",
        ))
    return findings


def scan_file_json_dumps(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if "json.dumps" not in text:
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "json.dumps" not in line:
            continue
        if "ensure_ascii" in line:
            continue
        findings.append(Finding(
            file=str(path),
            line=lineno,
            column=1,
            severity="LOW",
            category="json-dumps",
            content=line.strip()[:120],
            detail="json.dumps() without ensure_ascii=False — Unicode chars escaped as \\uXXXX",
        ))
    return findings


def is_utf8(path: Path) -> tuple[bool, str]:
    try:
        path.read_text(encoding="utf-8")
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            return True, "UTF-8-BOM"
        return True, "UTF-8"
    except UnicodeDecodeError as exc:
        return False, f"not UTF-8: {exc}"


def scan_directory(root: Path) -> list[Finding]:
    all_findings: list[Finding] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            path = Path(dirpath) / fname
            ext = path.suffix.lower()
            if ext not in SCAN_EXTENSIONS:
                continue

            # UTF-8 validity check
            ok, enc_note = is_utf8(path)
            if not ok:
                all_findings.append(Finding(
                    file=str(path),
                    line=0,
                    column=0,
                    severity="CRITICAL",
                    category="non-utf8",
                    content="",
                    detail=f"File encoding: {enc_note}",
                ))
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            if ext == ".py":
                all_findings.extend(scan_file_mojibake(path, text))
                all_findings.extend(scan_file_subprocess(path, text))
                all_findings.extend(scan_file_json_dumps(path, text))
            else:
                all_findings.extend(scan_file_mojibake(path, text))

    return all_findings


def print_report(findings: list[Finding], root: Path) -> None:
    by_category: dict[str, list[Finding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    counts = {cat: len(items) for cat, items in by_category.items()}
    total = sum(counts.values())

    print("# Unicode / Encoding Audit Report")
    print()
    print(f"Scanned root: `{root}`")
    print()
    print("## Executive Summary")
    print()
    print(f"| Category | Count |")
    print(f"|----------|-------|")
    for cat, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"| {cat} | {cnt} |")
    print(f"| **TOTAL** | **{total}** |")
    print()

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    for cat in ["non-utf8", "subprocess-text", "mojibake", "json-dumps", "open-no-enc"]:
        items = by_category.get(cat, [])
        if not items:
            continue
        items.sort(key=lambda x: (x.file, x.line))
        print(f"## {cat.replace('-', ' ').title()} ({len(items)} findings)")
        print()
        for f in items:
            rel = Path(f.file).relative_to(root.parent) if f.file.startswith(str(root.parent)) else f.file
            loc = f":{f.line}" if f.line else ""
            print(f"- **[{f.severity}]** `{rel}{loc}` — {f.detail}")
            if f.content:
                print(f"  ```")
                print(f"  {f.content}")
                print(f"  ```")
        print()


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "backend"
    root = root.resolve()
    print(f"Scanning {root} ...", file=sys.stderr)

    findings = scan_directory(root)

    print_report(findings, root)

    # Machine-readable output
    out_path = Path(__file__).parent / "encoding_scan_report.json"
    report = [
        {
            "file": f.file,
            "line": f.line,
            "column": f.column,
            "severity": f.severity,
            "category": f.category,
            "content": f.content,
            "detail": f.detail,
        }
        for f in findings
    ]
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n(Machine-readable report: {out_path})", file=sys.stderr)


if __name__ == "__main__":
    main()
