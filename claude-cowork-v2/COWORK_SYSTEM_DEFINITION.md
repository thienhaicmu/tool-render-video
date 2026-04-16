# COWORK SYSTEM DEFINITION
**Version**: 2.0 | **Language**: English | **Scope**: Claude Cowork V2

---

## 1. Purpose

The Cowork System is a structured protocol between an engineer and an AI agent (Claude Code).

Its purpose is to ensure that every engineering task is:
- Unambiguous before execution begins
- Schema-validated at every pipeline boundary
- Executed within declared scope without improvisation
- Reviewed against explicit acceptance criteria
- Archived as a complete, auditable artifact bundle

Without a cowork system, AI agents improvise scope, skip validation, and produce outputs that cannot be audited, reproduced, or safely rolled back. With a cowork system, AI execution becomes deterministic, traceable, and safe for production codebases.

---

## 2. Core Concept

The Cowork System has three layers:

```
┌─────────────────────────────────────────────────────────┐
│                    COWORK CORE                          │
│  Pipeline infrastructure: schemas, stages, logging,     │
│  retry logic, template engine, artifact bundling.       │
│  Reusable across any project. Never domain-specific.    │
├─────────────────────────────────────────────────────────┤
│                  BUSINESS PROFILE                       │
│  Project-specific: domain vocabulary, acceptance rules, │
│  entity definitions, risk criteria, coding standards.   │
│  Cloned and adapted per project.                        │
├─────────────────────────────────────────────────────────┤
│                     ADAPTER                             │
│  Glue: doc paths, LLM providers, executor mode,         │
│  environment variables, CLI config.                     │
│  Configured per deployment environment.                 │
└─────────────────────────────────────────────────────────┘
```

### Cowork Core
The invariant layer. Contains:
- 10-stage pipeline orchestrator (`pipeline.ts`)
- JSON schema validation at every stage boundary (Ajv)
- Structured NDJSON event logger with 13 event types
- Template engine with `{{VARIABLE}}` substitution and fail-fast unresolved placeholder detection
- Retry + timeout wrapper for all LLM calls (exponential backoff, 3 attempts, 60s per-call timeout)
- Artifact bundler with sha256 checksums and retention timestamps

### Business Profile
The project-specific layer. Contains:
- Domain vocabulary and terminology rules
- Business entities and their relationships
- Acceptance criteria patterns for this domain
- Risk categories specific to the business
- Coding standards and architectural constraints
- Example normalizations (few-shot examples) tuned to this domain

### Adapter
The environment-specific layer. Contains:
- `.env` configuration (executor mode, LLM providers, API keys, paths)
- `docs/` project documentation injected into normalization context
- `.claude-cowork/config.json` runtime overrides

---

## 3. Standard Folder Structure

