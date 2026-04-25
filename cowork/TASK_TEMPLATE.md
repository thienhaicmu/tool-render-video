# Task Template — Cowork

Use this template when submitting implementation, bug fix, or investigation tasks to Claude Code.

---

## Template

```text
Task: [One-line description — what to fix or implement]

Scope:
- Minimal change only
- Files in scope: [list affected files if known, e.g. backend/app/services/subtitle_engine.py]
- Do not modify files outside scope
- Do not refactor unrelated code

Context:
- [Relevant log line, error code, or job ID]
- [Relevant file and function name]
- [Any constraint or known behavior that must be preserved]

Constraints:
- Preserve API field names and status enums
- Keep fallback paths intact (NVENC→CPU, WS→polling, copy→reencode)
- edit_session_id check must come before source_mode dispatch
- No destructive operations without explicit confirmation

Verify:
- Run /test after change
- Report exact pass/fail output

Output:
## Summary
## Assumptions
## Files Changed
## Verification Result
## Residual Risk
```

---

## Examples

### Bug Fix
```text
Task: Fix subtitle slice SRT offset — subtitles appear 2s late for all segments after the first.

Scope: backend/app/services/subtitle_engine.py only. No refactor.

Context:
- /error returned: step=transcribing_full, exception=IndexError at line 142
- Suspect: offset not applied when slicing SRT for part N > 0

Verify: /test dev
Output: Summary, files changed, test result, risk.
```

### Feature Extension
```text
Task: Add 2:3 aspect ratio support to the render output options.

Scope: Add to aspect ratio preset list only. No UI overhaul. No pipeline changes.

Context:
- Existing presets: 9:16, 1:1, 3:4
- New preset must use same crop/scale logic as existing ones

Verify: /test
Output: Summary, assumptions, files changed, test result.
```

### Root Cause Investigation (no patching)
```text
Task: Analyze the latest render failure and propose the minimal fix.

Inputs:
- /error result (paste here)
- channels/<code>/logs/<job_id>.log (paste relevant lines)

Output: Root cause, exact files and functions, patch plan.
DO NOT patch until plan is explicitly confirmed.
```

### Review a Completed Patch
```text
Review this patch for scope creep, compatibility risks, and missing validation.

[paste git diff here]

Return: pass/needs-fix + required minimal fixes.
Use the checklist in prompts/review-fix.md.
```

---

## Task Quality Checklist (Before Closing)

- [ ] Change is within the stated scope
- [ ] API fields and status enums are preserved
- [ ] Fallback paths are intact
- [ ] /test has been run and result is included
- [ ] Residual risks are explicitly stated
- [ ] No unrelated files were modified
