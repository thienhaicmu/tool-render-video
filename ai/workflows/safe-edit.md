# Workflow: Safe Edit

## Purpose

Editing any file with medium-to-high blast radius.
Applies whenever Edit tool is being used on a non-LOW-risk file.

## Pre-Conditions (check before starting)

- [ ] Is there an approved plan? If NO → STOP, route to planner
- [ ] Is the file in the protected list? (See `PROJECT_MAP.md` and `AGENTS.md`)
  - If YES → confirm explicit HIGH-risk user approval exists
- [ ] Is the file listed as safe in `CURRENT.md`? Check "What Must NOT Be Touched"

## Step-by-Step

### Step 1 — Read the file first (mandatory)

```
Read tool: <exact file path>
```

Never edit from memory. Never edit based on what a previous session said the file contains.
Current state may differ from assumptions.

### Step 2 — Locate the exact edit point

Identify line numbers and surrounding context.
Verify the code matches what the plan assumed.
If file state differs from plan assumptions → **STOP, re-read, re-plan**.

### Step 3 — Make the minimal edit

Use **Edit tool** (surgical diff), not Write tool (full rewrite).
Change only what the plan specifies.
Do not touch adjacent code even if it looks improvable.

### Step 4 — Verify immediately

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m py_compile app\<changed_file>.py
```

If py_compile fails → fix before proceeding. Do not hand off broken code.

### Step 5 — Run focused test

```powershell
python -m pytest tests\<relevant_test>.py -v --tb=short
```

### Step 6 — Self-review before handoff

- Did I touch more than the plan specified? If yes → undo extras
- Does the diff look minimal? Run `git diff` mentally
- Is the change backward compatible?

### Abort Conditions

| Condition | Action |
|-----------|--------|
| File state differs from plan assumptions | Stop, re-read, inform planner |
| py_compile fails | Fix first, never hand off broken |
| pytest regresses | Fix before declaring done |
| Adjacent code needs cleanup | Note it, do NOT fix it now — separate task |
| Edit would require touching a second protected file | Stop, escalate to leader |
