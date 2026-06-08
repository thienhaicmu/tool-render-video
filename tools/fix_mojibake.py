"""Auto-fix mojibake in source files.

Covers two classes of corruption:

CLASS A — 3-byte Unicode char saved as UTF-8, then re-read as CP1252 and
          re-saved as UTF-8.  Examples:
            â€"  (should be —  U+2014)
            â€"  (should be –  U+2013)
            â†'  (should be →  U+2192)

CLASS B — 2-byte Vietnamese / Latin-extended char (U+00C0–U+00FF) saved as
          UTF-8, re-read as Latin-1, re-saved as UTF-8.  The result is a 4-byte
          sequence starting with Ã that encodes the original Latin-1 byte.
          These appear in docstrings with Vietnamese text.

Strategy
--------
The replacements are assembled using chr() so this file is 100% ASCII and can
never itself be corrupted by a future encoding round-trip.

For CLASS A the mapping is derived from:
  original_char.encode("utf-8")  →  decode each byte as CP1252  →  mojibake str
For CLASS B the fix is:
  mojibake_str.encode("latin-1").decode("utf-8")

Usage
-----
  python tools/fix_mojibake.py [path ...]   # fix specific files
  python tools/fix_mojibake.py              # scan+fix backend/ directory

Options:
  --dry-run    Show what would change without writing files
  --report     Write tools/fix_mojibake_report.md

The script creates a .bak backup of every file it modifies.
"""
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# CLASS A replacements — built entirely from chr() so this file stays ASCII.
# Each entry: (mojibake_string, correct_unicode_char)
# ---------------------------------------------------------------------------
_CLASS_A: list[tuple[str, str]] = [
    # U+2014 EM DASH —  →  UTF-8: E2 80 94  →  CP1252: â€"
    (chr(0x00E2) + chr(0x20AC) + chr(0x201D), chr(0x2014)),
    # U+2013 EN DASH –  →  UTF-8: E2 80 93  →  CP1252: â€"
    (chr(0x00E2) + chr(0x20AC) + chr(0x201C), chr(0x2013)),
    # U+2026 ELLIPSIS …  →  UTF-8: E2 80 A6  →  CP1252: â€¦
    (chr(0x00E2) + chr(0x20AC) + chr(0x00A6), chr(0x2026)),
    # U+2192 RIGHT ARROW →  UTF-8: E2 86 92  →  CP1252: â†'
    (chr(0x00E2) + chr(0x2020) + chr(0x2019), chr(0x2192)),
    # U+201C LEFT DOUBLE QUOTE "  →  UTF-8: E2 80 9C  →  CP1252: â€œ
    (chr(0x00E2) + chr(0x20AC) + chr(0x0153), chr(0x201C)),
    # U+201D RIGHT DOUBLE QUOTE "  →  UTF-8: E2 80 9D  →  CP1252: â€
    # (only the 2-char prefix â€ not followed by em-dash suffix)
    # handled below as a standalone 2-char sequence where safe
    # U+2018 LEFT SINGLE QUOTE '  →  UTF-8: E2 80 98  →  CP1252: â€˜
    (chr(0x00E2) + chr(0x20AC) + chr(0x02DC), chr(0x2018)),
    # U+2019 RIGHT SINGLE QUOTE '  →  UTF-8: E2 80 99  →  CP1252: â€™
    (chr(0x00E2) + chr(0x20AC) + chr(0x2122), chr(0x2019)),
    # U+2500 BOX LIGHT HORIZONTAL ─  →  UTF-8: E2 94 80  →  CP1252: â€"… wait
    # actually E2 94 80:  E2=â, 94=" (CP1252), 80=€  → â"€
    (chr(0x00E2) + chr(0x201D) + chr(0x20AC), chr(0x2500)),
    # U+00E1 á  UTF-8: C3 A1  →  CP1252: Ã¡
    (chr(0x00C3) + chr(0x00A1), chr(0x00E1)),
    # U+00E0 à  UTF-8: C3 A0  →  CP1252: Ã
    (chr(0x00C3) + chr(0x00A0), chr(0x00E0)),
    # U+00E9 é  UTF-8: C3 A9  →  CP1252: Ã©
    (chr(0x00C3) + chr(0x00A9), chr(0x00E9)),
    # U+00E8 è  UTF-8: C3 A8  →  CP1252: Ã¨
    (chr(0x00C3) + chr(0x00A8), chr(0x00E8)),
    # U+00FA ú  UTF-8: C3 BA  →  CP1252: Ãº
    (chr(0x00C3) + chr(0x00BA), chr(0x00FA)),
    # U+00F9 ù  UTF-8: C3 B9  →  CP1252: Ã¹
    (chr(0x00C3) + chr(0x00B9), chr(0x00F9)),
    # U+00F3 ó  UTF-8: C3 B3  →  CP1252: Ã³
    (chr(0x00C3) + chr(0x00B3), chr(0x00F3)),
    # U+00F2 ò  UTF-8: C3 B2  →  CP1252: Ã²
    (chr(0x00C3) + chr(0x00B2), chr(0x00F2)),
]

