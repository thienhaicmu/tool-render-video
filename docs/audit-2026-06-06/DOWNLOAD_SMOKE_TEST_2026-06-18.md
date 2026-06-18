# Download Feature — Live Smoke Test + F11 fix — 2026-06-18

> Append-only record. Live end-to-end test of the download feature after the
> `DOWNLOAD_REVIEW_FIXES_2026-06-18` changes, using two real URLs supplied by
> the user. Surfaced one environment issue (stale yt-dlp pin) and one code
> bug (F11 — forced iOS client), both fixed here.

## Test matrix

| URL | platform | preview | download result |
|-----|----------|---------|-----------------|
| `youtube.com/watch?v=09qJl22qcDc` | youtube | ✅ heights [1440,1080,720,480,360] | ✅ 720p→720 (132 MB), best→1440 (580 MB) |
| `facebook.com/reel/1359680359390172` | facebook | ✅ 86 s, [1080,720] | ✅ 720p→720 (26 MB), best→1080 (38 MB) |

`detect_platform` / `is_allowed_url` classified both correctly.

## Validated fixes (from DOWNLOAD_REVIEW_FIXES)

- **F1 quality cap works on real downloads** — Facebook: `720p`→720 (26 MB)
  vs `best`→1080 (38 MB); YouTube: `720p`→720 vs `best`→1440. The selector
  is no longer a no-op.

## Issues found during the test

### ENV — stale `yt-dlp==2025.3.31` pin
Current YouTube extraction failed on every client with the pinned 2025.3.31
release ("Requested format is not available" / "no longer supported").
Upgrading to **yt-dlp 2026.6.9** restored extraction (default client →
full 1440p ladder). `requirements.txt` bumped to `yt-dlp==2026.6.9` with a
note to keep it current.

### F11 (CODE) — `engine.download_video` / `get_video_info` forced the iOS client for YouTube
- **File:** `engine/engine.py`
- **Defect:** Both functions did `opts.update(_IOS)` for YouTube
  (`player_client=["ios"]`). On current YouTube the iOS client returns
  "Requested format is not available", so the **live download path failed
  for every YouTube URL** even though the default client returns the full
  format ladder (and the robust `download_youtube` waterfall, which includes
  the default client, succeeded at 1080p).
- **Fix:** Removed the forced iOS override (and the now-unused `_IOS`
  constant). YouTube now uses yt-dlp's default client set, which already
  multi-tries web/tv/android/etc. Post-fix: live path downloads 720p and
  1440p correctly.

## Verification

- Full pytest after the F11 edit: **1403 passed, 0 failed**.
- `py_compile` clean on `engine.py`.
- Manual: both URLs download at the requested quality with correct height,
  file present on disk, correct `_<height>p` filename.

## Follow-ups (not done — flagged only)

- The live `engine.download_video` YouTube path is still single-shot (default
  client only). The robust `download_youtube` waterfall (multi-client +
  dynamic format probing + wall-clock) is more resilient but uses a different
  return/filename contract. Routing the download tab through it is a larger
  change deferred for a separate decision.
- yt-dlp needs periodic bumping; consider a looser constraint or a scheduled
  update check.
