/**
 * submitSources — sequential multi-source submit loop (god-file slice 4b).
 *
 * Extracted verbatim from RenderWorkflow.handleStartRender's batch path: each
 * source is submitted with the same cfg; successes and failures are collected
 * so the caller can toast "Queued N/M" and land the compose screen back on a
 * clean state. Pure/injectable (buildPayload + submit are passed in), so it's
 * unit-testable in isolation — the notification + state-reset side stays in the
 * component.
 */
import type { RenderRequest } from '@/types/api'
import type { Source } from './types'

export interface SubmitOutcome {
  submitted: string[]
  failed: string[]
}

export async function submitSources(
  sources: Source[],
  buildPayload: (srcValue: string) => RenderRequest,
  submit: (payload: RenderRequest) => Promise<string>,
): Promise<SubmitOutcome> {
  const submitted: string[] = []
  const failed: string[] = []
  for (const s of sources) {
    try {
      const id = await submit(buildPayload(s.value))
      submitted.push(id)
    } catch {
      failed.push(s.value)
    }
  }
  return { submitted, failed }
}
