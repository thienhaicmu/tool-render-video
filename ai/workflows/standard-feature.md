# Workflow: Standard Feature

## Flow Diagram

```
User
 └─ Leader (classify + route)
     └─ Planner (analyze + plan)
         └─ ⏸ GATE 1: User Approval
             └─ Developer (implement)
                 ├─ py_compile ✓
                 ├─ pytest ✓
                 └─ Reviewer (review)
                     ├─ PASS ──────────────── Git (commit proposal)
                     │                         └─ ⏸ GATE 2: Push Approval
                     ├─ CONDITIONAL ─────────► Developer (fix) ──► Reviewer
                     └─ REJECT ──────────────► Leader (re-route)
                                               └─ Reporter (summary)
```

## Step-by-Step

### Step 1 — Leader routes
- Read `CURRENT.md` for blockers
- Classify task type + risk level
- Route to planner

### Step 2 — Planner analyzes
- Read mandatory docs (CLAUDE.md → CURRENT.md → PROJECT_MAP.md → AGENTS.md → domain docs)
- Produce analysis template (see `planner.md`)
- List: files to touch, risks, test strategy, rollback, boundaries
- **⏸ STOP — output plan, wait for user approval**

### Step 3 — User approval (Gate 1)
- User reads planner output
- User explicitly says "go ahead" / "approved" / "do it"
- Developer starts ONLY after this confirmation

### Step 4 — Developer implements
- Read the actual files before editing (not from memory)
- Use Edit tool for surgical diffs, not Write tool for full rewrites
- py_compile after each Python file change
- Propose focused test

### Step 5 — Reviewer reviews
- Run `ai/rules/review.md` checklist
- Check auto-reject conditions first
- Output review template with PASS / CONDITIONAL / REJECT

### Step 6 — Git commit proposal
- `git status --short` + `git diff` review
- Propose explicit `git add <specific-file>` per file
- Propose commit message in required format
- **⏸ STOP — WAITING FOR PUSH APPROVAL**

### Step 7 — Reporter summarizes
- Short summary (~30 lines)
- Risks remaining, next steps
- Git status: WAITING FOR APPROVAL

## Timing

Gate 1 must complete before Step 4 starts.
Gate 2 must complete before push executes.
Never skip either gate for any risk level.
