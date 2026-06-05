# RenderPlan

**Status:** Stable contract (schema v1, Sprint 2.1 → Sprint 4)
**Module:** `backend/app/domain/render_plan.py`
**Persistence:** `jobs.render_plan_json TEXT NULL` (migration 0001, Sprint 2.1)

The `RenderPlan` is the single dataclass an AI Director hands to the
Render Engine. It describes WHICH clips to extract from a source video
and HOW each clip should be subtitled, framed, mixed, and overlaid. The
Render Engine never decides those things itself — it executes what the
plan says.

## Why this exists

Before Sprint 4 the decisions a final render needs were scattered across
the orchestration pipeline:

- subtitle style → `stages/part_asset_planner.py:395-419` (variant /
  creator / platform / DNA fallback chain)
- camera reframe → `stages/part_render_setup.py:202, 228`
  (`payload.motion_aware_crop`, `payload.reframe_mode`)
- per-clip rank → `render_pipeline.py:1037` (score-descending sort over
  per-part `output_score`)

Each decision was independently tunable in the legacy stack and the AI
layer's only contribution was the segment list (`LLMSegment`). The
RenderPlan unifies those decisions so that:

1. The AI Director can decide all of them in one round-trip.
2. The Render Engine has a single, ordered, defaulted shape to read.
3. Operators can grep one column (`jobs.render_plan_json`) for any
   field instead of reading per-stage logs.

## Schema (v1)

```
RenderPlan
├── schema_version: int = 1
├── clips: list[ClipPlan]
├── subtitle_policy: SubtitlePolicy
├── camera_strategy: CameraStrategy
├── audio_plan: AudioPlan
├── output_config: OutputConfig
├── overlays: list[dict]
└── creator_context_id: str = ""
```

### `ClipPlan`

One per output clip. Position in `clips` is meaningful — it is the
canonical order the orchestrator iterates parts.

| Field | Type | Default | Notes |
|---|---|---|---|
| `start` | float | 0.0 | seconds, ≥ 0 |
| `end` | float | 0.0 | seconds, ≤ `video_duration + 1.0` |
| `rank` | int | 0 | 1-based rank within the plan. `0` = "let backend decide" (Sprint 4.G fallback). |
| `score` | float | 0.0 | 0.0–1.0 |
| `clip_name` | str | "" | filesystem-safe stem; may be empty |
| `title` | str | "" | display title (≤ 120 chars) |
| `reason` | str | "" | model's editorial rationale (≤ 300 chars) |
| `hook_type` | str | "" | `question \| reveal \| contrast \| humor \| emotion \| statement` |
| `content_type` | str | "" | `interview \| vlog \| tutorial \| commentary \| montage \| gaming` |
| `viral_score` | float | 0.0 | 0.0–1.0 |
| `hook_score` | float | 0.0 | 0.0–1.0 |
| `retention_score` | float | 0.0 | 0.0–1.0 |
| `speech_density` | float | 0.0 | 1.0 = dense dialogue, 0.0 = pure visual |
| `duration_fit` | float | 0.0 | 1.0 = ideal short-form length |
| `cover_offset_ratio` | float | 0.0 | thumbnail moment as fraction of clip |

### `SubtitlePolicy`

Per-render subtitle decision. Consumed by `part_asset_planner` since
Sprint 4.E.

| Field | Type | Default | Vocabulary |
|---|---|---|---|
| `style` | str | "" | `viral \| clean \| story \| gaming` + 6 registered preset_ids: `tiktok_bounce_v1`, `viral_bold`, `story_clean_01`, `clean_pro`, `boxed_caption`, `pro_karaoke`. Unknown values soft-fall back. |
| `market` | str | "" | `us \| eu \| jp \| vn \| global \| ""` ("" = inherit upstream) |
| `emphasis_pass` | bool | false | Deferred — consume not migrated in Sprint 4.E because the bool can't disambiguate "default False" from "explicit False" without flipping baseline. |
| `line_break_rule` | str | "" | Deferred — consume not migrated; would require extending `apply_market_line_break_to_srt`'s signature. |

### `CameraStrategy`

Per-render camera reframe + motion decision. Consumed by
`part_render_setup` since Sprint 4.F.

| Field | Type | Default | Vocabulary |
|---|---|---|---|
| `motion_aware_crop` | bool | false | Deferred — same disambiguation blocker as `SubtitlePolicy.emphasis_pass`. |
| `reframe_mode` | str | "" | `center \| track \| fixed \| ""` ("" = legacy `payload.reframe_mode` fallback, defaulting to `"subject"`). Builder shim normalised `"subject" → "track"` while it existed (Sprint 2.2). Unknown values soft-fall back. |
| `tracker` | str | "" | `bytetrack \| trackerless \| legacy \| ""`. Deferred — no orchestration call site reads it; dispatch lives inside `services/motion_crop.py`. |

