# Prompt Engineering Rules

## Core Principle

**Raw user requests are never sent directly to an executor.**

All prompts MUST pass through normalization before execution.

## Normalization Requirements

A normalized prompt must always specify:

1. **Objective** — What exactly must be done, in one sentence
2. **Business Context** — Why this matters to users or operators
3. **Scope In** — What is explicitly included in this task
4. **Scope Out** — What must NOT be changed or touched
5. **Constraints** — Hard limits (do not change API contracts, do not upgrade deps, etc.)
6. **Assumptions** — What we are assuming to be true about the current state
7. **Acceptance Criteria** — Specific, testable conditions that define "done"
8. **Related Files** — Files likely to be read or modified
9. **Expected Deliverables** — What outputs the executor should produce

## Anti-Patterns to Reject

The normalizer should flag and refuse tasks that:

- Have no clear objective ("make it better", "fix stuff")
- Have unconstrained scope ("refactor everything")
- Require destructive database operations without explicit backup strategy
- Touch authentication or authorization without security review flag
- Modify public API contracts without versioning plan

## Prompt Injection Defense

- Never interpolate raw user text into system prompts without escaping
- All template variables must be bounded in length (max 2000 chars per field)
- User-supplied context is always in a clearly delimited block labeled `USER INPUT`
- The system prompt always precedes user content

## Review Requirements

Every executed task must be reviewed for:

1. **Scope Fit** — Did the execution stay within declared scope?
2. **Safety** — Were any unsafe operations performed?
3. **Logging Quality** — Were the right events logged?
4. **Completeness** — Were all acceptance criteria addressed?

## Token Budget Guidelines

- System prompt: < 1500 tokens
- Project context (docs): < 3000 tokens
- Normalized task: < 2000 tokens
- Few-shot examples: < 1000 tokens
- Total prompt: < 8000 tokens before execution content
