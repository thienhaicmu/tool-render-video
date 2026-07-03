"""
provider_stock.py — Stock-image Visual Generator provider (CS-G, online, opt-in).

Given a scene's ``visual_prompt`` (used as the search query), searches a stock
photo API (Pexels first, then Pixabay) and downloads the best match to the visual
cache, returning it as an ``image`` asset the render composites (with Ken Burns).

Opt-in + graceful: needs PEXELS_API_KEY and/or PIXABAY_API_KEY. With no key, no
network, or no result it returns None → the seam falls back to the local
provider. Never raises (Sacred Contract #3 spirit). Stdlib urllib only — no new
dependency. Results are cached by (prompt, size) so a query is fetched once.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Optional

from app.features.render.engine.visual import (
    SceneVisualAsset, SceneVisualRequest, cache_key, download_to, visual_cache_dir,
)

logger = logging.getLogger("app.render.visual.stock")

_TIMEOUT = int(os.getenv("CONTENT_STOCK_TIMEOUT", "20"))


def _pexels_search(query: str, key: str, w: int, h: int) -> str:
    orient = "portrait" if h >= w else "landscape"
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": query, "per_page": 3, "orientation": orient}
    )
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "AIVideoStudio/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        data = json.loads(r.read())
    photos = data.get("photos") or []
    if not photos:
        return ""
    src = photos[0].get("src") or {}
    return src.get("large2x") or src.get("large") or src.get("original") or ""


def _pixabay_search(query: str, key: str, w: int, h: int) -> str:
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode({
        "key": key, "q": query, "per_page": 3, "image_type": "photo",
        "orientation": "vertical" if h >= w else "horizontal",
    })
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:  # noqa: S310
        data = json.loads(r.read())
    hits = data.get("hits") or []
    if not hits:
        return ""
    return hits[0].get("largeImageURL") or hits[0].get("webformatURL") or ""


def resolve_stock(request: SceneVisualRequest) -> Optional[SceneVisualAsset]:
    """Search + download a stock image for the scene. None on no key / no
    network / no result (→ local fallback). Never raises."""
    try:
        query = (getattr(request, "prompt", "") or "").strip()
        if not query:
            return None
        pexels = (os.getenv("PEXELS_API_KEY") or "").strip()
        pixabay = (os.getenv("PIXABAY_API_KEY") or "").strip()
        if not pexels and not pixabay:
            logger.info("visual.stock: no PEXELS_API_KEY/PIXABAY_API_KEY set — skipping")
            return None

        w, h = int(request.width), int(request.height)
        cached = visual_cache_dir() / f"{cache_key('stock', query, w, h)}.jpg"
        if cached.exists() and cached.stat().st_size > 0:
            return SceneVisualAsset(kind="image", value=str(cached), provider="stock")

        img_url = ""
        if pexels:
            try:
                img_url = _pexels_search(query, pexels, w, h)
            except Exception as e:
                logger.info("visual.stock: pexels search failed: %s", e)
        if not img_url and pixabay:
            try:
                img_url = _pixabay_search(query, pixabay, w, h)
            except Exception as e:
                logger.info("visual.stock: pixabay search failed: %s", e)
        if not img_url:
            return None
        if not download_to(img_url, str(cached), timeout=_TIMEOUT):
            return None
        return SceneVisualAsset(kind="image", value=str(cached), provider="stock")
    except Exception as exc:
        logger.info("visual.stock: error %s", exc)
        return None
