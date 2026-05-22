# AI_PIPELINE_REVIEW.md — AI Pipeline Review

## AI Flow Overview

```
render_pipeline.py
  ↓ create_ai_edit_plan(request, context)       ← ai/director/ai_director.py
      ↓ get_mode_config(mode)                   ← ai/config/ai_modes.py
      ↓ normalize_transcript_chunks(...)        ← ai/analyzers/transcript_analyzer.py
      ↓ select_ai_segments(...)                 ← ai/director/clip_selector.py
      ↓ plan_camera_behavior(...)               ← ai/director/camera_planner.py
      ↓ plan_subtitle_behavior(...)             ← ai/director/subtitle_planner.py
      ↓ [optional] apply_creator_dna(...)       ← ai/creator_dna/dna_engine.py
      ↓ [optional] _retry_evaluate(...)         ← ai/analyzers/retry_analyzer.py
      ↓ [optional] _packaging_plan(...)         ← ai/packaging/clip_packaging_planner.py
      ↓ [optional] _retention_predict(...)      ← ai/analyzers/retention_predictor.py
      ↓ [optional] _cover_plan(...)             ← ai/thumbnail/cover_hint_planner.py
      ↓ [optional] _platform_adapt(...)         ← ai/platform/platform_adapter.py
      ↓ [optional] _debug_aggregate(...)        ← ai/debug/clip_debug_aggregator.py
      ↓ Returns: AIEditPlan (or None on any failure)
```

The AI edit plan is consumed selectively by `render_pipeline.py`:
- Camera plan → motion crop parameters
- Subtitle plan → subtitle style overrides
- Clip hints → segment selection influence
- Cover hint ratio → thumbnail frame selection
- Beat/pacing → playback speed nudges

---

## Provider Usage

**No external AI provider is called anywhere in the AI pipeline.**

The entire AI subsystem is local and heuristic. There are no calls to OpenAI, Anthropic, Ollama, or any LLM API. Despite having 60+ AI modules with names like `ai_director`, `strategy_planner`, `dna_engine`, `fusion_engine`, all intelligence is implemented as:

1. **Rule-based heuristics** — weighted scoring formulas, threshold comparisons, lookup tables
2. **Local embedding models** (optional) — sentence-transformers for RAG, only when installed
3. **Local Whisper** — speech transcription (not generative AI)
4. **JSON knowledge packs** — static domain knowledge loaded from `backend/knowledge/`

---

## Fake AI vs Real AI Analysis

### What Claims to be AI but is Heuristic

| Module | What it claims | What it actually does |
|--------|---------------|----------------------|
| `ai/director/ai_director.py` | "AI edit planning" | Calls heuristic analyzers, assembles a plan from rule-based functions |
| `ai/analyzers/hook_analyzer.py` | "Hook analysis" | Scores based on temporal position, scene density, word frequency patterns |
| `ai/analyzers/emotion_analyzer.py` | "Emotion analysis" | Simple keyword scoring on transcript text |
| `ai/analyzers/retention_predictor.py` | "Retention prediction" | Weighted combination of scene quality + hook scores |
| `ai/styles/style_classifier.py` | "Style classification" | Pattern matching on transcript content types |
| `ai/market/market_optimizer.py` | "Market optimization" | Lookup table with market-specific weight adjustments |
| `ai/creator_dna/dna_engine.py` | "Creator DNA" | Reads JSON creator profile from disk, applies preference overrides |
| `ai/orchestrator/render_orchestrator.py` | "AI orchestration" | Conflict resolution between plan components using priority rules |
| `ai/simulation/execution_simulator.py` | "Execution simulation" | Runs the same scoring formula with alternate parameters |
| `ai/mutations/mutation_engine.py` | "Safe render mutations" | Adjusts float parameters within defined safe ranges |
| `ai/multivariant/multivariant_planner.py` | "Multivariant AI planning" | Selects 3 segments by different score weightings (same as `_build_variant_segments`) |

### What is Genuinely Real (Local ML)

| Component | Technology | Status |
|-----------|-----------|--------|
| Whisper transcription | OpenAI Whisper (local) | **Real** — actual neural model |
| RAG embeddings | sentence-transformers (optional) | **Real** — but optional install, falls back to random vectors |
| FAISS vector search | FAISS (optional) | **Real** — but in-memory only, not persisted |
| TransNetV2 scene detection | TransNetV2 (optional) | **Real** — neural shot detector |
| MediaPipe face tracking | MediaPipe (optional) | **Real** — neural face landmark detection |
| DeepFilterNet audio | DeepFilterNet (optional) | **Real** — neural audio enhancement |
| XTTS voice | XTTS2 (optional) | **Real** — neural TTS |
| Viral scoring ML | sklearn Ridge (optional) | **Real** — but requires 30+ feedback records to activate |

### The Pattern

Every AI module follows the same pattern:
```python
try:
    from app.ai.dependencies import has_sentence_transformers
    _HAS_EMBEDDINGS = has_sentence_transformers()
except ImportError:
    _HAS_EMBEDDINGS = False
```

