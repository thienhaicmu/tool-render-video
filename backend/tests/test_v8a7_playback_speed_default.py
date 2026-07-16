"""V8-A7 regression guard — Audit 2026-06-08 closure.

Pre-V8-A7 the ``RenderRequest.playback_speed`` field defaulted to
``1.07`` — a silent 7% acceleration applied to every render. The FE
never set the field, so every produced clip ran 7% faster than the
source with no UI affordance to opt out. The audit flagged this as a
trust-breaking default because operators were producing
not-quite-real-time output without realising it.

V8-A7 (this guard) pins:

  1. The model default is now ``1.0`` (no silent acceleration).
  2. Every BE fallback that used to coerce ``None / 0`` to ``1.07``
     now coerces to ``1.0`` so the new default is consistent
     end-to-end across the 8 modified call sites.
  3. Sacred Contract #2 replay safety: a stored payload that
     explicitly carries ``playback_speed=1.07`` (a job created
     while the legacy default was active) still replays at
     ``1.07`` — Pydantic preserves the explicit field value during
     ``model_dump`` round-trip, so payload_json → RenderRequest →
     payload_json is bit-identical for the field.

Failure of any test below means the audit-2026-06-08 V8-A7 closure
has regressed — either the default flipped back, or a fallback
literal was reintroduced, or replay no longer preserves the explicit
1.07 value.
"""
from __future__ import annotations

from pathlib import Path


def test_render_request_default_playback_speed_is_1_0():
    """The model default is the heart of the V8-A7 closure."""
    from app.models.render import RenderRequest

    # Constructing without playback_speed must yield 1.0, NOT 1.07.
    # The required field list (source_video_path) is the only thing
    # that has to be set; everything else carries its own default.
    req = RenderRequest(source_video_path="/tmp/test.mp4")
    assert req.playback_speed == 1.0, (
        f"V8-A7 regression — RenderRequest.playback_speed default is "
        f"{req.playback_speed!r}, expected 1.0. The silent 7% "
        f"acceleration default came back."
    )


def test_explicit_1_07_in_payload_replays_at_1_07():
    """Sacred Contract #2 replay safety. A stored payload that was
    serialised while the legacy 1.07 default was active still
    decodes to 1.07 — the explicit value wins over the new default.
    """
    from app.models.render import RenderRequest

    # Simulate a stored payload_json from a pre-V8-A7 job.
    stored_payload = {
        "source_video_path": "/tmp/old_job.mp4",
        "playback_speed": 1.07,
    }
    req = RenderRequest(**stored_payload)
    assert req.playback_speed == 1.07, (
        "V8-A7 replay regression — a stored payload with explicit "
        "playback_speed=1.07 must replay at 1.07. If this fails, "
        "Sacred Contract #2 is broken for V8-A7 — historical jobs "
        "now run at a different speed than when they were created."
    )

    # And round-trip back to dict the same way (model_dump preserves it).
    dumped = req.model_dump()
    assert dumped["playback_speed"] == 1.07, (
        "V8-A7 replay regression — model_dump dropped the explicit "
        "1.07 value. Stored payload_json reserialisation would lose "
        "the legacy speed."
    )


