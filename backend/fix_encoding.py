"""Fix UTF-8 mojibake in Python source files.

100% ASCII source file: replacement strings are built with chr() so no editor
can re-encode them.  The mojibake was produced by reading UTF-8 bytes as
Windows-1252 and then re-saving as UTF-8.

Original char  UTF-8 bytes  cp1252 codepoints       mojibake sequence
  U+2026 ...   E2 80 A6     00E2  20AC  00A6         chr(0xe2)+chr(0x20ac)+chr(0xa6)
  U+2192 ->    E2 86 92     00E2  2020  2019         chr(0xe2)+chr(0x2020)+chr(0x2019)
  U+2014 --    E2 80 94     00E2  20AC  201D         chr(0xe2)+chr(0x20ac)+chr(0x201d)
  U+2500 box   E2 94 80     00E2  201D  20AC         chr(0xe2)+chr(0x201d)+chr(0x20ac)
  U+2013 -     E2 80 93     00E2  20AC  201C         chr(0xe2)+chr(0x20ac)+chr(0x201c)
"""
import pathlib

FILES = [
    "app/orchestration/pipeline_pre_render.py",
    "app/orchestration/render_pipeline.py",
]

REPLACEMENTS = [
    (chr(0xe2) + chr(0x20ac) + chr(0xa6),  chr(0x2026)),  # ... ellipsis
    (chr(0xe2) + chr(0x2020) + chr(0x2019), chr(0x2192)),  # -> right arrow
    (chr(0xe2) + chr(0x20ac) + chr(0x201d), chr(0x2014)),  # -- em dash
    (chr(0xe2) + chr(0x201d) + chr(0x20ac), chr(0x2500)),  # box light horizontal
    (chr(0xe2) + chr(0x20ac) + chr(0x201c), chr(0x2013)),  # -  en dash
]

base = pathlib.Path(__file__).parent

for rel_path in FILES:
    path = base / rel_path
    content = path.read_text(encoding="utf-8")
    original = content
    for bad, good in REPLACEMENTS:
        content = content.replace(bad, good)
    if content != original:
        path.write_text(content, encoding="utf-8")
        print(f"Fixed: {rel_path}")
    else:
        print(f"No change: {rel_path}")
