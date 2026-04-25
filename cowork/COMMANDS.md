# Slash Commands — Render Studio

All commands are routed through the dev command endpoint:

```
POST /api/dev/command
Content-Type: application/json

{"command": "/command-name [optional-args]"}
```

---

## Supported Commands

### /run

**Purpose:** Start the backend if not running. Confirm the backend is alive.

**Use when:**
- Backend is stopped or was just restarted after a code change
- Pre-flight check before running /test or /fix

**Expected response:**
- Backend status: already running or just started
- Log source: `data/logs/dev_run.log`

```json
{"command": "/run"}
```

---

### /test

**Purpose:** Run QA checks via `qa_runner`. Validate core routes and workflow expectations.

**Use when:**
- After any code change — run at minimum once after every patch
- To confirm no regressions before closing a task

```json
{"command": "/test"}
{"command": "/test dev"}
```

**Expected response:** pass/fail per check. Always report exact output, not a summary.

---

### /fix

**Purpose:** Apply a conservative auto-fix for known bug classes. If confidence is low, returns a fix plan instead of patching.

**Use when:** You have a structured error from `/error` or a log trace.

**This command is intentionally conservative:**
- If it cannot patch safely, it returns a plan.
- Do not force a patch if it returns a plan — present the plan to the user first.

```json
{"command": "/fix"}
{"command": "/fix render ffmpeg"}
{"command": "/fix upload selector"}
```

---

### /error

**Purpose:** Retrieve the highest-priority structured error from the error log.

**Use when:** A job has failed or the render pipeline has produced an error.

```json
{"command": "/error"}
```

**Expected response:** Structured error summary with error code, step, and message.
Follow up by reading: `data/logs/error.log` and `channels/<code>/logs/<job_id>.log`.

---

### /status

**Purpose:** Return the current system state — backend health, active jobs, last job result.

```json
{"command": "/status"}
```

---

### /log

**Purpose:** Return recent log lines from the structured log files.

```json
{"command": "/log"}
{"command": "/log error"}
{"command": "/log app 100"}
```

See [LOG_USAGE.md](LOG_USAGE.md) for full log file reference.

---

### /commit

**Purpose:** Generate a commit message from the current diff and stage changes for commit.

```json
{"command": "/commit"}
```

---

### /features

**Purpose:** Return the current feature summary for the project.

```json
{"command": "/features"}
```

---

## NOT a Slash Command

### /review

`/review` is **NOT** a slash command. There is no:
```json
{"command": "/review"}
```

The review workflow is a **prompt template**: [`prompts/review-fix.md`](../prompts/review-fix.md).

Use it by:
1. Opening `prompts/review-fix.md`
2. Copying the prompt into a Claude Code message after completing a patch
3. Following the checklist in that file

See also: [REVIEW_PROMPT.md](REVIEW_PROMPT.md) for the full protocol.

---

## Recommended Debug Sequence

```
/status     → confirm backend is alive
/error      → get the highest-priority structured error
/log error  → inspect raw error lines
/fix        → apply patch or get a plan
/test       → verify after patch
/commit     → stage and commit if tests pass
```
