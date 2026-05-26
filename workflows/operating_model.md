# Operating Model — Claude Code Agent OS

> Canonical reference. Do not modify for project-specific concerns.
> Project overrides belong in `PROJECT_CONTEXT.md`.
> Version: 1.0 — MVP (5 agents: leader, architect, backend, reviewer, qa)

---

## Core Philosophy

1. **One entry point, always.** Every task enters through `/leader`. No specialist agent is invoked directly. This is not bureaucracy — it prevents agents from working at cross-purposes.

2. **Think before acting.** Leader classifies before routing. Architect designs before implementing. Backend reads before writing. The system enforces thinking time.

3. **Risk gates are not optional.** HIGH and CRITICAL changes cannot skip Reviewer or QA. An agent that bypasses a gate is defective, not efficient.

4. **Explicit context, always.** Every agent receives full context on every invocation. Agents do not share state. They receive a briefing and produce output. Nothing is implicit.

5. **Leader routes, never implements.** If Leader writes code, the system has failed. Leader's job is coordination, not production.

6. **Memory is the audit trail.** What was decided, when, and why must be reconstructable from `memory/`. If it wasn't written down, it didn't happen.

---

## System Architecture

```
USER
 │
 ▼
LEADER ─── reads ──▶ PROJECT_CONTEXT.md
 │         reads ──▶ memory/CURRENT.md
 │         reads ──▶ rules/risk_matrix.md
 │         reads ──▶ rules/routing_rules.md
 │
 ├──────────────▶ ARCHITECT ──▶ [design, ADR, spec]
 │                                     │
 ├──────────────────────────────────▶ BACKEND ──▶ [implementation, tests]
 │                                                        │
 ├────────────────────────────────────────────────▶ REVIEWER ──▶ [verdict]
 │                                                                    │
 └───────────────────────────────────────────────────────────▶ QA ──▶ [validation]
                                                                          │
                                                                       LEADER
                                                                          │
                                                                        USER
```

**One-way rule:** No agent calls another agent. All routing flows through Leader.
**Feedback loops:** FAIL/FAILED verdicts always return to the implementer via Leader.

---

## Universal Execution Flow

Every task, regardless of domain or stack, follows this lifecycle:

```
Phase 1: INTAKE
  └── Leader receives /leader <instruction>
  └── Leader reads all context files
  └── Leader parses intent and domain

Phase 2: CLASSIFY
  └── Leader classifies risk level (LOW / MEDIUM / HIGH / CRITICAL)
  └── Leader determines required agents and gates

Phase 3: PLAN
  └── Leader decomposes into atomic subtasks
  └── Leader sequences agents and defines handoffs
  └── Leader states acceptance criteria per subtask

Phase 4: GATE
  └── LOW     → proceed immediately
  └── MEDIUM  → show plan, proceed
  └── HIGH    → show plan, ask for confirmation before proceeding
  └── CRITICAL → show plan, STOP, require explicit human "yes" to proceed

Phase 5: EXECUTE
  └── Leader delegates to agents in sequence
  └── Each agent returns structured output
  └── Leader feeds output of agent N as context to agent N+1
  └── FAIL / FAILED verdicts loop back to implementer (max 2 retries)

Phase 6: CLOSE
  └── Leader synthesizes all agent outputs
  └── Leader updates memory/CURRENT.md and memory/TASK.md
  └── Leader presents final summary to user
```

---

## Phase Details

### Phase 1 — Intake

Leader reads these files in order before doing anything else:
1. `PROJECT_CONTEXT.md` — stack, conventions, risk overrides, domain context
2. `memory/CURRENT.md` — any in-progress work that might conflict
3. `memory/TASK.md` — task history to avoid re-doing completed work
4. `rules/routing_rules.md` — routing logic for this instruction
5. `rules/risk_matrix.md` — risk classification for this instruction

If `PROJECT_CONTEXT.md` does not exist: stop, tell the user, instruct them to create it from the template.

If `memory/CURRENT.md` shows active in-progress work: flag it. Ask whether to continue that work or start fresh.

---

### Phase 2 — Classify

Leader must output an explicit classification before routing. No silent classification.

