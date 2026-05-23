# Skill: Feature Development

## When to Use

User wants to add new functionality.

## Workflow

```
Leader routes → Planner analyzes → [APPROVAL GATE] → Developer implements
→ Reviewer reviews → Git commits → Reporter summarizes → [PUSH GATE]
```

## Step-by-Step

1. **Leader**: classify task, assess risk, route to planner
2. **Planner**: read mandatory docs, produce analysis template, **STOP — wait for approval**
3. **User approves plan**: explicit "go ahead" required
4. **Developer**: implement minimal diff, py_compile, focused pytest
5. **Reviewer**: run checklist, output review template
   - PASS → step 6
   - CONDITIONAL → back to developer, then re-review
   - REJECT → back to planner
6. **Git**: propose explicit staging + commit message, **STOP — wait for push approval**
7. **Reporter**: short summary, risks remaining, next steps

## Approval Gates

- Gate 1 (mandatory): After planner output, before developer starts
- Gate 2 (mandatory): After commit proposal, before push

## Feature-Specific Rules

| Feature type | Rule |
|-------------|------|
| New AI capability | Default `opt_in=False` in `schemas.py` |
| New API route | Preserve all existing routes |
| New DB column | Additive only (with default), never drop existing |
| New UI feature | Identify which frontend state first; frontend work may be blocked (see CURRENT.md) |
| New render flag | Default to disabled in `RenderRequest` |

## Stop Conditions

- Planner finds scope is CRITICAL → warn user, pause, get explicit confirmation
- Reviewer rejects twice → escalate to leader for rescoping
- Scope creep detected mid-implementation → stop, return to planner
