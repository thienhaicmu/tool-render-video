import { useState } from 'react'
import { AIPlanCard } from './AIPlanCard'
import { SAMPLE_AI_PLAN } from '../../../lib/fallbacks'
import type { AIPlanCardData } from '../../../adapters/studioAdapters'

interface PlanStepProps {
  planCards: AIPlanCardData[] | null
  planLoading: boolean
  planError: string | null
}

export function PlanStep({ planCards, planLoading, planError }: PlanStepProps) {
  const [selectedCards, setSelectedCards] = useState<number[]>([])

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-3) var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 'var(--space-1)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        AI Recommendations
        {planError && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            {planError}
          </span>
        )}
      </div>
      {planLoading ? (
        /* Skeleton loading */
        [0, 1, 2].map((i) => (
          <div
            key={i}
            style={{
              height: '96px',
              backgroundColor: 'var(--surface-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg)',
              opacity: 0.6,
            }}
          />
        ))
      ) : (planCards ?? SAMPLE_AI_PLAN).map((card, i) => (
        <AIPlanCard
          key={card.title}
          {...card}
          selected={selectedCards.includes(i)}
          onApprove={() =>
            setSelectedCards((prev) =>
              prev.includes(i) ? prev.filter((j) => j !== i) : [...prev, i]
            )
          }
          onIgnore={() => setSelectedCards((prev) => prev.filter((j) => j !== i))}
        />
      ))}
    </div>
  )
}
