/**
 * clipState — shared per-clip state helpers (WP1).
 *
 * Extracted from RenderStage so both RenderStage and ClipTile can use them
 * without a circular import. RenderStage re-exports `clipStateKey` for its
 * existing consumers (StepRendering).
 */
import type { JobPartStageEnum } from '@/types/enums'
import type { Strings } from '../i18n'

export type ClipState = 'done' | 'failed' | 'active' | 'waiting'

export function clipStateKey(status: string): ClipState {
  const s = status.toLowerCase()
  if (s === 'done') return 'done'
  if (s === 'failed' || s === 'cancelled') return 'failed'
  if (s === 'waiting' || s === 'queued') return 'waiting'
  return 'active'
}

/** The per-clip pipeline nodes (Cut → Sub → Render). */
export const STEP_NODES = [
  { key: 'cutting',      label: 'Cut' },
  { key: 'transcribing', label: 'Sub' },
  { key: 'rendering',    label: 'Render' },
] as const satisfies readonly { key: JobPartStageEnum; label: string }[]

/** Human activity line for the focus card (tool names kept as detail). */
export function activityLabel(status: string, t: Strings): string {
  switch (status.toLowerCase()) {
    case 'cutting':      return `${t.actCutting} · FFmpeg`
    case 'transcribing': return `${t.actTranscribing} · Whisper AI`
    case 'rendering':    return `${t.actRendering} · FFmpeg`
    default:             return ''
  }
}
