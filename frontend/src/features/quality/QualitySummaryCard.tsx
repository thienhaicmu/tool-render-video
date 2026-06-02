/**
 * QualitySummaryCard — shows aggregate quality stats for a job.
 */
import { Badge } from '@/components/ui/Badge'
import { QualityBadge } from '@/components/quality/QualityBadge'
import type { QualitySummaryAggregate } from '@/types/api'
import './QualityPanel.css'

export interface QualitySummaryCardProps {
  summary: QualitySummaryAggregate
}

export function QualitySummaryCard({ summary }: QualitySummaryCardProps) {
  const noData = summary.average_score === 0 && summary.available_parts === 0

  return (
    <div className="quality-summary-card" data-testid="quality-summary-card">
      {noData ? (
        <div className="quality-summary-available">No parts reported yet.</div>
      ) : (
        <>
          <div className="quality-summary-top">
            <QualityBadge score={summary.average_score} size="sm" />
            <span className="quality-summary-available">
              {summary.available_parts} / {summary.total_parts} parts reported
            </span>
          </div>
          <div className="quality-summary-counts">
            {summary.critical_count > 0 && (
              <Badge variant="error" size="sm">
                {summary.critical_count} critical
              </Badge>
            )}
            {summary.error_count > 0 && (
              <Badge variant="error" size="sm">
                {summary.error_count} error
              </Badge>
            )}
            {summary.warning_count > 0 && (
              <Badge variant="warning" size="sm">
                {summary.warning_count} warning
              </Badge>
            )}
            {summary.info_count > 0 && (
              <Badge variant="info" size="sm">
                {summary.info_count} info
              </Badge>
            )}
            {summary.critical_count === 0 &&
              summary.error_count === 0 &&
              summary.warning_count === 0 &&
              summary.info_count === 0 && (
                <Badge variant="success" size="sm">No issues</Badge>
              )}
          </div>
        </>
      )}
    </div>
  )
}
