import { useState } from 'react'
import { type StudioStep } from '../../../stores/uiStore'
import { EmptyState } from '../../../components/ui/EmptyState'
import { SectionHeader } from '../../../components/ui/SectionHeader'

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

export function WorkflowPanel({ studioStep }: WorkflowPanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

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
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-sm)',
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
                  Content coming in B7
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
