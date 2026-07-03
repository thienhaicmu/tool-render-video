# ADR — Content Studio Platform Fork (Wave 5 / CU-X)

> **Status: PROPOSED — decision document, NOT an implementation.**
> Author pass: 2026-07-03. This ADR is the deliverable for
> Wave 5 of [CONTENT_STUDIO_UPGRADE_PLAN.md](CONTENT_STUDIO_UPGRADE_PLAN.md).
> It exists BECAUSE CU-X ("distributed substrate") **contradicts the core
> architecture** of this application and therefore must not be coded on a
> whim. Nothing here changes runtime behaviour. Waves 1–4 shipped as
> additive, contract-safe evolution; Wave 5 is a *fork*, and a fork is a
> product decision, not a task.

---

## 1. Context

The app is, by explicit design (CLAUDE.md → *Architecture Philosophy*):

> Modular monolith with process-isolated workers. Single SQLite database as
> sole state store. In-process `ThreadPoolExecutor` for job queue. FFmpeg
> subprocess for render execution. **No Redis, no cloud, no external queue.**

Content Studio (Waves 1–4) added a provider seam, a multi-pass AI Director, a
cost/decision layer and parallel per-scene render — all **on top of** that
substrate, without violating a single Sacred Contract. Wave 5 asks a different
question: *what if a user needs 100-scene / 2-hour videos, 500 concurrent
projects, or multi-GPU render sharding?* That workload does not fit a
single-machine, single-SQLite, in-process design.

This ADR records: **what the current substrate is, what would have to change,
what carries across unchanged, when the fork is justified, and the recommended
decision.**

---

## 2. Current substrate (code-verified)

