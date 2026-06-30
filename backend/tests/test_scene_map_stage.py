"""Architecture-review Batch D-2-thin (2026-06-30) — scene_map_stage contract.

Pins the behaviour of ``scene_map_stage.run_scene_map``:

  1. Kill switch (SCENE_MAP_ENABLED=0) returns None IMMEDIATELY without
     calling the detector or emitting events.
  2. Happy path — detector returns shots:
     - detector is called exactly once
     - cache_put is invoked with the raw detector output
     - persist is called with the SceneMap JSON blob
     - WS events fired: scene_map.start and scene_map.done (source="detect")
  3. Cache hit short-circuits the detector call.
  4. Detector returns empty / None → returns None, emits source="failed".
  5. Detector raising → returns None (Sacred Contract #3).
  6. Missing PySceneDetect dep auto-degrades with source="missing-dep".
  7. persist=False skips DB write but still emits events.
  8. emit_fn raising never breaks the stage.
"""
from __future__ import annotations

import pytest


def _good_shots() -> list:
    return [
        {"start": 0.0, "end": 5.0, "transition_score": 0.0},
        {"start": 5.0, "end": 12.5, "transition_score": 0.8},
        {"start": 12.5, "end": 30.0, "transition_score": 0.7},
    ]


def _collect_events():
    events: list[dict] = []

    def emit(**kwargs):
        events.append(kwargs)

    return events, emit


@pytest.fixture(autouse=True)
def _stage_env(monkeypatch):
    monkeypatch.setenv("SCENE_MAP_ENABLED", "1")
    yield


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_returns_none_without_calling_detector(monkeypatch):
    from app.features.render.engine.pipeline import scene_map_stage as stage
    monkeypatch.setenv("SCENE_MAP_ENABLED", "0")
    calls = {"n": 0}

    def fake_detect(video_path):
        calls["n"] += 1
        return _good_shots()

    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="j1", channel_code="vn", video_path="/tmp/v.mp4",
        emit_fn=emit,
        detect_scenes_fn=fake_detect,
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    assert result is None
    assert calls["n"] == 0
    assert events == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_calls_detector_caches_persists_and_emits():
    from app.features.render.engine.pipeline import scene_map_stage as stage
    detector_calls = []
    cache_puts = []
    persist_calls = []

    def fake_detect(video_path):
        detector_calls.append(video_path)
        return _good_shots()

    def fake_cache_put(p, shots):
        cache_puts.append((p, shots))

    def fake_persist(jid, blob):
        persist_calls.append((jid, blob))

    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="job-1", channel_code="vn",
        video_path="/tmp/movie.mp4",
        emit_fn=emit,
        detect_scenes_fn=fake_detect,
        cache_get_fn=lambda p: None,            # miss → forces detector
        cache_put_fn=fake_cache_put,
        update_scene_map_fn=fake_persist,
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    assert result is not None
    assert result.shot_count() == 3
    assert result.source_fps == 30.0
    assert result.total_duration_sec == 30.0

    # Detector invoked exactly once with the video_path.
    assert detector_calls == ["/tmp/movie.mp4"]

    # Cache put recorded the raw detector output.
    assert len(cache_puts) == 1 and cache_puts[0][0] == "/tmp/movie.mp4"
    assert cache_puts[0][1] == _good_shots()

    # Persistence recorded the SceneMap JSON blob.
    assert len(persist_calls) == 1
    jid, blob = persist_calls[0]
    assert jid == "job-1"
    import json
    data = json.loads(blob)
    assert data["schema_version"] == 1
    assert len(data["shots"]) == 3

    # WS events: scene_map.start → scene_map.done.
    event_names = [e["event"] for e in events]
    assert event_names == ["scene_map.start", "scene_map.done"]
    done = events[1]
    assert done["context"]["ok"] is True
    assert done["context"]["source"] == "detect"
    assert done["context"]["shot_count"] == 3


# ---------------------------------------------------------------------------
# Cache hit short-circuits the detector call
# ---------------------------------------------------------------------------


def test_cache_hit_skips_detector_and_emits_source_cache():
    from app.features.render.engine.pipeline import scene_map_stage as stage
    detector_calls = {"n": 0}

    def fake_detect(video_path):
        detector_calls["n"] += 1
        return _good_shots()

    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="j", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=emit,
        detect_scenes_fn=fake_detect,
        cache_get_fn=lambda p: _good_shots(),   # primed cache hit
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=lambda p: {"fps": 24.0, "duration": 30.0},
    )
    assert result is not None
    assert result.shot_count() == 3
    assert detector_calls["n"] == 0, "detector must NOT be invoked on cache hit"
    done = next(e for e in events if e["event"] == "scene_map.done")
    assert done["context"]["source"] == "cache"


# ---------------------------------------------------------------------------
# Detector failure modes
# ---------------------------------------------------------------------------