def test_no_1_07_literal_fallbacks_remain_in_engine():
    """Source-level guard. Pre-V8-A7 the codebase had 9 ``or 1.07``
    fallback literals inside the render engine (the model default
    plus 8 belt-and-suspenders fallbacks against missing/None
    payload values). V8-A7 replaced all of them with ``or 1.0``.

    A future change that reintroduces ``or 1.07`` in any engine
    module would silently re-enable the silent acceleration for the
    fallback path (which fires when payload.playback_speed is 0.0
    or omitted from a legacy stored payload).
    """
    import re

    backend_app = Path(__file__).resolve().parent.parent / "app"
    # Comments referencing the literal "1.07" are allowed (the V8-A7
    # closure comments explain the old default). Code references are
    # not. Match patterns that put 1.07 inside an `or` expression OR
    # as a function default — both are runtime fallbacks.
    forbidden = [
        re.compile(r"\bor\s+1\.07\b"),
        re.compile(r"=\s*1\.07\b(?!\s*[)#])"),  # `= 1.07` not followed by `)` or `#`
    ]
    # Documented false positives: 1.07 literals that are NOT playback-speed
    # fallbacks. anime_char.py uses 1.07 as an elder-body GEOMETRY scale
    # (`g[key] *= 1.07`) — unrelated to V8-A7's silent-acceleration fix.
    allowed = {("visual", "v2", "anime_char.py")}
    bad_hits: list[tuple[str, int, str]] = []
    for py in backend_app.rglob("*.py"):
        if py.parts[-3:] in allowed:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # Skip lines that are obviously comments / docstring prose.
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden:
                if pat.search(line):
                    # Strip inline `# ...` comments and recheck — the
                    # match might be inside a comment on a code line.
                    code_only = line.split("#", 1)[0]
                    if pat.search(code_only):
                        bad_hits.append((str(py.relative_to(backend_app)), i, line.strip()))

    assert not bad_hits, (
        f"V8-A7 regression — {len(bad_hits)} site(s) still use a "
        f"1.07 literal as a runtime fallback or function default. "
        f"V8-A7 standardised all of these to 1.0. Restore them or "
        f"document why the legacy literal must remain. Sites:\n  - "
        + "\n  - ".join(f"{p}:{n}  {ln}" for p, n, ln in bad_hits)
    )


def test_variant_segments_use_new_base_when_payload_speed_omitted():
    """``_build_variant_segments`` uses ``payload.playback_speed or
    1.0`` as the base for Aggressive / Balanced / Story variants
    (+0.05 / 0.00 / -0.05 deltas). Pre-V8-A7 the fallback was 1.07
    so a payload with playback_speed=None or 0.0 produced Aggressive
    at 1.12, Balanced at 1.07, Story at 1.02. Post-V8-A7 the same
    inputs produce 1.05 / 1.00 / 0.97 (the audit's "honest" baseline).
    """
    from app.features.render.engine.pipeline.pipeline_segment_selection import (
        _build_variant_segments,
    )

    class _MockPayload:
        playback_speed = None  # simulates a legacy stored payload missing the key
        subtitle_style = ""

    scored = [{
        "start": 10.0, "duration": 20.0,
        "hook_score": 80, "motion_score": 60, "viral_score": 70,
        "scene_quality_score": 65, "speech_density_score": 55,
        "market_score": 50, "duration_fit_score": 45,
        "content_type_hint": "vlog",
    }]
    variants = _build_variant_segments(scored, _MockPayload())
    # Three variants emit even from a single-scored input (each picks
    # the same single segment, then re-tags it). Pull the variant_*
    # speeds and verify they sit on the V8-A7 base of 1.0, not 1.07.
    by_type = {v["variant_type"]: v for v in variants}
    assert "balanced" in by_type, (
        "V8-A7 regression — variant builder no longer emits "
        "balanced variant. Pipeline shape changed; update test."
    )
    bal_speed = by_type["balanced"]["variant_playback_speed"]
    agg_speed = by_type["aggressive"]["variant_playback_speed"]
    story_speed = by_type["story_first"]["variant_playback_speed"]
    assert bal_speed == 1.0, (
        f"V8-A7 regression — balanced variant speed is {bal_speed}, "
        f"expected 1.0. The fallback literal in "
        f"pipeline_segment_selection.py:278 came back as 1.07."
    )
    # Aggressive = base + 0.05 (clamped to 1.15 max).
    assert abs(agg_speed - 1.05) < 1e-6, (
        f"V8-A7 regression — aggressive variant speed is {agg_speed}, "
        f"expected 1.05 (base 1.0 + 0.05)."
    )
    # Story = base - 0.05 (floored at 0.97).
    assert abs(story_speed - 0.97) < 1e-6, (
        f"V8-A7 regression — story_first variant speed is {story_speed}, "
        f"expected 0.97 (floor)."
    )
