/**
 * StatusPill — Compact status indicator with semantic color and animated dot.
 * Source: docs/design/components.md component #5
 */
export type StatusPillStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'interrupted'

interface StatusConfig {
  label: string
  dotColor: string
  textColor: string
  bg: string
}

const STATUS_CONFIG: Record<StatusPillStatus, StatusConfig> = {
  queued: {
    label: 'Queued',
    dotColor: 'var(--status-queued)',
    textColor: 'var(--status-queued)',
    bg: 'var(--status-queued-bg)',
  },
  running: {
    label: 'Running',
    dotColor: 'var(--status-running)',
    textColor: 'var(--status-running)',
    bg: 'var(--status-running-bg)',
  },
  completed: {
    label: 'Completed',
    dotColor: 'var(--status-success)',
    textColor: 'var(--status-success)',
    bg: 'var(--status-success-bg)',
  },
  partial: {
    label: 'Partial',
    dotColor: 'var(--status-partial)',
    textColor: 'var(--status-partial)',
    bg: 'var(--status-partial-bg)',
  },
  failed: {
    label: 'Failed',
    dotColor: 'var(--status-error)',
    textColor: 'var(--status-error)',
    bg: 'var(--status-error-bg)',
  },
  interrupted: {
    label: 'Interrupted',
    dotColor: 'var(--status-interrupted)',
    textColor: 'var(--status-interrupted)',
    bg: 'var(--status-warning-bg)',
  },
}

export interface StatusPillProps {
  status: StatusPillStatus
}

export function StatusPill({ status }: StatusPillProps) {
  const config = STATUS_CONFIG[status]

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        height: '22px',
        padding: '0 8px',
        borderRadius: 'var(--radius-sm)',
        backgroundColor: config.bg,
        fontSize: 'var(--text-xs)',
        fontWeight: 'var(--weight-medium)' as unknown as number,
        color: config.textColor,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        className={status === 'running' ? 'status-dot--running' : undefined}
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          backgroundColor: config.dotColor,
          flexShrink: 0,
        }}
      />
      {config.label}
    </span>
  )
}
