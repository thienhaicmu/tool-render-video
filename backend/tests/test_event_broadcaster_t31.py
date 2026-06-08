"""T3.1 EventBroadcaster regression guard — Audit 2026-06-08 (Batch A V8-C1).

The CRITICAL observability gap: pre-T3.1 the structured events from
`_emit_render_event` (~50 event types — render.plan.ai_emitted,
output_validation_warning, motion_crop_fallback, ...) were trapped
in JSONL log files. The FE only received DB-snapshot polling
(stage/status/progress), so live event detail was invisible.

T3.1 (commit will follow this test file) added `EventBroadcaster` to
render_events.py: a thread-safe pub/sub bus that bridges worker-thread
render events to the FastAPI event loop's WS handler. The WS handler
registers an asyncio.Queue per session; `_emit_render_event` pushes
to all subscribers of a job_id; the WS handler races the queue
against the existing DB-snapshot poll.

This file pins the broadcaster's contract:

1. **Basic register/push/unregister** — events arrive at subscribers
   in order; unregister removes the subscriber so subsequent pushes
   are no-ops.

2. **Subscription cap** — `MAX_SUBSCRIBERS_PER_JOB` defends against
   subscriber-leak DoS. Excess registrations return False without
   appending.

3. **Backpressure (drop-oldest)** — when a subscriber queue fills,
   the oldest queued event is dropped so the freshest events still
   arrive. The drop is counted via `dropped_count`.

4. **Cross-thread safety** — push from a worker thread enqueues to
   the WS event loop via `loop.call_soon_threadsafe`. This is the
   bridge that closes V8-C1.

5. **Sacred Contract #3 safety** — push NEVER raises, even when the
   loop is closed or the queue surface mutates concurrently.

6. **Integration with `_emit_render_event`** — emitting a render
   event triggers a broadcaster.push for any registered subscriber.
"""
from __future__ import annotations

import asyncio
import threading

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_broadcaster():
    """Provide a clean EventBroadcaster instance per test so state doesn't
    leak across tests. The module-level EVENT_BROADCASTER is the
    singleton used in production; here we test the class directly so
    tests don't interfere with each other."""
    from app.features.render.engine.pipeline.render_events import EventBroadcaster
    return EventBroadcaster()


@pytest.fixture
def event_loop_thread():
    """Spin a dedicated asyncio loop on a background thread. The render
    pipeline pushes from worker threads to a FastAPI event loop; this
    fixture simulates that topology: the test thread acts as the worker
    (calls push); the loop on the background thread acts as the WS
    handler (drains queues)."""
    loop = asyncio.new_event_loop()
    stop_event = threading.Event()

    def _run_forever():
        asyncio.set_event_loop(loop)
        try:
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_run_forever, daemon=True)
    t.start()
    # Yield a small handle to the test.
    yield loop
    # Cleanup: schedule loop stop on the loop's own thread, then join.
    try:
        loop.call_soon_threadsafe(loop.stop)
    except Exception:
        pass
    t.join(timeout=2)


def _run_on_loop(loop: asyncio.AbstractEventLoop, coro_factory):
    """Run a coroutine on the given loop and block for its result."""
    future = asyncio.run_coroutine_threadsafe(coro_factory(), loop)
    return future.result(timeout=2)


# ---------------------------------------------------------------------------
# 1. Basic register / push / unregister.
# ---------------------------------------------------------------------------


