# Project Initialization — Universal Onboarding Workflow

> Triggered by: `/leader initialize project` or `/leader audit current architecture`
> Owner: Leader (orchestrates), Architect (interprets findings)
> Outputs: PROJECT_CONTEXT.md, ARCHITECTURE.md, memory/CURRENT.md, memory/TASK.md, memory/RISKS.md, memory/DECISIONS.md
> Version: 1.0

---

## Purpose

Before any agent can work safely, the system must understand what it is working on.
This workflow replaces human-written project documentation when it doesn't exist,
augments it when it's incomplete, and audits it when it may be stale.

**This workflow runs in two scenarios:**
1. **Cold start** — no `PROJECT_CONTEXT.md` exists. The framework has never been used on this project.
2. **Architecture audit** — `PROJECT_CONTEXT.md` exists but the user wants it refreshed, or the team suspects it is stale.

**This workflow never edits source code.** It reads and infers only.

---

## Anti-Hallucination Contract

This contract governs the entire workflow. Every violation is a defect.

```
RULE 1: Never state a fact you cannot cite.
  Every inference must name the file or pattern that produced it.
  BAD:  "This project uses Redis for caching."
  GOOD: "This project likely uses Redis for caching (found: requirements.txt:redis==4.6.0, src/cache/redis_client.py)"

RULE 2: Confidence must be explicit.
  Every inferred fact carries a confidence level: HIGH | MEDIUM | LOW
  LOW confidence inferences are questions, not answers.
  BAD:  "Stack: Python / FastAPI"
  GOOD: "Stack: Python / FastAPI [HIGH — pyproject.toml, fastapi in dependencies, routers/ directory]"

RULE 3: Absence of evidence is not evidence of absence.
  If you cannot find tests, say "no test files detected" — not "this project has no tests."
  If you cannot find auth logic, say "auth logic not detected" — not "this project has no auth."

RULE 4: Never invent structure.
  Do not describe directories or files that you have not seen.
  Do not describe behaviors you have inferred from variable names alone.

RULE 5: State all uncertainty in the output files.
  Every section of every generated file must end with a confidence level.
  Sections with LOW confidence must be marked clearly for human review.
```

---

## Phase 1 — Repository Scan

Leader scans the repository in this order. Every scan step produces a list of findings.

### 1.1 — Entry Point Detection

Look for these files:
```
Python:    pyproject.toml, setup.py, setup.cfg, requirements.txt, Pipfile, poetry.lock
Node/TS:   package.json, tsconfig.json, bun.lockb, pnpm-lock.yaml, yarn.lock
.NET/C#:   *.sln, *.csproj, global.json, NuGet.config
Go:        go.mod, go.sum
Java:      pom.xml, build.gradle, build.gradle.kts, settings.gradle
Rust:      Cargo.toml, Cargo.lock
Ruby:      Gemfile, Gemfile.lock, .ruby-version
PHP:       composer.json, composer.lock
Elixir:    mix.exs, mix.lock
```

Record: which files were found, their locations, and whether they are at the root or nested.

### 1.2 — Framework Detection

Scan dependency files and source files for these signatures:

| Framework | Detection Signal |
|---|---|
| FastAPI | `fastapi` in requirements / pyproject; `from fastapi import` in source |
| Django | `django` in requirements; `INSTALLED_APPS` in settings; `manage.py` at root |
| Flask | `flask` in requirements; `from flask import Flask` in source |
| SQLAlchemy | `sqlalchemy` in requirements; `from sqlalchemy` in source |
| Alembic | `alembic.ini` at root; `alembic/` directory |
| Next.js | `next` in package.json; `next.config.js` or `next.config.ts` |
| React | `react` and `react-dom` in package.json |
| Vue | `vue` in package.json; `.vue` files |
| Angular | `@angular/core` in package.json |
| Express | `express` in package.json |
| NestJS | `@nestjs/core` in package.json |
| ASP.NET Core | `Microsoft.AspNetCore` in .csproj; `[ApiController]` in source |
| Entity Framework | `Microsoft.EntityFrameworkCore` in .csproj |
| Prisma | `@prisma/client` in package.json; `schema.prisma` |
| Drizzle | `drizzle-orm` in package.json |
| Gin (Go) | `github.com/gin-gonic/gin` in go.mod |
| Fiber (Go) | `github.com/gofiber/fiber` in go.mod |
| Anthropic SDK | `anthropic` in requirements / package.json; `from anthropic import` |
| LangChain | `langchain` in requirements; `from langchain` |

