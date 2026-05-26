# Scope Rules — Agent Scope Control System

> Read by: All agents before and during implementation.
> Enforced by: Every agent via scope signals. Leader re-gates on any SCOPE_EXPANDED.
> Do not modify for project-specific concerns — add overrides in `PROJECT_CONTEXT.md`.
> Version: 1.0

---

## Why This File Exists

Scope creep is the most common failure mode in AI-assisted engineering.

The pattern is always the same:
```
User says:    /leader fix JWT expiry bug
Agent does:   fixes the bug +
              refactors auth module +
              upgrades a dependency +
              renames 12 functions +
              extracts a new service class +
              updates 3 unrelated tests
```

The agent is not malicious. It is "being helpful." But the user asked for one thing and got eight. The extra seven things were not reviewed, not tested to the required depth, and not approved. Any of them could introduce a regression.

**This file makes scope a first-class constraint.** Every agent uses it. Every ambiguity is escalated. Every expansion requires approval.

---

## Scope Status Codes

Every agent ends every response with exactly one of these four status codes.

---

### IN_SCOPE

The work performed is within the boundaries of the delegated task.
Nothing was changed that was not in the plan.
Ready to proceed to the next agent.

```
Scope: IN_SCOPE
```

---

### OUT_OF_SCOPE

The agent discovered something that needs to change, but it is not related to the current task.
The agent did NOT make the change.
The agent logs it for future work.

```
Scope: OUT_OF_SCOPE
Observed: [What was noticed that is outside this task]
Recommendation: [Open a separate task / ignore / flag as tech debt]
Action taken: None — not modifying out-of-scope items
```

**The agent does not fix OUT_OF_SCOPE items.** It documents them and moves on.

---

### SCOPE_EXPANDED

The agent discovered that completing the stated task requires more work than the original plan described.
The agent has STOPPED before doing the extra work.
The agent is returning to Leader for re-planning and re-gating.

```
Scope: SCOPE_EXPANDED
Original task: [verbatim delegated task]
Discovered: [What was found that requires additional work]
Why it's required: [Why the original task cannot be completed without this]
Additional domains: [What additional domains are now involved]
Estimated additional risk: [LOW | MEDIUM | HIGH | CRITICAL]
Partial work completed: [What was done before the expansion was discovered]

Options:
A) Expand scope — include the discovered work in this task
B) Defer — complete original task only, open separate task for the rest
C) Abort — do not proceed with original task either
```

Leader must re-classify risk, re-plan, and re-gate before proceeding.

---

### BLOCKED

The agent cannot proceed without information, a decision, or an artifact that does not exist yet.
The agent has stopped completely.

```
Scope: BLOCKED
Blocked by: [Specific blocker — ambiguous spec / missing file / unresolved design question]
Needs: [Exactly what is required to unblock]
Partial work completed: [What was done before hitting the blocker]
```

---

## Scope Definition

**IN_SCOPE** means: the specific files, functions, and behaviors that were explicitly named or directly implied by the delegated task.

**The directly-implied rule:** Something is directly implied only if it is a mechanical prerequisite of the stated task. If you need to write a test for a function you are implementing, that test is IN_SCOPE. If you notice the test file is disorganized and decide to reorganize it, that is OUT_OF_SCOPE.

**The proximity trap:** Being near something does not put it in scope. If you are implementing a function inside `auth.py`, every other function in `auth.py` is OUT_OF_SCOPE unless it was explicitly part of the task.

---

## Decision Tree — Is This In Scope?

```
Was this change explicitly listed in the execution plan?
  YES → IN_SCOPE
  NO  → continue

Was this change explicitly requested by the user?
  YES → IN_SCOPE
  NO  → continue

Is this change a direct mechanical prerequisite of a task in the plan?
(A test for the function I am implementing. An import for the code I am writing.)
  YES → IN_SCOPE
  NO  → continue

Is this change required because the original task is impossible without it?
(The function I need to modify doesn't exist yet. The schema I need doesn't exist.)
  YES → SCOPE_EXPANDED — stop, flag, return to Leader
  NO  → continue

Is this something I noticed while doing the task that is wrong or could be better?
  YES → OUT_OF_SCOPE — do not change it. Document it. Move on.

Is something missing or unclear that prevents me from proceeding?
  YES → BLOCKED — stop, describe exactly what is missing
```