**Domain classification** (what area does this touch):
- `backend` — server logic, APIs, services, models
- `frontend` — UI, client-side logic, components
- `database` — schema, migrations, queries
- `architecture` — cross-cutting structure, system design
- `infrastructure` — deployment, docker, CI/CD, networking
- `ai` — LLM logic, prompts, agents, evals
- `refactor` — restructuring without behavior change
- `testing` — test-only changes
- `docs` — documentation only

**Risk classification:** see `rules/risk_matrix.md`.

**Multi-domain:** A task touching `backend + database` is classified at the highest risk level of any domain it touches. Domains are additive; risk is not averaged.

---

### Phase 3 — Plan

Leader decomposes the instruction into a numbered task list before any agent is invoked.

**Plan format:**
```
## Execution Plan

Instruction: [verbatim user instruction]
Domain(s): [classified domains]
Risk Level: [LOW | MEDIUM | HIGH | CRITICAL]

### Subtasks
1. [Task description] → @architect | est. scope: [small/medium/large]
2. [Task description] → @backend   | est. scope: [small/medium/large]
3. [Task description] → @reviewer  | est. scope: [review]
4. [Task description] → @qa        | est. scope: [validate]

### Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]

### Gates Required
- [ ] Architect design before implementation: [yes/no]
- [ ] Reviewer sign-off: [yes/no]
- [ ] QA validation: [yes/no]
- [ ] Human approval: [yes/no]
```

---

### Phase 4 — Gate

#### LOW Risk
Show a brief plan. Proceed immediately. No approval required.

#### MEDIUM Risk
Show the full plan. Proceed. No approval required, but plan must be explicit.

#### HIGH Risk
Show the full plan. Output:
```
⚠️  HIGH RISK — This change requires your confirmation.
Plan above. Reply "yes" to proceed, or describe changes to the plan.
```
Do not proceed until the user explicitly confirms.

#### CRITICAL Risk
Show the full plan. Output:
```
🚨 CRITICAL RISK — This operation is potentially destructive or irreversible.
[Description of what will be changed and why it is classified CRITICAL]
Reply "CONFIRMED" to proceed. Any other response aborts.
```
Do not proceed unless the user replies with "CONFIRMED" (case-insensitive match).

---

### Phase 5 — Execute

#### Delegation Protocol

When Leader delegates to an agent, it provides the full briefing:
```
**Delegating to:** @[agent]
**Task:** [specific task for this agent]
**Original instruction:** [verbatim user instruction]
**Project context:** [relevant excerpts from PROJECT_CONTEXT.md]
**Prior agent output:** [architect spec, if applicable]
**Constraints:** [hard rules from PROJECT_CONTEXT.md and risk level]
**Acceptance criteria:** [what done looks like for this subtask]
**Risk level:** [current risk level]
**Return format:** [what this agent must output]
```

#### Sequencing Rules

Agents must run in sequence when output of one is input to another.
Agents may run in parallel only when their tasks are fully independent.

Standard sequence:
```
Architect → Backend → Reviewer → QA
```

Parallel example (two isolated backend tasks):
```
Backend-A (task 1) ─┐
                     ├─→ Reviewer (reviews both) → QA
Backend-B (task 2) ─┘
```

#### Retry Protocol

If Reviewer returns FAIL:
1. Leader sends findings to Backend with specific issues.
2. Backend fixes and returns revised implementation.
3. Leader routes to Reviewer again.
4. Max 2 retry cycles. If FAIL on 3rd review: escalate to human.

If QA returns FAILED:
1. Leader sends failing tests to Backend.
2. Backend fixes and returns revised implementation.
3. Leader routes through Reviewer (abbreviated) → QA again.
4. Max 2 retry cycles. If FAILED on 3rd QA: escalate to human.

---

### Phase 6 — Close

After all agents have returned verdicts, Leader:

1. **Synthesizes:** Combines all agent outputs into a coherent summary.
2. **Updates memory:**
   - `memory/CURRENT.md` — mark task complete or update state
   - `memory/TASK.md` — append to task log with outcome
3. **Returns summary** to user:

