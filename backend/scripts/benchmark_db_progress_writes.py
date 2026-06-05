"""
DB progress-write benchmark — Sprint 7.7 pre-gate measurement tool.

Usage:
    python -m scripts.benchmark_db_progress_writes [--iterations 1000] [--warmup 100]
                                                   [--output bench_results.json]

Measures per-call latency of two SQLite connection patterns over a synthetic
workload representative of `update_job_progress`:

  * `_thread_conn()`  — current production for the render hot path
                        (thread-local persistent connection).
  * `db_conn()`        — proposed unification target
                        (context-manager, auto-commit/rollback per call).

Both call the same UPDATE statement against a temp DB initialised with WAL
mode + the project's standard PRAGMAs. Results printed as a console table
and written to JSON for archival.

Sprint 7.7 gate criteria (from docs/review/SPRINT_PLAN_2026-06-05.md):
  1. db_conn p95 latency < 5 ms
  2. db_conn total wall-time delta < 1 % vs _thread_conn

The interpretation block at the end of stdout flags PASS/FAIL against
those criteria, but the raw data is what should drive the Sprint 7.7
audit doc — copy the JSON into a SPRINT_7_7_BENCHMARK_<date>.md entry.

Methodology notes
-----------------
- Single thread, single connection per helper. Real production has parallel
  worker threads each with their own _thread_conn; the per-call cost
  measured here is the apples-to-apples comparison, NOT the multi-thread
  amplification effect.
- Warmup phase iterations are discarded — they pay first-connection-open
  cost which is amortised over a real render run.
- DB lives at $TMP/sprint_7_7_bench.db with WAL mode set via init_db().
- All statements commit synchronously (synchronous=NORMAL) so cost reflects
  what production sees, NOT in-memory journal-mode shortcuts.
- Stats reported in microseconds (us) — db writes on WAL-mode SSD are
  typically tens-to-hundreds of us.

Sprint 7.7 prep — see docs/review/SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md
for the full interpretation guide + ship-vs-defer decision matrix.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


# Allow running as `python -m scripts.benchmark_db_progress_writes` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force UTF-8 stdout so Windows cp1252 console doesn't crash on table glyphs
# the interpretation block uses (e.g. the `->` arrow recommended-line marker).
# Idempotent — Python ≥ 3.7 supports reconfigure on TextIOWrapper.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def _setup_temp_db() -> Path:
    """Create a temp dir + point APP_DATA_DIR at it BEFORE importing app.*.

    Must happen before any app.* import because core/config.py resolves
    APP_DATA_DIR at module load.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="sprint_7_7_bench_"))
    os.environ["APP_DATA_DIR"] = str(tmp_dir)
    # core/config.py builds CACHE_DIR / DATABASE_PATH from this. Pre-create
    # the data subdir so init_db's first connection has a place to land.
    (tmp_dir / "data").mkdir(parents=True, exist_ok=True)
    return tmp_dir


def _seed_one_job(jobs_repo_mod) -> str:
    """Insert one job that we can update repeatedly. Returns its job_id.

    upsert_job's `payload` arg goes through _json_dumps which only handles
    plain dicts (not Pydantic models). Pass an empty dict — payload content
    is irrelevant to the benchmark; only the UPDATE statement against the
    jobs row matters.
    """
    job_id = "sprint-7-7-bench-job"
    jobs_repo_mod.upsert_job(
        job_id=job_id,
        kind="render",
        channel_code="bench",
        status="rendering",
        stage="rendering_parallel",
        progress_percent=0,
        message="seed",
        payload={},
    )
    return job_id


