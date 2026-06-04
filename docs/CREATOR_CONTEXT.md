# CreatorContext

**Status:** Stable contract (schema v1, Sprint 3)
**Module:** `backend/app/domain/creator_context.py`
**Persistence:** Nested key `creator_prefs.prefs_json.creator_context` (NO schema migration)
**API:** `GET/PUT /api/settings/creator-context`

The `CreatorContext` is the channel-/persona-level editorial signal an
AI Director should bias on before emitting a RenderPlan. Unlike the
RenderPlan, the CreatorContext is **persistent across renders** — set
once per app instance, consumed by every subsequent LLM call.

## Why this exists

Before Sprint 3 the AI prompt had only the transcript + the
per-render `editorial_hint` derived from `payload.hook_strength` and
`payload.video_type`. There was no way to bias the LLM toward a
creator's house style — every job started from a blank persona.

The CreatorContext gives operators a single, persistent place to
describe the channel persona that should colour every clip
selection: channel name, brand voice, target audience, content
pillars, market, language, and a free-form editorial brief.

## Schema (v1)

```
CreatorContext
├── schema_version: int = 1
├── creator_id: str = ""
├── channel_name: str = ""
├── brand_voice: str = ""
├── target_audience: str = ""
├── content_pillars: list[str] = []
├── market: str = ""
├── language: str = ""
└── notes: str = ""
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `schema_version` | int | 1 | Bumped only on breaking shape change. |
| `creator_id` | str | "" | Opaque ID for future multi-creator routing. |
| `channel_name` | str | "" | Display name surfaced in logs and the UI. |
| `brand_voice` | str | "" | `viral \| educational \| entertaining \| authentic` (free-form — LLM tolerant). |
| `target_audience` | str | "" | `us \| eu \| jp \| vn \| global` (free-form). |
| `content_pillars` | list[str] | [] | Topic anchors. Accepts CSV string on read for forward-compat (`"a, b, c"` → `["a", "b", "c"]`). |
| `market` | str | "" | Shares vocabulary with `RenderPlan.SubtitlePolicy.market`. |
| `language` | str | "" | BCP-47 hint (`"vi"`, `"en"`, `"ja"`, …). |
| `notes` | str | "" | Free-form editorial brief; rendered verbatim into the AI prompt hint. |

## Serialisation contract

| Method | Behaviour |
|---|---|
| `CreatorContext.to_json()` | Deterministic — sorted keys, compact separators, `ensure_ascii=False`. |
| `CreatorContext.from_json(raw)` | Defensive — returns `None` on unparseable / non-object input. Unknown keys dropped, primitives coerced (string `"123"` → string `"123"`, bool `True` → string `"True"`, etc.). Never raises (Sacred Contract #3 spirit). |
| `CreatorContext.is_empty()` | True when every field is empty / blank — used by the builder to short-circuit empty contexts to a `None` return so the AI prompt skips the editorial hint entirely. |
| `CreatorContext.to_prompt_hint()` | Renders a deterministic one-line `"Channel: ... \| Brand voice: ... \| Target audience: ... \| ..."` string suitable for the existing `editorial_hint` parameter of `prompts.build_segment_prompt` / `build_render_plan_prompt`. Empty context → `""`. |

The hint format intentionally uses no `{}` characters in the rendered
output so the downstream `.format()` chain in `prompts.py` cannot
re-format any user-supplied text — pinned by
`test_creator_context_dataclass.py::test_hint_contains_no_format_placeholders`.

## Persistence (no schema migration)

The Sprint 3 plan originally specified additive columns on
`creator_prefs`. Audit (Sprint 3.1) showed the table already had a
`prefs_json TEXT DEFAULT '{}'` column from earlier sprints. The
implemented design stores the CreatorContext **as a nested key** inside
that existing JSON blob, so **no DB migration** was needed:

```
creator_prefs (id INTEGER PRIMARY KEY CHECK (id = 1),
               prefs_json TEXT DEFAULT '{}',
               updated_at TEXT)

→ prefs_json = {
     "ui_theme": "dark",      # other top-level prefs untouched
     "creator_context": {     # ← Sprint 3 nested payload
        "channel_name": "...",
        "brand_voice": "...",
        ...
     }
  }
```

Repository helpers in `backend/app/db/creator_repo.py`:

```python
get_creator_prefs() -> dict
upsert_creator_prefs(prefs: dict) -> dict

