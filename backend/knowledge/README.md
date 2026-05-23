# Knowledge Base — Local AI Render Knowledge

This directory contains the **local-first knowledge** used by the render AI for
filter-based platform and video-quality rule retrieval.

No external LLM is required at render runtime. All knowledge is loaded from
these files on startup and retrieved by matching user filters.

---

## Directory Structure

```
knowledge/
├── raw/
│   ├── video_samples/     — Reserved for sample video file references (empty)
│   ├── transcripts/       — Reserved for transcript source files (empty)
│   └── research_notes/    — Reserved for human-authored research notes (empty)
├── processed/
│   ├── platform_rules.jsonl   — Platform encoding and format constraints
│   ├── hook_patterns.jsonl    — Opening hook patterns for retention
│   ├── subtitle_rules.jsonl   — Subtitle readability and formatting rules
│   ├── pacing_rules.jsonl     — Cut pacing and timing patterns
│   ├── visual_rules.jsonl     — Visual quality rules (brightness, blur, etc.)
│   ├── cta_patterns.jsonl     — Call-to-action placement patterns
│   └── failure_patterns.jsonl — Known failure modes and QA checks
└── index/
    └── faiss.index            — FAISS vector index (generated; not committed)
```

---

## Knowledge Item Schema

Each line in a `.jsonl` file is one JSON object:

```json
{
  "id":            "unique_id_001",
  "type":          "hook_pattern | platform_rule | subtitle_rule | pacing_rule | visual_rule | cta_pattern | failure_pattern",
  "platform":      ["tiktok", "reels", "shorts", "youtube"],
  "niche":         ["education", "marketing", "entertainment", "general"],
  "duration_range": [min_seconds, max_seconds],
  "style":         ["viral", "talking_head", "b-roll", "any"],
  "rule":          "Human-readable description of the rule.",
  "render_usage":  { "key": "value" },
  "weight":        0.0–1.0,
  "tags":          ["tag1", "tag2"]
}
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `id` | string | Globally unique identifier (snake_case, no spaces) |
| `type` | string | Knowledge type — controls which retriever queries this file |
| `platform` | string[] | Target platforms this rule applies to |
| `niche` | string[] | Creator niches this rule is relevant for |
| `duration_range` | [int, int] | Min/max clip duration in seconds where this rule applies |
| `style` | string[] | Visual/content style tags |
| `rule` | string | Plain-English description of the rule or pattern |
| `render_usage` | dict | Structured hints consumed by the render pipeline (e.g. `aspect_ratio`, `cut_interval_range`, `qa_check`) |
| `weight` | float | Confidence/relevance score 0.0–1.0 (used for ranking when multiple rules match) |
| `tags` | string[] | Free-form tags for filtering and indexing |

---

## Usage in the Render Pipeline

1. **User submits render filters**: `platform`, `niche`, `style`, `duration`, `aspect_ratio`,
   `subtitle_style`, `output_count`, `target_goal`.
2. **Knowledge retriever** matches filters against `.jsonl` files by `platform`, `niche`,
   `duration_range`, and `style` fields.
3. **Top-N matching rules** (by `weight`) are assembled into a `CreativeBrief`.
4. The `CreativeBrief` drives deterministic render parameters (pacing, subtitle style,
   visual checks, CTA placement).
5. **QA pipeline** verifies the output against `render_usage.qa_check` fields from failure patterns.

---

## Adding New Knowledge

- Each `.jsonl` file uses one JSON object per line (no trailing commas, no arrays).
- Validate with: `python -c "import json; [json.loads(l) for l in open('processed/hook_patterns.jsonl')]"`
- After adding items, delete `index/faiss.index` to trigger index rebuild on next server start.

---

## FAISS Index

The `index/faiss.index` file is generated automatically from `processed/*.jsonl` on server
startup when it does not exist. It is **not committed to git** (see `.gitignore`).

If no knowledge files exist, the system degrades gracefully — a warning is logged and
renders proceed without AI knowledge augmentation.

---

## AI Governance

- Knowledge is retrieved by **filter matching**, not by semantic LLM queries at runtime.
- Cloud AI may be used **offline** to generate or curate knowledge items, but is never
  called during a render job.
- The runtime works fully **offline** once `index/faiss.index` is built.
- `memory_store` (in `app/ai/rag/`) is **RAG infrastructure** for render experience memory.
  `knowledge/` is **platform/video-quality knowledge** — these are separate concerns.