### 1.3 — Directory Structure Scan

Record the top-level directory structure and one level deep. Look for these patterns:

**Architecture signals:**
```
src/ or app/ at root → organized codebase (not everything in root)
controllers/ or routers/ → MVC or REST layer
services/ → service layer separation
models/ or entities/ → data model layer
repositories/ or data/ → data access layer
domain/ + application/ + infrastructure/ → Clean Architecture / DDD
core/ or shared/ → shared utilities
tests/ or test/ or __tests__/ or spec/ → test suite exists
migrations/ or alembic/ or flyway/ → database migration system
```

**Deployment signals:**
```
Dockerfile → containerized
docker-compose.yml or docker-compose.yaml → local orchestration
.github/workflows/ → GitHub Actions CI/CD
.gitlab-ci.yml → GitLab CI
k8s/ or kubernetes/ → Kubernetes
terraform/ → Infrastructure as Code
```

**Danger signals (flag immediately):**
```
*.env committed to the repo → possible credential leak
secrets.* at root → possible credential storage
TODO.md or FIXME.md → known tech debt tracked externally
BROKEN/ or legacy/ or old/ → explicit legacy code
_backup or .bak files → informal version control (technical debt signal)
```

### 1.4 — Codebase Health Scan

Perform these scans to produce health signals:

**God file detection:**
```
Files > 500 lines → flag as potential god file
Files > 1000 lines → flag as confirmed god file
Classes with > 20 methods → flag as potential god class
```

**Dependency hotspot detection:**
```
For each source file, count how many other files import it.
Files imported by > 10 other files → high-risk hotspot
Files imported by > 25 other files → critical hotspot (changes ripple everywhere)
```

**Test coverage signals:**
```
If test directory exists: note its location and apparent scope (unit/integration/e2e)
If no test directory exists: flag as HIGH risk
Check if test files shadow source files (e.g., tests/test_auth.py → src/auth.py)
```

**Tech debt signals:**
```
Search for: TODO, FIXME, HACK, XXX, DEPRECATED, NOSONAR in source files
Count occurrences. Anything > 20 is a tech debt accumulation signal.
Note files with the highest concentration.
```

**Hardcoded credential signals:**
```
Search for patterns: password=, api_key=, secret=, token= followed by a literal string value
Search for: AWS_ACCESS_KEY, sk-, pk-, Bearer <literal> in source files (not config)
Any match → flag as CRITICAL risk in RISKS.md
```

---

## Phase 2 — Inference

After scanning, Leader produces structured inferences. Every inference carries a confidence level.

### Confidence Levels

```
HIGH   — Signal is unambiguous. Multiple corroborating files. No alternative explanation.
MEDIUM — Signal is likely but could be misread. Only one corroborating file, or signal is indirect.
LOW    — Inference is based on convention, naming, or heuristic. Must be marked for human verification.
```

### 2.1 — Stack Inference

```
Language:    [inferred language] [confidence] — [evidence]
Runtime:     [version if detectable] [confidence] — [evidence]
Framework:   [inferred framework(s)] [confidence] — [evidence]
Database:    [inferred DB if any] [confidence] — [evidence]
Queue/Cache: [inferred queue/cache if any] [confidence] — [evidence]
Test fw:     [inferred test framework] [confidence] — [evidence]
Package mgr: [inferred package manager] [confidence] — [evidence]
```

### 2.2 — Architecture Inference

Classify the architecture using directory structure and import patterns:

| Architecture | Signal |
|---|---|
| **Monolith** | Single entry point, single package file, no clear service boundaries |
| **Modular monolith** | Single package file, clear module directories, explicit inter-module contracts |
| **Microservices** | Multiple package files at different directory levels, each with own entry point |
| **MVC** | controllers/ + models/ + views/ (or templates/) |
| **Clean Architecture** | domain/ + application/ + infrastructure/ + (api/ or presentation/) |
| **Hexagonal** | ports/ + adapters/, or core/ + adapters/ |
| **Layered (generic)** | src/api/ + src/services/ + src/data/ or similar vertical layering |
| **Scripts / procedural** | Few directories, many root-level files, no clear architecture pattern |
| **Unknown** | Structure does not match known patterns |

