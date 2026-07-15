"""
story_understanding.py — GĐ1 Story Compiler Pass 1 contract + deterministic validators.

StoryUnderstanding is the fact sheet the compiler extracts from a pasted chapter
BEFORE any writing happens: characters / locations / relationships / ordered events,
each event carrying a VERBATIM quote from the source. The quote is the verification
mechanism: an LLM's self-reported coverage can't be trusted, but a quote either IS a
substring of the chapter (after whitespace/case normalisation) or it isn't — so
coverage, ordering and lost-ending checks are all deterministic and free.

Also hosts the SCRIPT validators for Pass 2 (the Writer's screenplay-lite output):
speaker names must exist, major events must be reachable in the script (anchor-token
match), the ending must sit in the script's tail, and (idea mode) the spoken length
must hit its budget.

Pure + defensive (Sacred Contract #3 spirit): parsing never raises; a malformed
response yields None; validators always return a report, never an exception.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from app.features.render.ai.llm.story_parser_v2 import _extract_json_object

logger = logging.getLogger("app.render.story_understanding")

_QUOTE_MIN_CHARS = 12          # shorter quotes are too ambiguous to verify
_TAIL_FRACTION = 0.70          # last verified event must sit past this point of the chapter
_SCRIPT_TAIL_FRACTION = 0.65   # ... and its anchors past this point of the script


# ── Contract ──────────────────────────────────────────────────────────────────
@dataclass
class UEvent:
    id: str = ""
    summary: str = ""
    characters: list = field(default_factory=list)
    location: str = ""
    time: str = ""
    quote: str = ""
    importance: str = "minor"      # major | minor
    verified: bool = False         # quote matched the chapter (filled by validator)
    src_pos: int = -1              # normalised-chapter position of the quote (-1 = n/a)


@dataclass
class StoryUnderstanding:
    topic: str = ""
    genre: str = ""
    tone: str = ""
    characters: list = field(default_factory=list)     # [{id,name,role,gender,desc}]
    locations: list = field(default_factory=list)      # [{id,name,desc}]
    relationships: list = field(default_factory=list)  # [{a,b,type}]
    goals_conflicts: list = field(default_factory=list)
    events: list = field(default_factory=list)         # [UEvent]

    def character_names(self) -> "list[str]":
        out = []
        for c in self.characters:
            for k in ("name", "id"):
                v = str(c.get(k) or "").strip()
                if v:
                    out.append(v)
        return out


def _s(v) -> str:
    try:
        return str(v or "").strip()
    except Exception:
        return ""


def _slist(v, cap: int = 32) -> list:
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        s = _s(x)
        if s:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def parse_understanding(raw: "str | None") -> Optional[StoryUnderstanding]:
    """Parse the Call-1 JSON → StoryUnderstanding, or None. Never raises."""
    data = _extract_json_object(raw or "")
    if data is None:
        return None
    try:
        u = StoryUnderstanding(
            topic=_s(data.get("topic")), genre=_s(data.get("genre")), tone=_s(data.get("tone")),
            goals_conflicts=_slist(data.get("goals_conflicts")),
        )
        for c in (data.get("characters") or []):
            if isinstance(c, dict) and (_s(c.get("id")) or _s(c.get("name"))):
                cid = _s(c.get("id")) or _slug(_s(c.get("name")))
                u.characters.append({
                    "id": cid, "name": (_s(c.get("name")) or cid),
                    "role": _s(c.get("role")) or "support",
                    "gender": _s(c.get("gender")).lower(),
                    "desc": _s(c.get("desc")),
                })
        for l in (data.get("locations") or []):
            if isinstance(l, dict) and (_s(l.get("id")) or _s(l.get("name"))):
                lid = _s(l.get("id")) or _slug(_s(l.get("name")))
                u.locations.append({"id": lid, "name": (_s(l.get("name")) or lid),
                                    "desc": _s(l.get("desc"))})
        for r in (data.get("relationships") or []):
            if isinstance(r, dict) and _s(r.get("a")) and _s(r.get("b")):
                u.relationships.append({"a": _s(r.get("a")), "b": _s(r.get("b")),
                                        "type": _s(r.get("type"))})
        char_ids = {c["id"] for c in u.characters}
        loc_ids = {l["id"] for l in u.locations}
        for i, e in enumerate(data.get("events") or [], start=1):
            if not isinstance(e, dict):
                continue
            ev = UEvent(
                id=(_s(e.get("id")) or f"e{i}"),
                summary=_s(e.get("summary")),
                characters=[c for c in _slist(e.get("characters")) if c in char_ids],
                location=(_s(e.get("location")) if _s(e.get("location")) in loc_ids else ""),
                time=_s(e.get("time")),
                quote=_s(e.get("quote")),
                importance=("major" if _s(e.get("importance")).lower() == "major" else "minor"),
            )
            if ev.summary or ev.quote:
                u.events.append(ev)
        if not u.events and not u.characters:
            return None
        return u
    except Exception as exc:
        logger.info("story_understanding: parse error %s", exc)
        return None


# ── Deterministic verification ────────────────────────────────────────────────
def _norm(text: str) -> str:
    """Normalise for substring matching: NFC, lowercase, collapse whitespace, strip
    the quote/dash characters models love to 'improve'."""
    t = unicodedata.normalize("NFC", text or "").lower()
    t = re.sub(r"[\"'“”‘’«»…]|[–—]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def validate_understanding(u: StoryUnderstanding, chapter: str) -> dict:
    """Verify every event's quote against the chapter (substring on normalised text).
    Fills ``event.verified``/``src_pos`` in place. Returns a report:
    ``{verified, total, majors_verified, majors_total, tail_covered, order_ok,
    warnings[]}``. Never raises."""
    rep = {"verified": 0, "total": 0, "majors_verified": 0, "majors_total": 0,
           "tail_covered": False, "order_ok": True, "warnings": []}
    try:
        hay = _norm(chapter)
        if not hay:
            return rep
        positions: list[int] = []
        end_positions: list[int] = []
        for ev in u.events:
            rep["total"] += 1
            if ev.importance == "major":
                rep["majors_total"] += 1
            q = _norm(ev.quote)
            if len(q) >= _QUOTE_MIN_CHARS:
                pos = hay.find(q)
                if pos < 0 and len(q) > 60:      # long quote with a small edit → try its core
                    core = q[10:-10]
                    pos = hay.find(core)
                if pos >= 0:
                    ev.verified = True
                    ev.src_pos = pos
                    positions.append(pos)
                    end_positions.append(pos + len(q))
                    rep["verified"] += 1
                    if ev.importance == "major":
                        rep["majors_verified"] += 1
                    continue
            rep["warnings"].append(f"event {ev.id}: quote not found in source (unverified)")
        if positions:
            rep["tail_covered"] = max(end_positions) >= len(hay) * _TAIL_FRACTION
            if not rep["tail_covered"]:
                rep["warnings"].append(
                    "no verified event in the last 30% of the chapter — the ending may be missing")
            inversions = sum(1 for a, b in zip(positions, positions[1:]) if b < a)
            if inversions > max(1, len(positions) // 5):
                rep["order_ok"] = False
                rep["warnings"].append(f"event order diverges from the source ({inversions} inversions)")
    except Exception as exc:
        logger.info("story_understanding: validate error %s", exc)
    return rep


def understanding_block(u: StoryUnderstanding) -> str:
    """Render the compact FACTS block the Writer prompt embeds: characters, then the
    ordered event checklist (verified events only keep their order guarantee, but ALL
    events are listed — an unverified summary is still a to-cover item)."""
    try:
        lines: list[str] = []
        if u.topic:
            lines.append(f"TOPIC: {u.topic}")
        if u.genre:
            lines.append(f"GENRE: {u.genre}")
        if u.tone:
            lines.append(f"TONE: {u.tone}")
        if u.characters:
            lines.append("CHARACTERS:")
            for c in u.characters:
                bits = [c.get("name", ""), c.get("role", ""), c.get("gender", "")]
                desc = (c.get("desc") or "")[:80]
                lines.append("- " + " | ".join(b for b in bits if b) + (f" | {desc}" if desc else ""))
        if u.locations:
            lines.append("PLACES:")
            for loc in u.locations:
                name = loc.get("name", "")
                if name:
                    desc = (loc.get("desc") or "")[:120]
                    lines.append(f"- {loc.get('id', '')} | {name}" + (f" | {desc}" if desc else ""))
        if u.relationships:
            lines.append("RELATIONSHIPS:")
            for rel in u.relationships[:32]:
                lines.append(f"- {rel.get('a', '')} -> {rel.get('b', '')}: {rel.get('type', '')}")
        if u.goals_conflicts:
            lines.append("CORE CONFLICTS: " + " · ".join(u.goals_conflicts[:6]))
        if u.events:
            lines.append("EVENTS (cover ALL, in order):")
            for ev in u.events:
                tag = "[MAJOR] " if ev.importance == "major" else ""
                meta = []
                if ev.characters:
                    meta.append("characters=" + ",".join(ev.characters))
                if ev.location:
                    meta.append("location=" + ev.location)
                if ev.time:
                    meta.append("time=" + ev.time)
                verification = "verified" if ev.verified else "unverified"
                suffix = f" ({'; '.join(meta)})" if meta else ""
                lines.append(f"{ev.id}. {tag}{ev.summary}{suffix} [{verification}]")
                if ev.quote:
                    lines.append(f"   source quote: {ev.quote[:180]}")
        return "\n".join(lines).strip()
    except Exception:
        return ""


# ── Pass-2 SCRIPT validators ──────────────────────────────────────────────────
_SCENE_RE = re.compile(r"^\[SCENE\s*:\s*([^\]]+)\]\s*$", re.IGNORECASE | re.MULTILINE)
_DIALOG_RE = re.compile(r"^(?!NARR\b)([^:\n\[\]]{1,60}?)\s*(?:\(([^)]{0,24})\))?\s*:\s*[\"“]",
                        re.MULTILINE)


def script_spoken_chars(script: str) -> int:
    """Approximate SPOKEN length of a script: everything minus the [SCENE] markers,
    speaker names and format punctuation. Cheap + deterministic (length loop)."""
    try:
        t = _SCENE_RE.sub("", script or "")
        t = re.sub(r"^NARR\s*:\s*", "", t, flags=re.MULTILINE)
        t = re.sub(r"^[^:\n\[\]]{1,60}?\s*(?:\([^)]{0,24}\))?\s*:\s*", "", t, flags=re.MULTILINE)
        return len(re.sub(r"\s+", " ", t).strip())
    except Exception:
        return len(script or "")


def _event_anchors(ev: UEvent) -> "list[str]":
    """Tokens that place an event inside the SCRIPT: its character names are added by
    the caller; here we take the 2 longest words (>3 chars) of the quote/summary —
    rare enough to anchor, short enough to survive light rephrasing."""
    src = _norm(ev.quote or ev.summary)
    toks = sorted({w for w in src.split() if len(w) > 3}, key=len, reverse=True)
    return toks[:2]


def validate_script(script: str, u: Optional[StoryUnderstanding], *,
                    language: str = "vi", target_chars: int = 0) -> dict:
    """Deterministic Pass-2 gate. Returns ``{ok, spoken_chars, missing_events[],
    unknown_speakers[], tail_ok, warnings[]}``.  ``ok`` is False only for the
    repair-able failures (missing MAJOR events / empty script); everything else is a
    warning (the show must go on — Sacred #3 spirit)."""
    rep = {"ok": True, "spoken_chars": 0, "missing_events": [], "unknown_speakers": [],
           "tail_ok": True, "warnings": []}
    try:
        s = (script or "").strip()
        if not s or "[SCENE" not in s.upper():
            rep["ok"] = False
            rep["warnings"].append("script empty or missing [SCENE] markers")
            return rep
        rep["spoken_chars"] = script_spoken_chars(s)
        norm_script = _norm(s)

        # Speakers must be known (fuzzy: normalised name containment either way).
        if u is not None and u.characters:
            known = {_norm(n) for n in u.character_names()}
            for m in _DIALOG_RE.finditer(s):
                name = _norm(m.group(1))
                if not name or name == "narr":
                    continue
                if not any(name in k or k in name for k in known):
                    if name not in rep["unknown_speakers"]:
                        rep["unknown_speakers"].append(name)
            if rep["unknown_speakers"]:
                rep["warnings"].append(
                    "unknown speaker(s) in script (mapped to narrator at structure): "
                    + ", ".join(rep["unknown_speakers"][:8]))

        # Event coverage: an event is IN the script when any of its anchors appears.
        if u is not None and u.events:
            last_major_pos = -1
            for ev in u.events:
                anchors = _event_anchors(ev)
                names = []
                for cid in ev.characters:
                    c = next((c for c in u.characters if c.get("id") == cid), None)
                    if c and c.get("name"):
                        names.append(_norm(c["name"]))
                hit = -1
                for a in anchors + names:
                    p = norm_script.find(a)
                    if p >= 0:
                        hit = max(hit, p)
                        break
                if hit < 0:
                    if ev.importance == "major":
                        rep["missing_events"].append(ev.summary or ev.id)
                    else:
                        rep["warnings"].append(f"minor event possibly missing: {ev.id}")
                elif ev.importance == "major":
                    last_major_pos = max(last_major_pos, hit)
            if rep["missing_events"]:
                rep["ok"] = False
            if last_major_pos >= 0 and last_major_pos < len(norm_script) * _SCRIPT_TAIL_FRACTION \
                    and len(u.events) >= 3:
                rep["tail_ok"] = False
                rep["warnings"].append("the final major event sits early in the script — "
                                       "the ending may be under-told")

        # Idea-mode length gate (paste mode passes target_chars=0 → skipped).
        if target_chars > 0:
            lo = int(target_chars * 0.9)
            if rep["spoken_chars"] < lo:
                rep["warnings"].append(
                    f"script is short: {rep['spoken_chars']} vs target {target_chars} chars")
    except Exception as exc:
        logger.info("story_understanding: script validate error %s", exc)
    return rep


def understanding_gate(rep: dict, *, min_verified_ratio: float = 0.70) -> "list[str]":
    """Return blocking reasons for a Pass-1 validation report."""
    reasons: list[str] = []
    try:
        total = int(rep.get("total") or 0)
        verified = int(rep.get("verified") or 0)
        majors_total = int(rep.get("majors_total") or 0)
        majors_verified = int(rep.get("majors_verified") or 0)
        if total <= 0:
            reasons.append("understanding contains no verifiable events")
        elif verified / total < max(0.0, min(1.0, float(min_verified_ratio))):
            reasons.append(f"only {verified}/{total} events have verified source quotes")
        if majors_total > 0 and majors_verified < majors_total:
            reasons.append(f"only {majors_verified}/{majors_total} major events are verified")
        if not bool(rep.get("tail_covered")):
            reasons.append("no verified event covers the source ending")
        if not bool(rep.get("order_ok", True)):
            reasons.append("verified events are not in source order")
    except Exception as exc:
        reasons.append(f"understanding gate failed: {exc}")
    return reasons


def script_gate(rep: dict, *, target_chars: int = 0,
                min_target_ratio: float = 0.70) -> "list[str]":
    """Return blocking reasons after the bounded Writer repair/expand attempts."""
    reasons: list[str] = []
    try:
        if not bool(rep.get("ok")):
            reasons.append("script is empty or misses one or more major events")
        unknown = list(rep.get("unknown_speakers") or [])
        if unknown:
            reasons.append("unknown speakers remain: " + ", ".join(unknown[:8]))
        if not bool(rep.get("tail_ok", True)):
            reasons.append("the final major event is under-told or appears too early")
        spoken = int(rep.get("spoken_chars") or 0)
        if target_chars > 0 and spoken < target_chars * max(0.0, float(min_target_ratio)):
            reasons.append(f"script length {spoken} is below the accepted target floor")
    except Exception as exc:
        reasons.append(f"script gate failed: {exc}")
    return reasons


def validate_plan_coverage(script: str, plan) -> dict:
    """Measure deterministic spoken-token recall from approved script to StoryPlan."""
    rep = {"coverage": 0.0, "order_coverage": 0.0,
           "script_tokens": 0, "plan_tokens": 0, "warnings": []}
    try:
        source = _SCENE_RE.sub("", script or "")
        source = re.sub(r"^NARR\s*:\s*", "", source, flags=re.MULTILINE)
        source = re.sub(r"^[^:\n\[\]]{1,60}?\s*(?:\([^)]{0,24}\))?\s*:\s*", "", source,
                        flags=re.MULTILINE)
        plan_parts = []
        for beat in list(getattr(plan, "timeline", None) or []):
            try:
                plan_parts.extend((ln.text or "") for ln in beat.effective_lines())
            except Exception:
                plan_parts.append(getattr(beat, "narration", "") or "")
        src_tokens = [t for t in _norm(source).split() if len(t) > 1]
        normalized_plan = _norm(" ".join(plan_parts))
        plan_tokens = [t for t in normalized_plan.split() if len(t) > 1]
        rep["script_tokens"] = len(src_tokens)
        rep["plan_tokens"] = len(plan_tokens)
        if src_tokens:
            matched = sum((Counter(src_tokens) & Counter(plan_tokens)).values())
            rep["coverage"] = round(matched / len(src_tokens), 4)
            # Sample ordered 3-token anchors across the script and require monotonic
            # matches in the plan. This catches a Structure pass that preserves words
            # but silently reorders scenes or moves the ending.
            anchor_count = min(12, max(1, len(src_tokens) // 3))
            step = max(1, len(src_tokens) // anchor_count)
            anchors = [" ".join(src_tokens[i:i + 3])
                       for i in range(0, len(src_tokens), step)
                       if len(src_tokens[i:i + 3]) == 3][:anchor_count]
            cursor = 0
            ordered_hits = 0
            for anchor in anchors:
                pos = normalized_plan.find(anchor, cursor)
                if pos >= 0:
                    ordered_hits += 1
                    cursor = pos + len(anchor)
            rep["order_coverage"] = round(ordered_hits / len(anchors), 4) if anchors else 0.0
        if not src_tokens:
            rep["warnings"].append("approved script has no spoken tokens")
        elif rep["coverage"] < 0.75:
            rep["warnings"].append(
                f"StoryPlan preserves only {rep['coverage'] * 100:.0f}% of approved script tokens")
        if src_tokens and rep["order_coverage"] < 0.70:
            rep["warnings"].append(
                f"StoryPlan preserves only {rep['order_coverage'] * 100:.0f}% of ordered script anchors")
    except Exception as exc:
        rep["warnings"].append(f"plan coverage validation failed: {exc}")
    return rep


def _slug(name: str) -> str:
    t = unicodedata.normalize("NFD", name or "")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t).strip("_").lower()
    return t or "char"


__all__ = ["StoryUnderstanding", "UEvent", "parse_understanding", "validate_understanding",
           "understanding_block", "validate_script", "script_spoken_chars",
           "understanding_gate", "script_gate", "validate_plan_coverage"]
