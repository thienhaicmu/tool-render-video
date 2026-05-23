# Core Rules

**Source of truth**: code > docs. When they disagree: trust runtime implementation.

## Mandatory Read Order (no exceptions, every session)

1. `CLAUDE.md` — runtime truth, critical warnings
2. `CURRENT.md` — active blockers, what NOT to touch right now
3. `PROJECT_MAP.md` — file ownership, risk levels
4. `AGENTS.md` — protected files, safety rules (THE LAW)

## Sacred Contracts — Never Break

| Contract | Location |
|----------|----------|
| `result_json` aliases: `output_rank_score`, `is_best_output`, `is_best_clip` | `render_pipeline.py` |
| `RenderRequest` new fields must default to `False`/disabled | `schemas.py` |
| AI modules: return `None` on failure, NEVER raise | All `backend/app/ai/**` |
| `data/app.db`: NEVER delete or modify directly | Runtime data |
| `docs/review/**`: READ ONLY, NEVER edit | Audit ledger |
| `docs/archive/**`: READ ONLY, NEVER edit | Historical record |

## Adding Audit Findings (correct process)

1. Create **new** file: `docs/review/TOPIC_YYYY-MM-DD.md`
2. Reference the previous file if updating a finding
3. NEVER edit existing files in `docs/review/`

## After Every Python Change (mandatory)

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m py_compile app\<changed_file>.py
```

## Before Declaring Done (mandatory)

```powershell
python -m pytest tests\<relevant_test>.py -v --tb=short
```

## Blast Radius Order (highest → lowest risk)

`render_pipeline.py` > `render_engine.py` > `schemas.py` > `subtitle_engine.py` > `motion_crop.py` > `ai_director.py` > `routes/*` > `services/*` > `docs/*`

## Minimal Patch Rule

Use Edit tool (surgical diff) over Write tool (full rewrite).
Change only what the plan specifies. Never touch adjacent code.
