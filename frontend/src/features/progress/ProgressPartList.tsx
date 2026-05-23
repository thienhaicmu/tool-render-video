/**
 * ProgressPartList — shows active render parts with per-part progress bars.
 */
import { ProgressPartItem } from './ProgressPartItem'

export interface ProgressPartListProps {
  activeParts: Array<{ part_no: number; status: string; progress_percent: number }>
  completedParts: number
  failedParts: number
  totalParts: number
}

const MAX_DISPLAYED_PARTS = 5

export function ProgressPartList({
  activeParts,
  completedParts,
  failedParts,
  totalParts,
}: ProgressPartListProps) {
  // No parts yet
  if (activeParts.length === 0 && totalParts === 0) {
    return (
      <div
        data-testid="progress-part-list-empty"
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          opacity: 0.7,
        }}
      >
        Parts will appear once rendering starts.
      </div>
    )
  }

  // Parts exist but none active — show summary
  if (totalParts > 0 && activeParts.length === 0) {
    return (
      <div
        data-testid="progress-part-list-summary"
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
        }}
      >
        {completedParts}/{totalParts} complete, {failedParts} failed
      </div>
    )
  }

  const displayed = activeParts.slice(0, MAX_DISPLAYED_PARTS)

  return (
    <div
      data-testid="progress-part-list"
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
    >
      {displayed.map((part) => (
        <ProgressPartItem
          key={part.part_no}
          part_no={part.part_no}
          status={part.status}
          progress_percent={part.progress_percent}
        />
      ))}
      {activeParts.length > MAX_DISPLAYED_PARTS && (
        <div
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            opacity: 0.7,
          }}
        >
          +{activeParts.length - MAX_DISPLAYED_PARTS} more active parts
        </div>
      )}
    </div>
  )
}