# Longer CLASS A entries that share a prefix with shorter ones must come first
# so we don't partially replace them.  Sort by descending length.
_CLASS_A.sort(key=lambda x: -len(x[0]))


def _fix_class_a(text: str) -> tuple[str, int]:
    """Apply CLASS A replacements. Returns (fixed_text, change_count)."""
    changes = 0
    for bad, good in _CLASS_A:
        if bad in text:
            count = text.count(bad)
            text = text.replace(bad, good)
            changes += count
    return text, changes


def _fix_class_b_line(line: str) -> str:
    """Attempt CLASS B fix on a single line via latin-1 round-trip.

    Only applied when the line contains 0xC3 (Ã) sequences AND the
    round-trip succeeds (no UnicodeDecodeError), which avoids corrupting
    lines that legitimately contain Ã.
    """
    if chr(0x00C3) not in line:
        return line
    try:
        candidate = line.encode("latin-1").decode("utf-8")
        # Sanity: result should be printable / no control chars
        if all(ord(c) >= 0x20 or c in "\t\n\r" for c in candidate):
            return candidate
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return line


def fix_file(path: Path, dry_run: bool = False, class_b: bool = False) -> dict:
    """Fix mojibake in a single file.

    Returns a result dict with keys: path, class_a_changes, class_b_changes,
    modified, backup.
    """
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"path": str(path), "error": "not UTF-8 — skipped"}

    text, class_a_changes = _fix_class_a(original)

    class_b_changes = 0
    if class_b:
        fixed_lines = []
        for line in text.splitlines(keepends=True):
            fixed_line = _fix_class_b_line(line)
            if fixed_line != line:
                class_b_changes += 1
            fixed_lines.append(fixed_line)
        text = "".join(fixed_lines)

    modified = text != original
    backup = None

    if modified and not dry_run:
        backup = str(path) + ".bak"
        shutil.copy2(path, backup)
        path.write_text(text, encoding="utf-8")

    return {
        "path": str(path),
        "class_a_changes": class_a_changes,
        "class_b_changes": class_b_changes,
        "modified": modified,
        "backup": backup,
    }


SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md",
                   ".yaml", ".yml", ".srt", ".vtt", ".txt"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__",
             ".mypy_cache", ".pytest_cache", "dist", "build",
             "static", "static-v2", "static-v3", "whisper_cache"}


def fix_directory(root: Path, dry_run: bool = False, class_b: bool = False) -> list[dict]:
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            path = Path(dirpath) / fname
            if path.suffix.lower() not in SCAN_EXTENSIONS:
                continue
            result = fix_file(path, dry_run=dry_run, class_b=class_b)
            if result.get("modified") or result.get("class_a_changes", 0) > 0:
                results.append(result)
    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Fix mojibake in source files")
    parser.add_argument("paths", nargs="*", help="Files or directories to fix")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--class-b", action="store_true",
                        help="Also apply CLASS B (Latin-1 round-trip) fix — use with caution")
    parser.add_argument("--report", action="store_true", help="Write markdown report")
    args = parser.parse_args()

    dry_run = args.dry_run
    class_b = args.class_b
    results: list[dict] = []

    if args.paths:
        for p in args.paths:
            path = Path(p).resolve()
            if path.is_file():
                results.append(fix_file(path, dry_run=dry_run, class_b=class_b))
            elif path.is_dir():
                results.extend(fix_directory(path, dry_run=dry_run, class_b=class_b))
    else:
        root = Path(__file__).parent.parent / "backend"
        results.extend(fix_directory(root.resolve(), dry_run=dry_run, class_b=class_b))

    # Summary
    modified = [r for r in results if r.get("modified")]
    errors = [r for r in results if "error" in r]

    action = "Would fix" if dry_run else "Fixed"
    print(f"{action} {len(modified)} file(s).")
    print()

    for r in modified:
        rel = r["path"]
        a = r.get("class_a_changes", 0)
        b = r.get("class_b_changes", 0)
        bak = f" (backup: {r['backup']})" if r.get("backup") else ""
        parts = []
        if a:
            parts.append(f"{a} CLASS-A")
        if b:
            parts.append(f"{b} CLASS-B")
        print(f"  {rel}: {', '.join(parts)} change(s){bak}")

    if errors:
        print(f"\n{len(errors)} file(s) skipped (not UTF-8):")
        for r in errors:
            print(f"  {r['path']}: {r['error']}")

    if args.report:
        report_path = Path(__file__).parent / "fix_mojibake_report.md"
        lines = ["# Mojibake Fix Report\n\n"]
        lines.append(f"Mode: {'dry-run' if dry_run else 'applied'}\n\n")
        lines.append(f"## Modified Files ({len(modified)})\n\n")
        for r in modified:
            lines.append(f"- `{r['path']}` — CLASS-A: {r.get('class_a_changes',0)}, CLASS-B: {r.get('class_b_changes',0)}\n")
        if errors:
            lines.append(f"\n## Skipped Files ({len(errors)})\n\n")
            for r in errors:
                lines.append(f"- `{r['path']}`: {r['error']}\n")
        report_path.write_text("".join(lines), encoding="utf-8")
        print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