```
project-root/
│
├── claude-cowork-v2/                   ← COWORK ROOT
│   │
│   ├── .claude-cowork/
│   │   ├── config.json                 ← Runtime config overrides
│   │   └── state.json                  ← Last-run metadata
│   │
│   ├── docs/                           ← BUSINESS PROFILE DOCS (injected at normalization)
│   │   ├── project-overview.md
│   │   ├── architecture.md
│   │   ├── coding-standards.md
│   │   ├── prompt-rules.md
│   │   ├── task-definition.md
│   │   ├── review-checklist.md
│   │   ├── logging-standard.md
│   │   └── contexts/
│   │       ├── backend.md
│   │       ├── frontend.md
│   │       ├── testing.md
│   │       └── infra.md
│   │
│   ├── prompts/
│   │   ├── system/
│   │   │   ├── claude-cowork-system.md     ← AI behavioral constraints
│   │   │   ├── prompt-normalizer-system.md ← Normalizer LLM instructions
│   │   │   └── reviewer-system.md          ← Reviewer LLM instructions + schema contract
│   │   ├── templates/
│   │   │   ├── execution-task.md           ← Task pack template ({{VARIABLE}} format)
│   │   │   ├── review-task.md              ← Reviewer instruction block (static, no variables)
│   │   │   └── final-summary.md            ← Human-readable summary template
│   │   └── fewshots/
│   │       └── normalize-examples.md       ← Calibration examples for normalizer LLM
│   │
│   ├── schemas/                            ← JSON Schema (Ajv, draft-07, additionalProperties: false)
│   │   ├── task.schema.json
│   │   ├── normalized-prompt.schema.json
│   │   ├── execution-log.schema.json
│   │   ├── review-report.schema.json
│   │   ├── artifact-manifest.schema.json
│   │   └── pipeline-config.schema.json
│   │
│   ├── scripts/                            ← PIPELINE IMPLEMENTATION
│   │   ├── types.ts                        ← All TypeScript interfaces (single source of truth)
│   │   ├── config.ts                       ← Config loading + validation
│   │   ├── logger.ts                       ← Structured JSON logger
│   │   ├── ids.ts                          ← ID generation
│   │   ├── schema.ts                       ← Ajv validation utilities
│   │   ├── prompt-loader.ts                ← Prompt file loader
│   │   ├── doc-loader.ts                   ← Doc context builder
│   │   ├── task-intake.ts                  ← Stage 1: Raw task ingestion
│   │   ├── normalize-prompt.ts             ← Stage 2: LLM normalization
│   │   ├── build-task-pack.ts              ← Stage 3: Task pack assembly
│   │   ├── run-claude-task.ts              ← Stage 4: Executor
│   │   ├── collect-results.ts              ← Stage 5: Result enrichment
│   │   ├── review-task.ts                  ← Stage 6: Review engine
│   │   ├── generate-final-summary.ts       ← Stage 7: Summary generator
│   │   ├── archive-artifacts.ts            ← Stage 8: Artifact bundler
│   │   └── pipeline.ts                     ← Main orchestrator
│   │
│   ├── tasks/
│   │   ├── incoming/                       ← Raw task JSON inputs
│   │   ├── normalized/                     ← Validated NormalizedPrompt JSON
│   │   ├── taskpacks/                      ← Assembled task pack markdowns
│   │   ├── execution-results/              ← ExecutionResult JSON
│   │   └── reviews/                        ← ReviewReport JSON
│   │
│   ├── logs/
│   │   ├── events/                         ← NDJSON event logs (by date + by task)
│   │   ├── prompts/                        ← Full prompts sent to LLM (for quality audit)
│   │   ├── executions/                     ← CLI stdout/stderr captures
│   │   └── reviews/                        ← Review report copies
│   │
│   ├── artifacts/                          ← Immutable artifact bundles
│   │   └── <task_id>/<run_id>/
│   │       ├── raw-prompt.json
│   │       ├── normalized-prompt.json
│   │       ├── task-pack.md
│   │       ├── execution-result.json
│   │       ├── review-report.json
│   │       ├── final-summary.md
│   │       ├── artifact-manifest.json      ← Checksums + retention timestamp
│   │       └── logs-index.ndjson
│   │
│   ├── COWORK_SYSTEM_DEFINITION.md         ← THIS FILE
│   ├── HUONG_DAN_SU_DUNG_COWORK.md
│   ├── business-profile.md
│   ├── package.json
│   ├── tsconfig.json
│   ├── .env
│   └── .env.example
│
└── [main project source]                   ← The business codebase the AI works on
```

---

## 4. Template System

All task-facing documents use `{{VARIABLE}}` placeholders. The renderer performs exact string replacement and enforces that zero unresolved placeholders survive to disk.

### Template variables — execution-task.md

| Variable | Source |
|---|---|
| `{{TASK_ID}}` | `NormalizedPrompt.task_id` |
| `{{RUN_ID}}` | Generated `run_id` |
| `{{TITLE}}` | `NormalizedPrompt.title` |
| `{{GENERATED_AT}}` | `nowIso()` |
| `{{COMPLEXITY}}` | `NormalizedPrompt.estimated_complexity` |
| `{{TASK_TYPE}}` | `NormalizedPrompt.task_type` |
| `{{OBJECTIVE}}` | `NormalizedPrompt.objective` |
| `{{BUSINESS_CONTEXT}}` | `NormalizedPrompt.business_context` |
| `{{DOC_CONTEXT}}` | Aggregated project documentation |
| `{{SCOPE_IN}}` | Bullet list from `scope_in[]` |
| `{{SCOPE_OUT}}` | Bullet list from `scope_out[]` |
| `{{CONSTRAINTS}}` | Bullet list from `constraints[]` |
| `{{ASSUMPTIONS}}` | Bullet list from `assumptions[]` |
| `{{RELATED_FILES}}` | Bullet list from `related_files[]` |
| `{{ACCEPTANCE_CRITERIA}}` | Numbered list from `acceptance_criteria[]` |
| `{{LOGGING_REQUIREMENTS}}` | Bullet list from `logging_requirements[]` |
| `{{EXPECTED_DELIVERABLES}}` | Bullet list from `expected_deliverables[]` |
| `{{RISK_FLAGS}}` | Bullet list from `risk_flags[]` |
| `{{REVIEW_CHECKPOINTS}}` | Bullet list from `review_checkpoints[]` |

