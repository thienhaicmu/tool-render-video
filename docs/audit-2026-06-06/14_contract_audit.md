# 14 — FE ↔ BE Contract Audit

Field-by-field comparison of the 10 most-trafficked contracts. Authority: Pydantic models in `backend/app/models/schemas.py` + per-route inline models, vs handwritten TS in `frontend/src/types/api.ts` + per-client `frontend/src/api/*.ts`.

> Context: Phase 5 FINDING-T05 noted there is no CI enforcement of `npm run check:openapi-drift`. Phase 6 FINDING-API09 noted `extra="ignore"` on `RenderRequest` silently drops unknown fields. These two together create the largest single risk surface in this audit.

---

## Contracts examined

| # | Contract | BE source | FE source | Drift verdict |
|---|---|---|---|---|
| 1 | `RenderRequest` (POST /api/render/process) | `schemas.py:111-475` | `types/api.ts:70-194` + `RenderWorkflow.tsx` | **5 issues** |
| 2 | `PrepareSourceRequest/Response` | `schemas.py:39-46` + `router.py:350` | `render.ts:48-67` | clean |
| 3 | `JobAiSummary` | `routes/jobs.py:376-443` (dict) | `jobs.ts:121-164` | **1 issue** |
| 4 | WebSocket event (Sacred Contract #6) | `routes/jobs.py:680` | `RenderSocketClient.ts:131-146` | clean |
| 5 | `Job` + `JobPart` (GET /api/jobs/{id}) | `schemas.py:877-893` + `routes/jobs.py:370` | `types/api.ts:227-270` | **3 issues** |
| 6 | `QualityReport` | `routes/jobs.py:544-580` (dict) | `types/api.ts:284-292` | clean |
| 7 | Editing (Trim/Rerender/Export) | `editing/router.py:38-52` | `editing.ts` | clean |
| 8 | `CreatorContext` | `routes/settings.py:36-97` | `creatorContext.ts:17-32` | clean |
| 9 | Feedback | `routes/feedback.py:33-55` | `feedback.ts:12-36` | minor |
| 10 | Downloader job shapes | `features/download/router.py:104-120` | `platformDownloader.ts:3-102` | minor |

---

## Top 5 risks (sorted by severity × usage)

### FINDING-C01 (HIGH) — `RenderRequest.part_order` accepts an enum the BE never honors

[schemas.py:157](../../backend/app/models/schemas.py): `part_order: Optional[str] = "viral"` — no validator.

[types/api.ts:94](../../frontend/src/types/api.ts) constrains FE to `'viral' | 'sequential'`. The FE happily sends `'sequential'`. The BE accepts it (because `extra="ignore"` doesn't trigger and the key is in the model). The downstream pipeline does not branch on `'sequential'` — segments come out in viral-rank order regardless.

**Impact:** silent UX-vs-behavior mismatch. User picks "sequential" → gets viral-ordered output → has no idea why.

**Fix:** add Pydantic validator that rejects unknown values or actually wires `sequential` into the ranking step.

### FINDING-C02 (HIGH) — Cloud LLM API keys travel in plaintext POST body

[schemas.py:312-391](../../backend/app/models/schemas.py): `ai_cloud_api_key`, `gemini_api_key`, `openai_api_key`, `claude_api_key` are all plain `Optional[str]`.

[RenderWorkflow.tsx](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx) reads from `localStorage` and includes in `buildPayload()`. The BE then writes the whole payload to `jobs.payload_json` for resume/replay.

**Impact:**
- Plaintext credentials in DB column `payload_json` → forever (no scrubbing).
- Plaintext in per-job logs (event emission includes payload context in some sites).
- Anything that ever exports a job (debug dump, support bundle) leaks the key.

(Repeats Phase 1 FINDING-F07 and Phase 4 BR02-adjacent concerns.)

**Fix:** require server-side `.env` keys; backend rejects any `*_api_key` field in incoming RenderRequest. FE drops the input control or only uses it for the *test-cloud-ai* endpoint where the key is consumed inline and not stored.

### FINDING-C03 (HIGH) — `JobPart` FE type declares fields not present in DB or route

[types/api.ts:254-270](../../frontend/src/types/api.ts) declares:

```ts
clip_name?: string;
ai_title?: string;
ai_reason?: string;
source?: string;
```

The DB `job_parts` schema (Phase 1) has no such columns. [routes/jobs.py:370](../../backend/app/routes/jobs.py) returns `list_job_parts(job_id)` which is just the DB row.

Either these fields are **injected somewhere later** (e.g., merged from `result_json` per part by an additional helper) or the TS type is **aspirational** (planned feature that never landed). Today, the FE reads `.clip_name` etc. and gets `undefined`.

**Fix:** trace the actual injection point in the route or remove the fields from the TS type. Add a comment one way or the other.

### FINDING-C04 (HIGH) — `extra="ignore"` blocks contract-evolution detection

[schemas.py:117](../../backend/app/models/schemas.py): `model_config = ConfigDict(extra="ignore")` on `RenderRequest` (and `PrepareSourceRequest`).

Documented reason: replay of stored payloads with deprecated `groq_*` keys must not 422. Real cost: during a phased rollout when FE deploys before BE, new FE fields are silently dropped — no 422, no warning, no log. The render runs but without the new feature. Debugging this is hours of "why didn't the flag take effect".

**Fix (recommended):** split into two models.

```python
class RenderRequestStrict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # used by POST /api/render/process

class RenderRequestLenient(BaseModel):
    model_config = ConfigDict(extra="ignore")  # used by resume/replay paths
```

Couple this with FE-side strict typing (already there in `api.ts`) and the contract becomes self-policing.

### FINDING-C05 (MED) — Default value drift on `target_platform`

[schemas.py:275](../../backend/app/models/schemas.py): BE default `"youtube_shorts"`.

[RenderWorkflow.tsx:~34](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx): FE default `"tiktok"`.

When the FE form is in its initial state and the user submits without touching the platform selector, what gets sent depends on whether the FE always-includes-the-field (whatever `cfg.target_platform` is, default `"tiktok"`) or sometimes-omits-it (then BE silently uses `"youtube_shorts"`). A typical user picks viral / TikTok defaults — they expect TikTok aspect, hashtags, length rules. Getting YouTube Shorts defaults is wrong UX.

**Fix:** pick one canonical default and use it in both places.

---

## Other findings

### FINDING-C06 (MED) — `JobStatus.kind` and `JobStatus.status` are unenumerated on BE

[schemas.py:880-882](../../backend/app/models/schemas.py): `kind: str`, `status: str` — no Pydantic validator on either.

FE types constrain both to TS unions. If BE introduces a new `kind` (e.g., `"render_batch"` for queued batch renders), FE renders fall through default branches or display "unknown" labels.

**Fix:** introduce a Python `enum.StrEnum` (or validators) shared via codegen.

### FINDING-C07 (MED) — `JobAiSummary.confidence_tier` may be empty

[routes/jobs.py:~410](../../backend/app/routes/jobs.py) reads `best_clip.get("confidence_tier")` and falls through to empty string when missing. [jobs.ts:158](../../frontend/src/api/jobs.ts) declares it as `string` (non-optional). When `available=true` but no per-clip confidence data exists, FE may render `<Badge>{tier}</Badge>` with empty content.

**Fix:** either narrow the TS type to `string | ""` and handle, or guarantee a default ("high"/"medium"/"low") on the BE.

### FINDING-C08 (MED) — Downloader response missing `platform` in FE type

[features/download/router.py:~210](../../backend/app/features/download/router.py): `start_download` returns `{job_id, platform}`. FE [platformDownloader.ts](../../frontend/src/api/platformDownloader.ts) reads only `job_id` — `platform` is dropped. Cosmetic today (FE infers from URL), but `platform` is the BE's authoritative classification (TikTok handler vs generic yt-dlp), so missing it loses debugging information.

**Fix:** add `platform` to the FE response type and surface it in the download tab (badge per row).

### FINDING-C09 (LOW) — Feedback submit body is fully optional

[routes/feedback.py:33-55](../../backend/app/routes/feedback.py): every field has a default. POST with empty body would be accepted (with `rating=0` which fails `CHECK` constraint at DB, but the schema doesn't reject upfront).

**Fix:** make `rating` required on the Pydantic model (no default), reject the body without the field.

### FINDING-C10 (LOW) — Massive number of `RenderRequest` BE-only fields

Approximately 50+ fields on `RenderRequest` are accepted by BE but never set by the FE (preset internals, channel-mode helpers, AI Director fields from Phase G that were never removed, legacy `groq_*` aliases, etc.). These do not break the contract (they have safe defaults) but they bloat the schema and obscure what's actually wired.

**Fix:** Phase 11 roadmap item — split `RenderRequest` into `RenderRequestPublic` (FE-facing, ~30 fields) and `RenderRequestInternal` (server-derived). Verify each "BE-only" field is still alive (the Phase G AI Director fields almost certainly are not — see Phase 4 dead-code report).

---

## Risk matrix

| # | Contract | Issue | Failure mode | Likelihood | Severity |
|---|---|---|---|---|---|
| C01 | RenderRequest.part_order | enum unenforced | wrong part order silently | HIGH (already a 2-value enum on FE) | **HIGH** |
| C02 | RenderRequest.*api_key | plaintext in DB + logs | credential leak via support bundle / DB dump | MED (if any user enables cloud LLM) | **HIGH** |
| C03 | JobPart.{clip_name,ai_title,…} | FE reads fields BE doesn't produce | undefined chains / "—" labels | MED (depends on which screens read these) | **HIGH** |
| C04 | RenderRequest extra="ignore" | new FE field silently dropped | phased rollout misbehaviour | MED (during deploys) | **HIGH** |
| C05 | target_platform default | FE/BE differ | unexpected aspect/length defaults | MED (only when user doesn't touch the picker) | **MED** |
| C06 | Job.kind/status unenumerated | type drift | unknown labels on UI | MED (over time) | **MED** |
| C07 | confidence_tier empty | empty pill | cosmetic | MED | **MED** |
| C08 | Downloader.platform missing | lost info | debug-only | LOW | **LOW** |
| C09 | Feedback required-field | empty POST accepted upstream | downstream CHECK fails | LOW (no fast-error) | **LOW** |
| C10 | RenderRequest bloat | maintenance / confusion | none today | n/a | **LOW** |

---

## Recommendations (priority order)

1. **Add validator on `RenderRequest.part_order` and wire `sequential` into ranking** (or reject it). C01.
2. **Disallow `*_api_key` in incoming `RenderRequest`. Require server `.env` keys.** C02. (Combined with Phase 1 FINDING-F07 fix.)
3. **Audit `JobPart` field origin and either inject or delete from FE type.** C03.
4. **Split `RenderRequest` into `RenderRequestStrict` (POST handler, `extra="forbid"`) and `RenderRequestLenient` (replay/resume, `extra="ignore"`).** C04.
5. **Adopt `JobStage`/`JobPartStage` as `enum.StrEnum`; expose via codegen.** Repeats Phase 4 BR05. C06.
6. **Enforce `check:openapi-drift` in CI** (`.github/workflows/ci.yml`). Closes Phase 5 FINDING-T05 + provides the substrate for items 1–4 above to be detectable.
7. **Align `target_platform` default** (FE+BE), C05.
8. **Add `platform` to FE downloader response type** (C08).
9. **Make `rating` required on feedback model** (C09).
10. **Schedule `RenderRequest` decomposition** (split public/internal) as a Phase 11 roadmap item. C10.

---

## Cross-references

- WS event shape verified ✓ — Sacred Contract #6 holds.
- `result_json` Sacred Contract #1 keys (`output_rank_score`, `is_best_output`, `is_best_clip`) verified in Phase 1 (database inventory §H) and reaffirmed here.
- `extra="ignore"` ↔ Sacred Contract #2 trade-off discussed at length in Phase 1 §H and here.

End of 14_contract_audit.md.