def _bench_thread_conn(connection_mod, job_id: str, n: int, warmup: int) -> list[int]:
    """Run n+warmup writes via _thread_conn(). Returns per-call latency in ns."""
    sql = (
        "UPDATE jobs SET stage=?, progress_percent=?, message=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE job_id=?"
    )

    # Warmup: don't record.
    for i in range(warmup):
        conn = connection_mod._thread_conn()
        conn.execute(sql, ("rendering_parallel", i % 100, f"warmup-{i}", job_id))
        conn.commit()

    latencies_ns: list[int] = []
    for i in range(n):
        t0 = time.perf_counter_ns()
        conn = connection_mod._thread_conn()
        conn.execute(sql, ("rendering_parallel", i % 100, f"bench-{i}", job_id))
        conn.commit()
        t1 = time.perf_counter_ns()
        latencies_ns.append(t1 - t0)

    # Release thread-local connection so we don't leave it pinned.
    connection_mod.close_thread_conn()
    return latencies_ns


def _bench_db_conn(connection_mod, job_id: str, n: int, warmup: int) -> list[int]:
    """Run n+warmup writes via db_conn() ctxmgr. Returns per-call latency in ns."""
    sql = (
        "UPDATE jobs SET stage=?, progress_percent=?, message=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE job_id=?"
    )

    for i in range(warmup):
        with connection_mod.db_conn() as conn:
            conn.execute(sql, ("rendering_parallel", i % 100, f"warmup-{i}", job_id))
            conn.commit()

    latencies_ns: list[int] = []
    for i in range(n):
        t0 = time.perf_counter_ns()
        with connection_mod.db_conn() as conn:
            conn.execute(sql, ("rendering_parallel", i % 100, f"bench-{i}", job_id))
            conn.commit()
        t1 = time.perf_counter_ns()
        latencies_ns.append(t1 - t0)

    return latencies_ns


def _summarise(latencies_ns: list[int]) -> dict:
    """Per-helper stats in microseconds + throughput."""
    us = [v / 1000.0 for v in latencies_ns]
    us_sorted = sorted(us)
    n = len(us_sorted)
    total_sec = sum(us) / 1_000_000.0
    return {
        "iterations": n,
        "median_us": round(statistics.median(us_sorted), 2),
        "p95_us": round(us_sorted[int(n * 0.95)], 2),
        "p99_us": round(us_sorted[int(n * 0.99)], 2),
        "mean_us": round(statistics.mean(us), 2),
        "stdev_us": round(statistics.stdev(us), 2) if n > 1 else 0.0,
        "min_us": round(us_sorted[0], 2),
        "max_us": round(us_sorted[-1], 2),
        "total_sec": round(total_sec, 4),
        "throughput_per_sec": round(n / total_sec, 1) if total_sec > 0 else 0.0,
    }


def _print_table(results: dict[str, dict]) -> None:
    """Compact comparison table."""
    helpers = list(results.keys())
    fields = [
        ("median_us", "Median (us)"),
        ("p95_us", "p95 (us)"),
        ("p99_us", "p99 (us)"),
        ("mean_us", "Mean (us)"),
        ("stdev_us", "Stdev (us)"),
        ("min_us", "Min (us)"),
        ("max_us", "Max (us)"),
        ("throughput_per_sec", "Throughput (calls/sec)"),
    ]
    name_col = max(len(h) for h in helpers) + 2
    val_col = 16
    print()
    print(f"{'Helper':<{name_col}}" + "".join(f"{title:>{val_col}}" for _, title in fields))
    print("-" * (name_col + val_col * len(fields)))
    for helper in helpers:
        stats = results[helper]
        cells = "".join(f"{stats[key]:>{val_col}}" for key, _ in fields)
        print(f"{helper:<{name_col}}{cells}")
    print()