If architecture is `Unknown` or confidence is LOW: flag for human clarification.

### 2.3 — Project Type Classification

| Type | Definition | Signals |
|---|---|---|
| **Greenfield** | New, minimal code. Less than 30 days of commits or < 10 source files. | Few files, no migrations, no legacy markers |
| **Active** | Ongoing, well-structured project. | Test suite present, migration history, recent commits across many files |
| **Legacy** | Old code with accumulated debt. | Old dependency versions, TODO concentration, god files, minimal tests |
| **Messy** | Active but structurally chaotic. | Mixed architecture patterns, files in wrong places, test/source co-mingled |
| **Partially documented** | Has some structure but missing context. | PROJECT_CONTEXT.md absent, sparse README, no ARCHITECTURE.md |

### 2.4 — Protected Zone Detection

The following are automatically flagged as protected zones. Agents require explicit scope approval before modifying them.

```
auth/           → Authentication and authorization logic
security/       → Security primitives
jwt/ or token/  → Token management
payments/ or billing/ or stripe/ or paypal/ → Payment processing
migrations/ or alembic/ → Database migration history
*.env (any)     → Environment configuration
secrets.*       → Credential storage
deploy/         → Deployment scripts
.github/workflows/ → CI/CD pipelines
k8s/ or kubernetes/ → Infrastructure
terraform/      → Infrastructure as Code
```

Any file in these zones is automatically HIGH or CRITICAL risk (see `rules/risk_matrix.md`).

### 2.5 — Critical System Identification

Beyond protected zones, identify systems where failure affects all users:

- The primary authentication middleware (wherever it intercepts all requests)
- The primary database session manager
- The primary error handler / exception middleware
- The application entry point (main.py, Program.cs, index.ts, etc.)
- Shared configuration loader

These are flagged in ARCHITECTURE.md as `[CRITICAL PATH]`.

---

## Phase 3 — Output Generation

After Phase 1 and 2, generate the following files. Each section below defines the exact content structure.

---

### Output 1: PROJECT_CONTEXT.md

Generated at: project root (`PROJECT_CONTEXT.md`)
Overwrite behavior: If file exists, compare and flag differences. Do not silently overwrite.

```markdown
# PROJECT_CONTEXT.md
# Generated by: /leader initialize project
# Date: [YYYY-MM-DD]
# Confidence: [overall confidence level]
# ⚠️ REVIEW REQUIRED: [list sections marked LOW confidence]

---

## Project Identity

Name: [inferred from package.json name, pyproject.toml, or directory name]
Type: [Greenfield | Active | Legacy | Messy | Partially documented]
Architecture: [inferred architecture type] [confidence]
Stack: [language + framework] [confidence]
Status: [inferred from commit recency and file structure]

---

## Stack

Language(s): [inferred] [confidence]
Framework(s): [inferred] [confidence]
Database(s): [inferred] [confidence]
Infrastructure: [inferred] [confidence]
Package Manager: [inferred] [confidence]
Test Framework: [inferred] [confidence]
CI/CD: [inferred] [confidence]

⚠️ LOW CONFIDENCE ITEMS — verify before relying on these:
[List any LOW confidence inference here]

---

## Repository Structure

[Paste actual top-level directory tree — max 2 levels deep]
[Do not invent structure]

---

## Core Conventions

[Leave blank with note: "Not inferrable from code — fill in manually"]

Code style: [inferred from config files: .eslintrc, .prettierrc, pyproject.toml[tool.black], etc.]
Commit format: [inferred from recent commit messages if visible]
Branch strategy: [inferred from branch names if visible]
Secrets management: [inferred from .env.example, Vault config, etc.]

---

## Domain Context

[Leave blank with note: "Cannot be inferred — requires human input"]

---

## Protected Zones (auto-detected)

[List all detected protected zones from Phase 2.4]
Each entry:
  - Path: [path]
  - Type: [auth | payments | migrations | infra | secrets]
  - Risk Level: [HIGH | CRITICAL]
  - Reason: [why it was flagged]

---

## Critical Systems (auto-detected)

[List all detected critical path systems from Phase 2.5]

---

## God Files Detected

[List files flagged in Phase 1.4]
Each entry:
  - File: [path]
  - Lines: [count]
  - Risk: Why changes here affect many callsites

---

## Dependency Hotspots

[List files imported by > 10 other files]
  - File: [path]
  - Imported by: [count] files
  - Risk: HIGH — changes ripple

---

## ⚠️ Requires Human Input

The following sections cannot be inferred from code and must be filled in manually:
- Domain context and business rules
- Core coding conventions (not captured in config files)
- Team contacts and escalation paths
- External system credentials and environments
- Known intentional tech debt

---
Confidence: [HIGH | MEDIUM | LOW — explain if not HIGH]
```

