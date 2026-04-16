# Bug Fix Task — Surgical Repair Only

> Generated automatically from runtime error capture.
> Do NOT restart the project. Do NOT refactor unrelated code.
> Inspect the current workspace and fix only the specific bug described below.

---

## Error Identity

| Field | Value |
|---|---|
| Error ID | `{{ERROR_ID}}` |
| Session ID | `{{SESSION_ID}}` |
| Task ID | `{{TASK_ID}}` |
| Run ID | `{{RUN_ID}}` |
| Timestamp | `{{TIMESTAMP}}` |

---

## Runtime Context

| Field | Value |
|---|---|
| Component | `{{COMPONENT}}` |
| Action | `{{ACTION}}` |
| Error Name | `{{ERROR_NAME}}` |

---

## Error Message

```
{{ERROR_MESSAGE}}
```

---

## Stack Trace

```
{{STACK_TRACE}}
```

---

## Input at Time of Failure

```json
{{INPUT_SUMMARY}}
```

---

## Related Files

{{RELATED_FILES}}

---

## Suspected Runtime Flow

{{SUSPECTED_FLOW}}

---

## Your Task

You are operating in the current workspace. Follow these instructions exactly:

1. **Inspect** — Read the related files and any files in the suspected runtime flow. Do not assume — read the actual current state of the code.

2. **Locate root cause** — Use the error message, stack trace, input summary, and suspected flow to identify the exact line or logic that caused this failure. Be specific.

3. **Fix only this bug** — Make the minimal change required to fix the root cause. Do not:
   - Refactor unrelated code
   - Rename variables or files not involved in this bug
   - Add new features or improve unrelated areas
   - Change project architecture
   - Modify test files unless they directly test the broken behavior

4. **Validate** — Confirm the fix addresses the root cause without introducing new failures.

5. **Return** — Provide:
   - A short root-cause summary (2–4 sentences)
   - Full updated contents of every file you modified (only modified files)

Do not return partial diffs. Return complete updated file contents for each modified file.
