/**
 * QualityPartList — renders the list of QualityPartCard components.
 */
import { QualityPartCard } from './QualityPartCard'
import type { QualityPartSummary } from '../../types/api'
import './QualityPanel.css'

export interface QualityPartListProps {
  jobId: string
  parts: QualityPartSummary[]
}

export function QualityPartList({ jobId, parts }: QualityPartListProps) {
  if (parts.length === 0) {
    return (
      <div
        className="quality-empty"
        data-testid="quality-part-list-empty"
        style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)' }}
      >
        No parts data.
      </div>
    )
  }

  return (
    <div className="quality-part-list" data-testid="quality-part-list">
      {parts.map((part) => (
        <QualityPartCard key={part.part_no} jobId={jobId} part={part} />
      ))}
    </div>
  )
}
