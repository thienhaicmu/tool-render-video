# Review Workflow — Prompt Template

> **Important:** `/review` is NOT a slash command.
> There is no `POST /api/dev/command {"command": "/review"}`.
>
> This file is a **prompt template** to use manually after completing a patch.

---

## When to Use This

Run a review after any change that:
- Touches `orchestration/render_pipeline.py` or `routes/render.py`
- Modifies frontend files (`render-ui.js`, `render-engine.js`, `index.html`)
- Affects API contracts, status enums, or path conventions
- Spans more than one file
- Was produced by an auto-fix without manual inspection

---

## Review Prompt (Copy-Paste to Claude Code)

```text
Review this patch for scope creep, compatibility risks, and missing validation.

[paste git diff here]

Check:
1. Did the change stay within the stated scope?
2. Are API field names, status enums, and path conventions preserved?
3. Are fallback paths (NVENC→CPU, WS→polling, copy→reencode) intact?
4. Is edit_session_id checked before source_mode dispatch in the pipeline?
5. Is there any silent re-download path when edit_session_id is set?
6. Are text_layer fields (x_percent, y_percent, font_family) preserved?
7. Is there any unrelated refactor in the diff?
8. Are there missing validation guards at the HTTP layer?
9. Does the change stay in the correct layer? (no pipeline logic in routes)

Return:
## Review Result
pass / needs-fix

## Findings
- ...

## Required Fixes
- ...

## Minimal Fix Strategy
- ...
```

---

## Pass Criteria

A patch passes review when:
- [ ] Change is fully contained within the stated scope
- [ ] No API breaking changes without explicit request
- [ ] No fallback path removed
- [ ] No pipeline logic added to routes
- [ ] No unrelated refactor in the diff
- [ ] edit_session_id check comes before source_mode dispatch
- [ ] No silent re-download on missing session
- [ ] /test has been run and result is included
- [ ] Residual risks are explicitly stated

---

## Relationship to prompts/review-fix.md

`prompts/review-fix.md` is the short, reusable prompt template for Claude Code.
This file (`cowork/REVIEW_PROMPT.md`) is the full protocol with context.

Both serve the same purpose — post-patch quality gate — but this file explains *why* each check exists.