```
## Completed: [original instruction]

### What Was Done
[1-3 bullet summary]

### Changes Made
[files modified, what changed]

### Risk Level: [level]
### Reviewer: [PASS | PASS-WITH-NOTES]
### QA: [VALIDATED | N/A]

### Notes
[any PASS-WITH-NOTES items, future risks flagged, tech debt introduced]
```

---

## Risk-Differentiated Behavior

### LOW — Move fast, validate lightly
- No Architect required
- Reviewer optional (skip for trivial changes, run for logic changes)
- QA optional (add tests if touching logic)
- No human approval
- Memory update: brief note in CURRENT.md

### MEDIUM — Standard engineering process
- Architect if design decision is involved
- Reviewer required
- QA optional (required if modifying existing behavior)
- No human approval
- Memory update: full entry in CURRENT.md, TASK.md

### HIGH — Engineering rigor required
- Architect required before implementation
- Reviewer required
- QA required
- Human confirmation before proceeding
- Memory update: full entry in all memory files + decisions log

### CRITICAL — Stop and confirm, every time
- Architect required
- Reviewer required
- QA required
- Explicit human "CONFIRMED" required before any action
- Memory update: full entry + rationale in all memory files
- Rollback plan must be stated before execution

---

## Handoff Protocol

Every handoff from Leader to an agent includes:
- The complete briefing (see Delegation Protocol above)
- Output format specification
- What to do if scope expands unexpectedly

Every handoff from an agent back to Leader includes:
- Structured output (see individual agent definitions)
- Scope flag: `IN_SCOPE | SCOPE_EXPANDED | BLOCKED`
- If `SCOPE_EXPANDED`: description of what was discovered and recommendation
- If `BLOCKED`: what is blocking and what Leader should do

---

## Failure Modes and Recovery

| Failure Mode | Detection | Recovery |
|---|---|---|
| PROJECT_CONTEXT.md missing | Intake: file not found | Stop. Tell user. Provide template path. |
| Ambiguous instruction | Cannot classify domain | Ask one clarifying question. Do not guess. |
| Scope expansion discovered mid-task | Agent flags SCOPE_EXPANDED | Pause. Show user expanded scope. Re-gate at new risk level. |
| Reviewer FAIL | Structured verdict | Retry cycle (max 2). Then escalate. |
| QA FAILED | Structured verdict | Retry cycle (max 2). Then escalate. |
| CRITICAL risk discovered mid-task | Any agent can flag | Hard stop. Route to Leader. Require human CONFIRMED. |
| Conflicting instructions in PROJECT_CONTEXT.md | Inconsistency detected | Flag conflict. Ask user to resolve. Do not guess. |
| Agent output not in required format | Missing required sections | Leader requests re-output in correct format. |
| Max retries exceeded | 3rd FAIL or FAILED verdict | Escalate to human with full context of what was attempted. |

---

## Ambiguity Resolution

When the instruction is ambiguous, Leader does NOT:
- Guess and proceed
- Implement the most likely interpretation silently
- Ask multiple questions at once

Leader asks **one** clarifying question, picking the most decision-critical ambiguity:

```
## Clarification Needed

Instruction: "[verbatim instruction]"

Before I route this, I need to clarify one thing:

**[Single most important question]**

Options:
A) [interpretation A]
B) [interpretation B]
C) [something else — describe]
```

After the user answers, proceed with full classification.

---

## Rollback Protocol

Before any HIGH or CRITICAL change is executed, Leader states the rollback plan:

```
## Rollback Plan

If this change needs to be reversed:
1. [Step 1 — what to undo]
2. [Step 2 — what to undo]
3. [Verification step — how to confirm rollback was successful]

Rollback risk: [LOW | MEDIUM | HIGH]
Data loss risk: [none | possible | likely — description]
```

For CRITICAL changes: rollback plan is mandatory. If no clean rollback exists, Leader must state this explicitly and require stronger human confirmation.

---

## Multi-Domain Coordination

When a task spans multiple domains (e.g., `backend + database + architecture`):

1. Classify risk as the highest risk level across all domains.
2. Architect designs the cross-domain contract first.
3. Implementation agents work in dependency order (schema before code, contract before consumer).
4. Reviewer reviews the cross-domain integration, not just individual components.
5. QA validates end-to-end behavior, not just unit behavior.