def test_register_push_unregister_basic_round_trip(fresh_broadcaster, event_loop_thread):
    """A registered subscriber receives pushed events in order; after
    unregister, subsequent pushes are no-ops (don't arrive)."""
    loop = event_loop_thread
    job_id = "job-rt"

    # Create the queue ON the WS event loop (mirrors the real handler).
    queue = _run_on_loop(loop, lambda: _create_queue(200))

    ok = fresh_broadcaster.register(job_id, queue, loop)
    assert ok is True

    # Push 3 events from the test thread; they cross to the loop via
    # call_soon_threadsafe.
    fresh_broadcaster.push(job_id, {"event": "first", "seq": 1})
    fresh_broadcaster.push(job_id, {"event": "second", "seq": 2})
    fresh_broadcaster.push(job_id, {"event": "third", "seq": 3})

    # Drain on the loop's thread.
    drained = _run_on_loop(loop, lambda: _drain_queue(queue, expected=3))

    assert [d["seq"] for d in drained] == [1, 2, 3]

    # Unregister; subsequent pushes are no-ops.
    fresh_broadcaster.unregister(job_id, queue)
    fresh_broadcaster.push(job_id, {"event": "after-unreg", "seq": 99})

    drained_after = _run_on_loop(loop, lambda: _drain_queue(queue, expected=0, timeout=0.2))
    assert drained_after == [], (
        f"Event was pushed to an UNregistered subscriber — broadcaster "
        f"is leaking refs. Got: {drained_after}"
    )


def test_push_to_unknown_job_id_is_silent_noop(fresh_broadcaster):
    """Pushing to a job_id with no subscribers must NOT raise and must
    NOT spend per-subscriber work. Pre-T3.1 most call sites had no
    listener; the no-subscriber path is the hot path."""
    fresh_broadcaster.push("never-registered", {"event": "nobody-listens"})
    # If we got here without raising, the contract holds.


# ---------------------------------------------------------------------------
# 2. Subscription cap.
# ---------------------------------------------------------------------------


def test_subscription_cap_refuses_overflow(fresh_broadcaster, event_loop_thread):
    """Registering more than MAX_SUBSCRIBERS_PER_JOB subscribers for the
    same job_id must return False and NOT append. Defends against a
    bad client opening many WS sessions on one job."""
    loop = event_loop_thread
    job_id = "job-cap"
    cap = fresh_broadcaster.MAX_SUBSCRIBERS_PER_JOB

    queues = [_run_on_loop(loop, lambda: _create_queue(10)) for _ in range(cap)]
    for q in queues:
        assert fresh_broadcaster.register(job_id, q, loop) is True

    # The (cap+1)-th must be refused.
    overflow_queue = _run_on_loop(loop, lambda: _create_queue(10))
    assert fresh_broadcaster.register(job_id, overflow_queue, loop) is False

    # Push one event; only the registered subscribers receive it.
    fresh_broadcaster.push(job_id, {"event": "to-all"})
    for q in queues:
        drained = _run_on_loop(loop, lambda q=q: _drain_queue(q, expected=1))
        assert len(drained) == 1
    # Overflow queue stays empty.
    drained_overflow = _run_on_loop(
        loop, lambda: _drain_queue(overflow_queue, expected=0, timeout=0.2),
    )
    assert drained_overflow == []


# ---------------------------------------------------------------------------
# 3. Backpressure (drop-oldest).
# ---------------------------------------------------------------------------


def test_backpressure_drops_oldest_when_queue_full(fresh_broadcaster, event_loop_thread):
    """When a subscriber queue fills, the broadcaster drops the OLDEST
    queued event and enqueues the newest. dropped_count tracks the
    cumulative drops so the operator can detect over-saturated FE."""
    loop = event_loop_thread
    job_id = "job-bp"

    # Tiny queue for easy overflow.
    queue = _run_on_loop(loop, lambda: _create_queue(3))
    fresh_broadcaster.register(job_id, queue, loop)

    # Push 5 events into a queue of size 3.
    for i in range(5):
        fresh_broadcaster.push(job_id, {"event": f"e{i}", "seq": i})

    # Allow call_soon_threadsafe to settle on the loop.
    _run_on_loop(loop, lambda: asyncio.sleep(0.1))

    drained = _run_on_loop(loop, lambda: _drain_queue(queue, expected=3))
    seqs = [d["seq"] for d in drained]

    # The newest 3 events MUST have arrived. The exact dropped seqs
    # depend on the order of call_soon_threadsafe dispatch vs. the
    # subsequent put_nowait — we tolerate any 3 of the 5 as long as
    # the newest (seq=4) survives.
    assert 4 in seqs, (
        f"Backpressure must preserve the NEWEST event (seq=4). "
        f"Drained seqs: {seqs}. The drop-oldest policy is the contract: "
        f"old events also persist to JSONL log files; new events on "
        f"the WS are the live signal."
    )
    assert fresh_broadcaster.dropped_count(job_id) >= 2, (
        f"5 pushes into queue(maxsize=3) must drop at least 2. "
        f"dropped_count: {fresh_broadcaster.dropped_count(job_id)}"
    )


