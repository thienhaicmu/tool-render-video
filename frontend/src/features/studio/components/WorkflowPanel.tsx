import { useState } from 'react'
import { type StudioStep } from '../../../stores/uiStore'
import { EmptyState } from '../../../components/ui/EmptyState'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { AIPlanCard } from './AIPlanCard'
import { ReviewWorkspace } from './ReviewWorkspace'

export interface WorkflowPanelProps {
  studioStep: StudioStep | null
}

const STEP_TITLES: Record<StudioStep, string> = {
  source:  'Source Setup',
  analyze: 'AI Analysis',
  plan:    'Plan',
  edit:    'Edit Settings',
  render:  'Render Options',
  review:  'Review',
}

const STEP_SECTIONS: Record<StudioStep, string[]> = {
  source:  ['Source Settings'],
  analyze: ['Analysis Config'],
  plan:    ['Plan Settings', 'Clip Selection'],
  edit:    ['Clip Settings', 'Subtitle', 'Voice', 'AI Assistance', 'Platform'],
  render:  ['Render Options'],
  review:  ['Review Summary'],
}

const SAMPLE_AI_PLAN = [
  {
    title: 'Hook Opening',
    confidence: 87,
    reasoning: 'Hook identified at 0:04. Strong visual cut predicted to retain audience.',
    impact: '+12% watch duration',
    tags: ['hook', '0:04', 'high retention'],
  },
  {
    title: 'Climax Moment',
    confidence: 74,
    reasoning: 'Peak energy moment at 1:32. AI markers indicate high engagement.',
    impact: '+8% completion rate',
    tags: ['climax', '1:32', 'energy peak'],
  },
  {
    title: 'Call-to-Action Close',
    confidence: 61,
    reasoning: 'Strong verbal CTA detected at 3:48. Subtitle density peaks here.',
    impact: '+5% conversion signal',
    tags: ['cta', '3:48', 'verbal'],
  },
]

export function WorkflowPanel({ studioStep }: WorkflowPanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selectedCards, setSelectedCards] = useState<number[]>([])

  const toggleSection = (title: string) => {
    setExpanded((prev) => ({ ...prev, [title]: !prev[title] }))
  }

  const isSectionExpanded = (title: string, index: number) =>
    expanded[title] !== undefined ? expanded[title] : index === 0

  return (
    <div
      style={{
        width: 'var(--inspector-width)',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--surface-panel)',
        borderLeft: '1px solid var(--border-subtle)',
        overflowY: 'auto',
      }}
    >
      {/* Panel header */}
      <div
        style={{
          height: '40px',
          display: 'flex',
          alignItems: 'center',
          padding: '0 var(--space-4)',
          flexShrink: 0,
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-base)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-primary)',
          }}
        >
          {studioStep !== null ? STEP_TITLES[studioStep] : 'Workflow'}
        </span>
      </div>

      {/* Panel body */}
      {studioStep === null ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState
            primary="Select a step to begin"
            secondary="Use the strip above to navigate"
          />
        </div>
      ) : studioStep === 'plan' ? (
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
          <div
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-tertiary)',
              marginBottom: 'var(--space-1)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            AI Recommendations
          </div>
          {SAMPLE_AI_PLAN.map((card, i) => (
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
      ) : studioStep === 'review' ? (
        <ReviewWorkspace />
      ) : (
        <div style={{ flex: 1 }}>
          {STEP_SECTIONS[studioStep].map((section, i) => (
            <div key={section}>
              <SectionHeader
                title={section}
                expanded={isSectionExpanded(section, i)}
                onToggle={() => toggleSection(section)}
              />
              {isSectionExpanded(section, i) && (
                <div
                  style={{
                    padding: 'var(--space-3) var(--space-4)',
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  Content coming in B9+
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
