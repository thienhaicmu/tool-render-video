# Git Rules

## Auto-Approved (settings.local.json allowlist)

```bash
git status
git status --short
git diff <file>
git log --oneline -N
```

## Requires Explicit User Approval Each Time

```bash
git add <specific-file-path>    # name the exact file
git commit -m "..."
git push
```

## FORBIDDEN — Never Run

```bash
git add .                        # stages everything including secrets
git add *                        # same risk
git add -A                       # same risk
git push --force                 # destroys remote history
git commit --amend               # on published commits
git reset --hard                 # without explicit request
git checkout -- .                # destroys working tree changes
git clean -f                     # destroys untracked files
```

## Push Approval Rule

These phrases are NOT push approval:
- "OK"
- "looks good"
- "done"
- "great"

User MUST say explicitly: **"push"** or **"go ahead with push"**

## Commit Message Format

```
<type>: <imperative verb> <what changed>

<why — 1 sentence max, only if non-obvious>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Types: `feature` | `bugfix` | `docs` | `phase` | `refactor` | `test` | `config`

## gitignored — Cannot Commit

- `.claude/` — entire directory (includes `agents/`, `settings.local.json`)
- `backend/static-new/` — Vite build output
- `data/` — runtime database and temp files
- `channels/` — rendered video outputs
- `*.db`, `*.log`

## Staging Discipline

Always name files explicitly:
```powershell
git add backend/app/routes/voice.py
git add backend/tests/test_voice.py
```

Never stage by directory unless ALL changes in that directory are intentional and reviewed.
