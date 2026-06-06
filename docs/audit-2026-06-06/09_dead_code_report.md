# 09 — Dead Code Report

Source code only. Branch `feature/ai-workflow-upgrade`. Targets: unused services, hooks, APIs, DTOs, models, SQL, utilities, orphan caches, stale references.

---

## CRITICAL

### FINDING-DC01 — Dead import path (CONFIRMED, CRITICAL)

[backend/app/features/render/ai/diagnostics.py:74](../../backend/app/features/render/ai/diagnostics.py)

```python
from app.ai.rag.sqlite_store import SQLiteMemoryStore, _default_db_path
```

Module `app.ai.rag.sqlite_store` does not exist on this branch (verified). The import is inside a `try/except`, so it fails silently — but the AI diagnostics endpoint will **always** report SQLite memory store as unavailable. The RAG memory store was removed in Phase G (per CLAUDE.md L352-357), and this import was missed.

**Action:** delete the try-block or replace with a static "not available" response.

---

## HIGH

### FINDING-DC02 — 15 unused upload Pydantic models in active `schemas.py`

[backend/app/models/schemas.py:479-877](../../backend/app/models/schemas.py)

The upload feature was removed in Phase 4F.5A. The router is gone, but the Pydantic models stayed. Cross-codebase grep returns 0 references for:

| Line | Class |
|---|---|
| 479 | `UploadRequest` |
| 528 | `UploadQueueAddRequest` |
| 552 | `UploadAccountBase` |
| 601 | `UploadAccountCreate` |
| 606 | `UploadAccountUpdate` |
| 663 | `ProxyTestRequest` |
| 671 | `AddUploadVideoRequest` |
| 698 | `UpdateUploadVideoRequest` |
| 717 | `UploadVideoResponse` |
| 735 | `UploadQueueUpdateRequest` |
| 754 | `UploadQueueResponse` |
| 776 | `UploadSchedulerStatusResponse` |
| 799 | `ProxyPoolCreate` |
| 833 | `ProxyPoolUpdate` |
| (also) | + `UploadQueueRunRequest` etc. — exhaustive grep yields ~15 |

These dead definitions actively mislead new readers into thinking the upload pipeline is live. **Action:** delete all 15.

### FINDING-DC03 — Three ghost top-level dirs (repeat of Phase 1 B01)

`backend/app/ai/`, `backend/app/orchestration/`, `backend/app/quality/` — each has only `__pycache__/` subdirs and no Python sources. **Action:** delete directories entirely; CLAUDE.md references must be updated in the same commit.

### FINDING-DC04 — Orphan `.pyc` cache in `services/__pycache__/`

Compiled bytecode for ~30 deleted modules survives in `backend/app/services/__pycache__/`:

```
motion_crop_legacy.cpython-311.pyc
motion_crop.cpython-{311,313}.pyc
audio_*.cpython-311.pyc                (8 files)
cancel_registry.cpython-311.pyc        (moved to app/jobs/cancel.py)
caption_engine.cpython-311.pyc
clip_scorer.cpython-311.pyc
db_backup.cpython-311.pyc              (now in features/render/engine/pipeline/)
editing_service.cpython-311.pyc        (now in features/render/editing/)
encoder_helpers.cpython-311.pyc        (now in features/render/engine/encoder/)
hook_optimizer.cpython-311.pyc
job_manager.cpython-311.pyc            (now app/jobs/manager.py)
manifest_writer.cpython-311.pyc        (now stages/)
motion_crop_path*.pyc                  (now features/render/engine/motion/)
remotion_adapter.cpython-311.pyc
render_engine.cpython-{311,313}.pyc    (deleted Sprint 6.D)
report_service.cpython-311.pyc         (now features/render/engine/pipeline/)
scene_detector.cpython-311.pyc
segment_builder.cpython-{311,313}.pyc
subtitle_engine.cpython-{311,313}.pyc
text_overlay.cpython-{311,313}.pyc
thumbnail_quality.cpython-311.pyc
translation_service.cpython-311.pyc
tts_service.cpython-311.pyc
upload_engine.cpython-311.pyc
viral_scorer.cpython-{311,313}.pyc
voice_profiles.cpython-311.pyc
```

