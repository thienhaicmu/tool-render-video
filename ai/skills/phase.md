# Skill: Phase Execution

## When to Use

User initiates a named phase (e.g., "Phase B1", "Phase C1", "Phase A3").

## Workflow

1. Read the entire phase spec before doing anything
2. Read `CURRENT.md` — check blockers that might invalidate phase assumptions
3. Identify scope boundaries (what is IN and OUT of scope)
4. Break into sub-tasks, assess risk per sub-task
5. For each sub-task:
   a. Planner analyzes (if MEDIUM+ risk)
   b. Get approval (if MEDIUM+ risk)
   c. Developer implements
   d. Verify (py_compile + pytest)
   e. ONLY then proceed to next sub-task
6. Reporter produces phase report at end
7. Git: propose commit for all tracked changes
8. **STOP — wait for push approval**

## Phase Report Sections (mandatory)

```
# Phase Completed
# Files Created
# Files Modified
# <Phase-specific sections>
# Runtime Safety Verification
# Tests Performed
# Git Diff Summary
# Commit Message
# Push Status: WAITING FOR APPROVAL
# Risks
# Recommended Next Phase
```

## Stop Conditions

- Any sub-task touches protected files without explicit approval → STOP, escalate
- Phase spec contradicts current state in `CURRENT.md` → STOP, verify first, do not assume
- Sub-task produces py_compile failure → fix before proceeding to next sub-task
- Sub-task produces pytest regression → stop phase, report, do not continue

## Key Rule

Never start implementation of the next sub-task before the current one is verified.
Phases executed out of order corrupt the project state.

## Phase History Convention

Phase naming: `A1`, `A2`, `A3`, `B1`, `B2`, `C1`, ...
Letter = category (A=Foundation, B=Build, C=Cleanup)
Number = sequence within category
