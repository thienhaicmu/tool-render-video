# Clear-History feature + yt-dlp auto-update — 2026-06-18

> Append-only record. Two user-requested additions plus a one-off data reset.

## 1. yt-dlp always-latest

YouTube breaks older yt-dlp releases (see `DOWNLOAD_SMOKE_TEST_2026-06-18`,
the 2025.3.31 pin failed extraction). To stop this recurring:

- `requirements.txt`: yt-dlp is now **unpinned** — fresh installs get the
  newest release.
- New `app/features/download/engine/auto_update.py`:
  `maybe_update_ytdlp()` runs `pip install -U yt-dlp` in the background.
  - Throttled to once / 12 h via a marker file (`APP_DATA_DIR/.ytdlp_update_check`).
  - Disable with `YTDLP_AUTO_UPDATE=0`.
  - Never blocks startup, never raises; the upgrade takes effect on the
    next process start.
- `main.py` startup launches it on a daemon thread (alongside the existing
  whisper/cookie warmups).

## 2. Clear-history / reset feature

- New `app/db/history_repo.py` → `clear_history(preserve_active=True)`:
  one transaction deleting `jobs, job_parts, download_jobs, assets,
  clip_feedback, render_ab_scores, platform_metrics`. **Never** touches
  `schema_versions, creator_prefs, creator_prefs_channel, render_presets`.
  - `preserve_active=True` (default) keeps `running`/`queued` render jobs
    (and their parts) and `queued`/`downloading` downloads so a live job is
    never orphaned — Sacred Contract #7.
  - Uses `DELETE FROM` via `db_conn` (additive-only; no DROP/TRUNCATE, WAL
    untouched). Skips tables absent from a given DB. Never raises.
- New `app/services/maintenance.py:clear_all_cache(cache_dir)` — wipes all
  render-cache files (any age), skips `.tmp` sidecars (atomic-write safe).
- New endpoint `POST /api/settings/clear-history`
  (`{clear_cache?: bool, preserve_active?: bool}`) → per-table delete counts
  (+ cache stats when `clear_cache`).
- Tests: `tests/test_clear_history.py` (4) — wipe, preserve-active,
  settings/presets preserved, never-raises.

## 3. One-off reset performed (this session)

The local `data/app.db` was reset to "factory" history state at the user's
request:
- **Backup first:** `VACUUM INTO data/app.db.backup-20260618_101831`
  (4068 KB, consistent snapshot incl. WAL). The DB file itself is never
  deleted (Contract #7).
- `clear_history(preserve_active=False)` → 612 rows removed (224 jobs,
  356 job_parts, 14 download_jobs, 17 render_ab_scores, 1 clip_feedback).
- `clear_all_cache` → 27 cache files removed.
- Preserved: `creator_prefs` (1), `render_presets` (5), `schema_versions`
  (11).

## Verification

- Full pytest: **1407 passed, 0 failed** (1403 + 4 new).
- `py_compile` clean; the new subprocess call carries `encoding="utf-8"`
  (enforced by `test_unicode_encoding`).
- Manual: reset verified all history tables at 0, settings/presets intact.