The corresponding `.py` sources are gone. These get re-collected on every `git clean -fdx`, but should not be tracked. **Action:** add `__pycache__/` to `.gitignore` (verify it isn't already; if it is, run `git rm -r --cached backend/app/services/__pycache__/`).

### FINDING-DC05 — Bytecode-only orphans under `ai/` ghost dir

Same pattern under `backend/app/ai/{analysis,context,llm}/__pycache__/`. 19 `.pyc` files survive without source:

```
ai/analysis/__pycache__: hybrid_analyzer, local_analyzer, merger, signals
ai/analysis/cloud/__pycache__: base, groq_provider, openai_provider, prompt_builder, response_parser
ai/context/__pycache__: builder, creator_context
ai/llm/__pycache__: claude_provider, gemini_provider, openai_provider, parser, prompts, providers (init)
```

All migrated to `features/render/ai/**`. **Action:** delete with `git clean -fdx backend/app/ai/`.

---

## MEDIUM

### FINDING-DC06 — Unused download schemas

[backend/app/models/schemas.py:49,54](../../backend/app/models/schemas.py): `DownloadBatchRequest`, `DownloadRetryRequest` — zero callers. `QuickProcessRequest` (L58) IS used by `features/render/router.py` quick-process endpoint. **Action:** delete the first two.

### FINDING-DC07 — FE comments mark removed upload endpoints

[frontend/src/api/upload.ts:8-15](../../frontend/src/api/upload.ts) lists 7 removed routes. Phase 6 will independently catalog active backend endpoints, but the FE is honest about removal. No action needed beyond verifying no shadow code in `frontend/src/features/**` still tries to call them.

### FINDING-DC08 — Backward-compat `groq_*` fields in RenderRequest

[backend/app/models/schemas.py](../../backend/app/models/schemas.py): fields `groq_only_mode` (L381), `groq_api_key` (L391), plus `ai_provider` doc strings mentioning `"groq"` (L309, 387). Sprint 7.5 deleted the Groq provider implementation; Sprint 7.6 LITE deleted the GroqSegment alias. Sacred Contract #2 ("new fields default to disabled") justifies keeping the FE-facing fields — but if no FE or stored payload actually sets them, they're dead and may be removed in a subsequent sprint.

**Action:** before deleting, run a one-shot SQL audit:

```sql
SELECT COUNT(*) FROM jobs
WHERE json_extract(payload_json, '$.groq_only_mode') IS NOT NULL
   OR json_extract(payload_json, '$.groq_api_key') IS NOT NULL;
```

If zero, safe to drop the fields in a Sacred-Contract-#2-aware migration.

---

## LOW

### FINDING-DC09 — `dev_commands.py` references deleted `render_engine.py`

[backend/app/services/dev_commands.py](../../backend/app/services/dev_commands.py) — multiple hint strings and error messages reference `backend/app/services/render_engine.py` (deleted Sprint 6.D). The path no longer exists; the strings remain. Dev-only tool, so blast radius is zero.

### FINDING-DC10 — `App.tsx` deprecated panel aliases

[frontend/src/App.tsx:37-39](../../frontend/src/App.tsx): `render` and `history` panel values map to `HistoryScreen`. Comment marks them "Deprecated aliases — do not add new usage." Intentional backward-compat; can be removed in next major UI revision.

### FINDING-DC11 — `routes/voice.py` (~20 LOC) thin TTS test stub

[backend/app/routes/voice.py](../../backend/app/routes/voice.py): 19 LOC, single endpoint wrapping `profiles.get_voice_profiles()`. FE does not call `/api/voice/*` (Phase 1 verified — `frontend/src/api/*.ts` lists no voice client). Phase 6 will confirm.

### FINDING-DC12 — Standalone HTML prototypes never referenced

`render-flow.html` (144 KB), `prototype.html` (96 KB) at repo root. Phase 1 verified neither is imported by any FE source. CLAUDE.md still treats `render-flow.html` as canonical design intent. **Action:** move to `docs/design/` and update CLAUDE.md, OR delete and adopt the live `RenderWorkflow.tsx` as the only source of truth.

---

## Summary

| Severity | Count | Recommendation |
|---|---|---|
| CRITICAL | 1 | DC01 — delete dead import this sprint |
| HIGH | 4 | DC02/DC03/DC04/DC05 — batch cleanup |
| MEDIUM | 3 | DC06/DC07/DC08 — verify before delete |
| LOW | 4 | DC09–DC12 — cosmetic |

End of 09_dead_code_report.md.
