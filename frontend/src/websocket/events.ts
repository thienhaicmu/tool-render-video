/**
 * Typed WebSocket event interfaces for /api/jobs/{jobId}/ws
 * Contract: docs/ui/UI_BACKEND_CONTRACT.md §11
 */
import type { WebSocketEvent, WebSocketErrorEvent, StoryModel } from '../types/api'

export type { WebSocketEvent, WebSocketErrorEvent }

// ── recap.plan.ready event context (Sacred Contract #6 additive event) ────────
// Typed shape of the `context` block on the recap.plan.ready WsLogEvent, mirror
// of the backend projection in recap_pipeline.py (the `_scene_blocks` list +
// the episodes/story_model payload). All fields optional — consumers render
// defensively. Pinned by backend/tests/test_recap_plan_ready_ws_shape.py.

/** One scene block — mirrors the `_scene_blocks` dict in recap_pipeline.py.
 *  part_no === n (render order). */
export interface RecapSceneBlock {
  n: number
  ep: number
  act: number
  start: number
  end: number
  dur: number
  title: string
  mode: string
  climax: boolean
}

export interface RecapEpisodeInfo {
  title: string
  acts: number
  scenes: number
}

export interface RecapPlanReadyContext {
  episodes?: RecapEpisodeInfo[]
  acts?: Array<{ title: string; beat: string; scenes: number }>
  scenes?: RecapSceneBlock[]
  scene_modes?: string[]
  original_audio_scenes?: number
  total_target_sec?: number
  story_summary?: string
  story_model?: StoryModel
  editorial?: Record<string, unknown>
}

/**
 * Render pipeline stage values sent in job.stage.
 * Matches backend JobStage enum (app/core/stage.py).
 */
export enum RenderStage {
  Queued = 'queued',
  Starting = 'starting',
  Running = 'running',
  Analyzing = 'analyzing',
  Downloading = 'downloading',       // kept for backward compat with stored records
  SceneDetection = 'scene_detection',
  SegmentBuilding = 'segment_building',
  TranscribingFull = 'transcribing_full',
  Rendering = 'rendering',
  RenderingParallel = 'rendering_parallel',
  WritingReport = 'writing_report',
  Done = 'done',
  Failed = 'failed',
  Complete = 'complete',             // legacy alias
  Finalizing = 'finalizing',         // legacy alias
  Error = 'error',                   // legacy alias
}

/**
 * Type guard: incoming WS message is a progress event.
 * Per Sacred Contract 6 (CLAUDE.md), every progress event must carry the
 * three top-level keys job, parts, summary. A regression that drops any
 * one of them must NOT pass this guard, or the UI will read stale/empty
 * values silently.
 *
 * T3.1 — Audit 2026-06-08 closure (Batch A V8-C1): progress frames
 * now also carry a ``type: "snapshot"`` discriminator. The check
 * stays on the three Sacred Contract keys (subset semantics), so the
 * additional ``type`` field does not break this guard for old or new
 * consumers.
 */
export function isProgressEvent(msg: unknown): msg is WebSocketEvent {
  return (
    typeof msg === 'object' &&
    msg !== null &&
    'job' in msg &&
    'parts' in msg &&
    'summary' in msg
  )
}

/**
 * Type guard: incoming WS message is an error event (has 'error' key).
 */
export function isErrorEvent(msg: unknown): msg is WebSocketErrorEvent {
  return typeof msg === 'object' && msg !== null && 'error' in msg
}

/**
 * T3.1 — Audit 2026-06-08 closure (Batch A V8-C1).
 *
 * A live log/structured event bridged from the backend's
 * ``_emit_render_event`` JSONL stream via the EVENT_BROADCASTER. Carries
 * the event metadata the UI uses to render an "AI activity panel" or
 * a live log view alongside the snapshot-derived progress UI.
 *
 * The shape mirrors the dict appended to `<job_id>.log` by
 * `_emit_render_event`. Most fields are best-effort; consumers should
 * treat missing/null entries defensively.
 */
export interface WsLogEvent {
  timestamp: string
  level: string
  event: string
  module?: string
  message?: string
  job_id?: string
  step?: string
  error_code?: string
  context?: Record<string, unknown>
  exception?: string
  traceback?: string
  duration_ms?: number
}

/**
 * Type guard: incoming WS message is a T3.1 log/event message
 * (``{"type": "event", "event": {...}}``). The event channel is
 * additive — pre-T3.1 consumers don't dispatch on ``type`` and
 * silently ignore these messages.
 */
export function isLogEvent(msg: unknown): msg is { type: 'event'; event: WsLogEvent } {
  if (typeof msg !== 'object' || msg === null) return false
  const m = msg as Record<string, unknown>
  return m.type === 'event' && typeof m.event === 'object' && m.event !== null
}
