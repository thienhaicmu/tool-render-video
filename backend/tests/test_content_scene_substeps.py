"""Mục 6 — per-scene sub-step progress signalling (2026-07-07).

scene_stage.render_one_scene emits a RENDERING progress+message at each of the 3
real composition boundaries so the Content monitor can show an accurate sub-step
strip (Narration → Visual → Compose) instead of guessing from the overall
percent. This pins the ordered sequence + monotonic progress, with the heavy
TTS/visual/ffmpeg calls stubbed so the test is offline + fast.

Sacred Contract #5: only progress_percent + message are added — the RENDERING /
DONE status names are unchanged.
"""
from __future__ import annotations


def test_scene_substep_progress_sequence(tmp_path, monkeypatch):
    from app.features.render.engine.stages.content import scene_stage
    from app.features.render.engine.stages.content.context import ContentRenderContext
    from app.domain.content_plan import ContentPlan, ContentScene

    # Capture every job-part write (status, progress, message) in call order.
    captured: list[tuple[str, int | None, str | None]] = []

    def _fake_upsert(job_id, part_no, part_name, status, **kw):
        captured.append((str(status), kw.get("progress_percent"), kw.get("message")))

    monkeypatch.setattr(scene_stage, "upsert_job_part", _fake_upsert)

    # Stub the heavy work: visual resolve returns a plain local colour asset
    # (no fallback), the scene render "succeeds".
    class _Asset:
        kind = "color"
        value = "#101820"
        provider = "local"

    monkeypatch.setattr(scene_stage, "resolve_scene_visual", lambda req, provider: _Asset())
    monkeypatch.setattr(scene_stage, "render_content_scene", lambda **kw: True)

    ctx = ContentRenderContext(
        job_id="jobX", effective_channel="test", scenes_dir=tmp_path,
        width=1080, height=1920, fps=30.0, sample_rate=48000,
        language="vi-VN", gender="female", voice_id=None, tts_engine="edge",
        add_subtitle=True, word_by_word=False, visual_provider="local",
        bg_kind="color", bg_value="#101820", imagen_tier="", subtitle_pick="",
        cancel_cb=lambda: False,
    )
    plan = ContentPlan(topic="t", scenes=[ContentScene(index=0, narration="hi", role="hook")])
    scene = plan.scenes[0]

    # pre_audio supplied → skips real TTS; the narration sub-step still fires.
    res = scene_stage.render_one_scene(
        ctx, plan, 1, scene, "local", pre_audio=("dummy.mp3", 5.0), pre_word_srt=None,
    )
    assert res["clip"] is not None, "scene should render successfully with stubs"

    prog_msgs = [(p, m) for (_st, p, m) in captured]
    # The 3 sub-step boundaries fire in order with their canonical messages.
    assert (15, "synthesizing narration") in prog_msgs
    assert (45, "resolving visual") in prog_msgs
    assert (75, "composing scene") in prog_msgs

    # Progress is monotonic non-decreasing and terminates at 100 (DONE).
    progs = [p for (_st, p, _m) in captured if p is not None]
    assert progs == sorted(progs), f"progress not monotonic: {progs}"
    assert progs[-1] == 100

    # Order: narration(15) precedes visual(45) precedes compose(75).
    order = [p for p in progs if p in (15, 45, 75)]
    assert order == [15, 45, 75], f"sub-step order wrong: {order}"


def test_scene_substep_visual_fallback_marks_background(tmp_path, monkeypatch):
    """A requested online provider that returns a local asset still flows through
    the visual sub-step and records the fallback message (progress 55)."""
    from app.features.render.engine.stages.content import scene_stage
    from app.features.render.engine.stages.content.context import ContentRenderContext
    from app.domain.content_plan import ContentPlan, ContentScene

    captured: list[tuple[str, int | None, str | None]] = []
    monkeypatch.setattr(
        scene_stage, "upsert_job_part",
        lambda job_id, part_no, part_name, status, **kw: captured.append(
            (str(status), kw.get("progress_percent"), kw.get("message"))
        ),
    )

    class _Asset:
        kind = "color"
        value = "#000"
        provider = "local"   # requested provider was online → this is a fallback

    monkeypatch.setattr(scene_stage, "resolve_scene_visual", lambda req, provider: _Asset())
    monkeypatch.setattr(scene_stage, "render_content_scene", lambda **kw: True)
    monkeypatch.setattr(scene_stage, "_job_log", lambda *a, **k: None)

    ctx = ContentRenderContext(
        job_id="jobY", effective_channel="test", scenes_dir=tmp_path,
        width=1080, height=1920, fps=30.0, sample_rate=48000,
        language="vi-VN", gender="female", voice_id=None, tts_engine="edge",
        add_subtitle=True, word_by_word=False, visual_provider="ai_image",
        bg_kind="color", bg_value="#000", imagen_tier="", subtitle_pick="",
        cancel_cb=lambda: False,
    )
    plan = ContentPlan(topic="t", scenes=[ContentScene(index=0, narration="hi", role="body")])

    res = scene_stage.render_one_scene(
        ctx, plan, 1, plan.scenes[0], "ai_image",
        pre_audio=("dummy.mp3", 5.0), pre_word_srt=None,
    )
    assert res.get("fallback") is True
    msgs = [m for (_st, _p, m) in captured]
    assert any("unavailable — using background" in (m or "") for m in msgs)
    progs = [p for (_st, p, _m) in captured if p is not None]
    assert progs == sorted(progs) and progs[-1] == 100