---

### Output 2: ARCHITECTURE.md

Generated at: `memory/ARCHITECTURE.md`

```markdown
# ARCHITECTURE.md
# Generated by: /leader initialize project
# Date: [YYYY-MM-DD]
# Last updated: [YYYY-MM-DD] by [Leader | Architect]
# ⚠️ Sections marked LOW must be verified by a human or Architect

---

## System Type

[Monolith | Modular Monolith | Microservices | Scripts | Unknown]
Confidence: [HIGH | MEDIUM | LOW]
Evidence: [files/patterns that support this classification]

---

## Architecture Pattern

[MVC | Clean Architecture | Hexagonal | Layered | Unknown]
Confidence: [HIGH | MEDIUM | LOW]
Evidence: [directories and patterns detected]

---

## Component Map

[List all top-level modules/services detected]
For each:
  Component: [name]
  Path: [directory path]
  Role: [inferred role — API layer | service layer | data layer | shared utilities | unknown]
  Confidence: [HIGH | MEDIUM | LOW]
  Critical path: [YES | NO | UNKNOWN]

---

## Dependency Graph (inferred)

[Describe the import/dependency relationships between major modules]
[Only describe what was observed — do not invent]
[If circular dependencies were detected, list them explicitly]

Circular dependencies found: [YES/NO]
If YES:
  - [file A] ↔ [file B] — [risk level]

---

## Database Layer

Database: [inferred]
ORM/query layer: [inferred]
Migration system: [inferred]
Migration history: [count of migrations if directory found]
Confidence: [HIGH | MEDIUM | LOW]

---

## External Integrations

[List any external services detected from imports or config]
  - Service: [name]
  - Evidence: [file or import that indicates it]
  - Confidence: [HIGH | MEDIUM | LOW]

---

## Test Architecture

Test framework: [inferred]
Test types detected: [unit | integration | e2e | none detected]
Test coverage: [unknown — cannot infer without running coverage tool]
Test co-location: [tests beside source | tests in separate directory | unknown]

---

## Deployment Architecture

[Containerized | Bare metal | Serverless | Unknown]
Evidence: [Dockerfile present | docker-compose | k8s | none]
CI/CD: [GitHub Actions | GitLab CI | none detected | unknown]

---

## Known Risks (from scan)

[Pull from RISKS.md — do not duplicate, cross-reference]
See: memory/RISKS.md

---

## Architect Notes

[Empty — to be filled by Architect agent during design tasks]

---
Confidence: [overall confidence]
Requires human verification: [list specific sections]
```

---

### Output 3: memory/CURRENT.md

Generated at: `memory/CURRENT.md`

```markdown
# CURRENT.md
# Initialized by: /leader initialize project
# Date: [YYYY-MM-DD]

---

## Active Task

ID: T-001
Instruction: /leader initialize project
Risk Level: LOW
Status: COMPLETE

---

## Completed

Initialization scan completed [YYYY-MM-DD].
Generated:
- PROJECT_CONTEXT.md [confidence: HIGH | MEDIUM | LOW]
- memory/ARCHITECTURE.md [confidence: HIGH | MEDIUM | LOW]
- memory/RISKS.md [N risks identified]
- memory/DECISIONS.md [initialized empty]
- memory/TASK.md [initialized]

## ⚠️ Requires Human Review

[List all LOW confidence inferences]
[List all sections marked "fill in manually"]

---
Ready for: /leader <next instruction>
```

---

### Output 4: memory/TASK.md

Generated at: `memory/TASK.md`