# Sprint 3 additions:
get_creator_context() -> Optional[CreatorContext]
upsert_creator_context(context: Optional[CreatorContext]) -> Optional[CreatorContext]
```

Both new helpers wrap their DB access in `try/except` — a transient
persistence failure logs a warning and returns `None` rather than
crashing a live render. Other top-level `prefs_json` keys are
preserved on every upsert and on clear (`upsert_creator_context(None)`
removes the `creator_context` key without touching `ui_theme` or any
other neighbour).

## Builder layer

`backend/app/ai/context/creator_context.py` exposes
`CreatorContextBuilder` — a thin façade in front of `creator_repo` that:

1. Reads the persisted context.
2. Returns `None` when no context exists OR when the persisted context
   is `is_empty()` (the two states are functionally equivalent — the
   AI prompt skips the editorial hint either way).
3. Provides a Sprint-4+ extension seam (`_enrich`) where future
   sprints will mix in derived signals (clip feedback ranking,
   channel performance bias, etc.). Sprint 3 ships this as a
   pure pass-through.
4. Module-level convenience wrapper `build_creator_context()` so
   callers (the LLM stage) import a single function rather than
   instantiate the class.

Every public entry point catches all exceptions and surfaces `None` —
Sacred Contract #3 is absolute for the AI layer.

## API

| Method | Path | Body / Response |
|---|---|---|
| GET | `/api/settings/creator-context` | → `CreatorContextEnvelope` |
| PUT | `/api/settings/creator-context` | `CreatorContextPayload` body → `CreatorContextEnvelope` |

```typescript
interface CreatorContextPayload {
  creator_id: string
  channel_name: string
  brand_voice: string
  target_audience: string
  content_pillars: string[]
  market: string
  language: string
  notes: string
}

interface CreatorContextEnvelope {
  is_configured: boolean
  creator_context: CreatorContextPayload
}
```

`is_configured` is `false` when the persisted context is missing or
empty. A `PUT` with an all-blank payload clears the persisted context;
a subsequent `GET` returns `is_configured=false` + a default-shaped
payload so the frontend can render the same form unconditionally.

Backend uses Pydantic's `extra="ignore"` so older / newer clients
that include extra fields are not 422'd (same backward-compat
pattern Sprint 1.2 introduced on `PrepareSourceRequest`).

## Frontend

`frontend/src/api/creatorContext.ts` — typed client:

```typescript
export const BLANK_CREATOR_CONTEXT: CreatorContextPayload
export async function getCreatorContext(): Promise<CreatorContextEnvelope>
export async function putCreatorContext(body: CreatorContextPayload): Promise<CreatorContextEnvelope>
```

`frontend/src/features/settings/SettingsScreen.tsx` — `CreatorContextSection`
panel above the system-info panels. 8 form fields (channel,
brand_voice, target_audience, content_pillars as CSV, market,
language, editorial brief) + status badge (`CHƯA / ĐÃ CẤU HÌNH`) +
Save and Clear buttons.

The CSV ↔ list[str] conversion lives entirely in the UI — the wire
shape stays `list[str]`. The textarea for `notes` accepts any
characters including curly braces; the prompt-hint formatter strips
nothing.

## AI integration

Sprint 3 wired CreatorContext into the existing
`_build_editorial_hint(payload)` helper at
`backend/app/orchestration/llm_stage.py`. The helper now:

1. Builds the legacy payload-derived hint (`hook_strength` +
   `video_type`).
2. Calls `build_creator_context()`. If it returns a non-empty
   CreatorContext, appends `.to_prompt_hint()` to the legacy hint
   with `" | "` separator.
3. Wraps the whole append in `try/except` — a failure in the AI
   context layer never affects the legacy hint.

The combined hint is then handed to `prompts.build_segment_prompt`
(legacy LLM path) AND to `prompts.build_render_plan_prompt`
(Sprint 4.B → 4.D AI emission path) without modification. The
prompt's `{editorial_section}` placeholder receives the hint verbatim
as a literal substring — no second `.format()` pass — so curly
braces in the hint never KeyError.

## Sacred Contracts touched

- **#2 RenderRequest defaults** — `CreatorContext` is never a render
  payload field; it lives in `creator_prefs.prefs_json` and is read
  via the builder at LLM stage time. Nothing about the per-render
  payload shape changed.
- **#3 AI modules return None on failure** — every helper involved
  (`get_creator_context`, `upsert_creator_context`, `CreatorContextBuilder.build`,
  `build_creator_context`) catches all exceptions and surfaces `None`.
  The LLM stage's hint append is itself wrapped in `try/except`.
- **#7 SQLite additive-only** — no schema change. The existing
  `creator_prefs.prefs_json TEXT DEFAULT '{}'` column carries the new
  payload at a nested key. Pre-Sprint-3 prefs blobs without the
  `creator_context` key read as "no context configured" → builder
  returns `None` → LLM behaviour byte-identical baseline.

## Sprint trail

| Sprint | Contribution | Key commits |
|---|---|---|
| 3 | Dataclass + repo helpers + builder + `llm_stage._build_editorial_hint` wire-up | `3daa41d` |
| 3-FE | `/api/settings/creator-context` endpoint + `SettingsScreen` UI + vitest | `62133a3` |
