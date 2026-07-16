"""Prometheus instrumentation registry.

Sprint 6.C — centralizes counter/histogram/gauge definitions so call sites
just `from app.services.metrics import RENDER_JOBS_TOTAL` and use them. A
single import surface keeps name + label drift from happening across the
codebase.

Falls back to no-op stubs if `prometheus_client` is missing (defensive —
the dep is in requirements.txt but the import-time guard lets the app
boot even on environments where the package failed to install). The
`/metrics` endpoint reports a 503 in that degraded mode.
"""
from __future__ import annotations

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
    )
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


# ── No-op fallback so call sites never need to guard on _AVAILABLE ───────────


class _NoOpMetric:
    """Drop-in shim for Counter/Histogram/Gauge when prometheus_client is missing."""

    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs):
        return None

    def dec(self, *args, **kwargs):
        return None

    def set(self, *args, **kwargs):
        return None

    def observe(self, *args, **kwargs):
        return None

    def time(self):
        return _NoOpTimer()


class _NoOpTimer:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def is_available() -> bool:
    """True iff prometheus_client is installed + metrics are real."""
    return _AVAILABLE


# ── Metric definitions ───────────────────────────────────────────────────────

if _AVAILABLE:
    # Dedicated registry — keeps our metrics separate from any other
    # prometheus_client-using lib in the process. Tests can introspect this
    # registry without touching the global default.
    REGISTRY = CollectorRegistry()

    RENDER_JOBS_TOTAL = Counter(
        "render_jobs_total",
        "Total number of render jobs by terminal status",
        ["status"],
        registry=REGISTRY,
    )
    # Buckets sized to typical render durations: 10s (preview) → 2h (long mixes)
    RENDER_JOB_DURATION = Histogram(
        "render_job_duration_seconds",
        "Wallclock time per render job from start to terminal",
        ["status"],
        buckets=(10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200),
        registry=REGISTRY,
    )

    FFMPEG_INVOCATIONS_TOTAL = Counter(
        "ffmpeg_invocations_total",
        "FFmpeg subprocess invocations by outcome",
        ["result"],
        registry=REGISTRY,
    )
    FFMPEG_DURATION = Histogram(
        "ffmpeg_duration_seconds",
        "Single FFmpeg invocation wallclock time",
        ["result"],
        buckets=(1, 5, 15, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    NVENC_ACQUIRE_WAIT = Histogram(
        "nvenc_acquire_wait_seconds",
        "Time spent blocked on NVENC_SEMAPHORE before acquiring",
        buckets=(0.01, 0.1, 0.5, 1, 5, 15, 60),
        registry=REGISTRY,
    )
    NVENC_ACTIVE_SESSIONS = Gauge(
        "nvenc_active_sessions",
        "Currently-held NVENC encoder sessions",
        registry=REGISTRY,
    )

    JOB_QUEUE_PENDING = Gauge(
        "job_queue_pending",
        "Jobs waiting in the priority queue",
        registry=REGISTRY,
    )
    JOB_QUEUE_ACTIVE = Gauge(
        "job_queue_active",
        "Jobs currently executing",
        registry=REGISTRY,
    )

    DB_BACKUPS_TOTAL = Counter(
        "db_backups_total",
        "Online SQLite backups taken by outcome",
        ["result"],
        registry=REGISTRY,
    )

    # Audit FINDING-DB09 / ST-15 closure (Batch 10A 2026-06-06).
    # Captures the wall-time spent opening + WAL-initing a SQLite connection
    # in the two production paths:
    #   - role="db_conn":      per-call open+PRAGMA inside the HTTP path ctxmgr
    #   - role="_thread_conn": first-call open+PRAGMA on render worker threads
    #                          (cache-hit reuse is NOT observed — it's ~free)
    # Bucket choices: WAL open is typically < 5 ms on a healthy WAL; long
    # tail observations indicate contention or fsync stalls.
    DB_CONN_ACQUIRE_WAIT = Histogram(
        "db_conn_acquire_seconds",
        "Time spent opening + initializing a SQLite connection",
        ["role"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 5),
        registry=REGISTRY,
    )

    LLM_RENDER_PLAN_CALLS = Counter(
        "llm_render_plan_calls_total",
        "LLM render plan calls by provider and outcome",
        ["provider", "status"],   # status: success | empty | error
        registry=REGISTRY,
    )
    LLM_RENDER_PLAN_LATENCY = Histogram(
        "llm_render_plan_seconds",
        "Latency of render plan LLM call per provider",
        ["provider"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
        registry=REGISTRY,
    )
    LLM_SEGMENTS_SELECTED = Counter(
        "llm_segments_selected_total",
        "Cumulative count of video segments (clips) selected by AI, per provider",
        ["provider"],
        registry=REGISTRY,
    )

    # F-07 (Story audit): the Story Mode super-plan LLM call was previously
    # invisible on /metrics (only the clip render-plan path was instrumented).
    # status ∈ {success, empty}; provider ∈ {openai, gemini, claude}.
    LLM_STORY_PLAN_CALLS = Counter(
        "llm_story_plan_calls_total",
        "Story Mode super-plan LLM calls by provider and outcome",
        ["provider", "status"],
        registry=REGISTRY,
    )
    LLM_STORY_PLAN_LATENCY = Histogram(
        "llm_story_plan_seconds",
        "Latency of the Story Mode super-plan LLM call per provider",
        ["provider"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 240),
        registry=REGISTRY,
    )
    # Phase 0 (Story cost review, 2026-07-16): BILLED tokens per planning stage
    # (understanding | writer | writer_repair | structure | structure_repair | …)
    # so "P90 cost per plan" is answerable from /metrics instead of estimates.
    # kind ∈ {input, output}. Fed by story_director_v2._observed_call via the
    # thread-local usage ledger (ai/llm/usage.py).
    LLM_STORY_TOKENS = Counter(
        "llm_story_tokens_total",
        "Billed LLM tokens for Story planning by provider, stage and direction",
        ["provider", "stage", "kind"],
        registry=REGISTRY,
    )

    # CM-1 (2026-07-07): Content Studio preview cost/abuse guard. The
    # /visual/preview + /narration/preview endpoints are unauthenticated
    # (loopback) and can trigger PAID provider calls (Imagen/Veo). Every call is
    # observable so runaway spend or abuse is visible on /metrics.
    # outcome ∈ {ok, rate_limited, budget_capped, paid_disabled, failed}.
    CONTENT_PREVIEW_TOTAL = Counter(
        "content_preview_total",
        "Content Studio preview calls by endpoint, provider and outcome",
        ["endpoint", "provider", "outcome"],
        registry=REGISTRY,
    )

    # R7 recap two-pass observability (2026-06-30 architecture review, Phase 1).
    # LLM_RECAP_PASS_CALLS — outcome of each recap pass (pass-1 story model
    # health + pass-2 scene selection). Label `phase` is story|recap (NOT `pass`
    # — that's a Python keyword and breaks .labels(**)). status: success|empty.
    LLM_RECAP_PASS_CALLS = Counter(
        "llm_recap_pass_calls_total",
        "Recap two-pass LLM calls by phase and outcome",
        ["phase", "status"],   # phase: story | recap ; status: success | empty
        registry=REGISTRY,
    )
    # LLM_RECAP_TWO_PASS_TOTAL — pass-2 outcome split by whether a pass-1 story
    # model was available, so the two-pass quality uplift is measurable directly.
    LLM_RECAP_TWO_PASS_TOTAL = Counter(
        "llm_recap_two_pass_total",
        "Recap selection outcome by whether a pass-1 story model was available",
        ["story_model", "status"],   # story_model: yes|no ; status: success|empty
        registry=REGISTRY,
    )

    # Architecture-review Batch A (2026-06-30): coarse-grained LLM cost
    # visibility per provider + task. Uses CHARS, not tokens — counting real
    # tokens requires touching every provider's response handler (HIGH-tier
    # files) and is deferred to Batch C, where the Comprehension stage hoist
    # naturally wraps the call site. Chars/4 ≈ tokens (Anthropic-stated rule
    # of thumb), so this is sufficient for budget dashboards while the
    # real-token instrumentation lands.
    #
    # task ∈ {render_plan, story, editorial, recap, rewrite}. Adding a new
    # LLM call elsewhere SHOULD register its own task label here so the
    # billing surface stays exhaustive.
    LLM_CALL_PROMPT_CHARS_TOTAL = Counter(
        "llm_call_prompt_chars_total",
        "Sum of system+user prompt characters sent to the LLM, by provider and task",
        ["provider", "task"],
        registry=REGISTRY,
    )
    LLM_CALL_RESPONSE_CHARS = Histogram(
        "llm_call_response_chars",
        "Distribution of raw LLM response character count, by provider and task",
        ["provider", "task"],
        buckets=(100, 500, 1000, 5000, 10000, 50000, 100000, 250000),
        registry=REGISTRY,
    )

    # AI rewrite (voice_source="ai_rewrite") — per-part LLM call that
    # rewrites the per-part transcript into TTS narration sized for the
    # clip duration. Mirrors LLM_RENDER_PLAN_* shape so dashboards can
    # render both calls side-by-side.
    LLM_REWRITE_CALLS = Counter(
        "llm_rewrite_calls_total",
        "LLM rewrite calls by provider and outcome",
        ["provider", "status"],   # status: success | empty
        registry=REGISTRY,
    )
    LLM_REWRITE_LATENCY = Histogram(
        "llm_rewrite_seconds",
        "Latency of rewrite LLM call per provider",
        ["provider"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
        registry=REGISTRY,
    )
    LLM_REWRITE_CHAR_DELTA = Histogram(
        "llm_rewrite_char_delta",
        "Char-count delta (rewritten - original) per provider, per part",
        ["provider"],
        buckets=(-2000, -1000, -500, -200, -50, 0, 50, 200, 500, 1000, 2000),
        registry=REGISTRY,
    )

    # ADR-007 (2026-06-27): observability for the cancel/Whisper-hang fix.
    # WHISPER_HANGS_TOTAL — incremented when run_with_hard_timeout fires
    # the TimeoutError path. Label `model` is the Whisper model name.
    WHISPER_HANGS_TOTAL = Counter(
        "whisper_hangs_total",
        "Whisper transcribe calls killed by the hard-timeout safety net",
        ["model"],
        registry=REGISTRY,
    )
    # CANCEL_SUBPROCESS_KILL_LATENCY — wall-clock from cancel_event.set()
    # to the moment process_render actually exits its run_render_pipeline
    # call. Measures effective cancel responsiveness. The job-level
    # Whisper wrap (run_with_hard_timeout) polls every 1s, so cancel
    # latency should land in [0.5, 2.5] under load. Outliers indicate
    # subprocess kill is not propagating.
    CANCEL_SUBPROCESS_KILL_LATENCY = Histogram(
        "cancel_subprocess_kill_latency_seconds",
        "Wall-clock delay between cancel signal and worker exit",
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
        registry=REGISTRY,
    )

    # Phase A — AI/Render boundary visibility.
    # Tracks how often the render engine overrides an empty or invalid AI
    # field with its own editorial fallback.  field label: the RenderPlan
    # field that was missing (e.g. "subtitle_style", "reframe_mode").
    RENDER_ENGINE_EDITORIAL_OVERRIDES = Counter(
        "render_engine_editorial_overrides_total",
        "Times the render engine used its own editorial fallback because AI left a field empty",
        ["field"],
        registry=REGISTRY,
    )

    # Perf-opt Phase 0 (2026-06-16) — baseline observability before any
    # render-pipeline optimisation work. Pure-additive; no behaviour change.

    # Per-stage timing. Lets the audit trace which stage dominates a job and
    # measure the delta after each phase of optimisation work.
    # Stage labels (canonical set):
    #   source_prep | whisper_full | llm_call | segment_seed | per_part_cut |
    #   per_part_assets | per_part_encode | per_part_audio | qa | ranking | finalize
    RENDER_STAGE_DURATION = Histogram(
        "render_stage_seconds",
        "Wallclock time per render pipeline stage",
        ["stage"],
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    # Cache hit/miss counters. The six cache types audited in the
    # 2026-06-16 perf report. outcome ∈ {hit, miss}.
    CACHE_LOOKUPS_TOTAL = Counter(
        "render_cache_lookups_total",
        "Cache lookups by cache type and outcome",
        ["cache", "outcome"],
        registry=REGISTRY,
    )

    # Whisper transcription timing (separate from FFMPEG_DURATION).
    # model ∈ {tiny, base, small, medium, large-v3, ...},
    # engine ∈ {openai, faster}.
    WHISPER_TRANSCRIBE_DURATION = Histogram(
        "whisper_transcribe_seconds",
        "Whisper transcription wallclock per call",
        ["model", "engine"],
        buckets=(1, 5, 10, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    # DB write counter by writer surface — used to verify Phase 2
    # progress-write coalescing.
    DB_WRITES_TOTAL = Counter(
        "render_db_writes_total",
        "DB write operations during a render",
        ["surface"],
        registry=REGISTRY,
    )

else:
    REGISTRY = None  # type: ignore[assignment]

    RENDER_JOBS_TOTAL = _NoOpMetric()         # type: ignore[assignment]
    RENDER_JOB_DURATION = _NoOpMetric()       # type: ignore[assignment]
    FFMPEG_INVOCATIONS_TOTAL = _NoOpMetric()  # type: ignore[assignment]
    FFMPEG_DURATION = _NoOpMetric()           # type: ignore[assignment]
    NVENC_ACQUIRE_WAIT = _NoOpMetric()        # type: ignore[assignment]
    NVENC_ACTIVE_SESSIONS = _NoOpMetric()     # type: ignore[assignment]
    JOB_QUEUE_PENDING = _NoOpMetric()         # type: ignore[assignment]
    JOB_QUEUE_ACTIVE = _NoOpMetric()          # type: ignore[assignment]
    DB_BACKUPS_TOTAL = _NoOpMetric()           # type: ignore[assignment]
    DB_CONN_ACQUIRE_WAIT = _NoOpMetric()      # type: ignore[assignment]
    LLM_RENDER_PLAN_CALLS = _NoOpMetric()     # type: ignore[assignment]
    LLM_RENDER_PLAN_LATENCY = _NoOpMetric()   # type: ignore[assignment]
    LLM_SEGMENTS_SELECTED = _NoOpMetric()     # type: ignore[assignment]
    LLM_STORY_PLAN_CALLS = _NoOpMetric()      # type: ignore[assignment]
    LLM_STORY_PLAN_LATENCY = _NoOpMetric()    # type: ignore[assignment]
    LLM_STORY_TOKENS = _NoOpMetric()          # type: ignore[assignment]
    LLM_RECAP_PASS_CALLS = _NoOpMetric()      # type: ignore[assignment]
    LLM_RECAP_TWO_PASS_TOTAL = _NoOpMetric()  # type: ignore[assignment]
    LLM_CALL_PROMPT_CHARS_TOTAL = _NoOpMetric()  # type: ignore[assignment]
    LLM_CALL_RESPONSE_CHARS = _NoOpMetric()      # type: ignore[assignment]
    LLM_REWRITE_CALLS = _NoOpMetric()         # type: ignore[assignment]
    LLM_REWRITE_LATENCY = _NoOpMetric()       # type: ignore[assignment]
    LLM_REWRITE_CHAR_DELTA = _NoOpMetric()    # type: ignore[assignment]
    WHISPER_HANGS_TOTAL = _NoOpMetric()       # type: ignore[assignment]
    CANCEL_SUBPROCESS_KILL_LATENCY = _NoOpMetric()  # type: ignore[assignment]
    RENDER_ENGINE_EDITORIAL_OVERRIDES = _NoOpMetric()  # type: ignore[assignment]
    RENDER_STAGE_DURATION = _NoOpMetric()      # type: ignore[assignment]
    CACHE_LOOKUPS_TOTAL = _NoOpMetric()        # type: ignore[assignment]
    WHISPER_TRANSCRIBE_DURATION = _NoOpMetric()  # type: ignore[assignment]
    DB_WRITES_TOTAL = _NoOpMetric()            # type: ignore[assignment]
    CONTENT_PREVIEW_TOTAL = _NoOpMetric()      # type: ignore[assignment]


# ── Shared cache-instrumentation decorator ───────────────────────────────────

from functools import wraps as _wraps


def instrument_cache(cache_label: str):
    """Decorator: emit render_cache_lookups_total{cache, outcome} on every call.

    Pure observation — never alters the wrapped function's return value or
    raises. ``outcome`` is ``hit`` when the result is not None, else ``miss``.
    The counter inc is wrapped in its own try/except so a misbehaving metric
    backend never breaks the cache path. Single definition shared by every
    cache module (motion/cache.py, pipeline/pipeline_cache.py) so the metric
    contract can't drift between copies.
    """
    def decorator(fn):
        @_wraps(fn)
        def wrapped(*args, **kwargs):
            result = fn(*args, **kwargs)
            try:
                outcome = "hit" if result is not None else "miss"
                CACHE_LOOKUPS_TOTAL.labels(cache=cache_label, outcome=outcome).inc()
            except Exception:
                pass
            return result
        return wrapped
    return decorator
