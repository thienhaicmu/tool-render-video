# Engineering Standards

## Scope
- Make the smallest correct change.
- Edit only required files.
- No unrelated refactors.

## Compatibility
- Preserve existing APIs and data/path conventions.
- Preserve fallback behavior unless task requires change.

## Safety
- Do not run destructive operations unless explicitly requested.
- Do not weaken security-related behavior.
- Do not add dependencies unless required.

## Assumptions
- State assumptions explicitly.
- Mark unknown facts as `TODO`.

## Verification
- Run practical checks for touched areas.
- If checks cannot run, provide exact manual verification steps.
