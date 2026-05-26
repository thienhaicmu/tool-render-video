# Routing Rules — Universal Agent Routing

> Read by: Leader on every invocation.
> Do not modify for project-specific concerns — add overrides in `PROJECT_CONTEXT.md`.
> Version: 1.0

---

## Routing Philosophy

The routing system answers one question: **which agents, in what order, for this task?**

The answer comes from three inputs applied in this order:
1. **Domain detection** — what area of the system does this touch?
2. **Intent classification** — what is the task asking to do?
3. **Risk level** — what gates are required regardless of intent?

Risk level gates override routing. If the risk matrix says Architect is required, Architect runs even if the routing table says skip.

Leader never routes randomly. Every routing decision is traceable to this file.

---

## Domain Detection

Leader classifies every instruction into one or more domains before routing.

### Domain Keywords

| Domain | Signal Keywords / Phrases |
|---|---|
| `backend` | endpoint, API, route, service, controller, handler, model, schema, job, queue, worker, cron, middleware, auth, session, cache, database query, ORM, repository |
| `frontend` | UI, component, page, view, layout, CSS, style, form, button, modal, navigation, client-side, browser, React, Vue, Next.js, SPA, animation |
| `database` | table, column, migration, index, constraint, schema, query, SQL, ORM model, seed, fixture, relation, foreign key, backfill |
| `architecture` | redesign, restructure, refactor architecture, pattern, layer, separation of concerns, dependency, module boundary, system design, ADR, interface contract |
| `infrastructure` | Docker, Dockerfile, docker-compose, CI/CD, pipeline, deploy, Kubernetes, container, environment variable, secret, certificate, nginx, reverse proxy, cloud, AWS, GCP |
| `ai` | prompt, LLM, agent, model, context window, tool call, embedding, retrieval, eval, fine-tune, inference, Claude, GPT, Anthropic |
| `refactor` | refactor, clean up, reorganize, rename, extract, simplify, deduplicate, restructure (without architecture changes) |
| `testing` | test, spec, coverage, mock, fixture, integration test, unit test, e2e test, test suite |
| `docs` | README, documentation, comment, docstring, changelog, wiki |

### Multi-Domain Detection

If the instruction activates keywords from multiple domains:
1. Record all activated domains.
2. Route to the highest-priority agent for the combination (see Multi-Domain table).
3. Risk level = maximum across all domains.

---

## Intent Classification

| Intent | Trigger Phrases | Primary Action |
|---|---|---|
| `create` | "add", "create", "build", "implement", "write", "new", "introduce" | Build something new |
| `modify` | "change", "update", "modify", "edit", "adjust", "tweak" | Change existing behavior |
| `fix` | "fix", "bug", "broken", "error", "issue", "failing", "crash", "not working" | Repair a defect |
| `refactor` | "refactor", "clean up", "reorganize", "simplify", "extract", "restructure" | Change structure, preserve behavior |
| `design` | "redesign", "architect", "plan", "design", "propose", "evaluate", "ADR" | Produce a design before any code |
| `optimize` | "optimize", "performance", "slow", "faster", "reduce", "improve speed" | Performance improvement |
| `review` | "review", "check", "audit", "look at", "evaluate this code" | Review existing code |
| `test` | "test", "add tests", "coverage", "write tests", "validate" | Testing work |
| `document` | "document", "write docs", "README", "explain" | Documentation |

---

## Primary Routing Table

