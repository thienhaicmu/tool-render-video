# Workflow: Review Flow

## When Triggered

User asks to review: a file, a diff, a recent commit, a phase output, or any code change.
Also triggered automatically as Step 5 in standard-feature and bugfix workflows.

## Flow Diagram

```
User (review request)
 └─ Reviewer (read + checklist)
     ├─ PASS ───────────► Git (if commit needed) ──► Reporter
     ├─ CONDITIONAL ────► Developer (fix list) ──► Reviewer again
     └─ REJECT ─────────► Leader (re-route + explain) ──► Reporter
```

## Step-by-Step

### Step 1 — Identify scope
- What exactly is being reviewed? Single file? Diff? Phase output?
- Read only the changed files (not the entire codebase)

### Step 2 — Auto-reject check first (fastest gate)
Check `ai/rules/review.md` auto-reject conditions:
- Protected file edited without approval? → REJECT immediately
- Sacred aliases removed? → REJECT immediately
- `git add .` proposed? → REJECT immediately
- If any auto-reject triggered → stop reviewing, report REJECT with reason

### Step 3 — Full checklist
Run `ai/rules/review.md` review checklist:
- API contracts
- WebSocket shape
- RenderRequest defaults
- result_json aliases
- AI graceful degradation
- Output validation intact
- Overengineering detection

### Step 4 — Output review template
Use `reviewer.md` template exactly.
Rate: **PASS** | **CONDITIONAL** | **REJECT**

### Step 5 — Handoff
- **PASS** → git (if commit needed) or reporter (if docs/no tracked changes)
- **CONDITIONAL** → developer with exact conditions list, re-review after fix
- **REJECT** → leader with clear explanation

## Token Optimization

Read only what changed.
Do not read `render_pipeline.py` in full unless the review is specifically about it.
Focus review time on regressions and contracts, not style.