### `AudioPlan`

Per-render audio decision. Consumed by future stage migration (not in
Sprint 4 scope).

| Field | Type | Default | Notes |
|---|---|---|---|
| `voice_enabled` | bool | false | inherit `payload.voice_enabled` semantics |
| `voice_provider` | str | "" | inherit `payload.tts_engine` semantics (`edge \| xtts`) |
| `bgm_enabled` | bool | false | |
| `cta_audio` | str | "" | path to optional CTA audio overlay |

### `OutputConfig`

Per-render encoder parameters. Not consumed by Sprint 4 stages — these
remain `payload`-derived in the FFmpeg call sites.

| Field | Type | Default |
|---|---|---|
| `codec` | str | "" |
| `preset` | str | "" |
| `crf` | int | 0 |
| `fps` | int | 0 |
| `width` | int | 0 |
| `height` | int | 0 |

### `overlays`

`list[dict]` of overlay descriptors. Loose shape so the AI Director can
add new overlay kinds without a schema bump.

Recognised `kind` values:

- `{"kind": "title", "text": str}`
- `{"kind": "cta", "type": "comment | part_2 | follow | auto"}`
- `{"kind": "hook", "text": str}`

### `creator_context_id`

Opaque ID referencing the `CreatorContext` (Sprint 3) that informed AI
choices. Sprint 4 does not read it; reserved for Sprint 5+ when
Creator Context becomes a render-time signal.

## Serialisation contract