### Template variables — final-summary.md

`{{TITLE}}`, `{{TASK_ID}}`, `{{RUN_ID}}` (×2), `{{TASK_TYPE}}`, `{{COMPLEXITY}}`, `{{GENERATED_AT}}`, `{{OBJECTIVE}}`, `{{BUSINESS_CONTEXT}}`, `{{EXECUTION_STATUS}}`, `{{EXECUTOR_MODE}}`, `{{DURATION_MS}}`, `{{EXIT_CODE}}`, `{{EXECUTION_SUMMARY}}`, `{{FILES_CHANGED}}`, `{{RISKS}}`, `{{VERDICT_BADGE}}`, `{{OVERALL_SCORE}}`, `{{SCOPE_FIT_SCORE}}`, `{{SAFETY_SCORE}}`, `{{LOGGING_SCORE}}`, `{{CRITERIA_TABLE}}`, `{{SCOPE_ASSESSMENT}}`, `{{SAFETY_ASSESSMENT}}`, `{{LOGGING_ASSESSMENT}}`, `{{REVIEW_SUMMARY}}`, `{{RECOMMENDATIONS}}`, `{{FOLLOWUP_TASKS}}`, `{{BLOCKING_ISSUES}}`, `{{SESSION_ID}}`

### Fail-fast rule

If any `{{VARIABLE}}` pattern remains in rendered output, the pipeline throws immediately with a specific list of unresolved placeholders. Silent broken templates are not permitted.

---

## 5. Schema Principle

Every pipeline artifact is defined by a JSON Schema and validated at creation time.

**Schema properties enforced on all schemas:**
- `"additionalProperties": false` — no undocumented fields survive validation
- `"required": [...]` — mandatory fields explicitly declared
- Enum constraints on all categorical fields
- Format constraints (`date-time`, `uri`) where applicable

**Schema validation chain:**

```
RawTask               → task.schema.json
NormalizedPrompt      → normalized-prompt.schema.json
ExecutionResult       → execution-log.schema.json
ReviewReport          → review-report.schema.json
ArtifactManifest      → artifact-manifest.schema.json
PipelineConfig        → pipeline-config.schema.json
```

**Key schema constraints:**
- `schema_version: "2.0"` is a required field on all domain artifacts
- `estimated_complexity` enum: `trivial | small | medium | large | xl` — `"epic"` is not valid
- `reviewer_mode`: `llm | deterministic | mock`
- Review scores are flat fields (`scope_fit_score`, `safety_score`, `logging_score`, `overall_score`) — NOT nested under `"scores"`
- `acceptance_criteria_results[].met` values: `yes | no | partial | not_verifiable`
- `acceptance_criteria_results[].evidence` (NOT `notes`)
- `followup_tasks` (NOT `followup_actions`)

---

## 6. Task System

### Task Types

| Type | Description | Common in this project |
|---|---|---|
| `bugfix` | Fix a defect in existing behavior | API route failures, render pipeline bugs |
| `feature` | Add new user-facing functionality | New upload channel, new render option |
| `refactor` | Improve structure without changing behavior | Service extraction, type improvements |
| `infra` | Infrastructure, tooling, configuration | Docker, CI, database migrations |
| `docs` | Documentation updates | API docs, README, architecture diagrams |
| `test` | Add or fix tests | Unit tests, integration tests |
| `security` | Security-related changes | Auth, input validation, secrets handling |
| `performance` | Performance improvements | Query optimization, caching, concurrency |

### Task Complexity

| Level | LOC | Files | Scope |
|---|---|---|---|
| `trivial` | < 10 | 1 | Single-line or config change |
| `small` | < 50 | 1–2 | Contained logic change |
| `medium` | < 200 | 2–5 | May touch API boundary |
| `large` | < 500 | 5+ | Cross-cutting concern |
| `xl` | > 500 | many | Should be decomposed before execution |

### Task Priority

`low` | `normal` | `high` | `critical`

### Task Lifecycle

