import { useState, useEffect } from 'react'
import { AIChip } from '../../../components/ui/AIChip'
import { ScoreBadge } from '../../../components/ui/ScoreBadge'
import { ReviewCard } from './ReviewCard'
import { ComparisonPanel } from './ComparisonPanel'
import { type ReviewCardData, type ReviewCardStatus } from '../types'
import { getJobHistory, getJobParts } from '../../../api/jobs'
import { mapPartsToReviewCards } from '../../../adapters/studioAdapters'
import { MOCK_REVIEW_CARDS } from '../../../lib/fallbacks'

export function ReviewWorkspace() {
  const [statuses, setStatuses] = useState<Record<string, ReviewCardStatus>>({})
  const [openComparison, setOpenComparison] = useState<string | null>(null)
  const [cards, setCards] = useState<ReviewCardData[]>(MOCK_REVIEW_CARDS)
  const [reviewLoading, setReviewLoading] = useState(true)

  useEffect(() => {
    getJobHistory(5, 0)
      .then((res) => {
        const completedJob = res.items.find(
          (item) => item.status === 'completed' || item.status === 'completed_with_errors',
        )
        if (!completedJob) return
        return getJobParts(completedJob.job_id)
      })
      .then((parts) => {
        if (!parts) return
        const mapped = mapPartsToReviewCards(parts)
        if (mapped.length > 0) setCards(mapped)
      })
      .catch(() => {
        // silent — MOCK_REVIEW_CARDS remain
      })
      .finally(() => setReviewLoading(false))
  }, [])

  const avgConfidence = Math.round(
    cards.reduce((sum, c) => sum + c.confidence, 0) / cards.length
  )

  const getStatus = (id: string): ReviewCardStatus => statuses[id] ?? 'pending'

  const approvedCount = cards.filter((c) => getStatus(c.id) === 'approved').length
  const allApproved = approvedCount === cards.length

  const handleApprove = (id: string) =>
    setStatuses((prev) => ({ ...prev, [id]: 'approved' }))

  const handleReject = (id: string) => {
    setStatuses((prev) => ({ ...prev, [id]: 'rejected' }))
    if (openComparison === id) setOpenComparison(null)
  }

  const handleRestore = (id: string) =>
    setStatuses((prev) => ({ ...prev, [id]: 'pending' }))

  const handleCompare = (id: string) =>
    setOpenComparison((prev) => (prev === id ? null : id))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* AI Summary Bar */}
      <div
        style={{
          backgroundColor: 'var(--surface-card)',
          borderBottom: '1px solid var(--border-subtle)',
          padding: 'var(--space-3) var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <AIChip variant="applied" label="AI Director" />
          <ScoreBadge value={avgConfidence} size="sm" />
        </div>
        {reviewLoading && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            Loading…
          </span>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              height: '20px',
              padding: '0 var(--space-2)',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--surface-input)',
              color: 'var(--text-tertiary)',
              fontSize: 'var(--text-xs)',
            }}
          >
            {cards.length} recommendations
          </span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              height: '20px',
              padding: '0 var(--space-2)',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--accent-subtle)',
              color: 'var(--accent-primary)',
              fontSize: 'var(--text-xs)',
            }}
          >
            High confidence
          </span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              height: '20px',
              padding: '0 var(--space-2)',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--status-success-bg)',
              color: 'var(--status-success)',
              fontSize: 'var(--text-xs)',
            }}
          >
            ↑ Avg +8% retention
          </span>
        </div>
      </div>

      {/* Scrollable card list */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--space-3) var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
        }}
      >
        {cards.map((card) => (
          <div key={card.id}>
            <ReviewCard
              data={card}
              status={getStatus(card.id)}
              isComparisonOpen={openComparison === card.id}
              onApprove={() => handleApprove(card.id)}
              onReject={() => handleReject(card.id)}
              onRestore={() => handleRestore(card.id)}
              onCompare={() => handleCompare(card.id)}
            />
            <ComparisonPanel
              isOpen={openComparison === card.id}
              onClose={() => setOpenComparison(null)}
            />
          </div>
        ))}
      </div>

      {/* Publish Readiness Bar */}
      <div
        style={{
          borderTop: `1px solid ${allApproved ? 'var(--status-success)' : 'var(--border-subtle)'}`,
          backgroundColor: allApproved ? 'var(--status-success-bg)' : 'var(--surface-card)',
          padding: 'var(--space-3) var(--space-4)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          transition: 'background-color var(--duration-card) var(--ease-out), border-color var(--duration-card) var(--ease-out)',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-sm)',
            color: allApproved ? 'var(--status-success)' : 'var(--text-secondary)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
          }}
        >
          {allApproved
            ? `${cards.length} clips approved`
            : `${approvedCount} of ${cards.length} approved`}
        </span>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            height: '20px',
            padding: '0 var(--space-2)',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: allApproved ? 'var(--status-success)' : 'transparent',
            color: allApproved ? 'var(--text-inverse)' : 'var(--text-tertiary)',
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
          }}
        >
          {allApproved ? 'Ready for publish' : 'Approve all clips to publish'}
        </span>
      </div>
    </div>
  )
}
