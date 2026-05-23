/**
 * Error formatting helpers for API responses.
 * Prevents [object Object] from appearing in user-facing notifications.
 */
import { ApiError } from '../api/client'

/**
 * Extract a human-readable message from any thrown value.
 * Handles FastAPI 422 detail arrays, plain strings, and ApiError instances.
 */
export function _formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = err.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      // FastAPI 422: [{loc, msg, type}]
      return detail
        .map((d: unknown) =>
          typeof d === 'object' && d !== null && 'msg' in d
            ? String((d as Record<string, unknown>).msg)
            : String(d),
        )
        .join('; ')
    }
    if (typeof detail === 'object' && detail !== null) {
      const d = detail as Record<string, unknown>
      if ('detail' in d) return String(d.detail)
      if ('message' in d) return String(d.message)
    }
    return err.message
  }
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return 'An unexpected error occurred'
}
