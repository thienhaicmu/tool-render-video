# PRODUCT STATE — CLEANUP-UPLOAD-AUTH1: Remove Deprecated Login Auth Runtime

**Branch:** `feature/ai-output-upgrade`
**Commit:** `refactor(upload): remove deprecated login auth runtime`
**Status:** Shipped

---

## Summary

The upload account login-check detection system is fully removed from runtime,
polling, API, and UI. The `405 Method Not Allowed` console error caused by
legacy polling against `/api/upload/accounts/{id}/login-check` no longer
occurs.

---

## Root Cause

`autoDetectLoginState()` was registered on a 60-second `setInterval` in all
three frontend builds (static, static-v3, static-v4). It sent GET requests to
`/api/upload/accounts/{account_id}/login-check`, but the backend route only
accepted POST — producing `405 Method Not Allowed` on every tick.

Even a corrected method would have been wrong: the route spawned a headless
Playwright browser per account to verify the login session, a heavyweight
operation that should never run automatically in the background.

---

## What Was Removed

### Frontend — all three builds (static, static-v3, static-v4) `upload-manager.js`

| Removed | Type | Description |
|---------|------|-------------|
| `autoDetectLoginState()` | function | Background loop that hit `/login-check` every 60 s |
| `setInterval(autoDetectLoginState, 60000)` | timer | The 60-second interval registration |
| `checkUploadAccountLogin(accountId)` | function | Button-triggered login check via the accounts endpoint |
| `checkSelectedAccountLogin()` | function | Wrapper that forwarded to `checkUploadAccountLogin` |
| `__loginCheckHint` | variable | Global state that stored error hints from login-check failures |
| `_showLoginCheckHint()` | function | Setter for `__loginCheckHint` |
| Login-check hint block in `renderSimpleSummary` | UI | Conditional hint text shown when check failed |
| Login-check hint block in `renderWorkspaceContext` | UI | Full error panel shown on check failures |
| `loginBtn` / `qs('uwLoginCheckBtn')` binding | event handler | Workspace login-check button wiring |
| `qs('spCheckLogin').onclick` binding | event handler | Simple-panel login-check button wiring |
| "Check Login" button (health row) | UI | Button in account health panel |
| "Login" button (UAM card) | UI | Login button in account manager card |
| "Check Login" button (wizard login step) | UI | Button in creator wizard login step |

### Backend — `backend/app/routes/upload.py`

| Removed | Description |
|---------|-------------|
| `POST /accounts/{account_id}/login-check` (`check_upload_account_login_state`) | Headless Playwright login detection endpoint |

---

## What Was Preserved

| Preserved | Why |
|-----------|-----|
| `login_state` field in DB and account schema | Still displayed on account cards to show current persisted state |
| `login_state` display in account card UI | Shows badge (logged_in / unknown / expired) — reading only, not polling |
| `loginState` variable in account card rendering | Used for health badge colour and status text |
| `markAccountLoggedIn()` | Manual confirmation flow — still the correct user action |
| `openAccountProfile()` | Opens Playwright profile browser — unchanged |
| `POST /api/upload/login/check` route | Used by render-engine.js upload check flow — different endpoint, different scope |
| `check_login_with_persistent_profile()` in upload_engine.py | Still used by `/api/upload/login/check` |
| `_is_upload_logged_in()` in upload_engine.py | Used inside the upload execution flow to verify session before upload |
| `login_with_persistent_profile()` in upload_engine.py | Interactive login flow — unchanged |
| `last_login_check_at` DB column | Schema preserved; no migration needed |

---

## UI Flow After Removal

The manual login flow remains intact:

1. User opens Upload Accounts
2. Account card shows login state badge from stored DB value
3. User clicks **Open Profile** → Playwright browser opens
4. User logs in manually in the browser
5. User closes the browser, clicks **Mark Logged In** → updates `login_state` to `logged_in`
6. Upload proceeds

The "Check Login" button (which triggered headless browser verification) is no
longer present. The **Mark Logged In** button is the sole mechanism to set
`login_state = logged_in`.

---

## Workspace Context Messages Updated

| Location | Before | After |
|----------|--------|-------|
| `renderSimpleSummary` next step hint | "Open Profile, log in, then Check Login." | "Open Profile, log in, then Mark Logged In." |
| `renderWorkspaceContext` "not logged in" | "Not logged in → Click Open Profile → login → then Check Login" | "Not logged in → Click Open Profile, log in, then click Mark Logged In" |

---

## Runtime After Cleanup

| Metric | Before | After |
|--------|--------|-------|
| Network requests to `/login-check` | Every 60 s per account | Zero |
| Console `405` errors | Every 60 s | Zero |
| Background Playwright launches | Every 60 s (on check) | Zero |
| Hidden login-polling timers | 1 (`autoDetectLoginState`) | 0 |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/static/js/upload-manager.js` | Remove 13 items: function, interval, buttons, hint system |
| `backend/static-v3/js/upload-manager.js` | Same as above |
| `backend/static-v4/js/upload-manager.js` | Same as above |
| `backend/app/routes/upload.py` | Remove `POST /accounts/{id}/login-check` route |
| `docs/upload/PRODUCT_STATE_CLEANUP_UPLOAD_AUTH1.md` | This file |

---

## Manual QA Checklist

- [ ] DevTools network: search "login-check" → 0 requests at idle
- [ ] Console: no 405 errors after 60 s of idle
- [ ] Upload accounts list loads correctly
- [ ] Account card shows login state badge (logged_in / unknown / expired)
- [ ] Open Profile button works
- [ ] Mark Logged In button works and updates state
- [ ] Upload flow works end to end
- [ ] Render pipeline unaffected
- [ ] No backend errors in console during any of the above
