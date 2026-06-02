/**
 * QualityPartCard — expandable card showing quality info for one render part.
 */
import { useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import { QualityBadge } from '@/components/quality/QualityBadge'
import { QualityIssueList } from '@/components/quality/QualityIssueList'
import { QualityLoadingState } from './QualityLoadingState'
import { QualityTraceRefs } from './QualityTraceRefs'
import { useQualityStore } from '@/stores/qualityStore'
import type { QualityPartSummary } from '@/types/api'
import './QualityPanel.css'

export interface QualityPartCardProps {
  jobId: string
  part: QualityPartSummary
}

export function QualityPartCard({ jobId, part }: QualityPartCardProps) {
  const [expanded, setExpanded] = useState(false)

  const reportKey = `${jobId}_${part.part_no}`
  const storedReport = useQualityStore((s) => s.reports[reportKey])
  const isLoading = useQualityStore((s) => Boolean(s.loading[reportKey]))
  const fetchPartQuality = useQualityStore((s) => s.fetchPartQuality)

  // Prefer inline report (from include_reports=true) over separately fetched
  const report = part.report ?? storedReport ?? null

  function handleToggle() {
    if (!part.available) return
    if (!expanded && !report && !isLoading) {
      void fetchPartQuality(jobId, part.part_no)
    }
    setExpanded((v) => !v)
  }

  return (
    <div className="quality-part-card" data-testid={`quality-part-card-${part.part_no}`}>
      <div
        className="quality-part-card-header"
        onClick={handleToggle}
        role="button"
        tabIndex={part.available ? 0 : -1}
        aria-expanded={expanded}
        aria-disabled={!part.available}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleToggle() }}
      >
        <div className="quality-part-card-header-left">
          <span>{expanded ? '▾' : '▸'}</span>
          <span>Part {part.part_no}</span>
        </div>
        <div className="quality-part-card-header-right">
          {part.available ? (
            <>
              <QualityBadge score={part.score} size="sm" />
              {part.issue_count > 0 && (
                <Badge variant="neutral" size="sm">
                  {part.issue_count} issue{part.issue_count !== 1 ? 's' : ''}
                </Badge>
              )}
            </>
          ) : (
            <span className="quality-part-unavailable">Not available</span>
          )}
        </div>
      </div>

      {expanded && part.available && (
        <div className="quality-part-card-body">
          {isLoading && !report ? (
            <QualityLoadingState />
          ) : report ? (
            <>
              <QualityIssueList issues={report.issues} />
              <QualityTraceRefs traceRefs={report.ai_trace_refs} />
            </>
          ) : (
            <div className="quality-part-unavailable">Loading report...</div>
          )}
        </div>
      )}
    </div>
  )
}
