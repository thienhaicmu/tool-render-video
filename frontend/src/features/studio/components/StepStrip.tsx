import { useState } from 'react'
import { type StudioStep } from '../../../stores/uiStore'

export interface StepStripProps {
  currentStep: StudioStep | null
  completedSteps?: StudioStep[]
  onStepClick: (step: StudioStep) => void
}

const STEP_ORDER: StudioStep[] = ['source', 'analyze', 'plan', 'edit', 'render', 'review']
const STEP_LABELS: Record<StudioStep, string> = {
  source:  'Source',
  analyze: 'Analyze',
  plan:    'Plan',
  edit:    'Edit',
  render:  'Render',
  review:  'Review',
}

export function StepStrip({ currentStep, completedSteps = [], onStepClick }: StepStripProps) {
  const currentIndex = currentStep !== null ? STEP_ORDER.indexOf(currentStep) : -1
  const [hoveredStep, setHoveredStep] = useState<StudioStep | null>(null)

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: 'var(--step-strip-height)',
        backgroundColor: 'var(--surface-panel)',
        borderBottom: '1px solid var(--border-subtle)',
        flexShrink: 0,
        padding: '0 var(--space-6)',
        gap: 0,
      }}
    >
      {STEP_ORDER.map((step, i) => {
        const isActive   = step === currentStep
        const isDone     = currentIndex > -1 ? i < currentIndex : completedSteps.includes(step)
        const isClickable = isDone && !isActive

        const numberBg   = isActive ? 'var(--accent-primary)'
                         : isDone   ? 'color-mix(in srgb, var(--status-success) 20%, transparent)'
                         :            'var(--surface-card)'
        const numberColor = isActive ? 'var(--text-primary)'
                          : isDone   ? 'var(--status-success)'
                          :            'var(--text-tertiary)'
        const labelColor  = isActive ? 'var(--text-primary)'
                          : isDone   ? 'var(--text-secondary)'
                          :            'var(--text-tertiary)'
        const labelWeight = isActive ? ('var(--weight-semibold)' as unknown as number) : ('var(--weight-regular)' as unknown as number)

        return (
          <div key={step} style={{ display: 'flex', alignItems: 'center' }}>
            {/* Step item */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                flexDirection: 'column',
                gap: 'var(--space-1)',
                cursor: isClickable ? 'pointer' : 'default',
                opacity: isActive || isDone ? 1 : 0.65,
                transition: 'background-color var(--duration-instant) var(--ease-out), opacity var(--duration-fast) var(--ease-in-out)',
                backgroundColor: isClickable && hoveredStep === step ? 'var(--surface-card)' : 'transparent',
                borderRadius: 'var(--radius-md)',
                padding: '0 var(--space-2)',
              }}
              onClick={isClickable ? () => onStepClick(step) : undefined}
              onMouseEnter={() => { if (isClickable) setHoveredStep(step) }}
              onMouseLeave={() => setHoveredStep(null)}
            >
              {/* Number circle */}
              <div
                className="step-number"
                style={{
                  width: '22px',
                  height: '22px',
                  borderRadius: '50%',
                  backgroundColor: numberBg,
                  color: numberColor,
                  fontSize: 'var(--text-sm)',
                  fontWeight: 'var(--weight-semibold)' as unknown as number,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                {i + 1}
              </div>
              {/* Label */}
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: labelColor,
                  fontWeight: labelWeight,
                  whiteSpace: 'nowrap',
                }}
              >
                {STEP_LABELS[step]}
              </span>
            </div>

            {/* Connector (not after last step) */}
            {i < STEP_ORDER.length - 1 && (
              <div
                style={{
                  width: '32px',
                  height: '1px',
                  backgroundColor: isDone ? 'var(--status-success)' : 'var(--border-subtle)',
                  margin: '0 var(--space-2)',
                  alignSelf: 'flex-start',
                  marginTop: '11px',
                }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
