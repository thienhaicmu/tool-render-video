/**
 * progress.utils.ts — pure utility functions for the live job progress panel.
 */
import type { ConnectionStatus } from './progress.types'

/** Clamp a progress value to [0, 100] */
export function normalizeProgressPercent(value: number | null | undefined): number {
  if (value === null || value === undefined || isNaN(value)) return 0
  return Math.max(0, Math.min(100, value))
}

/** Map backend stage string to a friendly UI label */
export function getStageLabel(stage: string | null | undefined): string {
  switch (stage) {
    case 'starting':         return 'Starting'
    case 'segment_building': return 'Analyzing Scenes'
    case 'rendering':        return 'Rendering Parts'
    case 'finalizing':       return 'Finalizing'
    case 'complete':         return 'Complete'
    case 'error':            return 'Error'
    case '':
    case null:
    case undefined:          return 'Processing'
    default:                 return 'Processing'
  }
}

/** Map job status to a friendly UI label */
export function getStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'queued':                  return 'Queued'
    case 'running':                 return 'Rendering'
    case 'completed':               return 'Complete'
    case 'completed_with_errors':   return 'Completed with Errors'
    case 'failed':                  return 'Failed'
    case 'interrupted':             return 'Interrupted'
    case 'cancelled':
    case 'canceled':                return 'Canceled'
    case 'cancelling':              return 'Canceling...'
    case '':
    case null:
    case undefined:                 return 'Processing'
    default:                        return 'Processing'
  }
}

/**
 * Determine ConnectionStatus from socket state.
 * - If terminal: always 'terminal'
 * - If connected: 'live'
 * - If reconnecting: 'reconnecting' (dropped but retrying, not yet failed)
 * - If error and not connected: 'disconnected'
 * - Otherwise (not yet connected, no error): 'connecting'
 */
export function deriveConnectionStatus(
  isConnected: boolean,
  isTerminal: boolean,
  error: string | null,
  isReconnecting = false,
): ConnectionStatus {
  if (isTerminal) return 'terminal'
  if (isConnected) return 'live'
  if (isReconnecting) return 'reconnecting'
  if (error) return 'disconnected'
  return 'connecting'
}

/**
 * Extract the latest message text.
 * Never exposes raw JSON — strips leading/trailing whitespace.
 * Returns '' for null/undefined/empty.
 */
export function extractLatestMessage(message: string | null | undefined): string {
  if (!message) return ''
  const trimmed = message.trim()
  return trimmed
}

/** Get a human-readable part label */
export function getPartLabel(partNo: number): string {
  return `Part ${partNo}`
}
