# Skill: Code Review

## When to Use

User asks to review a file, diff, recent commit, or phase output.
Reviewer agent uses this automatically post-implementation.

## Workflow

1. Identify exact scope — what file/diff/change is being reviewed
2. Read the relevant file(s) — do not review from memory
3. Run through `ai/rules/review.md` checklist
4. Check against auto-reject conditions first (fastest gate)
5. Assess: regressions, side effects, contract violations, overengineering
6. Output reviewer template (see `.claude/agents/reviewer.md`)

## Required Output

Use reviewer.md output template exactly.
Rate: **PASS** | **CONDITIONAL** | **REJECT**

## Handoff

- **PASS** → git agent (if commit needed) or reporter (if docs/no commit)
- **CONDITIONAL** → developer with exact list of conditions to fix
- **REJECT** → leader with explanation; do not proceed

## Stop Conditions

- Auto-reject trigger found → REJECT immediately, stop reviewing
- Scope is unclear → ask leader to clarify before reviewing

## Token Optimization

Read only the changed files, not the entire codebase.
Focus on: contracts, regressions, protected files.
Skip: whitespace, style, cosmetic issues.
