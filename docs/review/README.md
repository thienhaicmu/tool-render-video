# docs/review/ — READ-ONLY AUDIT LEDGER

**This directory must not be edited by agents or developers without explicit human authorization.**

---

## What this directory is

This directory contains audit records, product state reviews, AI pipeline reviews,
render quality assessments, and technical debt snapshots captured at specific points
in project history.

These files exist to record what was reviewed, what was found, and what decisions were made.
They are historical records, not current directives.

## Why it is read-only

Editing audit records is equivalent to altering a paper trail. These files derive
their value from being accurate at the time they were written. Retroactive edits
corrupt the historical record and invalidate the audit chain.

## AGENTS.md rule

AGENTS.md explicitly states (lines 111–113):

```
Protected folders:
- NEVER edit docs/review/**
- NEVER edit docs/archive/**
unless explicitly requested.
```

This rule applies to all agents, in all sessions, without exception.

## What to do if you need to record a new finding

Do NOT edit existing files in this directory.

Instead:
1. Create a **new file** in `docs/review/` with the current date in the filename
   (example: `BACKEND_REVIEW_2026-05-23.md`)
2. Reference the previous file if updating an earlier finding
3. Explain what changed and why in the new file

The historical record stays intact. The update becomes a new dated entry.

## Contents

Approximately 38 files covering:

- Product state reviews (`PRODUCT_STATE_*.md`)
- Backend and AI pipeline audits
- Frontend UI audits
- Technical debt reports
- Render quality assessments
- Scorecard and architecture reviews

All are historical records. None are current work directives.
