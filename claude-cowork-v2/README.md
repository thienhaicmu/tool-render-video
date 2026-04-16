# Claude Cowork V2

A production-ready AI-assisted engineering pipeline that processes raw engineering requests through a structured, auditable, and reviewable workflow powered by Claude Code.

---

## Purpose

Claude Cowork V2 provides a **normalized, schema-validated pipeline** between engineers and AI execution. Raw requests are never sent directly to the executor. Every task is:

1. Normalized into a structured specification
2. Validated against JSON schemas
3. Assembled into a task pack for the executor
4. Executed through a configurable adapter (Claude CLI, simulated, or dry-run)
5. Reviewed against acceptance criteria
6. Archived as a complete, auditable artifact bundle

---

## Folder Structure

```
claude-cowork-v2/
├── .claude-cowork/
│   ├── config.json          Runtime configuration (overridable via .env)
│   └── state.json           Last-run metadata
│
├── docs/                    Source-of-truth project documentation
│   ├── project-overview.md
│   ├── architecture.md
│   ├── coding-standards.md
│   ├── prompt-rules.md
│   ├── task-definition.md
│   ├── review-checklist.md
│   ├── logging-standard.md
│   └── contexts/
│       ├── backend.md
│       ├── frontend.md
│       ├── testing.md
│       └── infra.md
│
├── prompts/                 Prompt files loaded at runtime
│   ├── system/
│   │   ├── claude-cowork-system.md
│   │   ├── prompt-normalizer-system.md
│   │   └── reviewer-system.md
│   ├── templates/
│   │   ├── execution-task.md
│   │   ├── review-task.md
│   │   └── final-summary.md
│   └── fewshots/
│       └── normalize-examples.md
│
├── schemas/                 JSON schemas for all pipeline artifacts
│   ├── task.schema.json
│   ├── normalized-prompt.schema.json
│   ├── execution-log.schema.json
│   ├── review-report.schema.json
│   ├── artifact-manifest.schema.json
│   └── pipeline-config.schema.json
│
├── scripts/                 TypeScript pipeline implementation
│   ├── types.ts             All TypeScript interfaces
│   ├── config.ts            Config loading and validation
│   ├── logger.ts            Structured JSON logger
│   ├── ids.ts               ID generation
│   ├── schema.ts            Ajv validation utilities
│   ├── prompt-loader.ts     Prompt file loader
│   ├── doc-loader.ts        Documentation loader
│   ├── task-intake.ts       Raw task intake
│   ├── normalize-prompt.ts  Prompt normalization (LLM)
│   ├── build-task-pack.ts   Task pack assembly
│   ├── run-claude-task.ts   Executor adapter
│   ├── collect-results.ts   Result enrichment
│   ├── review-task.ts       Review engine
│   ├── generate-final-summary.ts  Summary generator
│   ├── archive-artifacts.ts Artifact archiving
│   └── pipeline.ts          Main orchestrator
│
├── tasks/
│   ├── incoming/            Raw tasks (input)
│   ├── normalized/          Validated, normalized tasks
│   ├── taskpacks/           Assembled task pack markdowns
│   ├── execution-results/   Execution result JSONs
│   └── reviews/             Review report JSONs
│
├── logs/
│   ├── events/              Structured NDJSON event logs
│   ├── prompts/             Prompt logs for quality review
│   ├── executions/          stdout/stderr from executor
│   └── reviews/             Review logs
│
├── artifacts/               Artifact bundles (one dir per task/run)
│   └── <task_id>/<run_id>/
│       ├── raw-prompt.json
│       ├── normalized-prompt.json
│       ├── task-pack.md
│       ├── execution-result.json
│       ├── review-report.json
│       ├── final-summary.md
│       ├── artifact-manifest.json
│       └── logs-index.ndjson
│
├── package.json
├── tsconfig.json
├── .env.example
└── .gitignore
```

---

## Setup

### Prerequisites

- Node.js >= 20.0.0
- npm or pnpm

### Install

```bash
cd claude-cowork-v2
npm install
```

### Configure

```bash
cp .env.example .env
# Edit .env to set your providers, API keys (if using real LLM), and executor mode
```

### Type check

```bash
npm run typecheck
```

---

