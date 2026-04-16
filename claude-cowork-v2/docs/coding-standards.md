# Coding Standards

## Language and Runtime

- Python 3.11+ for backend services
- TypeScript 5.x (strict mode) for pipeline tooling
- Node.js 20+ for pipeline scripts
- No JavaScript (use TypeScript exclusively)

## Python Standards

### Style
- Follow PEP 8
- Max line length: 100 characters
- Use type hints on all public function signatures
- Use `dataclasses` or `pydantic` for structured data, never plain dicts at API boundaries

### Imports
- Standard library first, then third-party, then local
- Use absolute imports from the `app` package root
- Never use `import *`

### Error Handling
- Always catch specific exception types, not bare `except:`
- Log the exception with context before re-raising or returning an error response
- Use `RuntimeError` for pipeline stage failures with a descriptive message

### Functions
- Keep functions under 50 lines; extract helpers if needed
- Functions must do one thing
- Name booleans with `is_`, `has_`, `can_` prefixes

## TypeScript Standards

### Style
- 2-space indentation
- Single quotes for strings
- No semicolons (enforced via tsconfig strict)
- Trailing commas in multiline structures

### Types
- No `any` — use `unknown` + type guards when input is untyped
- Prefer `interface` for objects, `type` for unions/aliases
- All function parameters and return types must be explicit

### Async
- Use `async/await`, never raw `.then()` chains
- Always handle rejected promises; never ignore `.catch()`
- Parallel independent operations use `Promise.all()`

### Error Handling
- Use typed error classes, not string throws
- Log errors with context before propagating
- Pipeline stages must not swallow errors silently

## Git Conventions

### Commits
- Format: `<type>(<scope>): <description>`
- Types: feat, fix, refactor, docs, test, chore, perf
- Keep commit messages under 72 characters

### Branches
- Feature: `feat/<ticket-id>-<short-description>`
- Fix: `fix/<ticket-id>-<short-description>`
- Never commit directly to `main`

## Testing Requirements

- Unit tests required for all pure functions
- Integration tests required for all API endpoints
- Render pipeline tests use recorded fixture data, not live downloads
- Test file naming: `test_<module>.py` or `<module>.test.ts`

## Security Standards

- Never log secrets, API keys, or PII
- Never accept user-supplied paths without sanitization
- Never execute shell commands with user-supplied strings without escaping
- Validate all external input at the API boundary
