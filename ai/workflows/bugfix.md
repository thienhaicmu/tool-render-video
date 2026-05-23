# Workflow: Bug Fix

## Flow Diagram

```
User reports bug
 └─ Debug skill (find root cause)
     ├─ LOW risk ────────► Developer (minimal fix)
     │                      └─ py_compile + pytest
     │                          └─ Reviewer ──► Git ──► Reporter
     └─ MEDIUM/HIGH risk ► Leader ──► Planner (analysis + approval)
                                        └─ ⏸ GATE: User Approval
                                            └─ Developer ──► Reviewer ──► Git ──► Reporter
```

## Step-by-Step

### Step 1 — Debug (always first)
- Find exact root cause: file:line + why it breaks
- Do NOT guess-fix without reading the actual code
- Output: `Root cause: <file:line> | Fix: <description> | Risk: LOW/MEDIUM/HIGH`

### Step 2 — Risk gate
- **LOW**: Developer can proceed with a brief self-plan (no planner needed)
- **MEDIUM/HIGH**: Route to leader → planner → user approval → developer

### Step 3 — Minimal fix
- Change only what fixes the root cause
- No opportunistic refactoring
- No "while I'm here" improvements
- py_compile after change

### Step 4 — Verify
```powershell
python -m py_compile app\<fixed_file>.py
python -m pytest tests\<relevant>.py -v --tb=short
```

### Step 5 — Review + Git + Report

## Special Rules

| Situation | Rule |
|-----------|------|
| Bug in `render_pipeline.py` | ALWAYS planner + approval, even for "small" fixes |
| Bug requires schema change | Check backward compat for all API consumers |
| Bug in AI module | Fix must preserve `return None` — never introduce `raise` |
| Bug masks itself silently | Never bypass validation to "fix" it — fix the root cause |
| Root cause unknown | Report unknown, do NOT guess-fix |

## Never

- Apply a fix without understanding root cause
- Add `try/except` to silence an error
- Modify render output validation to make a broken render "succeed"
- Fix multiple unrelated bugs in one commit (one bug per fix)