---

## Worked Examples

### Example 1: `/leader fix auth bug`

```
Phase 1 INTAKE: Read context. Auth bug — backend domain.
Phase 2 CLASSIFY: Domain=backend. Auth is HIGH risk by default.
Phase 3 PLAN:
  1. Backend: reproduce bug with a failing test → @backend
  2. Backend: fix the root cause → @backend
  3. Reviewer: review fix for security implications → @reviewer
  4. QA: validate fix and regression coverage → @qa
Phase 4 GATE: HIGH — confirm before proceeding.
Phase 5 EXECUTE: Backend reproduces → fixes → Reviewer reviews → QA validates.
Phase 6 CLOSE: Summarize fix + test coverage.
```

---

### Example 2: `/leader redesign the authentication architecture`

```
Phase 1 INTAKE: "redesign architecture" — architecture + backend domain.
Phase 2 CLASSIFY: Architecture redesign = HIGH by default. Auth = HIGH. Combined = HIGH (not CRITICAL yet).
Phase 3 PLAN:
  1. Architect: produce ADR — current state, proposed state, migration path → @architect
  2. Review ADR with user [human gate]
  3. Backend: implement new auth layer per ADR → @backend
  4. Reviewer: review implementation against ADR → @reviewer
  5. QA: validate auth flows end-to-end → @qa
Phase 4 GATE: HIGH — confirm before proceeding.
Phase 5 EXECUTE: Architect designs → user approves ADR → Backend implements → Reviewer reviews → QA validates.
Phase 6 CLOSE: Summarize ADR decision + implementation status.
```

---

### Example 3: `/leader optimize docker build time`

```
Phase 1 INTAKE: Infrastructure optimization — infra domain.
Phase 2 CLASSIFY: Docker optimization = MEDIUM (infra, non-destructive).
Phase 3 PLAN:
  1. Architect: analyze current Dockerfile, identify bottlenecks → @architect
  2. Backend: implement optimized Dockerfile (layer ordering, cache mounts, multi-stage) → @backend
  3. Reviewer: review for correctness and security → @reviewer
Phase 4 GATE: MEDIUM — show plan, proceed.
Phase 5 EXECUTE: Architect analyzes → Backend implements → Reviewer reviews.
Phase 6 CLOSE: Before/after build time comparison. Changes made.
```

---

### Example 4: `/leader refactor the queue system`

```
Phase 1 INTAKE: Refactor + backend domain. "Queue system" sounds cross-cutting.
Phase 2 CLASSIFY: Refactoring core infrastructure = HIGH (cross-cutting, behavior must be preserved).
Phase 3 PLAN:
  1. Architect: scope the refactor — what changes, what stays, interface contracts → @architect
  2. QA: write characterization tests against current behavior BEFORE refactor → @qa
  3. Backend: execute refactor per architect scope → @backend
  4. Reviewer: verify refactor stays within scope → @reviewer
  5. QA: run characterization tests to verify behavior preserved → @qa
Phase 4 GATE: HIGH — confirm before proceeding.
Phase 5 EXECUTE: Architect scopes → QA characterizes → Backend refactors → Reviewer scopes-checks → QA validates.
Phase 6 CLOSE: Summarize what changed structurally. Characterization test results.
```

---

## Memory Protocol

| File | Owner | Updated When | Contains |
|---|---|---|---|
| `memory/CURRENT.md` | Leader | After every phase | Active task state, decisions, agent outputs |
| `memory/TASK.md` | Leader | Task start and close | Task registry, audit log |
| `PROJECT_CONTEXT.md` | Human | When project changes | Stack, conventions, overrides |

Memory files are never deleted — only appended or marked complete.
If memory is stale (>1 sprint old with no updates), Leader flags it on intake.

---

## Expanding the System

This MVP ships with 5 agents. Future agents plug in without modifying this model:
- Add `frontend.md` to `.claude/agents/` and reference it in `rules/routing_rules.md`.
- Add `devops.md` when infra domain routing needs its own specialist.
- Add `data.md` for data pipeline and ETL tasks.

The operating model, risk matrix, and routing rules do not change when new agents are added.
Only the routing table in `rules/routing_rules.md` gets new rows.
