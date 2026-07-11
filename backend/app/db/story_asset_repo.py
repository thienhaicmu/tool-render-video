"""
story_asset_repo.py — offline asset library index (AL0).

The user drops generated / downloaded images into
``ASSET_LIBRARY_DIR/{kind}/{region}/{genre}/{slug}.png`` (see
docs/asset_library_prompts.md). ``scan_library`` walks that tree and upserts one
``story_assets`` row per file (deriving kind/region/genre/slug from the path), so
Story Mode can offer a "library-first" picker instead of always calling AI image
gen. An optional ``{file}.json`` sidecar overrides name/tags/license/source/style
(used for CC0 downloads that must record attribution).

All access goes through ``db_conn`` (Sacred Contract #7). Every function is
defensive: logs + returns a safe default on any error (never crashes a request).
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.db.connection import db_conn

logger = logging.getLogger("app.db.story_asset")

_KINDS = ("character", "background", "object", "frame")
_IMG_EXTS = {".png", ".webp", ".jpg", ".jpeg"}

_FULL_COLS = ("id, kind, region, genre, slug, name, tags, style, path, "
              "transparent, license, source, created_at, updated_at")
_FULL_KEYS = ("id", "kind", "region", "genre", "slug", "name", "tags", "style", "path",
              "transparent", "license", "source", "created_at", "updated_at")


def _row(row: Any) -> dict:
    d = dict(zip(_FULL_KEYS, row)) if isinstance(row, tuple) else {k: row[k] for k in _FULL_KEYS}
    d["transparent"] = bool(d.get("transparent"))
    return d


def _asset_id(path: str) -> str:
    return hashlib.sha1(str(path).encode("utf-8", "ignore")).hexdigest()


def upsert_asset(
    *,
    path: str,
    kind: str = "character",
    region: str = "",
    genre: str = "",
    slug: str = "",
    name: str = "",
    tags: str = "",
    style: str = "",
    transparent: bool = False,
    license: str = "",
    source: str = "",
    asset_id: str = "",
) -> str:
    """Create or update one asset row (keyed by a stable hash of ``path``). Returns
    the asset id, or "" on error / empty path. Never raises."""
    if not (path or "").strip():
        return ""
    aid = (asset_id or "").strip() or _asset_id(path)
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO story_assets
                    (id, kind, region, genre, slug, name, tags, style, path,
                     transparent, license, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind, region=excluded.region, genre=excluded.genre,
                    slug=excluded.slug, name=excluded.name, tags=excluded.tags,
                    style=excluded.style, path=excluded.path,
                    transparent=excluded.transparent, license=excluded.license,
                    source=excluded.source,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (aid, kind, region, genre, slug, name, tags, style, path,
                 1 if transparent else 0, license, source),
            )
            conn.commit()
        return aid
    except Exception as exc:
        logger.warning("upsert_asset failed path=%s: %s", path, exc)
        return ""


def list_assets(kind: str = "", region: str = "", genre: str = "", q: str = "",
                limit: int = 200) -> list[dict]:
    """List assets filtered by kind/region/genre and a free-text ``q`` (slug/name/tags).
    Newest first. Empty list on error. Never raises."""
    try:
        _lim = max(1, min(1000, int(limit)))
        where, args = [], []
        if (kind or "").strip():
            where.append("kind = ?"); args.append(kind)
        if (region or "").strip():
            where.append("region = ?"); args.append(region)
        if (genre or "").strip():
            where.append("genre = ?"); args.append(genre)
        if (q or "").strip():
            like = f"%{q.strip()}%"
            where.append("(slug LIKE ? OR name LIKE ? OR tags LIKE ?)")
            args += [like, like, like]
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        args.append(_lim)
        with db_conn() as conn:
            rows = conn.execute(
                f"SELECT {_FULL_COLS} FROM story_assets {clause} "
                "ORDER BY kind, region, genre, slug LIMIT ?",
                tuple(args),
            ).fetchall()
            return [_row(r) for r in rows]
    except Exception as exc:
        logger.warning("list_assets failed: %s", exc)
        return []


def get_asset(asset_id: str) -> Optional[dict]:
    """Return one asset dict, or None. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                f"SELECT {_FULL_COLS} FROM story_assets WHERE id = ?", (asset_id,),
            ).fetchone()
            return _row(row) if row is not None else None
    except Exception as exc:
        logger.warning("get_asset failed id=%s: %s", asset_id, exc)
        return None