## Running the Pipeline

### Full pipeline run (recommended starting point)

```bash
# From a sample JSON file
npm run pipeline -- --file tasks/incoming/sample-task.json

# From a quick prompt (development)
npm run pipeline -- --prompt "Fix the login bug" --by "alice"

# Resume from a previously intake'd task
npm run pipeline -- --task-id task_abc123def456
```

### Individual stages

```bash
# Intake a raw task
npm run intake -- --file tasks/incoming/sample-task.json

# Normalize a task (requires it to be intake'd first)
npm run normalize -- tasks/incoming/<task_id>.json

# Execute a task pack
npm run execute -- --task-id <task_id>

# Review an execution result
npm run review -- --task-id <task_id>

# Archive artifacts
npm run archive -- --task-id <task_id>
```

---

## Development Mode vs Production Mode

| Setting | Development | Production |
|---|---|---|
| `CLAUDE_EXECUTOR_MODE` | `simulated` | `claude_cli` |
| `NORMALIZER_PROVIDER` | `mock` | `openai_compat` |
| `REVIEWER_PROVIDER` | `mock` or `deterministic` | `openai_compat` |
| `LOG_LEVEL` | `debug` | `info` |

**Development mode** (defaults in `.env.example`) runs the entire pipeline without any real LLM calls or Claude CLI execution. All stages complete and produce valid artifacts — but normalized tasks and review reports are deterministic mocks.

**Production mode** requires:
- `NORMALIZER_API_KEY` — API key for the normalizer LLM
- `REVIEWER_API_KEY` — API key for the reviewer LLM (can be same key)
- `claude` CLI installed and authenticated (`claude --version` works)

---

## Plugging In Real LLM Providers

### Normalizer (normalize-prompt.ts)

The normalizer uses an `OpenAICompatNormalizerProvider` that works with any OpenAI-compatible endpoint, including Anthropic's Claude API.

Set in `.env`:
```
NORMALIZER_PROVIDER=openai_compat
NORMALIZER_MODEL=claude-sonnet-4-6
NORMALIZER_BASE_URL=https://api.anthropic.com/v1
NORMALIZER_API_KEY=sk-ant-...
```

### Reviewer (review-task.ts)

Same pattern:
```
REVIEWER_PROVIDER=openai_compat
REVIEWER_MODEL=claude-sonnet-4-6
REVIEWER_BASE_URL=https://api.anthropic.com/v1
REVIEWER_API_KEY=sk-ant-...
```

### Adding a new provider

1. Implement the `NormalizerProvider` or `ReviewerProviderInterface` interface in the respective script.
2. Add a new `case` to the factory function (`createNormalizerProvider` / `createReviewerProvider`).
3. Add the new value to the `NormalizerProvider` union type in `types.ts`.
4. Add it to `pipeline-config.schema.json`.

---

## Real Claude CLI Execution

`ClaudeCliExecutor` in `scripts/run-claude-task.ts` runs the real Claude Code CLI.

When `CLAUDE_EXECUTOR_MODE=claude_cli`, the executor:

1. Pipes the assembled task pack to `claude` via stdin
2. Runs `claude --print --output-format json` (non-interactive, structured output)
3. Parses the JSON response to extract the result text and error flag
4. Falls back to raw stdout if the CLI version does not support `--output-format json`
5. Writes full stdout/stderr to `logs/executions/<run_id>-stdout.txt` / `-stderr.txt`

**Prerequisites:**
- `claude` CLI installed and on `PATH` (or set `CLAUDE_CLI_COMMAND` to the full path)
- Claude Code authenticated: run `claude --version` to verify

**Optional CLI flags** (add to the `cliArgs` array in `ClaudeCliExecutor.execute()` per your CLI version):

| Flag | Purpose |
|---|---|
| `--no-auto-updates` | Suppress update-check output that can corrupt JSON stdout |
| `--dangerously-skip-permissions` | For headless CI environments without interactive approval |

**Configuration:**
```
CLAUDE_EXECUTOR_MODE=claude_cli
CLAUDE_CLI_COMMAND=claude   # or absolute path, e.g. /usr/local/bin/claude
TIMEOUT_SECONDS=300         # per-attempt timeout; retried up to MAX_RETRIES times
MAX_RETRIES=2
```

