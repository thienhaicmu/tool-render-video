/**
 * buildRenderPayload - P2.4: pure RenderRequest builder extracted from
 * RenderWorkflow. Every field comes from cfg + the source path passed in.
 * The wire-contract commentary (which fields were removed and why) moved
 * here with the code - see the inline notes.
 */
import type { RenderRequest } from '@/types/api'
import type { ConfigState } from './types'
import { RATIO_INFO } from './constants'

export function buildRenderPayload(cfg: ConfigState, srcValue: string): RenderRequest {
  return {
    source_mode:       'local',
    source_video_path: srcValue,
    output_dir:          cfg.outputDir || 'output',
    aspect_ratio:        RATIO_INFO[cfg.ratio].api,
    min_part_sec:        cfg.minSec,
    max_part_sec:        cfg.maxSec,
    // Pha 5.7 — source trim (omitted when 0 = whole source). Pipeline
    // clips the source in pipeline_source_prep before segmentation.
    edit_trim_in:        cfg.trimIn > 0 ? cfg.trimIn : undefined,
    edit_trim_out:       cfg.trimOut > 0 ? cfg.trimOut : undefined,
    // T1.4 follow-up — Audit 2026-06-08: removed `max_export_parts:
    // cfg.outputCount` from the wire (engine reads `output_count`
    // instead via render_pipeline.py:576). Sending both was wire-
    // duplication; only output_count survives.
    add_subtitle:                cfg.subEnabled,
    subtitle_style:              cfg.subStyle,
    highlight_per_word:          cfg.subHighlight,
    sub_font_size:               cfg.subFontSize,
    // P2 (2026-06-20): subtitle translation is independent of narration —
    // the narration self-translates to the voice language server-side
    // (part_voice_mix), so these drive only the on-screen subtitle.
    subtitle_translate_enabled:  cfg.subTranslate || undefined,
    subtitle_target_language:    cfg.subTranslate ? cfg.subTranslateLang : undefined,
    // T1.4 follow-up — Audit 2026-06-08: removed `part_order:
    // cfg.partOrder`. The BE validator at models/render.py:451-463
    // coerces the value to "viral" then no engine consumer reads it
    // (FINDING-C01 closure). Pure UI deceit on the wire.
    voice_enabled:               cfg.narrEnabled,
    voice_source:        cfg.narrEnabled ? cfg.voiceSource : undefined,
    voice_text:          cfg.narrEnabled && cfg.voiceSource === 'manual' ? cfg.voiceText : undefined,
    rewrite_tone:        cfg.narrEnabled && cfg.voiceSource === 'ai_rewrite' ? (cfg.rewriteTone || '') : undefined,
    narration_mode:      cfg.narrEnabled && cfg.voiceSource === 'ai_rewrite' ? (cfg.narrationMode || '') : undefined,
    reaction_intensity:  cfg.narrEnabled && cfg.voiceSource === 'ai_rewrite' && cfg.narrationMode === 'reaction' ? (cfg.reactionIntensity || '') : undefined,
    voice_language:      cfg.narrEnabled ? cfg.voiceLang as 'vi-VN' | 'ja-JP' | 'ko-KR' | 'en-US' | 'en-GB' : undefined,
    voice_gender:        cfg.narrEnabled ? cfg.voiceGender : undefined,
    tts_engine:          cfg.narrEnabled ? cfg.ttsEngine : undefined,
    voice_mix_mode:      cfg.narrEnabled ? cfg.voiceMixMode : undefined,
    // LLM segment selection — canonical llm_* fields. API keys from server .env.
    llm_enabled:  cfg.llmEnabled || undefined,
    ai_provider:  cfg.llmEnabled ? cfg.aiProvider : undefined,
    llm_model:    cfg.llmEnabled && cfg.llmModel ? cfg.llmModel : undefined,
    llm_language: cfg.llmEnabled && cfg.llmLanguage !== 'auto' ? cfg.llmLanguage : undefined,
    multi_variant:       cfg.multiVariant || undefined,
    cta_enabled:         cfg.ctaEnabled || undefined,
    cta_type:            cfg.ctaEnabled ? cfg.ctaType : undefined,
    hook_apply_enabled:  cfg.hookApplyEnabled || undefined,
    hook_overlay_enabled: cfg.hookOverlayEnabled || undefined,
    // T1.4 — Audit 2026-06-08 closure: removed `ai_auto_cut`,
    // `ai_use_semantic_hooks`, `ai_render_influence_enabled`,
    // `ai_beat_pulse_enabled` from the wire (Phase-G zombies — gated
    // by ctx.ai_edit_plan which is hardcoded None at
    // render_pipeline.py:931, so setting these `true` had zero
    // behavioural effect). Sprint 3 3E Subset B's rationale for
    // sending them was to keep new jobs aligned with the BE defaults;
    // now that they're outside the Public surface they can't even
    // reach the BE, so the alignment is automatic.
    motion_aware_crop:   cfg.focusMode === 'face' || cfg.focusMode === 'object',
    target_platform:     cfg.platform,
    effect_preset:       cfg.style,
    render_profile:      cfg.renderProfile,
    whisper_model:       cfg.whisperModel !== 'auto' ? cfg.whisperModel : undefined,
    render_format:       cfg.renderFormat,
    // Story Intelligence is a clips-path feature; the recap path runs its own
    // two-pass Story/Editorial stages unconditionally, so only forward the
    // flag for clips. undefined when off → stays off on the wire (Contract #2).
    use_story_intelligence: cfg.renderFormat === 'clips' ? (cfg.useStoryIntelligence || undefined) : undefined,
    target_duration:     cfg.targetDuration,
    // Recap = one long video; the AI picks scenes, so output_count is forced to 1.
    output_count:        cfg.renderFormat === 'recap' ? 1 : cfg.outputCount,
    reframe_mode:        cfg.focusMode,
    // T1.4 — Audit 2026-06-08 closure: removed `energy_style`,
    // `output_language`, `narration_style` (v2 vision dead — never
    // consumed by the render engine) and `asset_music_profile`
    // (UP27 — never wired). The dead form widgets + ConfigState for
    // energy_style / output_language / narration_style were removed
    // 2026-06-20 (#3 + A/B/C cleanup), along with assetMusicProfile and
    // the legacy aiCloud* cluster (badge rewired to the real llm* config).
    asset_logo_path:     cfg.assetLogoPath ?? undefined,
    asset_intro_path:    cfg.assetIntroPath ?? undefined,
    asset_outro_path:    cfg.assetOutroPath ?? undefined,
  }
}