def delete_asset(asset_id: str) -> bool:
    """Remove an asset row (does NOT delete the file on disk). Returns True. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute("DELETE FROM story_assets WHERE id = ?", (asset_id,))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_asset failed id=%s: %s", asset_id, exc)
        return False


# ── Folder scan ───────────────────────────────────────────────────────────────

def _parse_path(root: Path, path: Path) -> Optional[dict]:
    """Derive {kind, region, genre, style, slug} from the path convention. Returns None
    for a file that doesn't match (unknown top-level kind / too shallow)."""
    try:
        parts = path.relative_to(root).parts
    except Exception:
        return None
    if len(parts) < 2:
        return None
    kind = parts[0].lower()
    if kind not in _KINDS:
        return None
    slug = path.stem
    region = genre = style = ""
    mid = parts[1:-1]                                   # segments between kind and file
    if kind in ("character", "background"):
        if len(mid) >= 1:
            region = mid[0]
        if len(mid) >= 2:
            genre = mid[1]
    elif kind == "object":
        if len(mid) >= 1:
            region = mid[0]
    elif kind == "frame":
        if len(mid) >= 1:
            style = mid[0]
    return {"kind": kind, "region": region, "genre": genre, "style": style, "slug": slug}


def _sidecar(path: Path) -> dict:
    """Optional ``{file}.json`` metadata override (name/tags/license/source/style)."""
    sc = path.with_suffix(path.suffix + ".json")
    if not sc.exists():
        sc = path.with_suffix(".json")
    if not sc.exists():
        return {}
    try:
        data = json.loads(sc.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def scan_library(root: "str | Path | None" = None, *, prune_missing: bool = True) -> dict:
    """Walk the asset library and upsert one row per image file. Returns
    ``{"indexed": n, "pruned": m, "root": str}``. Files derive kind/region/genre/slug
    from their path; a ``{file}.json`` sidecar overrides name/tags/license/source/style.
    ``prune_missing`` removes DB rows whose file no longer exists. Never raises."""
    from app.core.config import ASSET_LIBRARY_DIR
    base = Path(root) if root is not None else Path(ASSET_LIBRARY_DIR)
    indexed = 0
    seen_ids: set[str] = set()
    try:
        if base.exists():
            for p in base.rglob("*"):
                if not (p.is_file() and p.suffix.lower() in _IMG_EXTS):
                    continue
                meta = _parse_path(base, p)
                if meta is None:
                    continue
                side = _sidecar(p)
                aid = _asset_id(str(p))
                seen_ids.add(aid)
                upsert_asset(
                    path=str(p), asset_id=aid, kind=meta["kind"],
                    region=side.get("region", meta["region"]),
                    genre=side.get("genre", meta["genre"]),
                    slug=side.get("slug", meta["slug"]),
                    name=side.get("name", meta["slug"].replace("_", " ")),
                    tags=side.get("tags", ""),
                    style=side.get("style", meta["style"]),
                    transparent=bool(side.get("transparent", meta["kind"] in ("character", "object", "frame"))),
                    license=side.get("license", "ai-generated"),
                    source=side.get("source", "local"),
                )
                indexed += 1
    except Exception as exc:
        logger.warning("scan_library walk failed: %s", exc)

    pruned = 0
    if prune_missing:
        try:
            with db_conn() as conn:
                rows = conn.execute("SELECT id, path FROM story_assets").fetchall()
                for r in rows:
                    rid = r[0] if isinstance(r, tuple) else r["id"]
                    rpath = r[1] if isinstance(r, tuple) else r["path"]
                    if not Path(rpath).exists():
                        conn.execute("DELETE FROM story_assets WHERE id = ?", (rid,))
                        pruned += 1
                conn.commit()
        except Exception as exc:
            logger.warning("scan_library prune failed: %s", exc)

    logger.info("scan_library: indexed=%d pruned=%d root=%s", indexed, pruned, base)
    return {"indexed": indexed, "pruned": pruned, "root": str(base)}
