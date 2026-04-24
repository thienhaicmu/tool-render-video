# Download System

Two independent download paths exist in the application:

1. **Render source download** — downloads a YouTube video as input to the render pipeline (`download_youtube()`)
2. **Download tab** — standalone batch downloader for saving public videos to disk (`download_public_video()`)

Both share the same proxy sanitization infrastructure. As of the latest patch, both also share the same multi-client YouTube retry strategy.

---

## Download tab — batch mode

Route: `POST /api/download/process`  
File: `backend/app/routes/download.py`

### Request

```json
{
  "urls": ["https://youtube.com/watch?v=...", "https://facebook.com/..."],
  "output_dir": "D:/Downloads/videos"
}
```

### Flow

```
POST /api/download/process
  ├─ _clean_urls() — deduplicate, strip whitespace
  ├─ _validate_url() — scheme check + detect_public_video_source()
  ├─ _resolve_output_dir() — mkdir parents
  ├─ upsert_job() — status: queued
  └─ submit_job(process_download_batch)
       └─ ThreadPoolExecutor (max 2 parallel)
            └─ _run_one(idx, url)
                 ├─ detect_public_video_source()
                 ├─ download_public_video(url, item_tmp_dir, progress_callback)
                 ├─ _unique_output_path() — avoid overwriting
                 └─ shutil.move(downloaded, final_path)
```

### Supported sources

| Source | Detection |
|---|---|
| YouTube | `youtube.com`, `youtu.be`, `m.youtube.com` |
| Facebook | `facebook.com`, `fb.watch`, `m.facebook.com` |
| Instagram | `instagram.com`, `instagr.am` |
| Unknown | → status `unsupported`, skip |

### Retry

`POST /api/download/retry/{job_id}`  
Body: `{"part_numbers": [2, 4]}` (empty = retry all failed)

Only parts with `status = "failed"` are re-attempted. Parts with `status = "done"` are preserved as-is.

### Per-item status values

| Status | Meaning |
|---|---|
| `waiting` | Queued, not yet started |
| `downloading` | Active download with progress |
| `done` | File saved to output_dir |
| `failed` | Error — user-friendly message stored |
| `unsupported` | URL did not match any known source |

---

## YouTube download — multi-client retry

File: `backend/app/services/downloader.py`  
Function: `download_youtube(url, temp_dir, context="render", progress_callback=None)`

### Problem

YouTube's player API requires a valid "client" token. Different clients (iOS app, Android app, TV browser) receive different format availability and different throttling behavior. A stale OS proxy entry (e.g. `127.0.0.1:9` from a stopped VPN) causes all requests to fail silently.

### Strategy

10 pre-defined attempts in order:

| Attempt | Client | Format |
|---|---|---|
| 1 | ios | `bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b` |
| 2 | ios | `bv*+ba/b` |
| 3 | android | `bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b` |
| 4 | android | `bv*+ba/b` |
| 5 | tv_embedded | `bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b` |
| 6 | tv_embedded | `bv*+ba/b` |
| 7 | auto | `bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b` |
| 8 | auto | `bv*+ba/b` |
| 9 | auto | `b[height<=1080]/b` |
| 10 | auto | `best` |

If all 10 fail with "Requested format is not available", a **dynamic fallback** runs:
- Probe available formats from each client (ios → android → tv_embedded → auto)
- Build concrete `format_id+format_id` pairs from actual stream list
- Retry up to 8 dynamic combinations

### Quality rejection

```python
if height and height < 480:
    raise RuntimeError(f"Got only {height}p - rejecting, trying next strategy")
```

Low-quality results are rejected so the next attempt can try for better.

### Structured logging

Every attempt logs structured events:

```
download.ytdlp.attempt  context=render attempt=1/10 client=ios format=... proxy_used=False
download.ytdlp.success  context=render attempt=1/10 client=ios format=... height=1080@60fps
download.ytdlp.failed   context=render attempt=2/10 client=ios format=... reason=...
download.failed_all_attempts  context=render proxy_used=... tried_formats=[...]
```

`context` is `"render"` when called from the render pipeline, `"download"` when called from the Download tab.

### File naming

- Render pipeline: `source.%(ext)s` → `source.mp4` (fixed name for pipeline stability)
- Download tab: after `download_youtube()` returns, the file is renamed to `{title-slug}.{ext}` for meaningful filenames

---

## Non-YouTube sources

Function: `download_public_video(url, temp_dir, progress_callback=None)`

For Facebook and Instagram, uses a single generic yt-dlp invocation:

```python
opts = {
    "outtmpl": "%(title).80s [%(id)s].%(ext)s",
    "format": "bv*+ba/b/best",
    "retries": 8,
    "proxy": proxy_val,
    ...
}
```

For YouTube URLs, `download_public_video()` now delegates to `download_youtube()` internally:

```python
if source == "youtube":
    yt = download_youtube(url, temp_dir, context="download", progress_callback=progress_callback)
    # rename source.* → {title-slug}.{ext}
    return adapted_result
```

This ensures the Download tab uses the same multi-client retry as the render pipeline.

---

## Proxy sanitization

Function: `_resolve_ytdlp_proxy(context)`

```python
# Priority order:
1. YTDLP_PROXY env var            → used as-is
2. HTTPS_PROXY / HTTP_PROXY / ALL_PROXY env vars → checked
3. urllib.request.getproxies()    → checked
4. Nothing → return ""            → explicit no-proxy
```

Bad hosts that trigger disable: `127.0.0.1`, `localhost`, `::1`, `0.0.0.0`

When a bad proxy is found:
- Log: `download.proxy.disabled context=... source=... proxy=... reason=bad_host`
- Return `""` (yt-dlp no-proxy mode)

The `"proxy": proxy_val` key is set in **all** yt-dlp option dicts, including health-check probes.

---

## Download health check

Route: `POST /api/render/download-health`  
Function: `check_youtube_download_health(url)`

Probes a YouTube URL without downloading, using the same client rotation (ios → android → tv_embedded → auto). Returns:

```json
{
  "ok": true,
  "client": "ios",
  "title": "Video Title",
  "best_height": 1080,
  "best_fps": 60,
  "video_stream_count": 12
}
```

Used by the editor to show "1080p available" before committing to render.

---

## Error messages (user-facing)

`_friendly_download_error(exc)` maps technical exceptions to readable messages:

| Internal pattern | User message |
|---|---|
| `unsupported link` / `invalid url` | Unsupported link |
| `private` / `unavailable` | Private or unavailable video |
| `login` / `sign in` / `cookies` | Login required |
| `proxy` / `player response` | Download failed. Check network/proxy settings. |
| `network` / `connection` / `timeout` | Download failed. Check network connection. |
| (other) | Download could not be completed |