def _interpret(results: dict[str, dict]) -> dict:
    """Apply the two Sprint 7.7 pass criteria + emit human-readable verdict.

    NOTE: this is heuristic interpretation aid only. The Sprint 7.7 audit doc
    is what makes the actual ship-vs-defer decision based on multiple runs.
    """
    tc = results["_thread_conn"]
    dc = results["db_conn"]

    crit1_pass = dc["p95_us"] < 5000.0  # < 5ms
    delta_pct = ((dc["total_sec"] - tc["total_sec"]) / tc["total_sec"] * 100.0) if tc["total_sec"] > 0 else 0.0
    crit2_pass = delta_pct < 1.0
    overall_pass = crit1_pass and crit2_pass

    return {
        "criterion_1_db_conn_p95_under_5ms": {
            "pass": crit1_pass,
            "actual_p95_us": dc["p95_us"],
            "threshold_us": 5000.0,
        },
        "criterion_2_wall_time_delta_under_1pct": {
            "pass": crit2_pass,
            "actual_delta_pct": round(delta_pct, 2),
            "threshold_pct": 1.0,
        },
        "overall_pass": overall_pass,
        "recommendation": (
            "Both pass criteria met — Sprint 7.7 unification candidate."
            if overall_pass
            else "At least one criterion failed — Sprint 7.7 ship requires "
                 "batching strategy OR _thread_conn stays. See "
                 "docs/review/SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md for "
                 "the escalation matrix."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sprint 7.7 DB progress-write benchmark")
    parser.add_argument("--iterations", type=int, default=1000,
                        help="Measured iterations per helper (default: 1000)")
    parser.add_argument("--warmup", type=int, default=100,
                        help="Warmup iterations (discarded; default: 100)")
    parser.add_argument("--output", type=str, default="",
                        help="JSON output path (default: tmp dir)")
    args = parser.parse_args()

    if args.iterations < 100:
        print("--iterations must be ≥ 100 for stable percentile stats", file=sys.stderr)
        return 2

    tmp_dir = _setup_temp_db()
    print(f"Temp DB dir: {tmp_dir}")

    # Import app.* only AFTER setting APP_DATA_DIR.
    from app.db import connection as connection_mod  # noqa: E402
    from app.db import jobs_repo  # noqa: E402

    # init_db() builds schema + sets WAL on the per-thread connection.
    connection_mod.init_db()

    # Confirm WAL mode is on (Sprint 7.7 pre-condition).
    with connection_mod.db_conn() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode == "wal", f"Expected WAL, got {journal_mode!r}"

    job_id = _seed_one_job(jobs_repo)
    print(f"Seeded job_id={job_id}; running {args.iterations} iterations + {args.warmup} warmup per helper")

    print("\n[1/2] _thread_conn() ...", flush=True)
    thread_lat = _bench_thread_conn(connection_mod, job_id, args.iterations, args.warmup)

    print("[2/2] db_conn() ...", flush=True)
    db_lat = _bench_db_conn(connection_mod, job_id, args.iterations, args.warmup)

    results = {
        "_thread_conn": _summarise(thread_lat),
        "db_conn": _summarise(db_lat),
    }
    interp = _interpret(results)

    metadata = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_path": str(connection_mod.DATABASE_PATH),
        "wal_mode": True,
        "iterations": args.iterations,
        "warmup": args.warmup,
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "implementation": platform.python_implementation(),
    }

    full_report = {
        "metadata": metadata,
        "results": results,
        "interpretation": interp,
    }

    _print_table(results)

    # Print interpretation.
    print("Sprint 7.7 pass criteria:")
    c1 = interp["criterion_1_db_conn_p95_under_5ms"]
    c2 = interp["criterion_2_wall_time_delta_under_1pct"]
    print(f"  [{'PASS' if c1['pass'] else 'FAIL'}] db_conn p95 < 5 ms          "
          f"(actual: {c1['actual_p95_us']:.1f} us)")
    print(f"  [{'PASS' if c2['pass'] else 'FAIL'}] wall-time delta < 1 %       "
          f"(actual: {c2['actual_delta_pct']:+.2f} %)")
    print(f"\n  → {interp['recommendation']}")

    # Output JSON.
    out_path = Path(args.output) if args.output else (tmp_dir / "bench_results.json")
    out_path.write_text(json.dumps(full_report, indent=2), encoding="utf-8")
    print(f"\nFull JSON report: {out_path}")
    print(f"Copy this JSON into a future docs/review/SPRINT_7_7_BENCHMARK_<date>.md entry.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
