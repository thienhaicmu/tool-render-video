/**
 * Utility functions for the jobs/history feature module.
 */
import type { HistoryItem } from '../../types/api'
import { isTerminalStatus } from '../../types/enums'

export { isTerminalStatus }

// ── Time helpers ──────────────────────────────────────────────────────────────

/**
 * Returns a human-readable relative time string.
 * e.g. "just now", "3 minutes ago", "2 hours ago", "3 days ago"
 */
export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 10) return 'just now'
  if (diffSec < 60) return `${diffSec} seconds ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} hour${diffHour === 1 ? '' : 's'} ago`
  const diffDay = Math.floor(diffHour / 24)
  return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`
}

/**
 * Returns a human-readable full datetime string.
 * e.g. "May 23, 2026, 10:30 AM"
 */
export function formatDateTime(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

// ── Status helpers ────────────────────────────────────────────────────────────

const ACTIVE_STATUSES = new Set(['running', 'queued', 'cancelling'])

export function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status)
}

// ── Action guards ─────────────────────────────────────────────────────────────

export function canCancel(item: HistoryItem): boolean {
  return isActiveStatus(item.status)
}

export function canRetry(item: HistoryItem): boolean {
  return item.can_retry
}

export function canRerun(item: HistoryItem): boolean {
  return item.can_rerun
}

export function canDelete(item: HistoryItem): boolean {
  return isTerminalStatus(item.status)
}