```
submitted → intake → normalized → validated → task_pack_built
         → executed → results_collected → reviewed
         → summarized → archived
```

### Event Types (13 total)

```
task.received
task.normalized
task.validation.failed
task.packaged
task.execution.started
task.execution.completed
task.execution.failed
task.review.started
task.review.completed
artifact.archived
pipeline.completed
pipeline.failed
llm.retry / llm.timeout / llm.failed / executor.retry / executor.failed
```

---

## 7. Workflow

### Full pipeline (10 stages)

```
Stage 1  INTAKE          Receive raw task, assign task_id, persist to tasks/incoming/
Stage 2  NORMALIZE       LLM transforms raw prompt → NormalizedPrompt (schema-validated)
Stage 3  BUILD PACK      Render execution-task.md template → task pack markdown
Stage 4  EXECUTE         Claude CLI processes task pack via stdin (--print --output-format json)
Stage 5  COLLECT         Enrich ExecutionResult (files_changed, risks, followups)
Stage 6  REVIEW          LLM or deterministic review → ReviewReport (schema-validated)
Stage 7  SUMMARIZE       Render final-summary.md from all stage outputs
Stage 8  ARCHIVE         Bundle all artifacts, compute checksums, write manifest
Stage 9  FINALIZE        Write pipeline.completed event, update state.json
Stage 10 SURFACE         Print summary table to console, exit 0 or 1
```

### Critical vs non-critical stages

| Stage | Critical | Behavior on failure |
|---|---|---|
| normalize | YES | Pipeline stops, partial archive attempted |
| build-task-pack | YES | Pipeline stops |
| execute | YES | Pipeline stops |
| collect-results | NO | Skipped, execution result used as-is |
| review | NO | Fallback deterministic review used |
| generate-final-summary | NO | Skipped, archive continues |
| archive | NO | Warning logged |

### Executor modes

| Mode | Behavior | When to use |
|---|---|---|
| `claude_cli` | Real Claude Code CLI execution via stdin | Production |
| `simulated` | Returns realistic mock result in 200ms | Development, CI |
| `dry_run` | Validates task pack only, no execution | Config verification |

### LLM provider modes

| Stage | Mock | Real |
|---|---|---|
| Normalize | `mock` — deterministic hardcoded NormalizedPrompt | `openai_compat` — any OpenAI-compatible endpoint |
| Review | `deterministic` — rule-based scoring | `openai_compat` — LLM-based code review |

---

## 8. AI Responsibilities

### What AI MUST do

1. **Read before writing.** Read every file that will be modified before making any change.
2. **Stay within declared scope.** Only touch files explicitly listed in `scope_in` or `related_files`.
3. **Satisfy acceptance criteria.** Every criterion in the task pack must be addressed.
4. **Emit required log events.** Every `logging_requirements` item must be implemented.
5. **Validate at boundaries.** Do not persist data that has not passed schema validation.
6. **Report what changed.** Produce a structured list of files read and files modified.
7. **Flag risks.** If an unexpected risk is discovered during execution, add it to `risks[]`.
8. **Produce a summary.** Write a 2-3 sentence summary of what was done.

### What AI must NOT do (see Section 10)

---

## 9. Clone Rules

When cloning this cowork system for a new project:

### Keep unchanged (Cowork Core)
- All `scripts/*.ts` files
- All `schemas/*.json` files
- `package.json`, `tsconfig.json`
- `prompts/templates/execution-task.md` structure (variables may be extended)
- `prompts/templates/review-task.md` (static instruction block)
- `prompts/system/claude-cowork-system.md`
- Logging format and event taxonomy

### Change for the new project (Business Profile)
- `docs/project-overview.md` — describe the new project
- `docs/architecture.md` — new architecture
- `docs/coding-standards.md` — new coding standards
- `docs/contexts/*.md` — new domain contexts
- `prompts/fewshots/normalize-examples.md` — add domain-specific examples
- `prompts/system/prompt-normalizer-system.md` — refine complexity calibration if needed
- `prompts/system/reviewer-system.md` — keep structure, adjust domain-specific review criteria
- `business-profile.md` — rewrite entirely for new project
- `HUONG_DAN_SU_DUNG_COWORK.md` — update examples for new domain

### Adapt per environment (Adapter)
- `.env` / `.env.example` — new API keys, paths, executor mode
- `.claude-cowork/config.json` — runtime overrides
- `CLAUDE_CLI_COMMAND` — path to Claude CLI
- `PROJECT_NAME` — new project name