---

## Artifact Lifecycle

Each pipeline run produces an artifact bundle at:
```
artifacts/<task_id>/<run_id>/
```

Contents:
- `raw-prompt.json` — original submission
- `normalized-prompt.json` — structured specification
- `task-pack.md` — what was sent to the executor
- `execution-result.json` — what the executor produced
- `review-report.json` — review verdict and scores
- `final-summary.md` — human-readable run summary
- `artifact-manifest.json` — file index with checksums
- `logs-index.ndjson` — structured event log for this run

Bundles are retained for `retention_days` (default: 30). The `retention_expires_at` field in the manifest indicates when it may be pruned.

---

## Logging Strategy

All logs are structured NDJSON. Each entry contains:

```json
{
  "timestamp": "2026-04-16T08:00:00.000Z",
  "level": "info",
  "component": "normalize-prompt",
  "task_id": "task_abc123",
  "run_id": "run_xyz789",
  "session_id": "sess_def456",
  "message": "task.normalized",
  "event_name": "task.normalized",
  "status": "completed",
  "metadata": { "task_type": "bugfix", "complexity": "small" }
}
```

Log files:
- `logs/events/<date>.ndjson` — all events by date
- `logs/events/<task_id>-events.ndjson` — all events for a specific task
- `logs/prompts/<task_id>-normalize.json` — prompt sent to normalizer LLM
- `logs/executions/<run_id>-stdout.txt` — executor stdout
- `logs/reviews/<task_id>-<run_id>.json` — review report copy

---

## Security Notes

1. **API keys are never in config files.** They are read from environment variables in the provider adapters.
2. **Raw prompts are never logged with secrets.** The prompt log contains the full prompt (for quality review) but providers must not pass secrets in prompt text.
3. **Logs never contain API keys, tokens, or passwords.** The logger intentionally omits the config's API key fields.
4. **`.env` is in `.gitignore`.** Never commit `.env`.

---

## Schema Validation

All pipeline artifacts are validated at creation time:

| Artifact | Schema |
|---|---|
| Raw task | `task.schema.json` |
| Normalized task | `normalized-prompt.schema.json` |
| Execution result | `execution-log.schema.json` |
| Review report | `review-report.schema.json` |
| Artifact manifest | `artifact-manifest.schema.json` |
| Pipeline config | `pipeline-config.schema.json` |

Validation uses Ajv with `allErrors: true` — all schema violations are reported, not just the first.

---

## Extending the Pipeline

### Add a new stage

1. Create `scripts/my-new-stage.ts` with a named export function.
2. Import and call it in `pipeline.ts` using `runStage()`.
3. Add appropriate event logging (`logger.event(...)`).
4. Persist any new artifacts and register them in `archiveArtifacts`.
5. Add a schema if the stage produces structured output.

### Customize normalization behavior

Edit `prompts/system/prompt-normalizer-system.md` to adjust how the normalizer interprets requests.

Add new few-shot examples to `prompts/fewshots/normalize-examples.md`.

### Customize review behavior

Edit `prompts/system/reviewer-system.md` and `prompts/templates/review-task.md`.

The deterministic reviewer rules are in `review-task.ts → buildDeterministicReview()`.

---

## Troubleshooting

**Pipeline exits with "Critical stage failed: normalization"**
- Check `logs/prompts/<task_id>-normalize.json` for the prompt sent to the normalizer.
- If using `mock` provider, this should never fail — check for a schema validation error.
- If using `openai_compat`, verify your API key and base URL.

**Task pack is missing `{{VARIABLE}}` placeholders**
- The execution-task.md template has an unmatched variable name.
- Check `prompts/templates/execution-task.md` for `{{VAR}}` patterns.
- Ensure the corresponding variable is set in `build-task-pack.ts → renderTaskPack()`.

**Review verdict is always `changes_requested`**
- Switch `REVIEWER_PROVIDER=openai_compat` for intelligent LLM-based review.
- The deterministic reviewer gives `accepted_with_followup` for simulated runs with score >= 6.

**Artifacts not appearing**
- Check `logs/events/` for `artifact.archived` events.
- Verify `ARTIFACT_ROOT` is writable.
