# Review Checklist

Used by both human reviewers and the automated reviewer engine.

## Scope

- [ ] Changes are within declared `scope_in`
- [ ] No files outside `related_files` were modified unexpectedly
- [ ] No dependency upgrades unless explicitly in scope
- [ ] No API contract changes unless explicitly in scope
- [ ] No database schema changes unless explicitly in scope

## Correctness

- [ ] All acceptance criteria are addressed
- [ ] No obvious logic errors in changed code
- [ ] Edge cases from the task spec are handled
- [ ] Error paths return meaningful messages

## Safety

- [ ] No raw shell command execution with unsanitized input
- [ ] No secrets or credentials in code or logs
- [ ] No file path traversal vulnerabilities introduced
- [ ] No SQL injection vectors introduced
- [ ] Auth/authz behavior unchanged (unless in scope)

## Logging

- [ ] Key stage transitions are logged
- [ ] Errors include enough context to debug without a debugger
- [ ] No sensitive data in log messages
- [ ] Log levels are appropriate (debug vs info vs error)

## Tests

- [ ] New logic has test coverage
- [ ] Existing tests still pass (not broken by changes)
- [ ] Test data does not contain real credentials or PII

## Documentation

- [ ] Public functions have docstrings if non-trivial
- [ ] README updated if behavior changed
- [ ] CHANGELOG entry for user-facing changes

## Scoring Rubric

| Category | 0 | 5 | 10 |
|----------|---|---|----|
| Scope Fit | Major violations | Minor drift | Exactly in scope |
| Safety | Critical issue | Mild concern | No issues |
| Logging | Missing critical logs | Some gaps | Complete |
| Completeness | < 50% criteria met | 50-90% met | All criteria met |