# ---------------------------------------------------------------------------
# 4. Sacred Contract #3 safety — push never raises.
# ---------------------------------------------------------------------------


def test_push_does_not_raise_when_loop_is_closed(fresh_broadcaster):
    """If the WS loop closes between subscriber-list snapshot and
    call_soon dispatch, push must silently drop the event. A raise
    here would surface up the render pipeline and could crash an
    active render — Sacred Contract #3 spirit applies."""
    # Create an asyncio loop, register, then CLOSE the loop.
    closed_loop = asyncio.new_event_loop()
    queue = closed_loop.run_until_complete(_create_queue(10))
    fresh_broadcaster.register("job-closed", queue, closed_loop)
    closed_loop.close()

    # Push must NOT raise.
    fresh_broadcaster.push("job-closed", {"event": "to-dead-loop"})


# ---------------------------------------------------------------------------
# 5. Integration with _emit_render_event.
# ---------------------------------------------------------------------------


def test_emit_render_event_pushes_to_broadcaster(monkeypatch, tmp_path, event_loop_thread):
    """The module-level EVENT_BROADCASTER must receive an event when
    `_emit_render_event` fires for a registered job_id. This is the
    actual integration point — the broadcaster is plumbed into the
    end of _emit_render_event."""
    from app.features.render.engine.pipeline.render_events import (
        EVENT_BROADCASTER,
        _emit_render_event,
    )

    # Redirect log dirs so _emit_render_event doesn't try to write to
    # production paths.
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.render_events.CHANNELS_DIR",
        tmp_path / "channels",
    )
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.render_events.LOGS_DIR",
        tmp_path / "logs",
    )

    loop = event_loop_thread
    job_id = "integ-job"
    queue = _run_on_loop(loop, lambda: _create_queue(10))

    EVENT_BROADCASTER.register(job_id, queue, loop)
    try:
        _emit_render_event(
            channel_code="test-channel",
            job_id=job_id,
            event="render.test.integration",
            level="INFO",
            message="T3.1 integration smoke",
            step="render.test",
        )

        drained = _run_on_loop(loop, lambda: _drain_queue(queue, expected=1))
        assert len(drained) == 1, (
            f"_emit_render_event must push to EVENT_BROADCASTER but "
            f"queue drained {len(drained)} events. T3.1 wiring is "
            f"broken; events stay in JSONL only."
        )
        evt = drained[0]
        assert evt["event"] == "render.test.integration"
        assert evt["job_id"] == job_id
        assert evt["level"] == "INFO"
    finally:
        EVENT_BROADCASTER.unregister(job_id, queue)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _create_queue(maxsize: int) -> asyncio.Queue:
    """Helper to build a queue on the loop's thread (coroutine
    instantiation guarantees binding to the running loop)."""
    return asyncio.Queue(maxsize=maxsize)


async def _drain_queue(queue: asyncio.Queue, expected: int, timeout: float = 0.5) -> list:
    """Drain up to ``expected`` events from the queue. If 0 are
    expected, wait ``timeout`` to confirm none arrived."""
    results: list = []
    if expected == 0:
        # Give the loop a slot to dispatch any pending call_soon.
        await asyncio.sleep(timeout)
        while not queue.empty():
            try:
                results.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return results
    deadline = asyncio.get_event_loop().time() + timeout
    while len(results) < expected and asyncio.get_event_loop().time() < deadline:
        try:
            results.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.01)
    return results
