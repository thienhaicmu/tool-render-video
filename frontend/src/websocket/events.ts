/**
 * Typed WebSocket event interfaces for /api/jobs/{jobId}/ws
 * Contract: docs/ui/UI_BACKEND_CONTRACT.md §11
 */
import type { WebSocketEvent, WebSocketErrorEvent } from '../types/api'

export type { WebSocketEvent, WebSocketErrorEvent }

/**
 * Render pipeline stage values sent in job.stage.
 * Matches backend JobStage enum (app/core/stage.py).
 */
export enum RenderStage {
  Starting = 'starting',
  SegmentBuilding = 'segment_building',
  Rendering = 'rendering',
  Finalizing = 'finalizing',
  Complete = 'complete',
  Error = 'error',
}

/**
 * Type guard: incoming WS message is a progress event (has 'job' key).
 */
export function isProgressEvent(msg: unknown): msg is WebSocketEvent {
  return typeof msg === 'object' && msg !== null && 'job' in msg
}

/**
 * Type guard: incoming WS message is an error event (has 'error' key).
 */
export function isErrorEvent(msg: unknown): msg is WebSocketErrorEvent {
  return typeof msg === 'object' && msg !== null && 'error' in msg
}
