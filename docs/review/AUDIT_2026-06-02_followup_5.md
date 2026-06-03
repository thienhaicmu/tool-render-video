# Audit 2026-06-02 — Track C Bug Fix C1: srt_path typo

Fifth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

The `srt_path` typo at `stages/part_done.py:114` (formerly preserved
verbatim during Sprint 6.D-2.5d per the no-while-I-am-here convention,
see `AUDIT_2026-06-02_followup_4.md` "Known-bug preservation" section).

## The bug

```python
# Pre-fix (line 114):
if srt_path is not None and Path(str(srt_path)).exists():  # NameError
    _qi_srt_path = Path(str(srt_path))
elif _qi_srt is not None and Path(str(_qi_srt)).exists():
    _qi_srt_path = Path(str(_qi_srt))
```

`srt_path` is never defined in `run_part_done`'s local scope. The
function parameter is named `srt_part`. The resulting `NameError` was
caught by the surrounding `try / except Exception: pass` at line 111,
which made `_assess_render_quality_intelligence` a **silent no-op for
ALL renders** since this code path was introduced.

## The fix

```python
# Post-fix:
if srt_part is not None and Path(str(srt_part)).exists():
    _qi_srt_path = Path(str(srt_part))
elif _qi_srt is not None and Path(str(_qi_srt)).exists():
    _qi_srt_path = Path(str(_qi_srt))
```

One-character class of change — `srt_path` → `srt_part`. The variable
name now matches the function parameter, restoring the original intent.

## Behavioral consequences

When the fix is live, `_assess_render_quality_intelligence` (which
lives in `app.orchestration.qa_pipeline`) now actually runs on every
part that has an SRT file. The helper:

1. Calls `assess_rendered_part_quality()` from `app.quality.assessor`
   (this exists and was deliberately authored; only the call site was
   broken).
2. Writes a sidecar JSON report at
   `<output_dir>/quality/<job_id>_part_<part_no>.json`.
3. Logs `quality_intelligence: report written job_id=... part_no=...
   score=... issues=... path=...` at INFO level per part.
4. Returns the report dict — but the caller in `run_part_done` drops
   the return value.

## Impact classification

| Surface | Impact |
|---|---|
| DB writes | None |
| WebSocket emits | None |
| Result_json | None (sidecar JSON is filesystem-only) |
| Frontend contract | None |
| Sacred Contracts 1–8 | None — no Contract surface touched |
| Filesystem | New `quality/` dir + JSON file per part. Purely additive. |
| Latency | One extra `assess_rendered_part_quality` call per part. Reads ffprobe metadata; small overhead. |
| Log volume | One INFO line per part. |
| Exception propagation | Still wrapped in outer try / except: pass — never raises. |

**Risk: LOW.** The activation produces purely additive observability
data with no impact on user-facing rendering output, ranking, or API
contracts.

## Test coverage

`tests/test_qa_pipeline_quality_integration.py::TestQualityIntelligenceCallSiteActivation::test_run_part_done_calls_assess_quality_when_srt_exists`
added in the same commit as the fix. Asserts:

1. `_assess_render_quality_intelligence` is invoked when `srt_part`
   exists on disk (`mock_assess.called == True`).
2. The `srt_path` kwarg passed to the helper equals the `srt_part`
   path we provided.

If the typo is ever reintroduced, this test fails because the
`NameError` falls into the outer except: pass and the mock never
receives a call.

Manual verification confirmed during commit:
```
mock_assess.called: True
srt_path kwarg: <tmp>/p.srt
```

## Pytest

2078 passed, 1 skipped, 0 failed (was 2077 + 1 = 2078 after adding
the regression-guard test). No baseline regression.

## References

- Code change: `backend/app/orchestration/stages/part_done.py` —
  one-line rename + docstring update.
- Test added: `backend/tests/test_qa_pipeline_quality_integration.py` —
  one new test class with one test method.
- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- Sprint 6.D closure: `docs/review/AUDIT_2026-06-02_followup_4.md`.
- Sister bug C2 (not yet fixed): missing `_mv_score_part` import at
  `stages/part_render_finalize.py:361`. Higher-impact behavioral
  change; deferred pending history investigation per Track C plan.

## Status

**Bug C1: CLOSED.** Track C remains open — bug C2 still preserved.
