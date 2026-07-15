"""
tag_geeme_pack.py — AI-vision tagging pass for the GEE! ME character library.

The 100 imported characters are numbered files with generic tags, so the Story
AI's library-pick can't tell "nam tóc đen hoodie" from "nữ tóc hồng váy". This
script sends each PNG (downscaled) ONCE through an OpenAI vision model and writes
the result into the asset's sidecar:

    name    — short display name ("young man in red hoodie")
    tags    — lowercase keywords (gender, age, hair, clothing+colors, props, vibe)

then re-indexes the library. Idempotent: already-tagged sidecars (marked with
"vision_tagged": true) are skipped — re-run resumes/repairs failures only.
Cost: ~100 × gpt-4o-mini vision ≈ well under $0.10 total.

Run from backend/:  python scripts/tag_geeme_pack.py [--force]
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.core.config  # noqa: E402,F401  (loads the root .env)
from app.core.config import ASSET_LIBRARY_DIR  # noqa: E402

MODEL = os.getenv("GEEME_TAG_MODEL", "gpt-4o-mini")
DIR = Path(ASSET_LIBRARY_DIR) / "character" / "us" / "hiendai"
WORKERS = 6

_PROMPT = (
    "This is one flat-vector cartoon character on a transparent background. Return ONLY a JSON "
    'object: {"name": "<max 8 words, e.g. young man in red hoodie with guitar>", '
    '"gender": "male|female", "age": "child|adult|elder", '
    '"tags": "<12-20 lowercase space-separated keywords: gender, age, hair color+style, '
    "facial hair/glasses if any, clothing items with colors, shoes, held props/objects, "
    'overall vibe (casual/office/sporty/artist/medical/etc)>"}. No prose, no markdown.'
)


def _b64_small(p: Path, side: int = 192) -> str:
    from PIL import Image
    im = Image.open(p).convert("RGBA")
    im.thumbnail((side, side))
    bg = Image.new("RGB", im.size, (245, 245, 245))
    bg.paste(im, mask=im)
    buf = io.BytesIO()
    bg.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _tag_one(client, png: Path) -> "tuple[str, dict | None, str]":
    try:
        b64 = _b64_small(png)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
            ]}],
            max_tokens=220, temperature=0.2,
            response_format={"type": "json_object"},
            timeout=60,
        )
        data = json.loads(resp.choices[0].message.content)
        name = str(data.get("name") or "").strip()
        tags = str(data.get("tags") or "").strip().lower()
        gender = str(data.get("gender") or "").strip().lower()
        age = str(data.get("age") or "").strip().lower()
        if not (name and tags):
            return png.name, None, "empty fields"
        extra = " ".join(x for x in (gender, age) if x)
        return png.name, {"name": name, "tags": f"geeme {extra} {tags}".strip()}, ""
    except Exception as exc:
        return png.name, None, str(exc)[:120]


def main() -> int:
    force = "--force" in sys.argv
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        print("OPENAI_API_KEY not set (.env)")
        return 1
    try:
        import openai
    except ImportError:
        print("openai SDK not installed")
        return 1
    client = openai.OpenAI(api_key=key)

    todo = []
    for png in sorted(DIR.glob("geeme_*.png")):
        sc = png.with_suffix(".png.json")
        side = {}
        if sc.exists():
            try:
                side = json.loads(sc.read_text(encoding="utf-8"))
            except Exception:
                side = {}
        if side.get("vision_tagged") and not force:
            continue
        todo.append((png, sc, side))
    print(f"tagging {len(todo)} character(s) with {MODEL} ...")
    ok, failed = 0, []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_tag_one, client, png): (png, sc, side) for png, sc, side in todo}
        for f in as_completed(futs):
            png, sc, side = futs[f]
            name, data, err = f.result()
            if data is None:
                failed.append(f"{name}: {err}")
                continue
            side.update(data)
            side["vision_tagged"] = True
            side.setdefault("transparent", True)
            sc.write_text(json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
            ok += 1
            if ok % 20 == 0:
                print(f"  {ok}/{len(todo)}")
    print(f"tagged {ok}/{len(todo)}" + (f" — failed: {failed[:5]}" if failed else ""))

    from app.db.story_asset_repo import scan_library, list_assets
    print("re-index:", scan_library())
    sample = [a for a in list_assets(kind="character", q="geeme", limit=500)][:5]
    for a in sample:
        print(f"  {a['slug']}: {a['name']}  |  {a['tags'][:90]}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