```markdown
# TASK.md — Task Registry
# Initialized: [YYYY-MM-DD]

---

## Task Log

[YYYY-MM-DD HH:MM] T-001 CREATED — "/leader initialize project"
[YYYY-MM-DD HH:MM] T-001 COMPLETE — Scan complete. [N] risks found. [N] LOW-confidence sections require human review.

---

## Completed

| ID | Instruction | Date | Risk | Outcome |
|----|-------------|------|------|---------|
| T-001 | /leader initialize project | [date] | LOW | [N risks found, confidence: HIGH/MEDIUM/LOW] |
```

---

### Output 5: memory/RISKS.md

Generated at: `memory/RISKS.md`

```markdown
# RISKS.md — Risk Registry
# Initialized by: /leader initialize project
# Date: [YYYY-MM-DD]

---

## Open Risks

[One entry per risk detected in Phase 1.4 and Phase 2]

### [RISK-001] — [Risk title]

Status: OPEN
Severity: [CRITICAL | HIGH | MEDIUM | LOW]
Type: [credential-leak | god-file | hotspot | no-tests | tech-debt | circular-dependency]
Location: [file or directory]
Evidence: [what was found that produced this risk]
Detected: [date]
Recommended action: [what should be done about it]

---

## Resolved Risks

[Empty at initialization — append here when risks are mitigated]

---

## Risk Summary

| ID | Title | Severity | Status |
|----|-------|----------|--------|
| RISK-001 | ... | CRITICAL | OPEN |
```

---

### Output 6: memory/DECISIONS.md

Generated at: `memory/DECISIONS.md`

```markdown
# DECISIONS.md — Architecture Decision Log
# Initialized by: /leader initialize project
# Date: [YYYY-MM-DD]

---

## Decision Log

[Empty at initialization — populated by Architect agent when ADRs are produced]

---

## Format

Each entry follows this structure:

### ADR-[NNN]: [Decision title]
Status: [Proposed | Accepted | Superseded | Rejected]
Date: [YYYY-MM-DD]
Author: @architect
Context: [why this decision was needed]
Decision: [what was decided]
Rationale: [why this option was chosen]
Consequences: [what becomes easier, what becomes harder]
Revisit when: [condition that would trigger reconsideration]
```

---

## Confidence Output Rules

After generating all files, Leader outputs a confidence summary:

```
## Initialization Complete

### Confidence Summary

| Area | Confidence | Notes |
|------|-----------|-------|
| Language/Runtime | HIGH | |
| Framework | HIGH | |
| Architecture pattern | MEDIUM | Two patterns detected — see ARCHITECTURE.md |
| Database | MEDIUM | Redis detected but role unclear |
| Test coverage | LOW | No test directory found |
| Domain context | NONE | Cannot infer — human input required |
| Conventions | LOW | Some detected from config, rest unknown |

### Files Generated
- PROJECT_CONTEXT.md [confidence: MEDIUM]
- memory/ARCHITECTURE.md [confidence: MEDIUM]
- memory/CURRENT.md [complete]
- memory/TASK.md [complete]
- memory/RISKS.md [N risks — see file]
- memory/DECISIONS.md [initialized empty]

### Human Action Required
1. Review and complete PROJECT_CONTEXT.md — especially: domain context, conventions, contacts
2. Verify LOW confidence inferences: [list them]
3. Address CRITICAL/HIGH risks in memory/RISKS.md: [list them]
4. Run /leader audit current architecture after completing the above
```

---

## Project Type Behavior

### Greenfield Project

Minimal scan findings. Most inferences will be LOW or NONE.
Generated files will be mostly empty with clear placeholder instructions.
Risk matrix will likely show LOW risk profile.
Leader outputs:
```
Greenfield project detected. Generated starter context files.
Fill in PROJECT_CONTEXT.md before running any task.
```

### Active Well-Structured Project

Rich scan findings. Most inferences will be HIGH or MEDIUM.
Generated files will be substantially populated.
Leader outputs a confidence summary and flags gaps for human review.

### Legacy Project

Many god files, high tech debt signal, old dependencies, minimal or no tests.
RISKS.md will be heavily populated.
Leader outputs:
```
⚠️ Legacy project signals detected:
- [N] god files (files > 500 lines)
- [N] dependency hotspots
- [N] TODO/FIXME/HACK markers
- Test coverage: none detected

Recommend: review RISKS.md before starting any modification task.
HIGH or CRITICAL risk level should be applied to most changes in this codebase.
```

