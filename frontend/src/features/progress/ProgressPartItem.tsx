/**
 * ProgressPartItem — compact card for a single active render part.
 */
import { ProgressBar } from '@/components/ui/ProgressBar'
import { getPartLabel, normalizeProgressPercent } from './progress.utils'

export interface ProgressPartItemProps {
  part_no: number
  status: string
  progress_percent: number
}

export function ProgressPartItem({ part_no, status, progress_percent }: ProgressPartItemProps) {
  const pct = normalizeProgressPercent(progress_percent)
  const isError = status === 'failed' || status === 'cancelled'

  return (
    <div
      data-testid={`progress-part-item-${part_no}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-1)',
        padding: 'var(--space-2)',
        backgroundColor: 'var(--color-bg-elevated)',
        borderRadius: 'var(--radius-sm)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 'var(--font-size-xs)',
        }}
      >
        <span style={{ color: 'var(--color-text-primary)', fontWeight: 'var(--font-weight-medium)' as unknown as number }}>
          {getPartLabel(part_no)}
        </span>
        <span style={{ color: isError ? 'var(--color-error)' : 'var(--color-text-secondary)' }}>
          {status}
        </span>
      </div>
      <ProgressBar
        value={pct}
        variant={isError ? 'error' : 'default'}
        style={{ height: '4px' }}
      />
    </div>
  )
}
