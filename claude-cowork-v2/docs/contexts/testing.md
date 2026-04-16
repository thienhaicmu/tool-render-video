# Testing Context

## Philosophy

Test the behavior, not the implementation. Focus on:
1. Public API contracts (endpoints return correct shapes)
2. Pipeline stage outputs (given input X, output Y)
3. Edge cases explicitly named in task acceptance criteria
4. Failure recovery (job restart, partial artifacts)

## Test Structure

```
backend/tests/
├── conftest.py          # Shared fixtures: test DB, temp dirs, mock ffmpeg
├── test_render_route.py # /api/render/* endpoint tests
├── test_job_manager.py  # Queue submission, recovery, deduplication
├── test_downloader.py   # YouTube download with recorded cassettes
├── test_render_engine.py # Stage-by-stage render tests with fixture video
└── test_upload_engine.py # Upload flow with Playwright mocks
```

## Fixture Strategy

- Use a 5-second 480p fixture video (`tests/fixtures/sample.mp4`) for render tests
- Never make real network requests in CI — record/replay with `pytest-recording`
- Use an in-memory SQLite DB for unit tests; file-based for integration tests
- Mock ffmpeg with a pre-built binary that returns fixture data for scene detection

## What Must Be Tested

| Feature | Test Type |
|---------|-----------|
| `prepare_source` endpoint | Integration — full download mock + session creation |
| `process_render` endpoint | Integration — full pipeline with fixture video |
| Job recovery on restart | Integration — simulate interrupted job, restart server |
| NVENC → CPU fallback | Unit — mock NVENC failure, verify CPU is used |
| WebSocket progress stream | Integration — submit job, verify WS events match DB |
| Preview session expiry | Unit — mock time, verify session cleanup |

## CI Requirements

- All tests must pass before merge to `main`
- Coverage must be > 70% for `services/` modules
- Flaky tests must be fixed or quarantined (marked `@pytest.mark.flaky`)
- No test may take > 60 seconds individually
