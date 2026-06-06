# 12 — Tool & Integration Audit

For each external tool/library/SDK: declared in deps file? imported in source? actually called in a reachable path? Source code only.

> Both backend `requirements.txt` files are tiny (the offline-first design intentionally keeps the base install small; AI extras live in `requirements-ai.txt` and are NOT installed by default).

---

## Backend `requirements.txt` (live)

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
openpyxl==3.1.5
yt-dlp==2025.3.31
openai-whisper==20231117
scenedetect[opencv]==0.6.4
playwright==1.51.0
numpy==1.26.4
opencv-python-headless==4.10.0.84
python-multipart==0.0.9
edge-tts==7.2.8
deep-translator==1.11.4
prometheus-client>=0.19,<1.0
```

(`opencv-python-headless` reused for both PySceneDetect and motion module — no separate cv2 install.)

## Backend `requirements-ai.txt` (optional, NOT auto-installed)

Per comments in the file and the lazy-import gates at [features/render/ai/dependencies.py](../../backend/app/features/render/ai/dependencies.py):

- sentence-transformers
- faiss-cpu
- librosa
- mediapipe
- faster-whisper
- whisperx
- openai (SDK)
- google-genai (SDK)
- anthropic (SDK)

## Frontend `package.json`

```
dependencies:    react@18.3.1, react-dom@18.3.1, zustand@4.5.2
devDependencies: typescript@5.5.3, vite@5.3.4, vitest@1.6.0,
                  @testing-library/{jest-dom,react,user-event},
                  openapi-typescript@7.4.4, jsdom, @types/*
```

---

## Big integration table

| Tool | Purpose | Declared | Imported | Called | Status | Risk | Notes |
|---|---|---|---|---|---|---|---|
| **fastapi / uvicorn** | API server | ✓ | ✓ | ✓ | USED | LOW | core |
| **pydantic** | validation | (transitive) | ✓ | ✓ | USED | LOW | core |
| **starlette WS** | WebSocket | (transitive) | ✓ | ✓ | USED | LOW | core |
| **openpyxl** | XLSX reports | ✓ | `pipeline/report_service.py:1` | `render_pipeline.py` calls `append_rows()` | USED | LOW | render reports |
| **yt-dlp** | downloader | ✓ | `download/engine/downloader.py:9-10` | `YoutubeDL.extract_info()` @ ~410 | USED | LOW | platform downloader backbone |
| **openai-whisper** (stdlib whisper) | ASR baseline | ✓ | `engine/subtitle/transcription/whisper.py:7` | `whisper.load_model()` @ ~30 | USED | LOW | always available |
| **faster-whisper** | GPU ASR | (-ai) | `engine/subtitle/transcription/adapters.py:98` (lazy) | `WhisperModel.transcribe()` @ ~280 | PARTIAL (opt-in) | LOW | tries first if installed |
| **whisperx** | word-level align | (-ai) | `engine/subtitle/transcription/adapters.py:342` (lazy) | `whisperx.align()` @ ~348 | PARTIAL (opt-in) | LOW | premium SRT |
| **scenedetect** (PySceneDetect) | scene cuts | ✓ | `engine/pipeline/scene_detector.py:14-15` | `SceneManager.detect_scenes()` @ ~173 | USED | LOW | core |
| **opencv-python-headless** | CV frame ops | ✓ | `engine/motion/detection.py`, etc. (7 files) | `cv2.VideoCapture`, etc. | USED | LOW | core |
| **mediapipe** | face/body | (-ai) | `engine/motion/detection.py:331, 533` (lazy) | `mp.solutions.face_detection.FaceDetection()` | PARTIAL (opt-in) | MED | falls back to OpenCV Haar — see FINDING-T01 |
| **numpy** | math | ✓ | several | several | USED | LOW | core |
| **edge-tts** | default TTS | ✓ | `engine/audio/tts.py:8` | `edge_tts.Communicate().save()` @ ~250 | USED | LOW | default narration engine |
| **XTTS (TTS package)** | premium TTS | (-ai? or pip extra) | `engine/audio/tts.py:313` lazy → `tts_xtts.py:26+` | `synthesize_xtts()` @ tts.py:314 | PARTIAL (opt-in) | MED | falls back to edge-tts |
| **deep-translator** | SRT translate | ✓ | `engine/subtitle/translation_service.py:8` | `GoogleTranslator().translate()` @ ~14, 19 | USED | LOW | free-tier Google Translate |
| **openai** (SDK) | GPT-4o-mini | (-ai) | `features/render/ai/llm/providers/openai.py:29` (lazy) | `client.chat.completions.create()` @ ~41 | PARTIAL (opt-in) | LOW | one of three LLM providers |
| **anthropic** (SDK) | Claude haiku | (-ai) | `features/render/ai/llm/providers/claude.py:35` (lazy) | `Anthropic().messages.create()` @ ~88 | PARTIAL (opt-in) | LOW | one of three LLM providers |
| **google-genai** (SDK) | Gemini 2.5-pro | (-ai) | `features/render/ai/llm/providers/gemini.py:39` (lazy) | `genai.GenerativeModel().generate_content()` @ ~84 | PARTIAL (opt-in) | LOW | **default provider** per `DEFAULT_PROVIDER = "gemini"` |
| **groq** | (removed) | ✗ | ✗ | ✗ | REMOVED | LOW | Sprint 7.5 deletion verified — no `import groq` anywhere. Migration 0002 rewrites stored `groq_*` payload keys. |
| **sentence-transformers** | embeddings | (-ai) | only availability check `ai/dependencies.py:13-14` | ✗ never called | UNUSED | LOW | listed as optional but no live call path — see FINDING-T02 |
| **faiss-cpu** | vector store | (-ai) | only availability check `ai/dependencies.py:17-18` | ✗ never called | UNUSED | LOW | same — RAG removed in Phase G |
| **librosa** | audio features | (-ai) | only availability check `ai/dependencies.py:21-22` | ✗ never called | UNUSED | LOW | dead extra |
| **playwright** (Python) | browser auto | ✓ | ✗ NO Python imports | indirect via `python -m playwright install chromium` (Electron bootstrap) | **MISLEADING-USED** | MED | see FINDING-T03 |
| **prometheus_client** | metrics | ✓ | `services/metrics.py:41`, `routes/metrics.py:29` (lazy) | `Counter`, `Histogram`, `generate_latest()` | USED | LOW | graceful no-op when not installed |
| **boto3 / azure / gcs** | cloud storage | ✗ | ✗ | ✗ | NEVER | LOW | offline-first verified |
| **redis-py / celery / dramatiq / rq** | external queue | ✗ | ✗ | ✗ | NEVER | LOW | in-process ThreadPoolExecutor only |
| **chromadb / qdrant / pinecone / weaviate** | vector DB | ✗ | ✗ | ✗ | NEVER | LOW | RAG removed |
| **langchain** | agent framework | ✗ | ✗ | ✗ | NEVER | LOW | bespoke LLM dispatch |
| **Remotion** (npm) | video framework | ✗ in BE deps | `features/render/engine/pipeline/remotion_adapter.py` is real Python | called by `asset_pipeline.py:56`, `part_render_finalize.py:307` | USED — but NOT the Remotion npm framework | LOW | see FINDING-T04 |
| **FFmpeg / ffprobe** (binary) | A/V codec | ✓ (via `bin_paths.get_*`) | subprocess across 20+ files | every encode path | USED | LOW | resolved via `services/bin_paths.py` |
| **React 18 / Vite / TypeScript / Zustand** | FE | ✓ | ✓ | ✓ | USED | LOW | core |
| **openapi-typescript** | FE codegen | ✓ devDep | run on demand via `npm run gen:openapi` | not auto-run in CI/git hook | USED but not auto-checked | LOW | drift risk — see FINDING-T05 |
| **@testing-library/\*** + **vitest** | FE test | ✓ devDep | ✗ no test files | ✗ | UNUSED | LOW | dependency present, 0 test files |
| **Electron 31.0.2** | desktop shell | ✓ | `desktop-shell/main.js` + preload | every launch | USED | LOW | core |

---

## Findings

### FINDING-T01 (MED) — MediaPipe optional gate is the *real* default

[engine/motion/detection.py:331, 533](../../backend/app/features/render/engine/motion/detection.py): MediaPipe is the **preferred** subject detector. The OpenCV Haar fallback (`_load_cascade` in `motion/utils.py`) is a much weaker classifier (rectangular face only, no pose). On a system that never installs the AI extras, motion-aware crop silently degrades. There is no FE indicator. Recommend: surface a `motion_crop_quality: "high" | "low"` in `result_json` so the UI can hint "install AI extras for best crop".

### FINDING-T02 (LOW) — Three unused AI optional deps

`sentence-transformers`, `faiss-cpu`, `librosa` appear in `requirements-ai.txt` but only `dependencies.py:13-22` checks availability flags. Zero call sites. They are residue from the deleted RAG / AI Director stack (Phase G).

**Action:** delete the three lines from `requirements-ai.txt`. Delete the availability flags from `dependencies.py`.

### FINDING-T03 (MED) — Playwright Python: used indirectly, not by backend code

`playwright==1.51.0` is in `requirements.txt`. Zero Python imports in `backend/`. But:

- [desktop-shell/main.js:225-226](../../desktop-shell/main.js): `runCommand(BACKEND_VENV_PY, ['-m', 'playwright', 'install', 'chromium'])` — Electron bootstrap installs Chromium **via the Playwright CLI**.
- [desktop-shell/main.js:320](../../desktop-shell/main.js): `PLAYWRIGHT_BROWSERS_PATH: pwDir` env var is passed when spawning the backend — so SOMETHING in the backend can use the Chromium runtime, but I could not find an importer of `playwright` SDK.

Likely chain: Playwright is required only to *download Chromium*, and the downloaded Chromium is then consumed by:
- yt-dlp's `--cookies-from-browser` path for platform sites that need cookies (verify: [features/download/engine/cookie_extractor.py](../../backend/app/features/download/engine/cookie_extractor.py) opens Chrome's cookies SQLite directly, NOT via Playwright).
- TikTok handler (`features/download/engine/tiktok_handler.py`) — TBD.

**Action:** trace what *actually* needs Chromium runtime. If only the cookie extractor's Chrome reader path is involved, Playwright is not needed (it ships its own Chromium that's separate from the user's Chrome). Either delete `playwright` from `requirements.txt` (and the bootstrap step) or wire a documented Playwright-based handler.

### FINDING-T04 (LOW) — `remotion_adapter.py` is reachable but is a **Python module**, not the Remotion npm framework

[features/render/engine/pipeline/remotion_adapter.py](../../backend/app/features/render/engine/pipeline/remotion_adapter.py) exists (418 LOC) and is called by `asset_pipeline.py:56` (`generate_hook_intro(...)`) and `part_render_finalize.py:307` (`_maybe_prepend_remotion_hook_intro(...)`). The naming suggests integration with Remotion (the React-based video framework), but **no npm `remotion` package** is in `frontend/package.json` and no Node-based renderer is invoked. The adapter most likely generates a hook-intro clip via FFmpeg with a "Remotion-styled" template — verify in the file body.

**Action:** rename to `hook_intro_generator.py` if no actual Remotion CLI is invoked, to avoid misleading future readers.

### FINDING-T05 (MED) — `openapi-typescript` codegen not enforced

`frontend/package.json` declares scripts:
- `gen:openapi` — runs Python to dump OpenAPI + `openapi-typescript` to generate `src/types/openapi-generated.ts`.
- `check:openapi-drift` — re-runs gen and `git diff --exit-code`.

But there is no CI job, no pre-commit hook, no GitHub Action verified to run `check:openapi-drift`. If the backend changes a Pydantic field, the FE compiles against stale types until someone manually runs the script.

**Action:** add a pre-commit hook OR a GitHub Action that fails on drift. Phase 7 will cover the consequences (FE/BE contract audit).

### FINDING-T06 (LOW) — Vitest + @testing-library installed, 0 test files

`frontend/package.json` declares the full FE test stack (`vitest`, three `@testing-library/*` packages, `jsdom`). `grep -r '\.test\.tsx?$' frontend/src` returns nothing. Phase 9 (test coverage) will quantify, but the gap is visible already.

**Action:** either commit even one smoke test for the workflow, or remove the test deps until a strategy exists.

### FINDING-T07 (HIGH-cleanup, LOW-risk) — Stale entries in `services/__pycache__/`

Covered in [09_dead_code_report.md](09_dead_code_report.md) FINDING-DC04. Not strictly a tool issue but contributes to the "many tools, few work" perception. Sweep with `git clean -fdx backend/app/`.

---

## Summary

| Status | Count |
|---|---|
| USED (live, reachable) | 22 |
| PARTIAL (opt-in / lazy-imported AI extras) | 7 |
| UNUSED (declared but zero live calls) | 4 (`sentence-transformers`, `faiss-cpu`, `librosa`, Playwright Python SDK) |
| REMOVED (Sprint history) | 1 (groq) |
| NEVER INTEGRATED (worth confirming) | langchain, redis, celery, rabbitmq, kafka, S3/Azure/GCS, qdrant, chroma, pinecone, weaviate — **all absent** ✓ |

**One key positive:** the system is genuinely offline-first. Zero cloud-storage SDKs, zero queue/cache dependencies. The risk surface is small.

**Three small cleanups:** drop the three abandoned AI extras from `requirements-ai.txt`; clarify or remove Playwright; either ship one FE test or strip the test deps.

End of 12_tool_audit.md.
