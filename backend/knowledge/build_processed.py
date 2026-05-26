"""
build_processed.py — Convert knowledge packs (packs/*.json) to FAISS-indexed JSONL format.

Reads packs with domains: market, retention, camera, creator, hook, pacing, subtitle.
Writes to processed/ with filenames matching domain.

Run from backend/ directory:
  python knowledge/build_processed.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PACKS_DIR = Path(__file__).parent / "packs"
PROCESSED_DIR = Path(__file__).parent / "processed"

PLATFORM_TAGS = {"tiktok", "youtube_shorts", "instagram_reels", "youtube", "reels", "shorts"}
NICHE_TAGS = {
    "lifestyle", "education", "entertainment", "comedy", "tutorial", "how_to",
    "travel", "food", "fitness", "sport", "finance", "music", "dance", "review",
    "ugc", "vlog", "community", "diy", "beauty", "fashion", "personal_brand",
    "brand", "commercial", "mental_health", "economics", "science", "history",
    "talking_head", "hook", "subtitle", "ecommerce",
}
DOMAIN_TO_TYPE = {
    "market":    "market_rule",
    "retention": "retention_rule",
    "camera":    "camera_rule",
    "creator":   "creator_rule",
    "hook":      "hook_pattern",
    "pacing":    "pacing_rule",
    "subtitle":  "subtitle_rule",
    "audio":     "audio_rule",
}
DOMAIN_TO_FILE = {
    "market":    "market_rules.jsonl",
    "retention": "retention_rules.jsonl",
    "camera":    "camera_rules.jsonl",
    "creator":   "creator_rules.jsonl",
    "hook":      "hook_rules_v2.jsonl",
    "pacing":    "pacing_rules_v2.jsonl",
    "subtitle":  "subtitle_rules_v2.jsonl",
    "audio":     "audio_rules.jsonl",
}

# Only convert these domains (hook/pacing/subtitle already have v1 JSONL files)
CONVERT_DOMAINS = {"market", "retention", "camera", "creator", "hook", "pacing", "subtitle", "audio"}


def _extract_platforms(applies_to: list[str]) -> list[str]:
    platforms = [t for t in applies_to if t in PLATFORM_TAGS]
    return platforms if platforms else ["tiktok", "youtube_shorts", "instagram_reels"]


def _extract_niches(applies_to: list[str]) -> list[str]:
    niches = [t for t in applies_to if t in NICHE_TAGS]
    return niches if niches else ["general"]


def _extract_duration_range(rec: dict) -> list[int]:
    lo = rec.get("target_duration_min", 0)
    hi = rec.get("target_duration_max", 120)
    return [int(lo), int(hi)]


def _extract_style(rec: dict) -> list[str]:
    styles = []
    sub = rec.get("subtitle_emphasis")
    if sub:
        styles.append(sub)
    hook_type = rec.get("hook_type")
    if hook_type:
        styles.append(hook_type)
    return styles if styles else ["general"]


def _build_render_usage(rec: dict) -> dict:
    usage: dict = {}
    if rec.get("hook"):
        usage["hook"] = True
    if rec.get("hook_type"):
        usage["hook_type"] = rec["hook_type"]
    if rec.get("hook_position"):
        usage["hook_position"] = rec["hook_position"]
    if rec.get("subtitle_emphasis"):
        usage["subtitle_emphasis"] = rec["subtitle_emphasis"]
    if rec.get("subtitle_words_per_block"):
        usage["subtitle_words_per_block"] = rec["subtitle_words_per_block"]
    if rec.get("subtitle_font_style"):
        usage["subtitle_font_style"] = rec["subtitle_font_style"]
    if rec.get("subtitle_position"):
        usage["subtitle_position"] = rec["subtitle_position"]
    if rec.get("subtitle_must_carry_full_meaning"):
        usage["subtitle_must_carry_full_meaning"] = True
    if rec.get("highlight_per_word"):
        usage["highlight_per_word"] = True
    if rec.get("loop_structure"):
        usage["loop_structure"] = True
    pacing = rec.get("pacing")
    if isinstance(pacing, dict):
        lo = pacing.get("cut_interval_min")
        hi = pacing.get("cut_interval_max")
        if lo is not None and hi is not None:
            usage["pacing"] = f"{lo}-{hi}s"
    if rec.get("target_retention_3s"):
        usage["target_retention_3s"] = rec["target_retention_3s"]
    if rec.get("target_retention"):
        usage["target_retention"] = rec["target_retention"]
    return usage if usage else {"general": True}


def convert_pack(pack_path: Path) -> list[dict]:
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    domain = data.get("domain", "")
    if domain not in CONVERT_DOMAINS:
        return []

    item_type = DOMAIN_TO_TYPE[domain]
    items = []
    for rule in data.get("rules", []):
        applies_to = rule.get("applies_to", [])
        rec = rule.get("recommendation", {})
        item = {
            "id": rule["id"],
            "type": item_type,
            "platform": _extract_platforms(applies_to),
            "niche": _extract_niches(applies_to),
            "duration_range": _extract_duration_range(rec),
            "style": _extract_style(rec),
            "rule": rule["title"] + " — " + rule["description"],
            "render_usage": _build_render_usage(rec),
            "weight": float(rule.get("confidence", 0.8)),
            "tags": list(set(applies_to)),
        }
        items.append(item)
    return items


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pack_files = sorted(PACKS_DIR.glob("*.json"))
    if not pack_files:
        print("No pack files found in", PACKS_DIR)
        sys.exit(1)

    # Group items by domain
    domain_items: dict[str, list[dict]] = {}
    for pack_path in pack_files:
        try:
            data = json.loads(pack_path.read_text(encoding="utf-8"))
            domain = data.get("domain", "")
            items = convert_pack(pack_path)
            if items:
                domain_items.setdefault(domain, []).extend(items)
                print(f"  {pack_path.name}: {len(items)} rules ({domain})")
        except Exception as exc:
            print(f"  SKIP {pack_path.name}: {exc}")

    # Write JSONL per domain
    total = 0
    for domain, items in domain_items.items():
        out_file = PROCESSED_DIR / DOMAIN_TO_FILE[domain]
        with out_file.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        total += len(items)
        print(f"  -> wrote {len(items)} items to {out_file.name}")

    print(f"\nTotal: {total} items written across {len(domain_items)} domain files.")


if __name__ == "__main__":
    main()
