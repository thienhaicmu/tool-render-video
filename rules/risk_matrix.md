# Risk Matrix — Universal Risk Classification

> Read by: Leader (classify), Reviewer (calibrate depth), QA (calibrate coverage).
> Do not modify for project-specific concerns — add overrides in `PROJECT_CONTEXT.md`.
> Version: 1.0

---

## Classification Philosophy

Risk is not about how hard the change is. It is about:
- **Blast radius:** How many systems/users are affected if this goes wrong?
- **Reversibility:** How hard is it to undo this if it breaks?
- **Data sensitivity:** Does this touch user data, credentials, or financial records?
- **System criticality:** Does this live on a path that must always work?

A one-line change that touches a payment processing function is HIGH.
A 500-line addition that is a new isolated utility is LOW.
Size does not determine risk. Impact does.

---

## The Four Levels

---

### LOW

**Definition:** The change is isolated. If it breaks, the blast radius is one module or one feature. It can be reverted in seconds. No shared systems are modified.

**Characteristics:**
- Self-contained — not called by other modules
- No behavior change to existing public interfaces
- No data mutation (reads only, or writes to isolated data)
- Easy to test in isolation
- Revert = delete the new code or revert one file

**Examples by Domain:**

| Domain | Example |
|---|---|
| Backend | Adding a new isolated utility function with tests |
| Backend | Renaming a local variable or private method |
| Backend | Adding a new config field with a safe default |
| Frontend | Styling changes with no logic change |
| Frontend | Adding a new UI component used in one place |
| Database | Adding an optional nullable column with no constraints |
| Architecture | Documenting an existing architecture decision |
| AI | Tweaking a non-critical prompt template |
| Infra | Updating a README or .gitignore |
| Testing | Adding tests for already-existing behavior |
| Docs | Any documentation update |

**Required Gates:**
```
Architect:  No
Reviewer:   Optional (use judgment — skip for trivial, run for logic)
QA:         Optional (required if touching existing logic)
Human OK:   No
```

**Testing requirement:** New logic should have a test. Docs and style changes do not.

**Rollback:** Instant. Revert the file.

---

### MEDIUM

**Definition:** The change touches shared systems or creates new contracts that other code will depend on. If it breaks, multiple callers or users are affected. Requires coordination to revert cleanly.

**Characteristics:**
- Creates new API surface (endpoint, function, event) that others will call
- Modifies existing shared utilities or services
- Adds new external dependencies
- Changes behavior others rely on (even if backwards-compatible)
- Adds a new database table, index, or relationship

**Examples by Domain:**

| Domain | Example |
|---|---|
| Backend | New internal or external API endpoint |
| Backend | New service class integrated into the DI container |
| Backend | Modifying shared middleware |
| Backend | Adding a third-party library or SDK |
| Backend | Changing error response format for existing endpoints |
| Frontend | New page or route |
| Frontend | New shared component used in multiple places |
| Frontend | Adding a new client-side state management flow |
| Database | New table with foreign keys |
| Database | Adding a NOT NULL column to an existing table |
| Database | New stored procedure or database function |
| Architecture | Introducing a new layer or pattern to the codebase |
| AI | Changing agent tool definitions or tool behavior |
| AI | Adding new memory or retrieval backend |
| Infra | Docker Compose changes affecting dev environment |
| Infra | New environment variable required in production |
| Refactor | Refactoring a module others import from |

**Required Gates:**
```
Architect:  Optional (required if design decision is involved)
Reviewer:   Required
QA:         Optional (required if existing behavior is modified)
Human OK:   No
```

**Testing requirement:** New endpoints and services must have tests. Modified shared utilities must have updated tests.

**Rollback:** Requires a migration reversal or revert + coordination with callers. Plan before proceeding.

---

### HIGH

**Definition:** The change touches a critical system boundary — authentication, authorization, payments, core data pipeline, public API contracts, or cross-cutting infrastructure. Failure here affects all users or violates a trust boundary.

