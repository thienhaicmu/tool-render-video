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

/** State of a single per-clip step node in the Cut → Sub → Render stepper. */
export type StepState = 'done' | 'active' | 'pending' | 'failed'

/** Index of the currently-active per-clip step, or -1 when the clip is
 *  waiting / done / failed (i.e. no single step is "in progress"). */
function activeStepIndex(status: string): number {
  switch (status.toLowerCase()) {
    case 'cutting':      return 0
    case 'transcribing': return 1
    case 'rendering':    return 2
    default:             return -1
  }
}

/**
 * Per-node state for the Cut → Sub → Render stepper, derived from the
 * frozen per-part status (Sacred Contract #5). Steps before the active
 * one are `done`, the active one `active`, later ones `pending`.
 *   done    → all three done
 *   failed  → all three failed (we don't know which step aborted)
 *   waiting → all three pending
 */
export function stepStates(status: string): StepState[] {
  const s = status.toLowerCase()
  if (s === 'done') return ['done', 'done', 'done']
  if (s === 'failed' || s === 'cancelled') return ['failed', 'failed', 'failed']
  const active = activeStepIndex(s)
  if (active < 0) return ['pending', 'pending', 'pending']
  return STEP_NODES.map((_, i) =>
    i < active ? 'done' : i === active ? 'active' : 'pending',
  )
}

/** Human activity line for the focus card (tool names kept as detail). */
export function activityLabel(status: string, t: Strings): string {
  switch (status.toLowerCase()) {
    case 'cutting':      return `${t.actCutting} · FFmpeg`
    case 'transcribing': return `${t.actTranscribing} · Whisper AI`
    case 'rendering':    return `${t.actRendering} · FFmpeg`
    default:             return ''
  }
}