| Domain | Intent | Risk | Primary Agent | Secondary Agents | Notes |
|---|---|---|---|---|---|
| `backend` | `create` | LOW | Backend | Reviewer (opt) | Simple isolated feature |
| `backend` | `create` | MEDIUM | Backend | Reviewer, QA | Shared contract created |
| `backend` | `create` | HIGH | Architect → Backend | Reviewer, QA | Design first |
| `backend` | `modify` | LOW | Backend | Reviewer (opt) | |
| `backend` | `modify` | MEDIUM | Backend | Reviewer | |
| `backend` | `modify` | HIGH | Architect → Backend | Reviewer, QA | |
| `backend` | `fix` | LOW | Backend | QA (opt) | Reproduce with test first |
| `backend` | `fix` | MEDIUM | Backend | QA | |
| `backend` | `fix` | HIGH | Backend | Reviewer, QA | Auth/security bugs always HIGH |
| `backend` | `optimize` | MEDIUM | Backend | Reviewer | Profile before optimizing |
| `backend` | `refactor` | MEDIUM | Architect → Backend | Reviewer | Scope refactor before touching |
| `backend` | `refactor` | HIGH | Architect → QA → Backend | Reviewer, QA | Characterize before refactoring |
| `database` | `create` | MEDIUM | Architect → Backend | Reviewer | Design schema before migrating |
| `database` | `modify` | HIGH | Architect → Backend | Reviewer, QA | Migration scripts are HIGH |
| `database` | `fix` | HIGH | Backend | Reviewer, QA | |
| `architecture` | `design` | HIGH | Architect | Reviewer | Output: ADR |
| `architecture` | `refactor` | HIGH | Architect → QA → Backend | Reviewer, QA | |
| `infrastructure` | any | HIGH | Architect → Backend | Reviewer | |
| `infrastructure` | any | CRITICAL | Human OK → Architect → Backend | Reviewer, QA | |
| `ai` | `modify` (prompts) | HIGH | Backend | Reviewer, QA (evals) | Prompts are HIGH by default |
| `testing` | any | LOW | QA | — | |
| `docs` | any | LOW | Leader (self) | — | No specialist needed |
| `review` | any | any | Reviewer | — | Direct review request |

---

## Routing Algorithm

Leader executes this algorithm on every `/leader` invocation:

```
STEP 1 — DETECT DOMAINS
  Extract signal keywords from the instruction.
  Map to one or more domains.
  If no domain detected → ask one clarifying question.

STEP 2 — CLASSIFY INTENT
  Match the primary verb/phrase to an intent category.
  If ambiguous intent → resolve with the most restrictive interpretation.

STEP 3 — CLASSIFY RISK
  Apply rules/risk_matrix.md classification.
  Apply PROJECT_CONTEXT.md risk overrides if present.
  Final risk = maximum across all detected domains.

STEP 4 — LOOK UP ROUTING TABLE
  Find the row matching (domain + intent + risk).
  If multiple domains match → use the highest-risk domain's routing row.
  Identify: primary agent, secondary agents, required gates.

STEP 5 — APPLY RISK GATES (override routing if needed)
  If risk = HIGH:  Architect required, Reviewer required, QA required.
  If risk = CRITICAL: Same + human CONFIRMED required.
  Gates add to routing, never remove.

STEP 6 — SEQUENCE AGENTS
  If Architect is in the plan → run first. Block on output.
  If QA characterization is needed (refactors) → run before Backend.
  Backend runs after Architect (if present).
  Reviewer runs after Backend.
  QA runs after Reviewer.

STEP 7 — OUTPUT PLAN
  Present plan to user. Apply gate per risk level.
  Execute only after gate is cleared.
```

---

## Multi-Domain Routing

When a task activates multiple domains, use this priority table to determine lead agent:

| Domains Activated | Lead Agent | Rationale |
|---|---|---|
| backend + database | Architect → Backend | Schema must be designed before code |
| backend + architecture | Architect → Backend | Design must precede implementation |
| backend + infrastructure | Architect → Backend | Cross-cutting — design first |
| architecture + any | Architect first | Architecture is always the upstream dependency |
| backend + testing | Backend then QA | Implement first, then validate |
| frontend + backend | Architect (if API contract) → parallel where independent | |
| ai + backend | Architect → Backend | AI tooling and backend usually share contracts |
| any + CRITICAL | Human OK → Architect → Backend | CRITICAL overrides all sequences |

---

## Worked Routing Examples

### `"add auth endpoint"`
```
Domains:  backend (endpoint, auth)
Intent:   create
Risk:     HIGH (auth = HIGH by default)
Routing:  Architect → Backend → Reviewer → QA
Gate:     Human confirmation required (HIGH)
```

### `"refactor the payment queue"`
```
Domains:  backend (queue), architecture (refactor)
Intent:   refactor
Risk:     HIGH (payments = HIGH, core queue = HIGH)
Routing:  Architect (scope) → QA (characterize) → Backend (refactor) → Reviewer → QA (validate)
Gate:     Human confirmation required (HIGH)
Notes:    Characterize behavior with tests BEFORE touching the queue.
```

### `"redesign architecture"`
```
Domains:  architecture (redesign)
Intent:   design
Risk:     HIGH (architecture redesign always HIGH)
Routing:  Architect (produce ADR) → human reviews ADR → Backend (implement) → Reviewer → QA
Gate:     Human confirmation at two points: before Architect proceeds AND after ADR is produced
```

