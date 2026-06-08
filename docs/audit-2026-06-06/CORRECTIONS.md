# Audit Corrections — 2026-06-06 (post-execution)

After Batch 1 execution and live sanity testing on the same day, several audit findings were verified against actual runtime behavior. Three significant corrections:

---

## Correction 1 — TEST09 RETRACTED ("zero FE tests" is wrong)

[16_test_audit.md](16_test_audit.md) FINDING-TEST09 claimed the FE had zero test files because the sub-agent's search used patterns `frontend/src/**/*.test.*` and `*.spec.*`, which returned nothing.

**Reality:** the FE test suite lives at `frontend/tests/` (not in `frontend/src/`). On 2026-06-06 `npm test` from `frontend/`:

```
Test Files  25 passed (25)
     Tests  390 passed (390)
   Duration 5.47s
```

26 test files (one is `setup.ts`, 25 are spec files) covering: api client, editor flow, trim flow, export flow, sidebar, topbar, stores, quality utils, job actions, progress panel, etc.

**Impact:** the architecture score in [28_executive_summary.md](28_executive_summary.md) was held down partly by the imagined zero FE coverage. With 390 passing FE tests, the **Testability dimension lifts from 4 → 6**, and the overall score from 5.4 → ~5.7.

---

## Correction 2 — T05/TEST10 RETRACTED ("no CI gate on tests / openapi-drift")

[12_tool_audit.md](12_tool_audit.md) FINDING-T05 and [16_test_audit.md](16_test_audit.md) FINDING-TEST10 claimed `check:openapi-drift` and overall pytest/vitest weren't enforced. Neither sub-agent inspected `.github/workflows/`.

**Reality:** [`.github/workflows/test.yml`](../../.github/workflows/test.yml) defines 4 CI jobs that run on push/PR to `main`:

1. `backend` — `python -m compileall backend/app -q` + `pytest --tb=short -q`. Runs on `windows-latest`.
2. `frontend` — `tsc -b` (type check) + `npm test` (vitest). Runs on `ubuntu-latest`. **Blocks PRs** (continue-on-error removed per comment).
3. `openapi-drift` — runs `npm run gen:openapi` and `git diff --exit-code src/types/openapi-generated.ts`. Fails with a clear hint if drift detected.
4. `devtools-security` — runs `tests/test_devtools_security.py` only, depends on `backend` job.

**Impact:** the audit's "no contract-evolution detection" risk is partly mitigated. Drift is caught by job 3. The remaining gap (Phase 7 FINDING-C04, silent field drop via `extra="ignore"`) still applies — but `openapi-generated.ts` won't go stale.

---

## Correction 3 — T06 RETRACTED ("vitest installed and unused")

Same root cause as Correction 1. Vitest is in active use: 390 tests across 25 spec files in `frontend/tests/`. Action item from FINDING-T06 ("ship one FE test or strip the test deps") is moot.

---

## Updated finding counts

Pre-corrections:
- HIGH: 15
- MED: ~35
- LOW: ~30

Post-corrections:
- HIGH: 12 (TEST09, TEST10, T05 removed)
- MED: ~34 (T06 removed)
- LOW: ~30

## Updated architecture score

| Dimension | Pre | Post | Why |
|---|---|---|---|
| Testability | 4 | **6** | 390 FE tests + 287 BE tests + 4 CI jobs |
| Maintainability | 5 | 5 | unchanged |
| Reliability | 6 | **6.5** | CI gates make regressions visible |
| Observability | 7 | 7 | unchanged |
| Scalability | 4 | 4 | unchanged |
| Readability | 6 | 6 | unchanged |
| Extensibility | 6 | 6 | unchanged |

**New overall score: (4+5+6+6+6+6.5+7) / 7 = 5.79 ≈ 5.8 / 10.**

(Up from 5.4. The corrections did not change anything about god files, ghost dirs, plaintext credentials, or NVENC concerns — those remain valid.)

---

## What was confirmed accurate during Batch 1 execution

- DC01 (dead import `app.ai.rag.sqlite_store`) — confirmed, deleted in this batch.
- B01 (ghost dirs `backend/app/{ai,orchestration,quality}/`) — confirmed, deleted in this batch.
- DB08 (no `ANALYZE` ever runs) — confirmed, added in this batch.
- C05 (`target_platform` default mismatch) — confirmed, FE='tiktok' / BE was 'youtube_shorts'. Aligned to 'tiktok' in this batch.
- C01 (`part_order` enum unvalidated) — confirmed, validator added in this batch (coercing, not raising, to preserve Sacred Contract #2 replay).
- CLAUDE.md stale-path notice — confirmed, banner added at top of CLAUDE.md.

---

## Items NOT corrected by this batch (still valid)

All HIGH findings except the 3 retracted above:

1. F07 / C02 — Cloud LLM API keys plaintext in DB/logs (still HIGH).
2. AI07 / BR02 / S07 — LLM hard-fail without retry/fallback (still HIGH).
3. R01 / BR04 — NVENC semaphore bypass risk (still HIGH).
4. BR01 — `_PREVIEW_SESSIONS` race (still HIGH).
5. U01 — zero auth (still HIGH if exposed publicly).
6. DC02 — 15 unused upload Pydantic models (still MED-HIGH).
7. T01 — MediaPipe silent degrade (still MED).
8. API09 — `extra="ignore"` field-drop (still HIGH).
9. C03 — JobPart phantom fields (still HIGH).
10. C04 — no strict/lenient split (still HIGH).
11. TEST02/03/04 — critical untested code paths (`render_pipeline.py`, `llm_pipeline.py`, Sacred Contract #6) (still HIGH).

Batch 2 and Batch 3 of the post-audit plan address these. Roadmap in [27_future_roadmap.md](27_future_roadmap.md) remains the canonical playbook.

End of CORRECTIONS.md.