---

## What Each Agent Can Change Without Approval

### Backend

**IN_SCOPE without asking:**
- The specific function, method, or class named in the task
- Tests for the specific function, method, or class being implemented or modified
- Imports required by the new/modified code (new import statements only)
- Error handling within the specific function being modified
- Docstrings or inline comments within the scope of the task

**Requires SCOPE_EXPANDED approval:**
- Any file not named in the execution plan
- Any shared utility or helper function
- Any interface contract or public API signature
- Any database model or schema
- Any configuration file
- Any new dependency (library, package, or service)
- Any test file not directly shadowing the target file

### Architect

**IN_SCOPE without asking:**
- The design document for the stated task
- The ADR for the stated decision
- Interface contracts within the stated design scope

**Requires SCOPE_EXPANDED approval:**
- Designs that span more components than the task described
- Designs that require changes to protected zones not mentioned in the task

### Reviewer

**IN_SCOPE without asking:**
- Reviewing every file changed by the implementation agent
- Flagging issues in those files

**Requires SCOPE_EXPANDED approval:**
- Reviewing files not changed by the implementation (if discovered to be relevant)
- Producing a FAIL verdict due to an issue outside the stated scope

### QA

**IN_SCOPE without asking:**
- Tests for the behavior described in the acceptance criteria
- Characterization tests for the area being refactored

**Requires SCOPE_EXPANDED approval:**
- Tests for behavior adjacent to the task but not part of it
- Changes to existing test fixtures or test utilities outside the stated scope

---

## What ALWAYS Requires Human Approval

Regardless of what the execution plan says, these always require human approval:

```
1. Adding a new external dependency (library, package, SDK)
   Why: New dependencies introduce security risk, licensing risk, and bloat.

2. Changing any file in a protected zone not listed in the original task
   Protected zones: auth/, security/, migrations/, payments/, deploy/, .env, CI/CD
   Why: These are high-blast-radius changes.

3. Renaming anything exported or used by external callers
   Why: Breaking changes to public contracts affect other systems.

4. Adding or modifying environment variable requirements
   Why: Config changes require deployment coordination.

5. Changing database schema in any way not specified in the task
   Why: Schema changes are irreversible in production without a migration.

6. Modifying any file that was explicitly listed as protected in PROJECT_CONTEXT.md
   Why: The project defined these as off-limits by convention.
```

---

## Risk-Level Scope Boundaries

The risk level of the task determines how strictly scope is enforced.

### LOW Risk

Scope: The specific function or file described.
Opportunistic improvements: NOT allowed, even when trivially simple.
If you notice something else wrong: log it in OUT_OF_SCOPE. Do not fix it.

Rationale: LOW risk tasks are fast and safe precisely because they are narrow. Widening them removes that safety without additional oversight.

### MEDIUM Risk

Scope: The module or feature described in the plan.
Adjacent changes: Allowed only if they are true prerequisites of the task and are noted explicitly in the implementation output.
New files: Allowed only if they are the direct artifact of the task (e.g., a new test file for the new endpoint).

### HIGH Risk

Scope: Strictly the system described in the Architect's design spec.
Every change must be traceable to a line in the design spec.
Changes not in the design spec: Always SCOPE_EXPANDED, even if they seem obviously correct.
Rationale: HIGH risk changes require that humans can audit exactly what was done and why.

### CRITICAL Risk

Scope: Only what the Architect explicitly scoped AND what the human approved in the CONFIRMED gate.
No deviation whatsoever.
If anything unexpected is encountered: SCOPE_EXPANDED immediately. Do not proceed.
Rationale: CRITICAL changes are irreversible. There is no "I'll just also fix this small thing while I'm here."

---

## Opportunistic Refactor Prevention

The most dangerous form of scope creep. The pattern:

```
Agent is implementing a new feature.
Agent notices that a function it is calling is poorly named.
Agent renames the function "while it's there."
The function is called from 15 other places.
3 of those places break.
The tests don't cover 2 of those places.
The bug ships to production.
```

