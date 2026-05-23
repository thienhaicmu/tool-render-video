# Review Rules

## docs/review/** — ABSOLUTE READ-ONLY

AGENTS.md line 111:
```
Protected folders:
- NEVER edit docs/review/**
- NEVER edit docs/archive/**
unless explicitly requested.
```

## Correct Way to Add a New Finding

1. Create **new** file: `docs/review/TOPIC_YYYY-MM-DD.md`
2. Reference the previous file if it relates to an earlier finding
3. Explain what changed and why in the new file
4. Never touch existing files

## Review Checklist (run before marking any task done)

- [ ] API payload + response compatibility preserved
- [ ] `RenderRequest` defaults unchanged (new fields default to disabled)
- [ ] Job status/stage/part transition names unchanged
- [ ] WebSocket progress + HTTP polling fallback both functional
- [ ] `result_json` parseable by history/output/AI UI code
- [ ] Output validation still catches missing, tiny, streamless, zero-duration videos
- [ ] Subtitle and voice paths still no-op safely when disabled
- [ ] AI phase changes bounded by safety rules (no import-time optional dep failures)
- [ ] Audit docs updated for any behavior/spec change

## Auto-Reject Conditions

Automatic reject — no discussion needed:

| Condition | Why |
|-----------|-----|
| Protected file edited without explicit approval | Safety rule violation |
| `output_rank_score` / `is_best_output` / `is_best_clip` removed | Breaks UI backward compat |
| API route path changed | Breaks existing API consumers |
| AI module can raise instead of return `None` | Crashes render pipeline |
| Output validation bypassed to fake success | Masks real failures |
| `backend/static-new/` assumed to be served UI | Phase B2 not resolved |
| `git add .` or `git add *` proposed | Git safety rule violation |

## Overengineering Triggers

Flag and ask planner to rescope if:
- Three or more files changed when one was expected
- New abstraction layer added for a single use case
- Helper function created for a function called once
- Existing working code refactored while fixing an unrelated bug
