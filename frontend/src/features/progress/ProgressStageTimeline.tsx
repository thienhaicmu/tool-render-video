/**
 * ProgressStageTimeline — compact linear stage indicator.
 * Shows 5 major stages. Completed stages appear checked/dimmed.
 * Current stage is highlighted. Future stages are muted.
 */

import type { RenderStage } from '../../types/enums'

interface Stage {
  key: RenderStage   // C1: validated against the backend stage contract
  label: string
}

const STAGES: Stage[] = [
  { key: 'queued',        label: 'Queued' },
  { key: 'analyzing',     label: 'Analyzing' },
  { key: 'rendering',     label: 'Rendering' },
  { key: 'writing_report', label: 'Finishing' },
  { key: 'done',          label: 'Done' },
]

/** Map backend stage to milestone index */
function stageToIndex(stage: string | null | undefined): number {
  switch (stage) {
    case 'queued':
    case 'starting':
    case 'running':            return 0
    case 'analyzing':
    case 'downloading':        // backward compat with stored records
    case 'scene_detection':
    case 'segment_building':
    case 'transcribing_full':  return 1
    case 'rendering':
    case 'rendering_parallel': return 2
    case 'writing_report':     return 3
    case 'done':
    case 'complete':
    case 'finalizing':         return 4
    case 'failed':             return 4
    default:                   return 0
  }
}

export interface ProgressStageTimelineProps {
  currentStage: string | null
}

export function ProgressStageTimeline({ currentStage }: ProgressStageTimelineProps) {
  const currentIndex = stageToIndex(currentStage)

  return (
    <div
      data-testid="progress-stage-timeline"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        fontSize: 'var(--font-size-xs)',
        flexWrap: 'nowrap',
        overflowX: 'auto',
      }}
    >
      {STAGES.map((stage, idx) => {
        const isCompleted = idx < currentIndex
        const isCurrent   = idx === currentIndex
        const isFuture    = idx > currentIndex

        return (
          <div
            key={stage.key}
            style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)', flexShrink: 0 }}
          >
            {/* Connector line */}
            {idx > 0 && (
              <div
                style={{
                  width: '16px',
                  height: '1px',
                  backgroundColor: isCompleted
                    ? 'var(--color-success)'
                    : 'var(--color-border)',
                }}
              />
            )}
            {/* Stage dot + label */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
              <div
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: isCompleted
                    ? 'var(--color-success)'
                    : isCurrent
                      ? 'var(--color-accent)'
                      : 'var(--color-border)',
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  color: isCompleted
                    ? 'var(--color-success)'
                    : isCurrent
                      ? 'var(--color-text-primary)'
                      : isFuture
                        ? 'var(--color-text-secondary)'
                        : 'var(--color-text-secondary)',
                  opacity: isFuture ? 0.5 : 1,
                  fontWeight: isCurrent ? ('var(--font-weight-medium)' as unknown as number) : undefined,
                  whiteSpace: 'nowrap',
                }}
              >
                {isCompleted ? '✓ ' : ''}{stage.label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