**Rule: Never rename, restructure, or refactor anything that was not in the task.**

This applies even when:
- The refactor is clearly correct
- The refactor is trivially simple
- The refactor would take 30 seconds
- The agent "noticed it anyway"

The correct action is OUT_OF_SCOPE. Note it. Let a human decide if it's worth a separate task.

The only exception: If the code being changed is **so broken** that it prevents the stated task from functioning correctly, it is SCOPE_EXPANDED (not a unilateral fix). Return to Leader.

---

## Hidden Work Detection

Signs that an agent may be doing work outside scope. Leader watches for these in agent outputs.

**In Backend output:**
- Files changed list contains files not in the execution plan
- Imports list contains new libraries not discussed
- "I also cleaned up..." or "I took the opportunity to..."
- Test file changes for tests unrelated to the new code
- Renamed symbols that are used outside the task's target files

**In Architect output:**
- Design scope is larger than the task description
- ADR covers decisions not part of the stated task
- Handoff instructions ask Backend to change files not in the plan

**In Reviewer output:**
- Findings outside the scope of the changes reviewed
- FAIL verdict for something that was already present before the task started (pre-existing issues are OUT_OF_SCOPE for this review)

**In QA output:**
- Tests written for behavior not in the acceptance criteria
- Changes to existing test utilities

When hidden work is detected: Leader must:
1. Note what was done outside scope.
2. Determine if it was IN_SCOPE (acceptable), SCOPE_EXPANDED (should have been flagged), or OUT_OF_SCOPE (was it undone?).
3. If OUT_OF_SCOPE changes were made: flag them to the user. Revert or create a separate task.

---

## Architectural Drift Prevention

Architectural drift is scope creep at the architecture level. Examples:

```
Task: "add a user settings endpoint"
Agent introduces: a new caching layer (not designed, not approved)

Task: "fix a slow database query"
Agent introduces: an async job queue (never discussed)

Task: "add a new API field"
Agent introduces: a new data validation layer (not in the design)
```

**Rule: Agents do not introduce new architectural patterns unilaterally.**

Any change that:
- Introduces a pattern not already present in the codebase
- Adds a new layer or abstraction to the system
- Creates a new cross-cutting concern
- Changes how components communicate

...is an architecture-level change and requires Architect involvement, regardless of how small the code change appears.

When Backend discovers that implementing the task "correctly" would require architectural changes:
→ SCOPE_EXPANDED. Return to Leader. Do not implement the architectural change unilaterally.

---

## Approval Request Format

When an agent raises SCOPE_EXPANDED, Leader presents this to the user:

```
⚠️ SCOPE EXPANSION DETECTED

Task: [original /leader instruction]
Discovered by: @[agent]

What was found:
[Specific description of what the agent discovered that requires more work]

Why it's required:
[Why the original task cannot be completed without addressing this]

Additional work needed:
[Specific description of what the extra work would be]

Additional risk level: [LOW | MEDIUM | HIGH | CRITICAL]
Additional domains: [what domains are now involved]

Impact of NOT expanding scope:
[What happens if we proceed with original scope only — incomplete feature, partial fix, etc.]

Options:
A) Expand scope — include the additional work in this task
   Risk consequence: re-gate at [new combined risk level]
   
B) Defer — complete original task only, open separate task for the additional work
   Risk consequence: original task completes at [original risk level]
   Note: [describe the state that will be left if deferred]

C) Abort — do not proceed with this task
   Risk consequence: no changes made

Reply with A, B, or C.
```

---

## Worked Examples

### Example 1: `fix JWT expiry bug`

```
Task given to Backend: "Fix the JWT expiry bug in src/auth/token.py"

IN_SCOPE:
- Reading src/auth/token.py
- Modifying the expiry logic in the token validation function
- Writing a test in tests/test_auth.py for the fixed behavior
- Any imports added to support the fix

OUT_OF_SCOPE (agent notes these and moves on):
- Renaming token.py to tokens.py (cleaner name, but not in the task)
- Refactoring the other functions in token.py (also poorly named)
- Upgrading the PyJWT dependency (noticed it's outdated)
- Reorganizing the test file structure

SCOPE_EXPANDED (agent must stop and flag):
- Discovering that the real bug is in the auth middleware, not token.py
  (The original task is misdirected — scope must be re-evaluated)

Result: Backend scope signal = IN_SCOPE
(Unless the middleware discovery is true, in which case: SCOPE_EXPANDED)
```

