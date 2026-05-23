/**
 * quality.utils.ts — pure helper functions for quality feature display.
 */
import { AI_TRACE_FRIENDLY } from './quality.types'

/**
 * Returns a friendly label for an AI trace ref.
 * Known refs return from the friendly map.
 * Unknown refs: strip 'ai.' prefix, replace underscores/dots with spaces, capitalize each word.
 */
export function getFriendlyTraceLabel(ref: string): string {
  if (!ref) return 'Unknown event'
  if (AI_TRACE_FRIENDLY[ref]) return AI_TRACE_FRIENDLY[ref]

  // Fallback: strip 'ai.' prefix, replace separators, capitalize words
  const cleaned = ref.replace(/^ai\./, '').replace(/[_.]/g, ' ')
  return cleaned
    .split(' ')
    .map((word) => (word.length > 0 ? word[0].toUpperCase() + word.slice(1) : word))
    .join(' ')
}

/**
 * Returns a text symbol for a severity level.
 * No emoji — plain text symbols only.
 */
export function getSeverityIcon(severity: string): string {
  switch (severity) {
    case 'critical': return '●'
    case 'error':    return '▲'
    case 'warning':  return '◆'
    case 'info':     return '●'
    default:         return '●'
  }
}

/** Format a quality score as "N/100". */
export function formatScore(score: number): string {
  return `${Math.round(score)}/100`
}