| Concern | Today | File |
|---|---|---|
| Job queue | Priority min-heap + one daemon scheduler thread → `ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)`. In-process only. | `backend/app/jobs/manager.py` |
| Job state | Single SQLite file, WAL mode, thread-local connection on the render hot path. Sole authority (Sacred Contract #7). | `backend/app/db/connection.py`, `data/app.db` |
| Recovery | On startup, DB rows left `queued`/`running` → `interrupted`; user resumes manually. In-memory holds/cancel evaporate on restart. | `manager.py:recover_pending_render_jobs` |
| Cancel / progress | In-memory cancel registry (evaporates on process death) + WebSocket/`GET /api/jobs/{id}` polling. | `backend/app/jobs/cancel.py`, `routes/jobs.py` |
| Asset store | Local filesystem under `APP_DATA_DIR/cache`, pruned by a periodic subdir-agnostic walker. Visual assets cached by `sha1(prompt,size,…)`. | `engine/visual/__init__.py`, `pipeline_cache.py` |
| GPU control | `NVENC_SEMAPHORE = Semaphore(3)` — a single **in-process** semaphore. Correct only because there is exactly one process per machine. | `encoder/ffmpeg_helpers.py` |

The single most important observation: **every coordination primitive above is
in-process.** The semaphore, the queue, the cancel registry, the thread-local
DB connection — all assume one Python process owns one machine. That assumption
is the app's greatest strength (zero ops, offline-first) and the exact thing a
distributed fork breaks.

---

## 3. What carries across the fork UNCHANGED

The good news, and the reason Waves 1–4 were worth doing regardless: the
*intelligence* layer is substrate-agnostic. It is pure data + pure functions.

| Layer | Why it ports cleanly |
|---|---|
| `engine.visual` provider seam | `resolve_scene_visual(request, provider=…)` is a pure dispatch over a dataclass request → asset. It has no knowledge of *where* it runs. A remote worker calls it identically. |
| `ContentPlan` / `StoryBible` (`domain/content_plan.py`) | Pure dataclasses with defensive `from_json`. Already the serialized wire/replay format (`content_plan_override`). A distributed queue ships the same JSON. |
| Provider Registry + Manifest (`engine/visual/registry.py`) | Capability metadata (`cost_tier`, `supports_seed`, `online`) is deployment-independent. |
| Decision Tree + BudgetTracker (`engine/visual/decision.py`) | Cost optimisation is a pure function of `(scene, budget)`. Runs the same on a laptop or a render farm. |
| Multi-pass AI Director (`ai/llm/…content…`) | LLM calls + parsers + validators. Stateless per call; already `return None` on failure (Sacred Contract #3). |

**Implication:** a fork replaces the *execution substrate* (Section 4), not the
Content Studio product. Roughly 80% of the Wave 1–4 investment survives.

---

## 4. What the fork must replace

| # | Substrate concern | Fork requirement | Breaks which contract |
|---|---|---|---|
| F1 | In-process queue (`manager.py`) | Durable distributed queue (e.g. Redis Streams / RabbitMQ / SQS) + separate worker processes. | *No external queue* philosophy. |
| F2 | Single SQLite (`app.db`) | Networked job-state store (Postgres) so N workers share state with real concurrent writers. | Sacred Contract #7 (sole SQLite authority); *Single SQLite* philosophy. |
| F3 | Local file cache | Object store (S3/MinIO) addressable by all workers; assets by content hash. | Offline-first default (needs opt-in). |
| F4 | In-process `NVENC_SEMAPHORE` | Per-GPU / per-node session accounting; a scheduler that shards scenes across GPUs/nodes. | Performance Protection (per-process semaphore no longer bounds a machine). |
| F5 | In-memory cancel + WS from one process | Distributed cancel (pub/sub) + progress fan-in from many workers to one client stream. | Frozen `_emit_render_event` shape must survive fan-in (Contract #6). |

None of F1–F5 is individually exotic; together they are a **different product**
with ops burden (a server to run, a DB to back up, a queue to monitor) that the
current offline-first desktop app deliberately does not have.

---

## 5. The seam strategy (how to keep the fork cheap)

The fork becomes *tractable* — instead of a rewrite — if two interfaces are
introduced **first**, with the current in-process implementation as the default:

```
JobQueue (protocol)
  submit(job_id, payload, priority) -> bool
  # default impl == today's manager.py (in-process ThreadPoolExecutor)
  # fork impl    == Redis/RabbitMQ producer + remote workers

AssetStore (protocol)
  put(key, bytes) -> uri ;  get(key) -> bytes|path ;  exists(key) -> bool
  # default impl == local filesystem cache (today)
  # fork impl    == S3/MinIO
```

Everything above the seam (Content Studio, provider layer, ContentPlan) never
learns which implementation is active. This is the **"seam abstraction
increment"** option — it can be built *inside* the offline-first app with zero
behaviour change (default impls are the current code), and it does NOT add
Redis/cloud. It merely makes a later fork a matter of writing a second
implementation, not surgery on `content_pipeline.py`.

> This increment is **out of scope for this ADR** (it is code + tests, HIGH-tier
> because it touches `manager.py`). It is recorded here as the recommended
> *first* step **if and when** the fork trigger fires.

---

## 6. When is the fork justified? (triggers)

Do **not** fork until at least one is durably true — not hypothetically:

- **Scale:** sustained demand for >1 render machine (multi-GPU sharding of a
  single long video, or many concurrent projects a single box can't keep up
  with).
- **Deployment:** the product moves from *offline-first desktop* to a *hosted
  service* (multi-tenant, always-on). The Docker image already sets
  `ALLOW_REMOTE=1` — a hosted deployment is the natural home for the fork.
- **Durability SLA:** job state must survive a machine loss (not just a process
  restart), which SQLite-on-one-disk cannot guarantee.

Absent a trigger, the fork is **negative value**: it adds ops cost, network
dependency and contract risk to a product whose selling point is "runs offline
on your machine, no cloud."

---

## 7. Options considered

| Option | Verdict |
|---|---|
| **A. Do nothing now; keep offline-first** | ✅ **Recommended.** No trigger is currently true. Waves 1–4 already delivered the AI differentiator. |
| **B. Seam abstraction increment** (Section 5), default = current impls | Recommended *first step* only when a trigger appears. Contract-safe, no cloud, makes the eventual fork cheap. |
| **C. Full distributed substrate now** (Redis + Postgres + S3 + multi-GPU) | ❌ Rejected now. Contradicts core philosophy + Sacred Contract #7; large ops burden; no demand. Only after B, under an approved CRITICAL-tier plan + full pytest, in a **separate deployment fork/branch** — never in the desktop line. |

---

## 8. Decision

**Adopt Option A (no substrate change now).** Keep the app offline-first,
single-SQLite, in-process. Record Option B (seam abstraction) as the sanctioned
*entry point* for a future fork and Option C as the eventual server-fork target
gated on a real trigger (Section 6).

Content Studio is, as of Wave 4, an **AI Video Production** feature on a
**single-machine substrate**. That is the correct shape for this product today.
The platform fork is a *deployment-model* decision for the user/product owner to
make when scale demands it — not an engineering task to execute pre-emptively.

---

## 9. Consequences

- **Positive:** zero new ops, no contract broken, offline-first intact. The AI
  layer (the differentiator) is already shipped and is fork-portable.
- **Deferred:** true horizontal scale, multi-GPU sharding, cross-machine
  durability. Acceptable — no current demand.
- **Follow-up when a trigger fires:** (1) build the `JobQueue` + `AssetStore`
  seams (Option B) inside the desktop app with default impls; (2) open a
  separate hosted-deployment fork implementing the remote impls + Postgres
  state store; (3) re-audit `NVENC_SEMAPHORE`, cancel transport and
  `_emit_render_event` fan-in against Contracts #4–#7 under an approved plan.

---

## 10. References

- [CONTENT_STUDIO_UPGRADE_PLAN.md](CONTENT_STUDIO_UPGRADE_PLAN.md) — Wave map (CU-1…CU-X)
- [ARCHITECTURE.md](ARCHITECTURE.md) — system call chain
- CLAUDE.md — Architecture Philosophy, Sacred Contracts #4/#6/#7, Performance Protections (NVENC)
- `backend/app/jobs/manager.py` — the in-process queue this ADR would fork
- `backend/app/features/render/engine/visual/` — the portable provider seam