---

### Example 2: `optimize API performance`

```
Task given to Backend: "Profile and optimize the /users endpoint — it's taking >2s"

IN_SCOPE:
- Running profiling on the /users endpoint handler
- Optimizing the database query used by that endpoint
- Adding a cache if caching is already used in this codebase
- Tests for the optimized endpoint

OUT_OF_SCOPE:
- Optimizing other endpoints "while in the area"
- Refactoring the service class that the endpoint calls
- Upgrading the ORM (noticed it's an old version)
- Adding a new caching layer that doesn't exist yet

SCOPE_EXPANDED:
- Discovering that the 2s delay is caused by a missing database index
  (Fixing this requires a migration — a different domain, a different risk level)
  Agent stops: "Database index is missing. This requires a migration (HIGH risk). 
               Cannot optimize without it. Returning to Leader for re-scoping."
```

---

### Example 3: `refactor the queue system`

```
This is HIGH risk. Scope is strictly the Architect's design spec.

Architect spec says: "Extract queue producer and consumer into separate classes.
                      No behavior change. Keep existing interface."

IN_SCOPE:
- Creating QueueProducer and QueueConsumer classes
- Moving existing logic into them
- Updating callers to use the new classes (if spec says so)
- Characterization tests for existing behavior (QA runs these first)

OUT_OF_SCOPE:
- Changing the queue implementation from Redis to RabbitMQ (not in spec)
- Adding retry logic that doesn't exist today (behavior change — not in spec)
- Renaming queue-related constants elsewhere in the codebase

SCOPE_EXPANDED:
- Discovering that 3 callers use the queue in a way not covered by the new interface
  Agent stops: "Found 3 callers with undocumented usage patterns. 
               Cannot complete refactor without addressing them. Returning to Leader."

CRITICAL scope violation:
- Backend starts implementing a completely different queue system
- This must never happen — any deviation from the Architect spec is SCOPE_EXPANDED
```

---

### Example 4: `upgrade PostgreSQL from 13 to 16`

```
Domain: infrastructure + database
Risk: HIGH (database upgrade affects all data operations)

IN_SCOPE:
- Updating the PostgreSQL version in docker-compose.yml
- Updating connection string configuration
- Updating the database driver version in package files
- Testing that the application starts and queries work

OUT_OF_SCOPE:
- Using PG 16 features that weren't available in PG 13
  (Adding new features is out of scope for an upgrade task)
- Refactoring queries to use new syntax
- Changing ORM configuration "while upgrading"

SCOPE_EXPANDED:
- Discovering that one query uses syntax deprecated in PG 14 that breaks in PG 16
  Agent stops: "Found deprecated syntax in src/db/legacy_report.py:112 that 
               fails in PG 16. Cannot complete upgrade without fixing. 
               Returning to Leader for re-scoping."
  (This is legitimate SCOPE_EXPANDED — the task cannot complete without it)
```

---

## Scope Enforcement by Phase

| Phase | Scope Check |
|---|---|
| Phase 3 — Plan | Leader defines explicit scope for each subtask. Every subtask has a bounded file list and behavior description. |
| Phase 5 — Execute (each agent) | Agent declares scope status at end of every output. |
| Phase 5 — Leader receiving agent output | Leader scans output for hidden work signals before routing to next agent. |
| Phase 6 — Close | Leader confirms final change list matches the plan. Any unexplained file changes are flagged. |

---

## The Scope Budget Concept

Every task has a scope budget: the set of files and behaviors the plan authorizes.

Anything inside the budget: proceed.
Anything outside the budget but required: SCOPE_EXPANDED — expand the budget first.
Anything outside the budget and not required: OUT_OF_SCOPE — note and ignore.

This is not bureaucracy. This is the difference between a surgical procedure and exploratory surgery.
The user asked for a scalpel cut. They did not consent to everything the surgeon noticed while in there.