def test_detector_returns_none_returns_none_and_emits_failed():
    from app.features.render.engine.pipeline import scene_map_stage as stage
    persist_calls = []
    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="failing", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=emit,
        detect_scenes_fn=lambda p: None,
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: persist_calls.append((jid, blob)),
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    assert result is None
    assert persist_calls == []
    done = next(e for e in events if e["event"] == "scene_map.done")
    assert done["context"]["ok"] is False
    assert done["context"]["source"] == "failed"


def test_detector_returns_empty_returns_none():
    from app.features.render.engine.pipeline import scene_map_stage as stage
    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="empty", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=emit,
        detect_scenes_fn=lambda p: [],
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    assert result is None


def test_detector_raising_does_not_propagate():
    from app.features.render.engine.pipeline import scene_map_stage as stage

    def boom(p):
        raise RuntimeError("scenedetect exploded")

    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="boom", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=emit,
        detect_scenes_fn=boom,
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=lambda p: {},
    )
    assert result is None
    done = next(e for e in events if e["event"] == "scene_map.done")
    assert done["context"]["ok"] is False


# ---------------------------------------------------------------------------
# Missing PySceneDetect dep auto-degrades
# ---------------------------------------------------------------------------


def test_missing_dep_auto_degrades_with_source_missing_dep(monkeypatch):
    """When the venv lacks scenedetect, the late-import returns None and
    the stage emits a `missing-dep` event without raising."""
    from app.features.render.engine.pipeline import scene_map_stage as stage
    # Force the late-import path by NOT injecting detect_scenes_fn AND
    # making _try_import_detect_scenes return None.
    monkeypatch.setattr(stage, "_try_import_detect_scenes", lambda: None)
    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="dep-miss", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=emit,
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=lambda p: {},
    )
    assert result is None
    done = next(e for e in events if e["event"] == "scene_map.done")
    assert done["context"]["source"] == "missing-dep"
    assert done["context"]["ok"] is False


# ---------------------------------------------------------------------------
# persist=False (test mode)
# ---------------------------------------------------------------------------


def test_persist_false_skips_db_write_but_still_emits():
    from app.features.render.engine.pipeline import scene_map_stage as stage
    persist_calls = []
    events, emit = _collect_events()
    result = stage.run_scene_map(
        job_id="dry", channel_code="vn",
        video_path="/tmp/v.mp4",
        persist=False,
        emit_fn=emit,
        detect_scenes_fn=lambda p: _good_shots(),
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: persist_calls.append((jid, blob)),
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    assert result is not None
    assert persist_calls == []
    done = next(e for e in events if e["event"] == "scene_map.done")
    assert done["context"]["ok"] is True


# ---------------------------------------------------------------------------
# Defensive — callbacks that raise never break the stage
# ---------------------------------------------------------------------------


def test_emit_fn_raising_does_not_break_stage():
    from app.features.render.engine.pipeline import scene_map_stage as stage

    def boom_emit(**kw):
        raise RuntimeError("WS broken")

    result = stage.run_scene_map(
        job_id="x", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=boom_emit,
        detect_scenes_fn=lambda p: _good_shots(),
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    assert result is not None


def test_persist_helper_raising_does_not_break_stage():
    from app.features.render.engine.pipeline import scene_map_stage as stage

    def boom_persist(jid, blob):
        raise RuntimeError("DB locked")

    result = stage.run_scene_map(
        job_id="x", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=None,
        detect_scenes_fn=lambda p: _good_shots(),
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=boom_persist,
        probe_metadata_fn=lambda p: {"fps": 30.0, "duration": 30.0},
    )
    # Stage still returns the map; persistence failure is logged only.
    assert result is not None


def test_probe_metadata_failure_defaults_to_zero():
    from app.features.render.engine.pipeline import scene_map_stage as stage

    def boom_probe(p):
        raise RuntimeError("ffprobe missing")

    result = stage.run_scene_map(
        job_id="x", channel_code="vn",
        video_path="/tmp/v.mp4",
        emit_fn=None,
        detect_scenes_fn=lambda p: _good_shots(),
        cache_get_fn=lambda p: None,
        cache_put_fn=lambda p, s: None,
        update_scene_map_fn=lambda jid, blob: None,
        probe_metadata_fn=boom_probe,
    )
    assert result is not None
    assert result.source_fps == 0.0
    assert result.total_duration_sec == 0.0


# ---------------------------------------------------------------------------
# Helpers + public API surface
# ---------------------------------------------------------------------------


def test_is_scene_map_enabled_reflects_env(monkeypatch):
    from app.features.render.engine.pipeline.scene_map_stage import is_scene_map_enabled
    monkeypatch.setenv("SCENE_MAP_ENABLED", "1")
    assert is_scene_map_enabled() is True
    monkeypatch.setenv("SCENE_MAP_ENABLED", "0")
    assert is_scene_map_enabled() is False


def test_default_is_scene_map_enabled_on(monkeypatch):
    """Reading the env var when unset returns the documented default."""
    from app.features.render.engine.pipeline.scene_map_stage import is_scene_map_enabled
    monkeypatch.delenv("SCENE_MAP_ENABLED", raising=False)
    assert is_scene_map_enabled() is True
