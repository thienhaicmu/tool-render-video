# Memory Rules — Agent Memory Protocol

> Read by: Leader on every task start, close, and memory update.
> Enforced by: Leader — no other agent writes to memory files directly.
> Do not modify for project-specific concerns.
> Version: 1.0

---

## Purpose

Memory files are the operating system's persistent state. They exist so that:
1. Work is not repeated between sessions.
2. Decisions are not re-litigated after they are made.
3. Risks discovered in one task inform future tasks.
4. The project context remains accurate as the project evolves.

Memory corruption — writing the wrong information to the wrong file — is as dangerous as a software bug.
It causes agents to make decisions on false premises.

This file defines exactly what goes in each memory file, who owns it, and when it must be updated.

---

## Memory File Ownership

| File | Owner | Can Update | Update Trigger |
|---|---|---|---|
| `memory/CURRENT.md` | Leader | Leader only | Task start, each phase, task close |
| `memory/TASK.md` | Leader | Leader only | Task created, status changed, task closed |
| `memory/DECISIONS.md` | Architect (via Leader) | Leader writes, Architect produces content | New architecture decision (ADR) produced |
| `memory/RISKS.md` | Any agent (via Leader) | Leader writes, any agent can flag | New risk discovered, risk mitigated |
| `PROJECT_CONTEXT.md` | Human (with Leader/Architect assistance) | Leader on initialization, human otherwise | Stack change, new convention, human request |
| `memory/ARCHITECTURE.md` | Architect (via Leader) | Leader writes, Architect produces content | Architecture changes confirmed |

**No agent writes to memory files directly.** Agents produce output. Leader writes memory. This is non-negotiable — it prevents race conditions, contradictory writes, and scope inflation in memory.

---

## Memory File Definitions

---

### CURRENT.md

**Purpose:** The live state of whatever task is currently in progress. One active task at a time.

**Lifecycle:**
```
CREATED:  When Leader begins a new task (Phase 1 of operating_model.md)
UPDATED:  After each phase completes
ARCHIVED: When task closes — append summary to TASK.md, then clear CURRENT.md
```

**Allowed content:**
- Active task ID and original instruction (verbatim)
- Current phase and status
- Subtask status checklist
- Decisions made during this specific task (not general architecture decisions)
- Blockers and what they are waiting on
- Agent outputs — summarized, not verbatim pasted
- Risk level classification
- Scope flags raised during the task

**Forbidden content:**
- Historical tasks (those belong in TASK.md)
- Architecture decisions that outlive this task (those belong in DECISIONS.md)
- Risks that outlive this task (those belong in RISKS.md)
- Code snippets or diffs (not memory — those are implementation artifacts)
- Agent prompts or briefings
- Anything that would be meaningless to a future reader who wasn't present for this task

**Size limit:** CURRENT.md must not exceed 200 lines. If it is growing beyond this, it is accumulating content that belongs in other files. Summarize and move.

**Format:**
```markdown
# CURRENT.md

## Active Task
ID: T-[NNN]
Instruction: [verbatim original instruction]
Risk Level: [LOW | MEDIUM | HIGH | CRITICAL]
Status: [Planning | In Progress | Blocked | Review | Validation | Done]
Started: [YYYY-MM-DD HH:MM]

## Subtasks
- [ ] [T-NNN-1] [description] → @architect [status]
- [x] [T-NNN-2] [description] → @backend [DONE]
- [ ] [T-NNN-3] [description] → @reviewer [In Progress]

## Agent Output Summaries
@architect: [one sentence summary of design output]
@backend: [one sentence summary of what was implemented]
@reviewer: [verdict — PASS/FAIL + key finding if any]
@qa: [verdict — VALIDATED/FAILED + key finding if any]

## Decisions This Task
- [Decision made and why — only decisions specific to this task]

## Blockers
- [description] — waiting on [human | external system] since [date]

## Notes
[Anything unexpected discovered during this task]
```

