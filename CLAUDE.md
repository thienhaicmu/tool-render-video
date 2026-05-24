# CLAUDE.md

## ⚡ AGENT TEAM PROTOCOL — ĐỌC TRƯỚC TIÊN

**Mọi request từ user đều đi qua agent team. Claude PHẢI act as leader agent mặc định.**

### Khi user gửi bất kỳ task nào:

1. **Phân loại task** (leader): xác định loại, risk level, route
2. **Plan trước** (planner): với MEDIUM/HIGH risk — DỪNG lại, viết plan, chờ user approve
3. **Implement** (developer): chỉ sau khi có approved plan
4. **Review** (reviewer): sau khi developer xong
5. **Commit** (git): chỉ sau reviewer PASS
6. **Báo cáo** (reporter): cuối phase hoặc khi user yêu cầu

### Agent team gồm:

| Agent | Subagent type | Vai trò |
|-------|---------------|---------|
| Leader | `leader` | Route task, gate approval — **Claude mặc định** |
| Planner | `planner` | Phân tích + plan (KHÔNG code) |
| Developer | `developer` | Implement (KHÔNG tự ý mở rộng scope) |
| Reviewer | `reviewer` | Review + reject nếu có regression |
| Git | `git` | Commit / push / PR |
| Reporter | `reporter` | Tóm tắt bằng tiếng Việt |

### Rule bắt buộc:

- LOW risk → developer trực tiếp (vd: bug 1-5 dòng rõ nguyên nhân)
- MEDIUM risk → planner → **user approve** → developer
- HIGH/CRITICAL → planner → **user approve bắt buộc** → developer
- Không biết risk → mặc định HIGH → planner trước

### Không được:

- Tự implement mà bỏ qua leader routing
- Developer bắt đầu khi chưa có plan approved (MEDIUM+)
- Commit trước khi reviewer PASS
- Chạm protected files mà không có approved plan

> **Agent definitions:** `.claude/agents/*.md`

---

## Project Identity

AI video rendering platform. Offline-first. Accepts YouTube URLs or local video files,
uses an AI Director to select best segments, renders them with FFmpeg as short-form vertical
videos with platform-optimized subtitles, overlays, and audio. No cloud API required.

## Runtime Truth

When docs and code conflict: **trust code**. Verified runtime state: 2026-05-23.

## Mandatory Reading Order

Before ANY code change — no exceptions:

1. **`AGENTS.md`** — workflow rules, protected files, safety rules (THE LAW)
2. **`docs/ARCHITECTURE.md`** — system identity, stability markers
3. **`CURRENT.md`** — what is broken now, what NOT to touch
4. **`PROJECT_MAP.md`** — file ownership in 30 seconds

Domain docs per AGENTS.md Step 1: render → `docs/RENDER_PIPELINE.md` |
API/UI → `docs/FRONTEND_CONTRACT_PACKET_V1.md` | subtitle → `docs/SUBTITLE_TRANSLATION.md` |
voice → `docs/VOICE_NARRATION.md` | Electron → `docs/DESKTOP_APP.md`

## Critical Warnings

- **`render_pipeline.py` is 5,816 lines.** Every render stage in one file. Never touch casually.
- **`docs/review/**` is READ-ONLY.** AGENTS.md line 111 forbids editing it. See `docs/review/README.md`.
- **`data/app.db` is the sole job state store.** NEVER delete or corrupt it.
- **Never use `git add *` or `git commit *`.** Stage explicit file paths only.
- **Three frontend states exist.** Read Frontend Truth below before touching any UI code.

## Quick Commands

```powershell
# Activate backend venv (Windows PowerShell, from repo root)
cd D:\tool-render-video\backend && .\.venv\Scripts\Activate.ps1

# Start backend with v2 UI:   .\run-backend-v2.ps1
# Start Electron desktop:     .\run-desktop-v2.ps1

# Syntax-check changed Python file
python -m py_compile app\routes\render.py   # example

# Run focused test
python -m pytest tests\test_render_guards.py -v --tb=short

# Run all backend tests (before broad changes)
python -m pytest
```

## Frontend Truth

Three frontend states coexist. Identify which is active before touching any UI file.

| State | Path | Active when |
|-------|------|-------------|
| Legacy HTML app | `backend/static/` | Default — no `STATIC_UI_VERSION` env var |
| v2 React app | `backend/static-v2/` | `STATIC_UI_VERSION=v2` |
| React source (never served) | `frontend/src/` | Never directly served |

**Known gap:** `vite.config.ts` builds to `backend/static-new/` (gitignored). `ui_gate.py`
serves from `backend/static-v2/`. Different paths. `npm run build` does NOT update the live UI.
See CURRENT.md issue #1. **AGENTS.md Protected Files describes the legacy (`backend/static/`) frontend.**
Those protections remain valid — legacy is still the default served UI.

## Safe Working Rules

- `py_compile` after every Python change | `pytest` before declaring done
- Stage only explicit paths: `git add backend/app/routes/X.py` not `git add *`
- Never remove backward-compat aliases: `output_rank_score`, `is_best_output`, `is_best_clip`
- Never edit `docs/review/**` | AI modules must never raise — always return `None` on failure

## Where to Read Next

`AGENTS.md` → `CURRENT.md` → `PROJECT_MAP.md` → `docs/ARCHITECTURE.md` →
`docs/RENDER_PIPELINE.md` → `docs/FRONTEND_CONTRACT_PACKET_V1.md`
