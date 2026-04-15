# QA Thinking Wall

## 1) System Overview
- Tool type: local AI video production + browser automation platform.
- Primary operator: single developer/operator managing channels, render jobs, and uploads.
- Real workflow:
  1. Create/select channel + account profile
  2. Configure browser/proxy/settings
  3. Login and persist session
  4. Download/process/render media
  5. Upload/schedule posts
  6. Monitor logs/jobs and recover failures

## 2) Current Feature Inventory

### Video Pipeline
- YouTube download with fallback: `implemented`
- Local source processing: `implemented`
- Optional intro black trim: `implemented`
- Batch render orchestration: `implemented`

### Browser/Profile
- Per-account browser profile isolation: `implemented`
- Portable browser bootstrap/discovery: `implemented`
- Profile recovery path when locked: `implemented`

### Login/Auth
- Login check with persistent profile: `implemented`
- Login autofill + manual OTP/captcha completion: `implemented`

### Proxy
- Proxy config persisted in channel settings/profile: `implemented`
- Proxy applied at browser launch: `implemented`

### Upload/Scheduling
- Upload navigation and file selection: `implemented`
- Upload start/outcome detection: `implemented`
- Scheduled slot planning and run tracking: `implemented`

### Diagnostics/Devtools
- Job logs and cleanup: `implemented`
- Dev commands (`/run`, `/test`, `/error`, `/fix`, `/status`, `/commit`, `/features`): `implemented`

## 3) Stability Map
- Stable:
  - SQLite job persistence
  - Channel/profile/settings storage
  - Core render orchestration API
- Usable but risky:
  - Browser automation selectors (UI drift risk)
  - Login/upload outcome detection (external UI dependency)
  - Portable runtime bootstrap (environment/file layout dependency)
- External fragility:
  - YouTube format availability and anti-bot constraints
  - TikTok login/upload UI changes and challenge flows
  - Proxy quality and availability

## 4) Workflow Map
- Profile setup: channel + account profile + browser preference
- Login: launch persistent profile, authenticate, verify session
- Proxy setup: save settings, apply on launch
- Render/download: source fetch + processing + output persistence
- Upload: open upload page, select file, submit, detect outcome
- Schedule: compute slots, queue runs, track progress/state
- Monitor: logs, job status, error extraction and targeted fixes

## 5) Pain Points / Blockers
- Selector brittleness when target UI changes
- Partial dependence on fixed sleeps in some browser paths
- External services prevent full deterministic CI-level end-to-end tests
- Error context can span multiple logs/paths and be noisy
- Runtime environment differences (permissions, portable binaries) cause startup/bootstrap failures

## 6) Roadmap Suggestions

### Immediate
- Keep selector fallback list updated from production incidents
- Tighten upload/login readiness checks and challenge detection
- Expand `/test` checks for regressions in critical APIs

### Short Term
- Add lightweight deterministic UI mock harness for upload/login states
- Add structured error taxonomy tags in logs for better `/error` signal
- Add regression snapshots for core request/response contracts

### Medium Term
- Introduce dedicated QA profile channels and fixture datasets
- Add scheduled QA runs with trend reporting (pass/fail by subsystem)
- Split browser automation selector packs from core logic for easier updates

## 7) QA Strategy
- Auto-test (high priority):
  - API validation and negative paths
  - File/path/writability checks
  - Profile/proxy config persistence and mapping
  - Upload preconditions and outcome state detection
- Manual validation required:
  - Real login (captcha/OTP)
  - Real upload completion on target platform
  - Proxy/network behavior under real conditions
- Monitor continuously:
  - Latest error category trends
  - Upload failure reasons by selector/state
  - Portable bootstrap and profile launch failures
