"""
character_resolver.py — GĐ3: deterministic character→library-asset resolution.

Đảo chiều asset-pick: the AI only DESCRIBES a character (canonical_desc / archetype /
gender / age); THIS resolver assigns the actual library asset from the real inventory
(vision-tagged GEE!ME characters + anything else in asset_library/character). The AI
never picks a slug it can't verify exists, and two characters in one story can never
share a face (uniqueness constraint).

Resolution order per character:
  1. LOCKED (series identity, characters.asset_slug)      → matched_exact
  2. EXISTING plan pick (Review / paste-JSON, slug valid)  → matched_exact
  3. Greedy best-score over UNUSED candidates:
       hard filter : opposite-gender candidates excluded
       score       : token overlap of the character's text (VN→EN visual-keyword
                     bridge) against the asset's name/tags/description (+gender/age
                     bonus, +archetype hits)
       ≥ MATCH_MIN  → matched   |  ≥ ASSIGN_MIN → needs_approval  |  else missing
Statuses land in ``plan.render.asset_status`` (Review chips / monitor); assignments
land in ``CharacterDef.asset`` — the existing master/overlay pipeline consumes them
unchanged. Pure + defensive: never raises; empty library → every char ``missing``.
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("app.render.char_resolver")

MATCHED_EXACT = "matched_exact"
MATCHED = "matched"
NEEDS_APPROVAL = "needs_approval"
MISSING = "missing"

MATCH_MIN = 4.0        # confident auto-match
ASSIGN_MIN = 1.0       # below MATCH_MIN but assignable (flag for approval)

# VN → EN visual-keyword bridge: canonical_desc is usually Vietnamese while the
# library tags are English (vision pass). Only LOOK words — story words don't matter.
_VI_EN = {
    "tóc": "hair", "đen": "black", "trắng": "white", "nâu": "brown", "vàng": "blonde yellow",
    "đỏ": "red", "hồng": "pink", "xanh": "blue green", "tím": "purple", "xám": "gray",
    "bạc": "gray silver", "dài": "long", "ngắn": "short", "xoăn": "curly", "búi": "bun",
    "áo": "shirt top", "khoác": "jacket coat", "vest": "suit", "sơ-mi": "shirt",
    "somi": "shirt", "váy": "dress skirt", "quần": "pants", "jean": "jeans",
    "hoodie": "hoodie", "mũ": "hat cap", "nón": "hat", "kính": "glasses",
    "râu": "beard", "ria": "mustache", "giày": "shoes sneakers", "dép": "sandals",
    "túi": "bag", "balo": "backpack", "đàn": "guitar", "sách": "book",
    "laptop": "laptop", "điện thoại": "phone", "trẻ": "young", "già": "elder old",
    "nam": "male man", "nữ": "female woman", "cô": "female woman", "anh": "male man",
    "ông": "male elder", "bà": "female elder", "bé": "child kid", "cậu": "male boy",
    "béo": "chubby", "gầy": "slim", "cao": "tall", "thấp": "short",
    "bác sĩ": "doctor medical", "y tá": "nurse medical", "cảnh sát": "police",
    "học sinh": "student", "sinh viên": "student", "văn phòng": "office",
    "đầu bếp": "chef", "ca sĩ": "singer", "hoạ sĩ": "artist", "thể thao": "sporty",
}
_STOP = {"the", "and", "with", "in", "a", "an", "of", "his", "her", "một", "người",
         "có", "và", "đang", "rất", "khá", "hơi", "màu"}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFC", (text or "")).lower()
    return re.sub(r"[^\wàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ\s-]",
                  " ", t)


def _char_tokens(c) -> "set[str]":
    """Search tokens for one CharacterDef: EN archetype + VN desc bridged to EN."""
    raw = " ".join([
        getattr(c, "archetype", "") or "", getattr(c, "name", "") or "",
        getattr(c, "canonical_desc", "") or "", getattr(c, "gender", "") or "",
        getattr(c, "age", "") or "",
    ])
    t = _norm(raw)
    for vi, en in _VI_EN.items():
        if vi in t:
            t += " " + en
    toks = {w for w in re.split(r"[\s_,;.-]+", t) if len(w) > 2 and w not in _STOP}
    return toks


def _cand_gender(hay: str) -> str:
    if " female" in hay or hay.startswith("female"):
        return "female"
    if " male" in hay or hay.startswith("male"):
        return "male"
    return ""


def _score(char_toks: "set[str]", gender: str, hay: str, hay_toks: "set[str]") -> float:
    s = float(len(char_toks & hay_toks))
    if gender and _cand_gender(hay) == gender:
        s += 3.0
    if "child" in char_toks and "child" in hay_toks:
        s += 2.0
    if ("elder" in char_toks or "old" in char_toks) and ("elder" in hay_toks or "old" in hay_toks):
        s += 2.0
    return s


def _candidates(region: str, genres: "tuple | list", style: "str | None" = None) -> "list[dict]":
    """Transparent character assets, scoped by genre group then WIDENED to the whole
    library when the scope is empty (a small library must never yield all-missing).
    ``style`` (kiến trúc style-aware): lọc về style hoạt động + asset không style;
    None → mọi style nhưng DEDUPE theo slug (một vai đa-style chỉ là MỘT ứng viên)."""
    from app.db.story_asset_repo import list_assets, _exists
    rows: list = []
    for g in (list(genres) or [""]):
        rows += list_assets(kind="character", genre=g, limit=1000, style=style)
    if not rows and genres:
        rows = list_assets(kind="character", limit=1000, style=style)
    seen: set = set()
    seen_slugs: set = set()
    out: list = []
    for a in rows:
        if a.get("id") in seen or not a.get("transparent") or not _exists(a.get("path", "")):
            continue
        if style is None and (a.get("slug") or "") in seen_slugs:
            continue                                   # multi-style twin → one candidate
        seen_slugs.add(a.get("slug") or "")
        seen.add(a.get("id"))
        hay = _norm(f'{a.get("slug", "")} {a.get("name", "")} {a.get("tags", "")} '
                    f'{a.get("description", "")}').replace("_", " ")
        a["_hay"] = hay
        a["_hay_toks"] = {w for w in hay.split() if len(w) > 2 and w not in _STOP}
        out.append(a)
    return out


def resolve_characters(plan, *, locked: "dict | None" = None, honor_existing: bool = True,
                       region: str = "", genres: "tuple | list" = (),
                       style: "str | None" = None) -> dict:
    """Assign a UNIQUE library asset to every plan character + fill
    ``plan.render.asset_status``. Returns a report:
    ``{statuses: {cid: state}, assigned: {cid: slug}, needs_approval: [cid],
    missing: [cid]}``. Mutates ``CharacterDef.asset`` in place. Never raises."""
    rep = {"statuses": {}, "assigned": {}, "needs_approval": [], "missing": []}
    try:
        from app.db.story_asset_repo import get_by_slug
        chars = list(getattr(plan, "characters", None) or [])
        if not chars:
            return rep
        locked = {str(k): str(v) for k, v in (locked or {}).items() if str(v or "").strip()}
        used: set = set()
        pending = []

        def _slug_of(a: dict) -> str:
            return str(a.get("slug") or "")

        # Pass 1 — locks + existing valid picks are authoritative (matched_exact).
        for c in chars:
            cid = (getattr(c, "id", "") or "").strip()
            lk = locked.get(cid, "")
            if lk and get_by_slug(lk, "character"):
                c.asset = lk
                rep["statuses"][cid] = MATCHED_EXACT
                rep["assigned"][cid] = lk
                used.add(lk)
                continue
            existing = (getattr(c, "asset", "") or "").strip()
            if honor_existing and existing and existing not in used \
                    and get_by_slug(existing, "character"):
                rep["statuses"][cid] = MATCHED_EXACT
                rep["assigned"][cid] = existing
                used.add(existing)
                continue
            pending.append(c)

        # Pass 2 — greedy unique best-score for the rest.
        if style is None:
            try:
                from app.db.story_asset_repo import active_library_style
                style = active_library_style(getattr(plan, "art_style", "") or "") or None
            except Exception:
                style = None
        cands = _candidates(region, genres, style)
        for c in pending:
            cid = (getattr(c, "id", "") or "").strip()
            toks = _char_tokens(c)
            gender = (getattr(c, "gender", "") or "").strip().lower()
            best, best_s = None, -1.0
            for a in cands:
                slug = _slug_of(a)
                if not slug or slug in used:
                    continue
                cg = _cand_gender(a["_hay"])
                if gender in ("male", "female") and cg and cg != gender:
                    continue                                   # hard filter
                s = _score(toks, gender, a["_hay"], a["_hay_toks"])
                if s > best_s:
                    best, best_s = a, s
            if best is not None and best_s >= ASSIGN_MIN:
                slug = _slug_of(best)
                c.asset = slug
                used.add(slug)
                rep["assigned"][cid] = slug
                if best_s >= MATCH_MIN:
                    rep["statuses"][cid] = MATCHED
                else:
                    rep["statuses"][cid] = NEEDS_APPROVAL
                    rep["needs_approval"].append(cid)
            else:
                c.asset = ""
                rep["statuses"][cid] = MISSING
                rep["missing"].append(cid)

        try:
            plan.render.asset_status = dict(rep["statuses"])
        except Exception:
            pass
        logger.info("char_resolver: %d char(s) → exact=%d matched=%d approval=%d missing=%d",
                    len(chars),
                    sum(1 for v in rep["statuses"].values() if v == MATCHED_EXACT),
                    sum(1 for v in rep["statuses"].values() if v == MATCHED),
                    len(rep["needs_approval"]), len(rep["missing"]))
    except Exception as exc:
        logger.warning("char_resolver: resolve failed (non-fatal): %s", exc)
    return rep


def resolver_enabled() -> bool:
    import os
    return os.getenv("STORY_CHAR_RESOLVER", "1") == "1"


__all__ = ["resolve_characters", "resolver_enabled",
           "MATCHED_EXACT", "MATCHED", "NEEDS_APPROVAL", "MISSING"]
