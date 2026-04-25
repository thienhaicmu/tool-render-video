# Cowork System — Render Studio

This directory is the **authoritative source** for all AI cowork workflows, operator guides, and Claude Code integration in this repository.

Read this file first before running any `/fix`, `/test`, or `/error` command.

---

## Quick Navigation

| File | Purpose |
|---|---|
| [COWORK_SYSTEM_DEFINITION.md](COWORK_SYSTEM_DEFINITION.md) | Full system definition and architecture rules for AI tools |
| [COMMANDS.md](COMMANDS.md) | All supported slash commands with usage |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current phase stability and safe next tasks |
| [LOG_USAGE.md](LOG_USAGE.md) | Where to look when diagnosing errors |
| [TASK_TEMPLATE.md](TASK_TEMPLATE.md) | Template for submitting tasks to Claude Code |
| [FIX_PROMPT.md](FIX_PROMPT.md) | Protocol for /fix workflow |
| [REVIEW_PROMPT.md](REVIEW_PROMPT.md) | Protocol for post-change review (NOT a slash command) |
| [SUMMARY_TEMPLATE.md](SUMMARY_TEMPLATE.md) | Output template for task summaries |
| [HUONG_DAN_SU_DUNG_COWORK.md](HUONG_DAN_SU_DUNG_COWORK.md) | Vietnamese operator guide |
| [business-profile.md](business-profile.md) | Business context for the tool |

---

## Claude Code Workflow Rules

### Before /fix
1. Read `cowork/COWORK_SYSTEM_DEFINITION.md`
2. Read `cowork/COMMANDS.md`
3. Run `git diff` to inspect what has changed
4. Identify the minimum required patch — one file, one function if possible
5. Do NOT refactor unless explicitly requested
6. Do NOT touch runtime files unless the bug lives there

### Before /test
1. Read `cowork/COMMANDS.md` for the exact test command
2. Run the documented QA command only
3. Report exact pass/fail output
4. Do NOT run long render tests unless explicitly requested

### Before /error
1. Check `data/logs/request.log` — Type 1 validation rejections
2. Check `data/logs/error.log` — Type 2 pipeline failures
3. Check `data/logs/app.log` — full pipeline event trace
4. Check per-job log: `channels/<code>/logs/<job_id>.log`
5. Check `data/logs/desktop-backend.log` — Type 3 system errors (Electron, unhandled)

### Before refactor
1. Produce a plan document first and present it to the user
2. Wait for explicit approval before writing any code
3. Never refactor as a side effect of a bug fix
4. Never touch code adjacent to the change scope

---

## Source of Truth

| Directory | Role |
|---|---|
| `cowork/` | Authoritative cowork workflow, commands, status, templates |
| `docs/` | Product and technical documentation |
| `doc/` | Engineering standards, execution policies, flow docs |
| `prompts/` | Reusable Claude Code prompt templates |
| `claude-cowork-v2/` | Companion automation scripts (bug capture, error ranking) |
| Root `README.md` | User-facing quick start only |
| Root `RULES.md` | Coding rules — authoritative |
| Root `STRUCTURE.md` | Folder layout reference — authoritative |

---

## Runtime Files — Do Not Modify Without Explicit Reason

These files define working production behavior. Do not change them during documentation or cowork-structure tasks:

- `backend/app/orchestration/render_pipeline.py`
- `backend/app/services/render_engine.py`
- `backend/app/routes/render.py`
- `backend/app/routes/jobs.py`
- `backend/static/js/render-ui.js`
- `backend/static/js/render-engine.js`
- `backend/static/index.html`
- `backend/static/css/app.css`