**Characteristics:**
- Authentication or authorization logic
- Payment or billing flows
- Data integrity guarantees
- Public API breaking changes (even versioned)
- Core pipeline or orchestration logic
- Background job scheduling or queue configuration
- Any change with potential for data corruption
- Any change where "it worked in staging but not prod" is a realistic scenario

**Examples by Domain:**

| Domain | Example |
|---|---|
| Backend | Modifying JWT validation or session management |
| Backend | Changing permission checks or role definitions |
| Backend | Adding or modifying rate limiting logic |
| Backend | Changing retry logic on critical async operations |
| Frontend | Modifying auth flow or protected route guards |
| Database | Altering an existing column type or constraint |
| Database | Adding an index to a large production table |
| Database | Writing or modifying a migration script |
| Architecture | Splitting a monolith service into two |
| Architecture | Changing event schema consumed by multiple services |
| AI | Changing a system prompt that controls agent behavior |
| AI | Modifying tool execution logic (especially sandboxed code execution) |
| Infra | Kubernetes resource limit changes |
| Infra | Changing background job concurrency or queue depth |
| Infra | Modifying load balancer or reverse proxy config |

**Required Gates:**
```
Architect:  Required — design must precede implementation
Reviewer:   Required
QA:         Required
Human OK:   Required — confirm before execution begins
```

**Testing requirement:** Integration tests that cover the modified critical path. Edge cases for auth/payment flows. Rollback must be tested in staging.

**Rollback:** Must be explicitly planned before execution. State the rollback steps before the human approves.

---

### CRITICAL

**Definition:** The change is potentially irreversible, destructive, or touches a security boundary that if breached puts users, data, or the business at risk. One mistake here cannot be undone without significant effort or data loss.

**Characteristics:**
- Destructive database operations (DROP, TRUNCATE, DELETE)
- Direct production data mutation
- Secrets or credential management
- Deployment pipelines and CI/CD configuration
- Security boundary changes (CORS, CSP, firewall, network policy)
- Removing or bypassing auth checks
- Mass user data operations
- Any operation where "undo" involves data recovery

**Examples by Domain:**

| Domain | Example |
|---|---|
| Backend | Removing an auth middleware from a route |
| Backend | Changing token expiry to a significantly longer window |
| Database | DROP TABLE, TRUNCATE, DELETE without WHERE clause |
| Database | Direct production data patching outside migration system |
| Database | Changing encryption at rest configuration |
| Architecture | Full service replacement or decomposition |
| Architecture | Changing the primary authentication provider |
| AI | Adding a tool that can execute arbitrary code without sandbox |
| AI | Removing safety guardrails from an agent |
| Infra | Modifying deployment pipeline (GitHub Actions, Dockerfile for prod) |
| Infra | Changing secrets management (Vault, AWS SSM, env var rotation) |
| Infra | Opening firewall rules or changing network topology |
| Infra | Force-pushing to main branch |

**Required Gates:**
```
Architect:  Required
Reviewer:   Required
QA:         Required
Human OK:   Required — "CONFIRMED" response mandatory, no exceptions
Rollback Plan: Required — stated before human approval is requested
```

**Testing requirement:** Full integration test suite must pass. Staging validation before prod. Manual verification checklist.

**Rollback:** Must be possible. If rollback would cause data loss, this must be stated explicitly. If no clean rollback exists, the operation requires elevated scrutiny.

---

## Quick Classification Guide

Use this as a fast-path check. If in doubt, classify higher.

```
Is this deleting or truncating data, or touching secrets?
  → CRITICAL

Is this touching auth, payments, migrations, or core pipelines?
  → HIGH

Is this creating new shared contracts (APIs, tables, events) or 
modifying existing shared code?
  → MEDIUM

Is this isolated, reversible, and contained to one module?
  → LOW
```

