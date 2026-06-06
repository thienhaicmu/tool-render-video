# 16 — Test Coverage Audit

Source code only. Tests = files at `backend/tests/test_*.py`. No coverage tool was run (no `.coverage` file in repo, no `coveragerc`); this audit is **module-presence coverage** — does each source module have a corresponding test file?

---

## 1. Inventory

### Backend tests — 15 files, 2,444 LOC

| Test file | LOC | Targets | Target LOC | Ratio |
|---|---|---|---|---|
| `test_pipeline_segment_selection.py` | 226 | `pipeline/pipeline_segment_selection.py` | 373 | 0.61 |
| `test_pipeline_qa.py` | 224 | `pipeline/qa_pipeline.py` (Sacred #8) | 385 | 0.58 |
| `test_ffmpeg_helpers.py` | 215 | `encoder/ffmpeg_helpers.py` | 647 | 0.33 |
| `test_pipeline_ranking.py` | 211 | `pipeline/pipeline_ranking.py` (Sacred #1) | 357 | 0.59 |
| `test_subtitle_srt.py` | 202 | `subtitle/generator/srt.py` | ~? | — |
| `test_clip_ops.py` | 192 | `encoder/clip_ops.py` | 402 | 0.48 |
| `test_job_manager.py` | 175 | `jobs/manager.py` | ~350 | 0.5 |
| `test_subtitle_ass.py` | 158 | `subtitle/generator/ass.py` | 457 | 0.35 |
| `test_subtitle_readability.py` | 153 | `subtitle/processing/readability.py` | 544 | 0.28 |
| `test_subtitle_styles.py` | 129 | `subtitle/processing/styles.py` | 388 | 0.33 |
| `test_download_service.py` | 129 | `features/download/service.py` | ~? | — |
| `test_stages_render_setup.py` | 111 | `stages/part_render_setup.py` | ? | — |
| `test_subtitle_transcription.py` | 109 | `subtitle/transcription/*.py` | 694 | 0.16 |
| `test_motion_crop.py` | 101 | `motion/crop.py` (skeleton) | 803 | 0.13 |
| `test_stages_asset_planner.py` | 100 | `stages/part_asset_planner.py` | 883 | 0.11 |
| `conftest.py` | 9 | (fixtures) | — | — |

### Frontend tests — 0 files

`frontend/package.json` declares `vitest`, `@testing-library/{jest-dom,react,user-event}`, `jsdom`. Grep `*.test.*` and `*.spec.*` across `frontend/src/` → **zero matches.**

---

## 2. Coverage by tier

Backend source: ~180 Python modules under `backend/app/**` (Phase 1). Backend tests target ~12 distinct source files. **Module-presence coverage ≈ 7 %.**

### CRITICAL-tier files (per CLAUDE.md + Phase 3) — coverage status

| File | LOC | Test? |
|---|---|---|
| `features/render/engine/pipeline/render_pipeline.py` | 1357 | **NO** |
| `features/render/engine/stages/part_renderer.py` | ~325 | indirect (asset_planner test only) |
| `features/render/engine/stages/part_render_finalize.py` | 639 | **NO** |
| `features/render/engine/pipeline/qa_pipeline.py` | 385 | YES ✓ |
| `features/render/engine/motion/crop.py` | 803 | partial (101 LOC test) |
| `features/render/engine/motion/path.py` | 406 | **NO** |
| `features/render/engine/motion/path_scene.py` | 592 | **NO** |

### HIGH-tier files — coverage status

| File | LOC | Test? |
|---|---|---|
| `models/schemas.py` | 892 | **NO** — most-trafficked contract surface, zero direct test |
| `jobs/manager.py` | ~350 | YES ✓ |
| `db/jobs_repo.py` | 205 | **NO** — Sacred Contract #1 keys are tested at pipeline_ranking layer only |
| `db/creator_repo.py` | ~150 | **NO** |
| `db/feedback_repo.py` | ~150 | **NO** |
| `db/download_repo.py` | ~150 | **NO** |
| `features/render/router.py` | 1195 | **NO** (god controller) |
| `features/render/engine/encoder/clip_renderer.py` | 905 | partial via ffmpeg_helpers |
| `features/render/engine/encoder/ffmpeg_helpers.py` | 647 | YES ✓ |
| `features/render/engine/encoder/clip_ops.py` | 402 | YES ✓ |
| `features/render/engine/pipeline/llm_pipeline.py` | 448 | **NO** (mandatory-LLM hard-fail logic UNTESTED) |
| `features/render/engine/pipeline/llm_stage.py` | ~? | **NO** |
| `features/render/ai/llm/__init__.py` (dispatcher) | ~? | **NO** |
| `features/render/ai/llm/parser.py` | 458 | **NO** — Sacred Contract #3 tested indirectly only |
| `features/render/ai/llm/prompts.py` | 423 | **NO** (format-safety regression — there is `test_creator_context_dataclass.py`? not present in this listing) |
| `features/render/ai/llm/providers/{claude,openai,gemini}.py` | each ~80 | **NO** |
| `features/render/ai/context/builder.py` | ~? | **NO** |
| `features/render/ai/visibility/ai_visibility_summary.py` | ~? | **NO** |
| `features/render/engine/pipeline/pipeline_render_loop.py` | ~? | **NO** |
| `features/render/engine/pipeline/pipeline_finalize.py` | ~? | **NO** |
| `features/render/engine/pipeline/render_events.py` | ~? | **NO** (Sacred Contract #6 untested) |
| `features/render/engine/subtitle/translation_service.py` | ~? | **NO** |
| `features/render/engine/audio/mixer.py` | ~? | **NO** |
| `features/render/engine/audio/tts.py` + `tts_xtts.py` | ~? | **NO** |
| `features/render/engine/quality/assessor.py` | 582 | **NO** |
| `features/render/engine/preview/session_service.py` | ~? | **NO** (Phase 4 BR01 race here, no test) |
| `routes/jobs.py` (WS handler) | 806 | **NO** (Sacred Contract #6 emission untested) |
| `routes/feedback.py`, `channels.py`, `settings.py`, `voice.py`, `metrics.py`, `files.py`, `devtools.py` | varies | **NO** |
| `features/render/editing/router.py` + `editing_service.py` | ~? | **NO** |
| `features/download/router.py` + adapters/* | ~? | partial (service-level test only) |

---

## 3. What the existing tests actually cover well

The tests that exist are **targeted and load-bearing**:

- `test_pipeline_ranking.py` — explicitly checks Sacred Contract #1 keys (`output_rank_score`, `is_best_output`, `is_best_clip`) at lines 170-175. ✓
- `test_pipeline_qa.py` — checks the QA gate failure codes (Sacred Contract #8). ✓
- `test_ffmpeg_helpers.py` — covers the retry loop + cancel polling. ✓
- `test_clip_ops.py` — covers cut paths (stream-copy vs accurate). ✓
- `test_pipeline_segment_selection.py` — exercises segment filter math. ✓
- `test_job_manager.py` — priority heap + shutdown semantics. ✓
- `test_subtitle_*.py` — exercises subtitle generation + readability (4 files).

**FINDING-TEST01 (POSITIVE, LOW):** the tests that exist are good. They protect the Sacred Contracts (#1 verified, #8 verified) and the riskiest math (FFmpeg retry, ranking). Quality is high; quantity is low.

---

## 4. What's NOT tested but is high-risk

### CRITICAL gaps

**FINDING-TEST02 (HIGH):** `render_pipeline.py` (1357 LOC orchestrator) has no test. JobStage transitions, feature-flag dispatch (4 active flags + 16 path combinations per Phase 3 R02), error paths, resume logic — all unverified.

**FINDING-TEST03 (HIGH):** `llm_pipeline.py` (448 LOC) untested. The 7 hard-fail sites that kill the job (Phase 2 §9, Phase 4 BR02) cannot be exercised by tests. A regression that silently swallows an LLM error → job ships broken output without anyone knowing.

**FINDING-TEST04 (HIGH):** Sacred Contract #6 (`_emit_render_event` shape) has no test. The contract test in Phase 1 is only for #1 (result_json keys). A typo in a stage helper could break the WS payload and every existing test still passes.

**FINDING-TEST05 (HIGH):** Sacred Contract #3 (AI modules return None) is verified by the audit (Phase 2 §8) but not by automated tests. A new AI provider added in a future sprint can quietly raise — no test would catch it.

**FINDING-TEST06 (MED):** zero tests for `routes/jobs.py` WS handler — the polling loop, the fingerprint diff, the error_kind classification. Phase 4 BR06 flagged sync-DB-in-async-loop; no benchmark, no integration test.

**FINDING-TEST07 (MED):** `db/jobs_repo.py` upsert + delete-cascade logic untested. A future sprint that moves to FK + ON DELETE CASCADE would have nothing to compare against.

**FINDING-TEST08 (MED):** `features/render/engine/preview/session_service.py` — the unprotected `_PREVIEW_SESSIONS` race condition (Phase 4 BR01) has no test that would surface concurrent mutation.

### FE gaps

**FINDING-TEST09 (HIGH):** zero FE tests. Vitest installed; no `*.test.tsx` or `*.spec.tsx` files. Risk surface: `RenderSocketClient.ts` reconnect logic, `RenderWorkflow.tsx` payload assembly (~700 LOC), state restoration on app launch, panel routing edge cases. Phase 5 FINDING-T06 flagged the same.

---

## 5. Test infrastructure

### `conftest.py` (9 LOC)

Minimal. Tests rely on per-file fixtures and direct setup.

### CI status

Not audited — no GitHub Actions config inspected this pass. But: `frontend/package.json` declares `check:openapi-drift` (Phase 5 FINDING-T05) which is not enforced. By extension, even running `pytest` is not guaranteed on every PR.

**FINDING-TEST10 (HIGH):** verify whether CI runs `pytest` and `vitest` on PR. If not, the existing 2,444 LOC of tests gates nothing.

---

## 6. Coverage benchmark vs project size

| Bucket | Backend |
|---|---|
| Backend source LOC | 40,146 |
| Backend test LOC | 2,444 |
| Test/Source LOC ratio | **6.1 %** |
| Modules with any test | 12 / ~180 = **6.7 %** |

Industry rough rules of thumb for a system this complex (with hardware-bound side effects + AI + concurrent FFmpeg):
- Minimum decent: 30 % test/source LOC, 50 % module coverage.
- Healthy: 50 % LOC, 70 % module.
- The system today is **5–10× under** that minimum bar.

---

## 7. Top 10 tests to write first (ROI-ordered)

1. **Sacred Contract #6 WS payload test** — write any pipeline stage event and assert `{job, parts, summary}` keys present. (Hour.)
2. **Sacred Contract #3 AI provider test** — parametrized test that every provider's public method returns None when its SDK raises. (Hour.)
3. **`llm_pipeline` hard-fail integration test** — mock provider failures, assert `LLMPipelineError` is raised with each of the 7 reasons. (Half-day.)
4. **`render_pipeline` happy-path smoke test** — mock LLM + Whisper + FFmpeg, run a 2-part render end-to-end, assert all stages emit + DB rows correct. (1–2 days.)
5. **`_PREVIEW_SESSIONS` race test** — spawn 50 threads doing register + evict concurrently, assert no KeyError. (Hour.)
6. **`delete_job` atomicity test** — simulate exception between the two DELETEs, assert rollback leaves both tables consistent. (Hour.)
7. **FE WS reconnect test** — Vitest + mock WS, send progress events, kill connection, assert reconnect attempts within backoff window. (Half-day.)
8. **FE `RenderWorkflow.tsx` payload assembly test** — render form, fill config, submit, assert payload shape matches BE Pydantic. (Half-day.)
9. **`routes/jobs.py` WS fingerprint test** — make 100 same DB reads, assert WS frame sent only once. (Hour.)
10. **OpenAPI drift CI test** — run `npm run check:openapi-drift`, fail PR if drift. (Hour.)

---

## 8. Summary

| Concern | State |
|---|---|
| Existing tests | high quality, narrow scope (6.7 % module coverage) |
| Sacred Contract #1 | ✓ tested directly |
| Sacred Contract #3 | NOT tested (verified by audit) |
| Sacred Contract #6 | NOT tested |
| Sacred Contract #8 | ✓ tested directly |
| `render_pipeline.py` (1357 LOC) | 0 % |
| `llm_pipeline.py` (448 LOC) | 0 % |
| WS handler (`routes/jobs.py`) | 0 % |
| Frontend | 0 % (Vitest installed, unused) |
| CI gate | not verified |

End of 16_test_audit.md.
