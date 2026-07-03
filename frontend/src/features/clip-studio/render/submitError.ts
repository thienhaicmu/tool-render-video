/**
 * submitError — parse a failed POST /api/render/process error into a
 * user-facing message + an optional dedup job id (god-file slice 4a).
 *
 * Extracted verbatim from RenderWorkflow.handleStartRender's catch block —
 * the trickiest, most error-prone part of the submit path. On a 409 the
 * backend detail reads e.g. "A render job for this source is already in
 * progress (job_id=<uuid>). …"; we surface it verbatim and pull the uuid so
 * the caller can jump to that running job's monitor. The state-machine side
 * (navigate / toast) stays in the component.
 */
export interface ParsedSubmitError {
  message: string
  dedupJobId: string | null
}

export function parseSubmitError(e: unknown): ParsedSubmitError {
  let message = 'Failed to start render'
  let dedupJobId: string | null = null
  if (e && typeof e === 'object' && 'status' in e && 'detail' in e) {
    const apiErr = e as { status: number; detail: unknown }
    message = typeof apiErr.detail === 'string'
      ? apiErr.detail
      : JSON.stringify(apiErr.detail)
    if (apiErr.status === 409 && typeof apiErr.detail === 'string') {
      const m = apiErr.detail.match(/job_id=([0-9a-f-]{36})/i)
      if (m) dedupJobId = m[1]
    }
  } else if (e instanceof Error) {
    message = e.message
  }
  return { message, dedupJobId }
}
