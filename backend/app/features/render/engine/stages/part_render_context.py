"""Per-part render context — state-holder dataclass for part_renderer.

Sprint 6.D-2.1 — extracted verbatim from stages/part_renderer.py
(lines 100-154 of the pre-extraction file). No logic changes; pure relocation.

`PartRenderContext` bundles all closure-captured state that the
orchestrator (`run_render_pipeline`) hands to the per-part workers
(`prepare_part_assets`, `process_one_part`). Originally lived as a
nested closure variable bag during the pre-Phase-A monolith era;
already-broken-out as a dataclass in Phase A-3 of the prior refactor.
Now lives in its own module so part_renderer.py stays focused on
per-part execution logic.

Field grouping (preserved verbatim from the original):
  - Job identity: job_id, effective_channel, total_parts, retry_count.
  - I/O paths: work_dir, output_dir, source_path, source dict, output_stem.
  - Payload + resume: payload, existing_parts.
  - AI state: ai_edit_plan, vis_intensity_hint.
  - Platform/render config: target_platform, tuned, ffmpeg_threads.
  - Cancel + motion: cancel_registry, src_stat_for_motion.
  - Subtitle: full_srt, full_srt_available, subtitle_enabled_by_idx,
    subtitle_cutoff.
  - Voice: voice_audio_path.
  - Market/hook: mv_market, mv_cfg, hook_apply_enabled,
    hook_applied_text, hook_score, hook_overlay_enabled.
  - AI subtitle: dna_clean_visual, ai_subtitle_emphasis_config.
  - Text layers: normalized_text_layers.
  - Mutable shared lists (passed by reference — same list object as
    outer scope): voice_part_tts_attempts, voice_mix_ok,
    sub_translate_attempts, sub_translate_partial, sub_translate_clean,
    sub_translate_failed_parts, recovery_notes.

The 7 mutable-list fields use `field(default_factory=list)` and are
ALSO populated by the caller via constructor kwargs with the outer
list references — appends inside per-part workers mutate the same
list objects that run_render_pipeline reads later for the
result_json payload. Do not change the field types or replace them
with tuples; the by-reference contract is load-bearing.

Public re-export contract:
  Two callers import `PartRenderContext` via `app.features.render.engine.stages.part_renderer`:
    - app/orchestration/pipeline_render_loop.py:28
    - app/orchestration/render_pipeline.py:99
  Both continue to work unchanged after this commit because
  part_renderer.py re-exports the class from this new module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.domain.render_plan import RenderPlan


@dataclass
class PartRenderContext:
    # Job identity
    job_id: str
    effective_channel: str
    total_parts: int
    retry_count: int
    # I/O paths
    work_dir: Path
    output_dir: Path
    source_path: Path
    source: dict
    output_stem: str
    # Payload
    payload: Any
    # Resume
    existing_parts: dict
    # AI state
    ai_edit_plan: Any
    vis_intensity_hint: Any
    # Platform/render config
    target_platform: str
    tuned: dict
    ffmpeg_threads: int
    # Cancel
    cancel_registry: Any
    # Motion
    src_stat_for_motion: Any
    # Subtitle
    full_srt: Path
    full_srt_available: bool
    subtitle_enabled_by_idx: dict
    subtitle_cutoff: float
    # Voice
    voice_audio_path: Any
    # Market/hook
    mv_market: str
    mv_cfg: dict
    hook_apply_enabled: bool
    hook_applied_text: str
    hook_score: Any
    hook_overlay_enabled: bool
    # AI subtitle
    dna_clean_visual: bool
    ai_subtitle_emphasis_config: Any
    # Text layers
    normalized_text_layers: Any
    # Mutable shared lists (passed by reference — same list object as outer scope)
    voice_part_tts_attempts: list = field(default_factory=list)
    voice_mix_ok: list = field(default_factory=list)
    sub_translate_attempts: list = field(default_factory=list)
    sub_translate_partial: list = field(default_factory=list)
    sub_translate_clean: list = field(default_factory=list)
    sub_translate_failed_parts: list = field(default_factory=list)
    recovery_notes: list = field(default_factory=list)
    # Sprint 2.3 — RenderPlan threaded from orchestration after the LLM stage.
    # Optional + default None to honor Sacred Contract #2 (new field defaults
    # to disabled equivalent — legacy contexts that don't set it work
    # unchanged). part_renderer.py does NOT consume this field in Sprint 2.3;
    # Sprint 4 will migrate decision logic to read it.
    render_plan: Optional[RenderPlan] = None