**When in doubt:** Go one level higher. Downgrading risk is a judgment you make after careful reading. Upgrading risk is free.

---

## Compound Risk Rules

When a task spans multiple domains, the final risk level is **the maximum of all domains**. Risk is never averaged.

| Combination | Final Risk |
|---|---|
| Backend (LOW) + Docs (LOW) | LOW |
| Backend (MEDIUM) + Database (MEDIUM) | MEDIUM |
| Backend (MEDIUM) + Auth (HIGH) | HIGH |
| Refactor (MEDIUM) + Database migration (HIGH) | HIGH |
| Any change + Production data mutation | CRITICAL |
| Any change + Secrets management | CRITICAL |
| Any change + Deployment pipeline | CRITICAL |

---

## Anti-Pattern Detection

These patterns auto-escalate risk by one level, regardless of domain:

| Anti-Pattern | Why It Escalates |
|---|---|
| "I'll fix the tests later" | Testing deferral is a signal the change isn't understood |
| "This is just a small change to X" where X is auth/payments/migrations | Minimization of critical-path changes |
| "It works the same way, just cleaner" with no characterization tests | Behavior equivalence is unverified |
| "We can always roll it back" with no rollback plan | Rollback assumed, not designed |
| "This only affects dev, not prod" for a shared configuration | Environments converge — prod will see this |
| Bypassing migration system with direct schema edits | Breaks reproducibility |
| Storing credentials in code or config files committed to git | Instant CRITICAL |

---

## Mid-Task Risk Escalation

Any agent that discovers a risk level higher than the classified level **must stop and escalate**:

```
## Risk Escalation

Originally classified: [original level]
Discovered during: [task description]
New classification: [new level]

Reason: [What was found that changes the risk level]

Do NOT proceed at the original risk level. 
Returning to Leader for re-classification and re-gating.
```

Leader must re-run Phase 4 (Gate) at the new risk level.

---

## Domain-Specific Risk Reference

### Backend
- New endpoint: MEDIUM
- Modified auth: HIGH
- New dependency with known CVEs: HIGH → CRITICAL depending on CVE
- Any shell=True or eval(): CRITICAL (security)
- Modifying global error handler: HIGH

### Database
- New nullable column: LOW
- New NOT NULL column: MEDIUM (requires backfill)
- Schema change to high-traffic table (millions of rows): HIGH (locking risk)
- Any DROP or TRUNCATE: CRITICAL
- Direct UPDATE to prod data: CRITICAL

### AI / Agentic Systems
- Prompt wording changes: LOW–MEDIUM (test with evals)
- System prompt changes: HIGH (affects all agent behavior)
- New tool with network access: HIGH
- New tool with code execution: CRITICAL
- Removing output filtering: CRITICAL

### Infrastructure
- README / .gitignore: LOW
- New env var with default: LOW–MEDIUM
- Docker build optimization: MEDIUM
- Production resource limits: HIGH
- Deployment pipeline changes: CRITICAL
- Network policy / firewall changes: CRITICAL

### Architecture
- Documenting existing patterns: LOW
- Introducing a new pattern: MEDIUM
- Cross-service contract change: HIGH
- Full service replacement: CRITICAL

---

## Classification Decision Tree

```
START
  │
  ├── Does this delete, truncate, or directly mutate production data?
  │     YES → CRITICAL
  │
  ├── Does this touch secrets, credentials, or deployment pipelines?
  │     YES → CRITICAL
  │
  ├── Does this remove or bypass auth, security boundaries, or safety checks?
  │     YES → CRITICAL
  │
  ├── Does this touch auth logic, payments, data integrity, core pipeline,
  │   or public API contracts?
  │     YES → HIGH
  │
  ├── Does this create new shared contracts (endpoints, tables, events)
  │   or modify existing shared code?
  │     YES → MEDIUM
  │
  └── Is this isolated, reversible, and contained to one module?
        YES → LOW
        UNSURE → go one level up
```