| Method | Behaviour |
|---|---|
| `RenderPlan.to_json()` | Deterministic — sorted keys, compact separators (`","`, `":"`), `ensure_ascii=False` so Vietnamese / CJK characters survive verbatim. |
| `RenderPlan.from_json(raw)` | Defensive — returns `None` on unparseable / non-object input. Unknown top-level keys silently dropped. Wrong-shape sub-blocks fall back to default sub-dataclasses. Primitives are coerced (`"22" → int 22`, `"true" → bool True`). **Never raises** (Sacred Contract #3 spirit). |

The two helpers are pure-stdlib; no third-party dependency.

## Persistence

| Column | Table | Type | Migration |
|---|---|---|---|
| `render_plan_json` | `jobs` | `TEXT DEFAULT NULL` | `migration_steps/0001_jobs_add_render_plan_json.py` (Sprint 2.1) |

Repository helpers in `backend/app/db/jobs_repo.py`:

```python
update_render_plan(job_id: str, plan_json: str | None) -> None
get_render_plan(job_id: str) -> str | None
```

Both helpers wrap their DB access in `try/except` — a transient
persistence failure logs a warning and returns silently rather than
crashing a live render (Sacred Contract #3).

## Pipeline flow

```
┌────────────────────────────────────────────────────────────────────┐
│ 1. orchestration/llm_pipeline.run_llm_pre_render()                 │
│      ↓ produces LLMPreRenderResult.scored: list[dict]              │
├────────────────────────────────────────────────────────────────────┤
│ 2. render_pipeline.py — RenderPlan acquisition (Sprint 4.D + 4.H)  │
│      ↓ if LLM_EMIT_RENDER_PLAN=1:                                  │
│      ↓   ai.llm.select_render_plan() → Optional[RenderPlan]        │
│      ↓ else:                                                       │
│      ↓   _render_plan = None  (Sprint 4.H — no shim fallback)      │
│      ↓                                                             │
│      ↓ if _render_plan is not None:                                │
│      ↓   jobs_repo.update_render_plan(job_id, plan.to_json())      │
│      ↓   emit render.plan.persisted + render.plan.ai_emitted       │
├────────────────────────────────────────────────────────────────────┤
│ 3. PartRenderContext.render_plan = _render_plan                    │
├────────────────────────────────────────────────────────────────────┤
│ 4. Stage consume sites read ctx.render_plan with safe fallbacks:   │
│      stages/part_asset_planner.py  → SubtitlePolicy.style+market   │
│      stages/part_render_setup.py   → CameraStrategy.reframe_mode   │
│      render_pipeline.py P5-1       → ClipPlan.rank (env-flag gate) │
└────────────────────────────────────────────────────────────────────┘
```

## Feature flag

`LLM_EMIT_RENDER_PLAN` (env var, strict `== "1"`).

- **OFF (default):** AI emission skipped, `ctx.render_plan` stays None,
  every stage resolver returns the legacy fallback value. Baseline
  behaviour byte-identical to pre-Sprint-4.
- **ON:** AI emission attempted. Success → consume. Failure / None →
  `ai_fallback` event + `ctx.render_plan` stays None + stage fallbacks.

The flag is read at module load in `render_pipeline.py` for the wire-up
itself, and per-call inside `pipeline_ranking._resolve_rank_from_plan`
(so tests can monkeypatch without module reload).

## Events emitted

| Event | When | Level | Context keys |
|---|---|---|---|
| `render.plan.ai_emitted` | AI emission returned a non-None RenderPlan | INFO | `clips_count`, `schema_version`, `provider` |
| `render.plan.ai_fallback` | AI returned None or raised | WARNING | `reason`, optionally `error_type` |
| `render.plan.persisted` | Plan saved to `render_plan_json` | INFO | `clips_count`, `schema_version` |
| `output_rank_computed` | Per-part ranking entry built | INFO | `+ rank_source` (Sprint 4.G) |
| `output_ranking_completed` | Final rank sort + best-clip selection | INFO | `+ rank_source` (Sprint 4.G) |
| `camera_strategy_applied` | Per-part camera resolved | INFO | `reframe_mode`, `reframe_mode_source`, `motion_aware_crop`, `camera_mode`, `aspect_ratio` |
| `subtitle_style_applied` | Per-part subtitle resolved | INFO | `subtitle_style`, `subtitle_style_source`, ... |

All events use the canonical `_emit_render_event` signature (Sacred
Contract #6 — frozen) with one of three additive `*_source` keys
documenting the resolver provenance:

- `subtitle_style_source ∈ { auto, explicit, render_plan, fallback_invalid_style }`
- `reframe_mode_source ∈ { fallback, render_plan, fallback_invalid_reframe }`
- `rank_source ∈ { fallback, render_plan, fallback_no_plan_rank, fallback_rank_collision, fallback_rank_invalid }`

## Versioning policy

| Change | Schema bump? | Backward compat |
|---|---|---|
| Add a new field with a safe default | No | Existing payloads deserialise with the new field at its default. |
| Add a new sub-dataclass field | No | Same. `RenderPlan.from_json` returns the default sub-dataclass when missing. |
| Rename / remove a field | Yes — bump `SCHEMA_VERSION` | Provide an `_migrate_from_vN` step inside `_from_dict`. |
| Change a field's type | Yes | Same. |

The `from_json` helper inspects `schema_version` and runs the
appropriate migration step before instantiating sub-dataclasses. v1
(Sprint 2.1) is the current shape; no migration steps exist yet.

## Sacred Contracts touched

- **#1 result_json aliases** — `output_rank_score`, `is_best_output`,
  `is_best_clip` are set unconditionally inside
  `_compute_output_ranking_entry` (`pipeline_ranking.py:237-238`).
  Neither the consume nor fallback rank path can drop them.
- **#2 RenderRequest defaults** — `render_plan_json` is `NULL` by
  default; `LLM_EMIT_RENDER_PLAN` defaults **ON since Sprint 7.6a
  (2026-06-05)** — operators set `LLM_EMIT_RENDER_PLAN=0` to revert
  to the pre-Sprint-7.6a baseline. Every resolver still returns the
  legacy fallback when `ctx.render_plan is None` (per-field merge),
  and the dual-mode try/except at `render_pipeline.py:457-552`
  guarantees AI emission failure cannot crash a render. See
  `docs/review/SPRINT_7_6a_LLM_FLAG_FLIP_2026-06-05.md`.
- **#3 AI modules return None on failure** — every helper involved
  (`select_render_plan`, `parse_render_plan_response`,
  `update_render_plan`, `get_render_plan`, every `_resolve_*_from_plan`)
  catches all exceptions and surfaces `None`.
- **#6 `_emit_render_event` signature** — frozen. Sprint 4 added new
  event names + new context keys, never changed the kwargs shape.
- **#7 SQLite additive-only** — `render_plan_json` was added with a
  `DEFAULT NULL`, no DROP, no RENAME, no type change.

## Sprint trail

| Sprint | Contribution | Key commits |
|---|---|---|
| 2.1 | Dataclass + DB column + `migration_steps/0001` + `jobs_repo` helpers | `ddc7065` |
| 2.2 | Builder shim (deleted in 4.H) | `66e3ab7` |
| 2.3 | Pipeline wire-up via PartRenderContext (Render Edit Protocol) | `0848d3a` |
| 4.A | Parser dual-mode — `parse_render_plan_response` | `7b3b758` |
| 4.B | Prompt dual-mode — `build_render_plan_prompt` | `70a1d94` |
| 4.C | Provider dispatch dual-mode — `select_render_plan` ×3 + dispatcher | `e2ac767` |
| 4.D | Flag-gated AI emission path (Render Edit Protocol) | `ae19d25` |
| 4.E | `subtitle_policy.style` + `.market` consume (Render Edit Protocol) | `ac5a65e` |
| 4.F | `camera_strategy.reframe_mode` consume (Render Edit Protocol) | `514d60a` |
| 4.G | `ClipPlan.rank` consume + env-flag gate (Render Edit Protocol) | `fcd9184` |
| 4.H | Builder shim retirement | `dbd758a` |