---

### TASK.md

**Purpose:** Permanent, append-only audit log of all tasks. The source of truth for what work has been done on this project.

**Lifecycle:**
```
CREATED:  When framework is initialized (/leader initialize project)
UPDATED:  Append-only — never delete or edit existing entries
NEVER:    Truncated, compressed, or summarized (it is the permanent record)
```

**Allowed content:**
- Task ID, original instruction, date, risk level, outcome
- One-line summary of what was done
- Task status history (created → in-progress → done/blocked)
- The task log (chronological action entries)

**Forbidden content:**
- Full agent outputs
- Code snippets or diffs
- Detailed implementation notes
- Anything that belongs in CURRENT.md, DECISIONS.md, or RISKS.md
- Duplicate entries for the same task

**Format:**
```markdown
# TASK.md — Task Registry

## In Progress
| ID | Instruction | Started | Risk | Status |
|----|-------------|---------|------|--------|
| T-007 | fix JWT expiry bug | 2025-01-15 | HIGH | In Progress |

## Completed
| ID | Instruction | Completed | Risk | Outcome |
|----|-------------|-----------|------|---------|
| T-001 | initialize project | 2025-01-10 | LOW | COMPLETE — 3 risks found |
| T-006 | add user profile endpoint | 2025-01-14 | MEDIUM | COMPLETE — Reviewer PASS |

## Task Log (append only)
[2025-01-10 09:00] T-001 CREATED — "/leader initialize project"
[2025-01-10 09:45] T-001 COMPLETE
[2025-01-14 14:00] T-006 CREATED — "/leader add user profile endpoint"
[2025-01-14 16:30] T-006 ROUTED → @architect
[2025-01-14 17:00] T-006 ROUTED → @backend
[2025-01-14 18:00] T-006 ROUTED → @reviewer — PASS
[2025-01-14 18:05] T-006 COMPLETE
```

---

### DECISIONS.md

**Purpose:** Permanent record of significant architecture decisions. An ADR (Architecture Decision Record) for every choice that was hard to make, is hard to reverse, or affects multiple systems.

**Lifecycle:**
```
CREATED:  On initialization (empty)
UPDATED:  Only when Architect produces an ADR for a significant decision
NEVER:    Updated for implementation choices, bug fixes, or routine tasks
ENTRIES:  Never deleted — superseded decisions are marked as such
```

**Allowed content:**
- ADR entries following the standard format
- Status updates on existing decisions (Proposed → Accepted → Superseded)
- Cross-references between related decisions

