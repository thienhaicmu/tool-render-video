/**
 * QualityPanel — on-demand quality report panel for a rendered job.
 * Renders inside JobDetailDrawer (380px width).
 * Never polled — fetched once on open (and on manual refresh).
 */
import { useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/Button'
import { QualityLoadingState } from './QualityLoadingState'
import { QualityEmptyState } from './QualityEmptyState'
import { QualityErrorState } from './QualityErrorState'
import { QualitySummaryCard } from './QualitySummaryCard'
import { QualityPartList } from './QualityPartList'
import { useQualityStore } from '@/stores/qualityStore'
import './QualityPanel.css'

export interface QualityPanelProps {
  jobId: string
  /** Job status value from JobStatus.status */
  jobStatus: string
}

/** Statuses where quality is not yet available */
const PENDING_STATUSES = new Set(['queued', 'running'])

/** Check if an error string suggests a 404 / not found */
function isNotFoundError(err: string): boolean {
  return (
    err.toLowerCase().includes('not found') ||
    err.toLowerCase().includes('404') ||
    err.toLowerCase().includes('no quality')
  )
}

export function QualityPanel({ jobId, jobStatus }: QualityPanelProps) {
  const summary = useQualityStore((s) => s.summaries[jobId])
  const isLoading = useQualityStore((s) => Boolean(s.loading[jobId]))
  const error = useQualityStore((s) => s.errors[jobId] ?? '')
  const fetchJobSummary = useQualityStore((s) => s.fetchJobSummary)
  const refreshJobSummary = useQualityStore((s) => s.refreshJobSummary)

  const isPending = PENDING_STATUSES.has(jobStatus)

  useEffect(() => {
    if (isPending) return
    if (!summary && !isLoading && !error) {
      void fetchJobSummary(jobId)
    }
  }, [jobId, isPending, summary, isLoading, error, fetchJobSummary])

  const handleRefresh = useCallback(() => {
    void refreshJobSummary(jobId)
  }, [jobId, refreshJobSummary])

  // Pending: quality not yet generated
  if (isPending) {
    return (
      <div className="quality-panel" data-testid="quality-panel">
        <div className="quality-panel-header">
          <span className="quality-panel-title">Quality</span>
        </div>
        <div className="quality-pending-notice">
          Quality report will be available after render completes.
        </div>
      </div>
    )
  }

  const isNotAvailable = !isLoading && error && isNotFoundError(error)

  return (
    <div className="quality-panel" data-testid="quality-panel">
      <div className="quality-panel-header">
        <span className="quality-panel-title">Quality</span>
        {!isPending && (summary || (error && !isLoading)) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
            data-testid="quality-refresh-btn"
          >
            Refresh
          </Button>
        )}
      </div>

      {isLoading && <QualityLoadingState />}

      {!isLoading && isNotAvailable && <QualityEmptyState />}

      {!isLoading && error && !isNotAvailable && (
        <QualityErrorState error={error} onRetry={handleRefresh} />
      )}

      {!isLoading && !error && !summary && <QualityEmptyState />}

      {!isLoading && !error && summary && (
        <>
          <QualitySummaryCard summary={summary.summary} />
          <QualityPartList jobId={jobId} parts={summary.parts} />
        </>
      )}
    </div>
  )
}