### `"optimize api performance"`
```
Domains:  backend (API, performance)
Intent:   optimize
Risk:     MEDIUM (optimization, not touching auth or core logic)
Routing:  Backend (profile and optimize) → Reviewer
Gate:     Show plan, proceed (MEDIUM — no human confirmation required)
Notes:    Profile first. Do not optimize before measuring.
```

### `"fix backend bug"`
```
Domains:  backend (fix, bug)
Intent:   fix
Risk:     Depends on which backend area. Start with MEDIUM.
          Re-classify if bug is in auth, payments, or core pipeline → HIGH.
Routing:  Backend (reproduce with failing test → fix) → QA
Gate:     MEDIUM → show plan and proceed. HIGH → confirm first.
```

### `"review this implementation"`
```
Domains:  review (explicit review request)
Intent:   review
Risk:     Determined by what is being reviewed
Routing:  Reviewer (direct)
Gate:     No gate — direct review request
Notes:    Reviewer determines risk of the implementation they are reviewing.
```

### `"add user profile table"`
```
Domains:  database (table), backend (model/schema)
Intent:   create
Risk:     MEDIUM (new table, no destructive operations)
Routing:  Architect (design schema) → Backend (create migration + model) → Reviewer
Gate:     Show plan, proceed (MEDIUM)
```

### `"drop the legacy audit_logs table"`
```
Domains:  database (DROP)
Intent:   modify (destructive)
Risk:     CRITICAL (DROP TABLE = always CRITICAL)
Routing:  Architect (impact analysis, confirm nothing reads this table) → human CONFIRMED → Backend → Reviewer → QA
Gate:     CRITICAL — require "CONFIRMED" before any action
```

---

## Conflict Resolution

### Conflict: Ambiguous domain
The instruction activates keywords from two domains with conflicting lead agents.

**Resolution:** Prioritize by dependency order. Architecture is upstream of backend; backend is upstream of frontend. The upstream domain's agent runs first.

### Conflict: Intent contradicts risk level
Example: "just quickly refactor the auth module" — intent suggests LOW (quick refactor) but domain forces HIGH (auth).

**Resolution:** Domain risk always wins. Verbalize the conflict to the user:
```
"This is described as a quick refactor, but it touches the auth module 
which is classified HIGH. I'll follow HIGH risk protocol."
```

### Conflict: PROJECT_CONTEXT.md overrides routing
If `PROJECT_CONTEXT.md` specifies a routing override that differs from this table:

**Resolution:** `PROJECT_CONTEXT.md` overrides win for that project. Log the override in the plan so it's visible.

---

## Fallback Behavior

If routing cannot be determined confidently:

1. Do not guess. Do not proceed.
2. Output the classification attempt and the ambiguity:
```
## Routing Ambiguity

Instruction: "[verbatim]"

I detected signals for: [domains]
But I cannot determine: [what is ambiguous]

To route correctly, I need to know:
[Single most important clarifying question]
```
3. After clarification, restart routing from Step 1.

---

## Anti-Chaos Rules

These rules prevent the most common failure modes:

| Rule | Reason |
|---|---|
| Never route directly to Backend for HIGH/CRITICAL without Architect | Implementation without design produces tech debt and rework |
| Never skip Reviewer for MEDIUM+ changes | Reviewer catches the 20% that implementation misses |
| Never skip QA characterization for refactors | Behavior is assumed preserved, not verified, without tests |
| Never route multiple unrelated tasks in one plan | Separate tasks get separate plans; mixing creates confusion |
| Never proceed on CRITICAL without human "CONFIRMED" | No exception. Ever. |
| Never route "optimize" before "profile" | Optimization without measurement is guessing |
| Never route a fix without reproducing it first | Fixes that aren't reproducible aren't real fixes |

---

## Future Compatibility

This routing table is designed to accept new agent rows without modification of the algorithm.

When new agents are added, update only:
1. The Domain Keywords table — add keywords for the new domain.
2. The Primary Routing Table — add rows for the new agent.
3. The Multi-Domain Routing table — add new combinations if relevant.

The algorithm (Steps 1-7) does not change.

**Reserved domains (not yet routed — future agents):**
- `frontend` → `@frontend` agent (not yet created)
- `infrastructure` → `@devops` agent (currently routes to Backend; override in PROJECT_CONTEXT.md)
- `data` → `@data` agent (not yet created)
- `security` → `@security` agent (not yet created; escalates to Reviewer in MVP)