### Messy Project

Architecture pattern is `Unknown` or mixed.
Multiple conflicting patterns detected.
Leader outputs:
```
⚠️ Inconsistent architecture detected:
Patterns found: [list]
This makes routing unreliable until architecture is clarified.

Recommend: /leader audit current architecture → review with team → update ARCHITECTURE.md
```

### Partially Documented Project

`PROJECT_CONTEXT.md` exists but is stale or incomplete.
Leader compares existing content to scan findings and produces a diff:
```
## PROJECT_CONTEXT.md Audit

Existing: [what the file currently says]
Detected: [what the scan found]
Conflicts: [where they disagree]
Missing: [what the scan found that isn't documented]
Stale: [what the file claims that the scan cannot confirm]
```

---

## Worked Examples

### Example 1: FastAPI Project

Scan finds:
```
pyproject.toml: fastapi=0.115, sqlalchemy=2.0, alembic, pytest, uvicorn
src/api/routers/ — 8 files
src/services/ — 12 files
src/models/ — 6 files
src/db/ — session.py, base.py
alembic/ — 24 migration files
tests/ — unit/ + integration/
Dockerfile, docker-compose.yml
.github/workflows/ci.yml
```

Inferences:
```
Language: Python 3.x [HIGH — pyproject.toml]
Framework: FastAPI [HIGH — direct dependency + routers/ directory]
Architecture: Layered (api → services → models → db) [HIGH — directory structure matches]
Database: SQLAlchemy ORM, PostgreSQL likely [MEDIUM — sqlalchemy present, no explicit PG config found]
Migrations: Alembic [HIGH — alembic.ini + 24 migration files]
Tests: pytest, unit + integration [HIGH — pytest in deps, tests/ directory]
CI/CD: GitHub Actions [HIGH — .github/workflows/]
```

Protected zones flagged: `alembic/` (migrations), `src/api/routers/auth.py` (if exists)
God files: none detected (if all files < 500 lines)
Tech debt: scan result

---

### Example 2: .NET Clean Architecture Project

Scan finds:
```
MyApi.sln — solution file
MyApi.Domain/ — .csproj
MyApi.Application/ — .csproj
MyApi.Infrastructure/ — .csproj
MyApi.Api/ — .csproj with Microsoft.AspNetCore.App
MyApi.Tests.Unit/ — xunit, Moq
MyApi.Tests.Integration/ — xunit, WebApplicationFactory
```

Inferences:
```
Language: C# / .NET [HIGH — .sln + .csproj files]
Framework: ASP.NET Core [HIGH — Microsoft.AspNetCore.App]
Architecture: Clean Architecture [HIGH — Domain/Application/Infrastructure/Api layer separation]
Database: Entity Framework Core [MEDIUM — likely in Infrastructure, need to confirm]
Tests: xUnit [HIGH — test projects detected]
```

Protected zones: `MyApi.Domain/` (core domain — never modify without Architect)

---

### Example 3: AI Agentic System

Scan finds:
```
pyproject.toml: anthropic, fastapi, redis, sqlalchemy, pytest
src/agents/ — 5 files
src/tools/ — 8 files
prompts/ — 12 .md files
src/memory/ — retrieval.py, store.py
src/workflows/ — 3 files
No test directory found
```

Inferences:
```
Language: Python [HIGH]
Framework: Custom agent loop + FastAPI [HIGH — both detected]
LLM Provider: Anthropic Claude [HIGH — anthropic in pyproject]
Architecture: Custom agentic [MEDIUM — agents/ + tools/ + workflows/ pattern]
Tests: NONE DETECTED [HIGH confidence finding — no test directory]
```

Risk flags:
```
RISK-001: No test suite detected [HIGH]
RISK-002: prompts/ directory — system prompt changes are HIGH risk [HIGH]
RISK-003: src/tools/ — tool execution logic is potentially CRITICAL risk
```

Leader outputs additional warning:
```
⚠️ AI system with no test suite detected.
All changes to prompts/, agents/, and tools/ should default to HIGH risk.
Evals should be established before modifications are made.
```
