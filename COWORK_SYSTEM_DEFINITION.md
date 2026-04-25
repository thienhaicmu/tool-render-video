> **DEPRECATED — root copy.**
> The authoritative version of this file is [`cowork/COWORK_SYSTEM_DEFINITION.md`](cowork/COWORK_SYSTEM_DEFINITION.md).
> This copy is kept for backward compatibility with any external links.

# COWORK System Definition (Render Studio)

## Purpose
This file defines how to work safely and effectively with AI coworkers (Claude Code, Codex) in this repository.

Goal:
- faster implementation
- safer fixes
- predictable QA and release behavior

## Project Reality (Do Not Violate)

- Render pipeline logic lives in `backend/app/orchestration/render_pipeline.py`.
- `routes/render.py` is HTTP boundary, not pipeline logic.
- Session-based render must not silently re-download when session is missing.
- Keep compatibility for status enums, path conventions (`video_output`/`video_out`), and fallback behavior.

Reference files:
- `RULES.md`
- `doc/engineering-standards.md`
- `doc/project-context.md`

## AI Cowork Roles

## Claude Code / Codex for implementation
Use for:
- focused bug fix
- small feature extension
- refactor with strict compatibility

## Human operator for decisions
Human should decide:
- scope change beyond original request
- destructive operations
- production release timing

## Dev Commands (`/run`, `/test`, `/fix`)

Render Studio exposes dev commands through backend:
- endpoint: `POST /api/dev/command`
- payload: `{"command": "..."}`

### `/run`
Purpose:
- start backend if not running
- return startup status and log source

Example:
```json
{"command":"/run"}
```

### `/test`
Purpose:
- run QA checks via `qa_runner`
- validate core routes and workflow expectations

Examples:
```json
{"command":"/test"}
{"command":"/test dev"}
```

### `/fix`
Purpose:
- apply conservative auto-fix for known bug classes
- otherwise generate targeted fix plan

Examples:
```json
{"command":"/fix"}
{"command":"/fix render ffmpeg"}
{"command":"/fix upload selector"}
```

Notes:
- `/fix` is intentionally conservative.
- If confidence is low, it returns a plan instead of patching.

## Optional Companion Commands
Supported by dev command service:
- `/error`
- `/status`
- `/commit`
- `/features`

## Safe Patch Rules (Mandatory)

1. Smallest correct change only.
2. Edit only required files.
3. No unrelated refactor.
4. Keep API/status/path compatibility unless explicitly changed.
5. Do not remove fallback paths (NVENC->CPU, WS->polling, etc.).
6. Do not run destructive operations unless explicitly requested.
7. State assumptions clearly.
8. Verify touched behavior; if not runnable, provide manual verification steps.

## Patch Workflow

1. Clarify task scope (single bug / single feature).
2. Read relevant context docs.
3. Locate exact code path.
4. Implement minimal patch.
5. Run `/test` (or targeted checks).
6. Summarize risk and next step.

## Prompt Templates (Repository Standard)

Use templates in `prompts/`:

- `prompts/system-coworker.md`
- `prompts/task-executor.md`
- `prompts/review-fix.md`

Recommended sequence:
1. `system-coworker` for behavior framing
2. `task-executor` for implementation
3. `review-fix` for post-change quality gate

## Practical Prompt Snippets

## A. Implement a scoped fix
```text
Task: Fix subtitle translation summary state for mixed failures.
Constraints: Minimal change, no unrelated refactor, preserve API.
Verify: /test dev
Output: Summary, changed files, verification, residual risk.
```

## B. Investigate runtime bug
```text
Task: Analyze latest render failure and propose minimal fix.
Inputs: /error result + channels/<code>/logs/<job_id>.log
Output: Root cause, exact files/functions, patch plan.
```

## C. Review completed patch
```text
Review this patch for scope creep, compatibility risks, and missing validation.
Return pass/needs-fix with required minimal fixes.
```

## Definition of Done (Cowork)

A cowork task is done only when:
- code change is minimal and safe
- behavior matches request
- verification result is included
- remaining risks are explicit
