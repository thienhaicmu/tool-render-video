import re


_UNSAFE = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_MULTI_SPACE = re.compile(r' {2,}')
_MULTI_DASH = re.compile(r'-{2,}')


def sanitize_filename(text: str, max_len: int = 120) -> str:
    text = str(text or "video").strip()
    text = _UNSAFE.sub("-", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_DASH.sub("-", text)
    text = text.strip("- ")
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] or text[:max_len]
    return text.strip("- ") or "video"


def build_output_filename(info: dict) -> str:
    title = sanitize_filename(info.get("title") or "video")
    height = int(info.get("height") or 0)
    fps = round(float(info.get("fps") or 0))
    ext = str(info.get("ext") or "mp4").lstrip(".")

    quality = f"{height}p" if height else "best"
    if fps > 30:
        quality += f"{fps}fps"

    return f"{title}_{quality}.{ext}"


def resolve_unique_path(output_dir, filename: str):
    from pathlib import Path
    p = Path(output_dir) / filename
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    idx = 2
    while True:
        candidate = Path(output_dir) / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1
