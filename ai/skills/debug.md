# Skill: Debug

## When to Use

User reports something not working. Error message. Unexpected behavior.
Test failure with unclear root cause.

## Workflow

1. Read the error message carefully — find the exact file:line
2. Read that file at the relevant location (never guess from memory)
3. Trace the call path upstream — find where the bad input originates
4. Identify root cause — not just the symptom
5. Assess risk of fix:
   - LOW → developer can proceed with brief plan
   - MEDIUM/HIGH → route to planner for approval
6. Implement minimal fix
7. Verify fix: `py_compile` + focused `pytest`

## Output

```
Root cause: <file:line + explanation of why this breaks>
Fix: <minimal patch description — what to change and where>
Risk: LOW | MEDIUM | HIGH
Planner needed: YES | NO
```

## Stop Conditions

Stop and escalate to leader if:
- Root cause is in `render_pipeline.py`, `render_engine.py`, `schemas.py`, `motion_crop.py`, `subtitle_engine.py`
- Root cause requires changing API contracts
- Root cause is unclear after reading 3 relevant files

## Never

- Fix symptoms without finding root cause
- Add `try/except` to silence errors
- Modify protected files to paper over a bug
- Guess-fix without reading the actual code

## Common Traps in This Codebase

- `backend/static-new/` not being served — NOT a code bug, it's Phase B2
- AI module failures — should return `None`, check if it's raising instead
- NVENC errors — check semaphore, don't remove the guard
- WebSocket disconnect — check polling fallback, don't remove it