### Never do when cloning
- Do not reuse `task_id` or `run_id` namespaces across projects
- Do not copy `tasks/`, `logs/`, `artifacts/` directories (these are runtime data)
- Do not hardcode API keys in any file
- Do not rename `schema_version` or change the `2.0` value without migrating all schemas

---

## 10. Constraints (What AI Must NOT Do)

These constraints apply to the Claude Code executor operating on the main project codebase:

1. **No scope creep.** If a file is listed in `scope_out`, it must not be read for writing purposes. Do not refactor code adjacent to the fix.
2. **No silent failures.** If an operation fails, surface it in `risks[]` or `errors`. Never catch-and-swallow.
3. **No untested schema changes.** Do not modify a JSON schema without understanding what artifacts it validates and what downstream effects result.
4. **No gold-plating.** A bugfix does not need a surrounding refactor. A feature does not need extra configurability beyond what was specified.
5. **No hardcoded secrets.** API keys, tokens, passwords must never appear in source files, even temporarily.
6. **No destructive operations without explicit approval.** Deleting files, dropping database tables, resetting migrations — these require explicit specification in the task.
7. **No skipping hooks or CI.** Do not use `--no-verify`, `--force`, or bypass linting/testing.
8. **No improvised dependencies.** Do not add `npm install`, `pip install`, or any new dependency not specified in the task.
9. **No changes to auth, payments, or database schema** unless `task_type` is `security` or `infra` AND the change is in `scope_in`.
10. **No retrying indefinitely.** LLM calls retry at most `max_retries + 1` times (default: 3). After exhaustion, fail fast with a structured error.

---

## 11. Output Requirements

### What the pipeline produces per run

| Artifact | Location | Schema |
|---|---|---|
| `raw-prompt.json` | `artifacts/<task>/<run>/` | `task.schema.json` |
| `normalized-prompt.json` | `artifacts/<task>/<run>/` | `normalized-prompt.schema.json` |
| `task-pack.md` | `artifacts/<task>/<run>/` | Template-rendered markdown |
| `execution-result.json` | `artifacts/<task>/<run>/` | `execution-log.schema.json` |
| `review-report.json` | `artifacts/<task>/<run>/` | `review-report.schema.json` |
| `final-summary.md` | `artifacts/<task>/<run>/` | Template-rendered markdown |
| `artifact-manifest.json` | `artifacts/<task>/<run>/` | `artifact-manifest.schema.json` |
| `logs-index.ndjson` | `artifacts/<task>/<run>/` | NDJSON structured events |
| `<run_id>-stdout.txt` | `logs/executions/` | Raw CLI output |
| `<run_id>-stderr.txt` | `logs/executions/` | Raw CLI errors |
| `<task_id>-normalize.json` | `logs/prompts/` | Full normalization prompt |
| `<date>.ndjson` | `logs/events/` | All events for the day |

### Review verdict thresholds

| Verdict | Condition |
|---|---|
| `accepted` | All criteria met, no scope violations, `overall_score >= 8` |
| `accepted_with_followup` | Criteria mostly met, minor issues, score 6–7 |
| `changes_requested` | Some criteria unmet but fixable, score 4–5 |
| `rejected` | Critical safety issue, OR score < 4, OR objective not addressed |

### Overall score formula

```
overall_score = (scope_fit × 0.25) + (safety × 0.35) + (logging × 0.15) + (completeness × 0.25)
```

Where `completeness` = % of `acceptance_criteria` with `met` = `"yes"` or `"partial"`, scaled 0–10.

---

## 12. Summary

The Cowork System enforces a contract between the engineer and the AI agent across three dimensions:

**Structural** — Every artifact has a schema. No artifact enters the pipeline without passing schema validation. No artifact leaves without being checksummed and archived.

**Behavioral** — The AI executor receives an unambiguous task pack with explicit scope, constraints, acceptance criteria, and logging requirements. It cannot hallucinate scope. It cannot improvise dependencies. It must stay within declared boundaries.

**Operational** — Every stage is logged with structured events. Every LLM call has retry with exponential backoff and a 60-second timeout. Every failure produces a partial artifact bundle for debugging. The pipeline exits non-zero on critical failures.

When cloning to a new project: replace the Business Profile and Adapter layers. The Core is invariant.
