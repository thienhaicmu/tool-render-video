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

_FULL_COLS = ("id, kind, region, genre, slug, name, tags, style, description, path, "
              "transparent, license, source, created_at, updated_at")
_FULL_KEYS = ("id", "kind", "region", "genre", "slug", "name", "tags", "style", "description", "path",
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
    description: str = "",
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
                    (id, kind, region, genre, slug, name, tags, style, description, path,
                     transparent, license, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind, region=excluded.region, genre=excluded.genre,
                    slug=excluded.slug, name=excluded.name, tags=excluded.tags,
                    style=excluded.style, description=excluded.description, path=excluded.path,
                    transparent=excluded.transparent, license=excluded.license,
                    source=excluded.source,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (aid, kind, region, genre, slug, name, tags, style, description, path,
                 1 if transparent else 0, license, source),
            )
            conn.commit()
        return aid
    except Exception as exc:
        logger.warning("upsert_asset failed path=%s: %s", path, exc)
        return ""


def list_assets(kind: str = "", region: str = "", genre: str = "", q: str = "",
                limit: int = 200, style: "Optional[str]" = None) -> list[dict]:
    """List assets filtered by kind/region/genre and a free-text ``q`` (slug/name/tags).
    ``style``: None = mọi style (mặc định, back-compat); "" = CHỈ asset không style;
    "x" = asset của style x HOẶC không style (styleless dùng chung mọi style).
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
        if style is not None:
            if (style or "").strip():
                where.append("(style = ? OR style = '')"); args.append(style.strip())
            else:
                where.append("style = ''")
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


def _exists(path: str) -> bool:
    try:
        return bool(path) and Path(path).exists() and Path(path).stat().st_size > 0
    except Exception:
        return False


def best_asset(kind: str, name: str = "", region: str = "", genre: str = "",
               *, transparent_only: bool = False, style: "Optional[str]" = None) -> Optional[dict]:
    """Best-matching library asset ROW (dict) for a fuzzy ``name`` lookup, or None.
    Shared core of :func:`match_asset` (which returns the path). Scoped by kind and,
    when a ``name`` signal exists, PROGRESSIVELY WIDENED (region+genre → region →
    unscoped) so a slightly-off region/genre no longer drops every candidate. A blank
    ``name`` stays strictly in the requested scope (never cross-region substitutes).
    Never raises.

    Ranking (highest first): exact slug/name → whole-query substring in
    slug/name/tags/DESCRIPTION → graded token overlap (more shared tokens wins). Score
    0 (no name signal at all) → None, so a random asset is never silently substituted."""
    key = (name or "").strip().lower()

    def _cands(rg: str, gn: str) -> list:
        cs = [a for a in list_assets(kind=kind, region=rg, genre=gn, limit=500, style=style)
              if _exists(a.get("path", ""))]
        if transparent_only:
            cs = [a for a in cs if a.get("transparent")]
        return cs

    try:
        if key:                                           # widen only when we can rank
            cands = (_cands(region, genre)
                     or (_cands(region, "") if genre else [])
                     or (_cands("", "") if (region or genre) else []))
        else:
            cands = _cands(region, genre)
        if not cands:
            return None
        if not key:
            return cands[0]                               # scope-only pick

        def _score(a: dict) -> int:
            nm = str(a.get("name", "")).lower()
            sg = str(a.get("slug", "")).lower()
            if key == nm or key == sg:                    # exact slug/name
                return 1000
            hay = (f"{sg} {nm} {str(a.get('tags', '')).lower()} "
                   f"{str(a.get('description', '')).lower()}")   # + rich description (F2)
            if key in hay:                                # whole query is a substring
                return 500
            # graded token overlap: rank by count of shared meaningful (>2-char) tokens
            toks = {t for t in key.replace("_", " ").replace(",", " ").split() if len(t) > 2}
            haytoks = set(hay.replace("_", " ").replace(",", " ").replace("/", " ").split())
            return len(toks & haytoks) if toks else 0     # 0 → None (no substitution)

        best = max(cands, key=_score)
        return best if _score(best) > 0 else None
    except Exception as exc:
        logger.warning("best_asset failed kind=%s name=%s: %s", kind, name, exc)
        return None


def match_asset(kind: str, name: str = "", region: str = "", genre: str = "",
                *, transparent_only: bool = False, style: "Optional[str]" = None) -> Optional[str]:
    """Best-effort deterministic library lookup — returns the on-disk PATH of the best
    matching asset (see :func:`best_asset` for ranking + widening), or None. Only
    returns an asset whose file still exists on disk. Never raises."""
    a = best_asset(kind, name, region, genre, transparent_only=transparent_only, style=style)
    return a["path"] if a else None


def known_styles() -> "set[str]":
    """Distinct non-empty style-pack ids present in the library (kiến trúc
    style-aware). Empty set on error. Never raises."""
    try:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT style FROM story_assets WHERE style != ''").fetchall()
        return {(r[0] if isinstance(r, tuple) else r["style"]) for r in rows}
    except Exception as exc:
        logger.warning("known_styles failed: %s", exc)
        return set()


def active_library_style(art_style: str) -> str:
    """Chuẩn hoá ``story_art_style``/plan.art_style → style-pack id đã cài trong thư
    viện ('' khi không khớp — mọi query rơi về asset không style). Never raises."""
    s = (art_style or "").strip().lower().replace(" ", "_").replace("-", "_")
    return s if s and s in known_styles() else ""


# Variant suffixes appended to a base slug (emotion/pose for characters, tod for
# backgrounds) — stripped when grouping the catalog, so the AI picks a BASE asset and
# the render resolves the right variant per beat.
_VARIANT_SUFFIXES = ("happy", "angry", "sad", "surprised", "wave", "cheer", "point", "hip",
                     "day", "night")
# Readable expansions for the derived catalog description (when no sidecar desc).
_REGION_NAME = {"cn": "Chinese", "jp": "Japanese", "ko": "Korean", "vi": "Vietnamese",
                "eu": "European", "us": "American"}
_GENRE_NAME = {"wuxia": "wuxia", "ngontinh": "romance", "horror": "horror",
               "fantasy": "fantasy", "codai": "historical", "hiendai": "modern"}


def _split_variant(slug: str) -> "tuple[str, str]":
    """(base_slug, variant) — variant is "" when the slug has no known suffix."""
    for s in _VARIANT_SUFFIXES:
        if slug.endswith("_" + s):
            return slug[: -(len(s) + 1)], s
    return slug, ""


def get_by_slug(slug: str, kind: str = "", style: str = "") -> Optional[str]:
    """Exact-slug → on-disk PATH of a library asset the AI plan chose (library-pick).
    Optionally scoped by ``kind`` (character|background|…). ``style`` (kiến trúc
    style-aware): ưu tiên biến thể của style đang hoạt động, rơi về bản không style,
    cuối cùng mới tới style khác — nên một slug đa-style luôn trả đúng biến thể.
    Returns the first candidate whose file still exists, else None. Never raises."""
    s = (slug or "").strip()
    if not s:
        return None
    try:
        where, args = ["slug = ?"], [s]
        if (kind or "").strip():
            where.append("kind = ?"); args.append(kind)
        with db_conn() as conn:
            rows = conn.execute(
                f"SELECT path, style FROM story_assets WHERE {' AND '.join(where)}",
                tuple(args),
            ).fetchall()
        want = (style or "").strip()

        def _rank(row_style: str) -> int:
            if want and row_style == want:
                return 0
            if row_style == "":
                return 1
            return 2 if not want else 3      # foreign style last (still usable)

        cands = []
        for r in rows:
            p = r[0] if isinstance(r, tuple) else r["path"]
            st = (r[1] if isinstance(r, tuple) else r["style"]) or ""
            if _exists(p):
                cands.append((_rank(st), p))
        cands.sort(key=lambda x: x[0])
        return cands[0][1] if cands else None
    except Exception as exc:
        logger.warning("get_by_slug failed slug=%s: %s", slug, exc)
        return None


def build_library_catalog(region: str = "", genre: str = "", cap: int = 300,
                          genres: "tuple | list | None" = None,
                          kinds: "tuple | list" = ("character", "background"),
                          style: "Optional[str]" = None) -> str:
    """Compact, described inventory of the library for the super-prompt so the AI can
    CHOOSE assets by slug (library-pick). Groups base + variants (one line per base slug):
    ``base_slug | region/genre | role-or-scene tokens | [emotions/poses | day,night]``.

    ``genres`` (optional) scopes the catalog to a GROUP of genre_keys (e.g. a wuxia story
    → {wuxia, codai}); it takes precedence over the single ``genre``. A story's characters
    span several art-style buckets, so a group avoids hiding valid picks while still
    shrinking the prompt. None → the single ``genre`` (""=all) → back-compat.
    Empty string when the library is empty (→ prompt stays byte-identical). Never raises."""
    scope = [g for g in (genres if genres else [genre])]        # [""] = all genres
    try:
        def _families(kind: str) -> dict:
            fam: dict = {}
            rows: list = []
            for g in scope:                                     # gather across the genre group
                rows += list_assets(kind=kind, region=region, genre=g, limit=1000, style=style)
            for a in rows:
                base, var = _split_variant(a.get("slug", ""))
                if not base:
                    continue
                e = fam.setdefault(base, {"region": a.get("region", ""), "genre": a.get("genre", ""),
                                          "style": a.get("style", ""), "description": "",
                                          "emotions": set(), "poses": set(), "tod": set()})
                d = (a.get("description", "") or "").strip()
                if d and (not var or not e["description"]):   # base variant's desc is authoritative
                    e["description"] = d
                if var in ("happy", "angry", "sad", "surprised"):
                    e["emotions"].add(var)
                elif var in ("wave", "cheer", "point", "hip"):
                    e["poses"].add(var)
                elif var in ("day", "night"):
                    e["tod"].add(var)
            return fam

        def _tokens(base: str, meta: dict) -> str:
            toks = [t for t in base.split("_")
                    if t and t not in (meta.get("region"), meta.get("genre"), meta.get("style"))]
            return " ".join(toks)

        def _desc(base: str, meta: dict) -> str:
            # authored sidecar description wins; else a readable derived phrase
            if meta.get("description"):
                return meta["description"]
            rn = _REGION_NAME.get(meta.get("region", ""), "")
            gn = _GENRE_NAME.get(meta.get("genre", ""), (meta.get("genre", "") or ""))
            return " ".join(x for x in (rn, gn, _tokens(base, meta)) if x)

        def _scope(meta: dict) -> str:
            return "/".join([x for x in (meta.get("region"), meta.get("genre"), meta.get("style")) if x])

        lines: list[str] = []
        # GĐ3: with the character RESOLVER on, characters are assigned by the engine —
        # the prompt then carries only the BACKGROUNDS section (kinds=("background",)).
        chars = _families("character") if "character" in (kinds or ()) else {}
        if chars:
            lines.append("CHARACTERS (transparent full-body; pick the closest, else asset=\"\"):")
            for base in sorted(chars)[:cap]:
                m = chars[base]
                extra = []
                if m["emotions"]:
                    extra.append("emotions:" + ",".join(sorted(m["emotions"])))
                if m["poses"]:
                    extra.append("poses:" + ",".join(sorted(m["poses"])))
                suffix = (" | " + " ".join(extra)) if extra else ""
                lines.append(f"  {base} | {_scope(m)} | {_desc(base, m)}{suffix}")
        bgs = _families("background") if "background" in (kinds or ()) else {}
        if bgs:
            lines.append("BACKGROUNDS (wide 16:9 scenes; pick the closest, else asset=\"\"):")
            for base in sorted(bgs)[:cap]:
                m = bgs[base]
                tod = (" | " + ",".join(sorted(m["tod"]))) if m["tod"] else ""
                lines.append(f"  {base} | {_scope(m)} | {_desc(base, m)}{tod}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("build_library_catalog failed: %s", exc)
        return ""


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
    for a file that doesn't match (unknown top-level kind / too shallow).

    Kiến trúc style-aware (JP three-style library): character/background chấp nhận một
    tầng thứ 3 tuỳ chọn là STYLE PACK id —
        {kind}/{region}/{genre}/{style}/{slug}.png
    Cùng một slug vai diễn có thể tồn tại ở nhiều style; các query (get_by_slug /
    best_asset / catalog / resolver) lọc theo style đang hoạt động. Path 2 tầng cũ
    (GEE!ME, nền procedural) giữ nguyên với style ""."""
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
        if len(mid) >= 3:
            style = mid[2]
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


def _load_sources_manifest(root: Path) -> list:
    """Optional ``<root>/asset_sources.json`` provenance manifest (AL5): default
    license/source per asset family, applied when a file has no per-file sidecar.
    Shape: ``{"families": [{"match": {"kind":..,"region":..,"genre":..},
    "license":.., "source":..}, ...]}``. Returns the families list ([] on any error /
    absent file). Never raises."""
    mf = root / "asset_sources.json"
    if not mf.exists():
        return []
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
        fams = data.get("families") if isinstance(data, dict) else None
        return [f for f in fams if isinstance(f, dict)] if isinstance(fams, list) else []
    except Exception:
        return []


def _manifest_match(families: list, meta: dict) -> dict:
    """First family whose ``match`` (kind/region/genre subset — blank keys are
    wildcards) fits ``meta``. {} if none matches."""
    for fam in families:
        m = fam.get("match") or {}
        if all((not m.get(k)) or m.get(k) == meta.get(k) for k in ("kind", "region", "genre")):
            return fam
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
    families = _load_sources_manifest(base)          # AL5 provenance defaults (may be [])
    try:
        if base.exists():
            for p in base.rglob("*"):
                if not (p.is_file() and p.suffix.lower() in _IMG_EXTS):
                    continue
                meta = _parse_path(base, p)
                if meta is None:
                    continue
                side = _sidecar(p)
                man = _manifest_match(families, meta)  # {} when no manifest/rule
                aid = _asset_id(str(p))
                seen_ids.add(aid)
                # Precedence for license/source: per-file sidecar > manifest > hardcoded.
                upsert_asset(
                    path=str(p), asset_id=aid, kind=meta["kind"],
                    region=side.get("region", meta["region"]),
                    genre=side.get("genre", meta["genre"]),
                    slug=side.get("slug", meta["slug"]),
                    name=side.get("name", meta["slug"].replace("_", " ")),
                    tags=side.get("tags", ""),
                    style=side.get("style", meta["style"]),
                    description=side.get("desc", side.get("description", "")),
                    transparent=bool(side.get("transparent", meta["kind"] in ("character", "object", "frame"))),
                    license=side.get("license", man.get("license", "ai-generated")),
                    source=side.get("source", man.get("source", "local")),
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