**Forbidden content:**
- Task status or task history (that's TASK.md)
- Implementation details ("we used a try/except here because...")
- Bug fix rationale
- Trivial choices (variable naming, function organization, loop style)
- Anything that will be irrelevant in 6 months

**The threshold test:** "Would a new engineer need to know about this decision to understand why the codebase is structured the way it is?" If yes → DECISIONS.md. If no → it belongs nowhere in memory.

**Format:**
```markdown
# DECISIONS.md

## Decision Log

### ADR-001: [Title]
Status: Accepted
Date: 2025-01-12
Author: @architect

Context:
[Why this decision was needed — what problem was being solved]

Decision:
[What was decided — be specific]

Rationale:
[Why this option over the alternatives]

Consequences:
- Makes easier: [what]
- Makes harder: [what]

Revisit when: [specific condition that would trigger reconsideration]

---

### ADR-002: [Title — supersedes ADR-001]
Status: Accepted (Supersedes ADR-001)
...
```

---

### RISKS.md

**Purpose:** Persistent registry of identified risks, vulnerabilities, and known tech debt. Risks stay open until they are explicitly mitigated.

**Lifecycle:**
```
CREATED:  On initialization (populated by project scan)
UPDATED:  When a new risk is discovered during any task
UPDATED:  When a risk is mitigated (mark as RESOLVED — never delete)
ENTRIES:  Never deleted — only marked RESOLVED
```

**Allowed content:**
- Risk entries with severity, evidence, and recommended action
- Resolution entries when risks are mitigated
- Risk status updates

**Forbidden content:**
- Task status
- Architecture decisions
- Implementation details
- Risks that were already captured (check before adding — prevent duplicates)

**Who can flag risks:** Any agent can flag a risk. The agent includes the risk in their structured output. Leader writes it to RISKS.md.

**Format:**
```markdown
# RISKS.md

## Open Risks

### RISK-001: Hardcoded API key in src/integrations/stripe.py
Status: OPEN
Severity: CRITICAL
Type: credential-leak
Location: src/integrations/stripe.py:47
Evidence: Found `api_key = "sk_live_..."` literal in source
Detected: 2025-01-10
Recommended action: Move to environment variable immediately. Rotate the key.

### RISK-002: No test suite
Status: OPEN
Severity: HIGH
Type: no-tests
Location: entire codebase
Evidence: No test directory found during initialization scan
Detected: 2025-01-10
Recommended action: Establish test suite before making any HIGH/CRITICAL changes

## Resolved Risks

### RISK-003: JWT token not expiring correctly
Status: RESOLVED
Severity: HIGH
Resolved: 2025-01-15
Resolution: Fixed in T-007. Token expiry now enforced in middleware. Tests added.
```

---

### PROJECT_CONTEXT.md

**Purpose:** Project-specific configuration file. Tells every agent how this specific project works — stack, conventions, protected zones, risk overrides.

**Lifecycle:**
```
CREATED:  By human (from template) or by Leader (/leader initialize project)
UPDATED:  By human when the project changes (new stack, new conventions)
UPDATED:  By Leader only during initialization or audit workflows
UPDATED:  By Architect (via Leader) when architecture changes are formalized
NEVER:    Updated during a routine task (bug fix, feature, refactor)
```

**Allowed content:**
- Stack description
- Architecture overview
- Coding conventions
- Protected zones
- Risk overrides
- Domain context
- External systems

**Forbidden content:**
- Task status or history
- Risk log
- Decision log
- Anything that changes frequently (if it changes every sprint, it doesn't belong here)

**Update frequency:** Should be stable. If it is changing every week, the project is in flux and this must be noted explicitly.

---

### ARCHITECTURE.md

**Purpose:** Living documentation of the current system architecture. Produced during initialization, updated when the architecture changes.

**Lifecycle:**
```
CREATED:  During /leader initialize project (auto-generated from scan)
UPDATED:  When Architect confirms an architectural change
UPDATED:  After /leader audit current architecture
NEVER:    Updated during a routine task (bug fix, feature, refactor)
```

**Allowed content:**
- Component map and roles
- Dependency relationships
- Data flow descriptions
- Deployment architecture
- Known architectural risks and constraints

**Forbidden content:**
- Task status
- Implementation details (function names, variable names)
- Risk log (cross-reference RISKS.md)
- Anything at a lower level than system/component architecture

---

## Update Rules — The Exact Protocol

### When to Write to CURRENT.md

| Event | Write to CURRENT.md? | What to write |
|---|---|---|
| Task starts (Phase 1) | YES | Full task header, empty subtask list |
| Architect completes | YES | Summary of design output (1-2 sentences) |
| Backend completes | YES | Summary of implementation (files changed) |
| Reviewer returns verdict | YES | Verdict + key findings if FAIL |
| QA returns verdict | YES | Verdict + key findings if FAILED |
| Blocker discovered | YES | Description + what it's waiting on |
| Scope expansion flagged | YES | What was discovered, what options were presented |
| Task closes | YES | Mark complete, then archive to TASK.md and clear |

### When to Write to TASK.md

| Event | Write to TASK.md? | What to write |
|---|---|---|
| Task created | YES | New row in In Progress, log entry CREATED |
| Task phase changes | YES | Log entry only (routing events) |
| Task completes | YES | Move to Completed, log entry COMPLETE |
| Task blocked | YES | Log entry BLOCKED, update status |
| Task aborted | YES | Move to Completed with outcome ABORTED |

### When to Write to DECISIONS.md

| Event | Write to DECISIONS.md? | What to write |
|---|---|---|
| Architect produces an ADR | YES | Full ADR entry |
| Architecture decision is reversed | YES | Update existing entry status to Superseded, add new ADR |
| Bug is fixed | NO | — |
| Implementation choice is made | NO | — |
| Framework version is upgraded | MAYBE | Only if the choice has significant architectural implications |
| New library is added | MAYBE | Only if it introduces a new architectural pattern |

### When to Write to RISKS.md

| Event | Write to RISKS.md? | What to write |
|---|---|---|
| Initialization scan finds risk | YES | Full risk entry |
| Reviewer flags a security issue | YES | Full risk entry at appropriate severity |
| QA finds a systemic test gap | YES | Risk entry — type: no-tests |
| Any agent finds a credential or secret | YES | CRITICAL risk entry immediately |
| Risk is resolved/mitigated | YES | Update entry status to RESOLVED |
| Bug is fixed that wasn't previously a tracked risk | NO | — |

### When to Write to PROJECT_CONTEXT.md

| Event | Write to PROJECT_CONTEXT.md? | What to write |
|---|---|---|
| /leader initialize project | YES | Generated content from scan |
| Stack change confirmed by Architect | YES | Updated stack section |
| New protected zone identified | YES | Add to protected zones section |
| Human requests update | YES | As requested |
| Bug fix | NO | — |
| Feature addition | NO | — |
| Refactor | NO | Unless it changes the architecture |

### When to Write to ARCHITECTURE.md

| Event | Write to ARCHITECTURE.md? | What to write |
|---|---|---|
| /leader initialize project | YES | Generated content from scan |
| Architecture change confirmed by Architect ADR | YES | Updated component map / dependency graph |
| /leader audit current architecture | YES | Refresh from scan |
| Bug fix | NO | — |
| Feature addition | NO | Unless it adds a new component |
| Refactor | MAYBE | Only if component structure changes |

---

## Update Decision Matrix

Quick reference for Leader — given a task completion event, which files update?

| Task Type | CURRENT | TASK | DECISIONS | RISKS | PROJECT_CONTEXT | ARCHITECTURE |
|---|---|---|---|---|---|---|
| Bug fix (LOW) | ✓ close | ✓ complete | ✗ | ✗ | ✗ | ✗ |
| Bug fix (HIGH — security) | ✓ close | ✓ complete | ✗ | ✓ RESOLVED | ✗ | ✗ |
| New feature (MEDIUM) | ✓ close | ✓ complete | ✗ | ✗ | ✗ | ✗ |
| New feature (HIGH) | ✓ close | ✓ complete | maybe | ✗ | ✗ | maybe |
| Architecture decision | ✓ close | ✓ complete | ✓ ADR | ✗ | maybe | ✓ |
| Refactor | ✓ close | ✓ complete | ✗ | ✗ | ✗ | maybe |
| New risk discovered (any task) | ✓ note | ✓ log | ✗ | ✓ new entry | ✗ | ✗ |
| Risk mitigated (any task) | ✓ note | ✓ log | ✗ | ✓ RESOLVED | ✗ | ✗ |
| Stack change | ✓ close | ✓ complete | ✓ ADR | ✗ | ✓ | ✓ |
| Initialization | ✓ init | ✓ init | ✓ init | ✓ from scan | ✓ generated | ✓ generated |

### Worked Example — JWT Expiry Bug Fix

```
Task: /leader fix JWT token expiry bug
Risk: HIGH (auth = HIGH)
Agents: Backend → Reviewer → QA

Updates:
  CURRENT.md    → YES: task status throughout, close on completion
  TASK.md       → YES: T-007 in-progress → complete
  DECISIONS.md  → NO: fixing a bug is not an architecture decision
  RISKS.md      → YES: if this was a tracked risk (RISK-004), mark RESOLVED
                     if NOT tracked, add a brief risk entry for the record
                     then immediately mark RESOLVED
  PROJECT_CONTEXT.md → NO: bug fix does not change project conventions
  ARCHITECTURE.md    → NO: fixing expiry logic does not change architecture
```

### Worked Example — Migrate from REST to GraphQL

```
Task: /leader migrate our API to GraphQL
Risk: HIGH (breaking API contract change)
Agents: Architect → Backend → Reviewer → QA

Updates:
  CURRENT.md    → YES: task status throughout
  TASK.md       → YES: in-progress → complete
  DECISIONS.md  → YES: ADR-NNN "Adopt GraphQL over REST" — Architect produces this
  RISKS.md      → YES: migration risks identified by Architect
  PROJECT_CONTEXT.md → YES: Framework section updated (GraphQL client, schema location)
  ARCHITECTURE.md    → YES: API layer description updated
```

---

## Anti-Noise Rules

These rules prevent memory files from accumulating useless content.

**1. No verbatim agent output in CURRENT.md.**
Summarize. One or two sentences per agent. Full outputs belong in the conversation, not memory.

**2. No ephemeral decisions in DECISIONS.md.**
"We used a for loop instead of a list comprehension" is not an architecture decision.

**3. No task-specific notes in RISKS.md.**
"The auth bug we fixed today was messy" is not a risk entry.

**4. No duplicate risk entries.**
Before adding to RISKS.md, scan for an existing entry on the same topic. Update the existing entry, do not create a duplicate.

**5. No status updates that do not change state.**
Do not write "Backend is still working on this" to TASK.md. Only write when state transitions.

**6. No future speculation in any memory file.**
"We might want to refactor X later" belongs in a GitHub issue or the conversation, not memory.

---

## Anti-Bloat Rules

**CURRENT.md:** Clear after every task. Archive to TASK.md. If CURRENT.md has more than 200 lines, something is wrong — summarize and move content to the appropriate file.

**TASK.md:** Never prune. It is the permanent record. It will grow. That is correct.

**DECISIONS.md:** One ADR per decision. Do not split one decision into multiple ADRs. Do not merge unrelated decisions into one ADR.

**RISKS.md:** Mark risks RESOLVED when they are mitigated. Never delete them. The historical record of what risks existed and when they were resolved is valuable.

**PROJECT_CONTEXT.md:** Should be stable. If it grows past 200 lines, review for content that should not be there (task history, implementation details, etc.).

**ARCHITECTURE.md:** Should describe the system at component level, not file level. If it is describing individual functions or classes, it is too detailed.

---

## Memory Expiration Policy

| File | Expires? | Policy |
|---|---|---|
| CURRENT.md | YES | Cleared after each task closes. Content archived to TASK.md. |
| TASK.md | NO | Permanent. Append-only. Never expires. |
| DECISIONS.md | NO | Permanent. Entries can be superseded but not deleted. |
| RISKS.md | NO | Permanent. Risks are RESOLVED, never deleted. |
| PROJECT_CONTEXT.md | SOFT | Valid until the project changes. Leader flags stale content during audit. |
| ARCHITECTURE.md | SOFT | Valid until architecture changes. Leader flags stale content during audit. |

**Stale detection:** During `/leader audit current architecture`, Leader compares ARCHITECTURE.md and PROJECT_CONTEXT.md against the current scan. Any detected mismatch is flagged:
```
⚠️ Stale memory detected:
  ARCHITECTURE.md says: [old content]
  Current scan finds: [new content]
  Action: Update ARCHITECTURE.md before proceeding
```