If the optional dependency is not installed, the module falls back to a stub/default return. This is architecturally sound for optional enhancement but means the system can present as "AI-powered" while running entirely on heuristics.

---

## Schema Validation

The AI subsystem has dedicated schema files for almost every module:
- `ai/clips/clip_batch_schema.py`, `clip_candidate_schema.py`, `clip_segment_schema.py`
- `ai/camera/camera_apply_schema.py`
- `ai/subtitles/subtitle_apply_schema.py`
- `ai/execution/execution_schema.py`
- etc.

**What these schemas are**: Python dataclasses or Pydantic-style classes that define the shape of AI plan components. They validate that the plan assembler produces well-formed outputs.

**What they don't do**: There is no validation that AI outputs are semantically sensible (e.g. a hook score of 50 for every clip is valid by schema but signals the analyzer produced no signal).

---

## RAG System

```
ai/rag/
├── vector_store.py     ← in-memory FAISS or cosine fallback
├── sqlite_store.py     ← SQLite-backed memory storage
├── memory_store.py     ← unified interface (combines vector + sqlite)
├── memory_writer.py    ← writes creator decisions to memory
├── retriever.py        ← retrieves similar memories
└── embeddings.py       ← sentence-transformers (optional)
```

**Strengths**:
- Graceful degradation: vector store falls back from FAISS to pure Python cosine similarity if FAISS not installed.
- SQLite persistence for memory — survives server restarts.
- Clean `LocalVectorStore` API.

**Weaknesses**:
- **No persistence for FAISS index**: Vector store is in-memory only. On every restart, all embeddings are lost. The SQLite store retains the text, but the FAISS index must be rebuilt. For large memory stores this is expensive.
- **Embedding dimension mismatch risk**: If sentence-transformers model changes (e.g. package upgrade from all-MiniLM-L6-v2 to a different model), the FAISS index silently stores vectors of wrong dimension alongside existing entries.
- **RAG not wired to main pipeline**: The RAG system exists and has test coverage, but in the actual `create_ai_edit_plan()` call, the `memory_store` context key is only populated if explicitly passed by the caller. `render_pipeline.py` does not pass a memory store to `create_ai_edit_plan()`. RAG retrieval is effectively inactive in production.

---

## Knowledge System

```
backend/knowledge/
├── camera/*.json           ← camera movement profiles
├── hooks/*.json            ← hook patterns by market/type
├── platforms/*.json        ← per-platform intelligence packs
├── subtitles/*.json        ← subtitle style knowledge
└── packs/*.json            ← combined knowledge packs
```

**What it does**: JSON files loaded by `knowledge_pack_loader.py`, retrieved via `knowledge_pack_retriever.py`, injected into the AI plan as context hints.

**Strengths**: Explicit, auditable, version-controlled domain knowledge. Adding a new platform or hook pattern is just adding a JSON file.

**Weaknesses**:
- Knowledge packs are loaded every render call (no module-level caching). For 20 JSON files this is fast but not free.
- No validation that JSON files conform to `knowledge_pack_schema.py` at load time — a malformed JSON silently falls back to empty dict.
- The knowledge influence on the actual render is indirect and small — it adds a few score points or overrides a subtitle style. The platform-specific fine-tuning is meaningful but not transformative.

---

## AI Output Quality Gates

`ai/quality_gate/quality_gate_engine.py` exists and is referenced in the AI plan assembly. It evaluates:
- Hook quality (hook_quality_evaluator.py)
- Camera quality (camera_quality_evaluator.py)
- Subtitle quality (subtitle_quality_evaluator.py)
- Unified quality (unified_quality_evaluator.py)

**Real check**: These evaluators apply rule-based scoring against the AI plan components (e.g. "does the camera plan have a defined motion mode?" "does the subtitle style have word limit set?").

**Not a real quality gate**: They do not inspect the rendered video output. They validate the plan structure, not the render result.

---

## Fallback Behavior

Every AI function is wrapped with `try/except Exception` at the `ai_director.py` level:
```python
try:
    plan = _build_plan(request, context, mode, job_id)
    ...
except Exception as exc:
    logger.warning("ai_director_failed job_id=%s: %s", job_id, exc)
    return None
```

Returning `None` causes `render_pipeline.py` to proceed without any AI influence. This is correct and safe. The render always completes even if all AI planning fails.

---

## Problems Summary

| Problem | File | Severity |
|---------|------|----------|
| RAG not connected to production pipeline | `render_pipeline.py` (missing memory_store kwarg) | High |
| FAISS index not persisted — lost on restart | `ai/rag/vector_store.py` | High |
| Heuristic systems mislabeled as AI throughout | All `ai/` modules | Medium (honest internally, misleading externally) |
| ML viral scorer never trained without manual intervention | `services/viral_scorer.py` | Medium |
| Knowledge packs loaded per-render without caching | `ai/knowledge/knowledge_pack_loader.py` | Low |
| Embedding dimension mismatch risk on model upgrade | `ai/rag/vector_store.py` | Low |
