import { useState } from 'react'
import { type StudioStep } from '../../../stores/uiStore'
import { useI18n } from '../../../i18n/useI18n'
import { useUIStore } from '../../../stores/uiStore'

interface StepNavProps {
  currentStep: StudioStep | null
  onStepClick: (step: StudioStep) => void
}

const STEP_ORDER: StudioStep[] = [
  'source', 'analyze', 'plan', 'edit', 'review', 'render', 'monitor', 'results',
]

export function StepNav({ currentStep, onStepClick }: StepNavProps) {
  const { t } = useI18n()
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)

  const activeStep = currentStep ?? 'source'
  const currentIndex = STEP_ORDER.indexOf(activeStep)

  return (
    <nav style={s.nav}>
      {/* Logo strip at top */}
      <div style={s.logo}>
        <span style={s.logoMark}>✦</span>
      </div>

      {/* Steps */}
      <div style={s.stepList}>
        {STEP_ORDER.map((step, i) => {
          const isDone   = i < currentIndex
          const isActive = i === currentIndex
          const isFuture = i > currentIndex
          const isHovered = hoveredIdx === i && isDone

          const bgColor = isActive
            ? 'rgba(123,97,255,0.1)'
            : isHovered
            ? 'rgba(255,255,255,0.04)'
            : 'transparent'

          return (
            <div
              key={step}
              onClick={isDone ? () => onStepClick(step) : undefined}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              style={{
                ...s.item,
                backgroundColor: bgColor,
                cursor: isDone ? 'pointer' : 'default',
                opacity: isFuture ? 0.28 : 1,
              }}
            >
              {/* Left accent bar — active only */}
              {isActive && <div style={s.accentBar} />}

              {/* Circle */}
              <div style={{
                ...s.circle,
                backgroundColor: isActive
                  ? '#7B61FF'
                  : isDone
                  ? 'rgba(52,200,120,0.15)'
                  : 'var(--surface-input)',
                border: isActive
                  ? '1.5px solid #7B61FF'
                  : isDone
                  ? '1.5px solid rgba(52,200,120,0.5)'
                  : '1.5px solid var(--border-subtle)',
                color: isActive
                  ? '#fff'
                  : isDone
                  ? 'var(--status-success)'
                  : 'var(--text-disabled)',
              }}>
                {isDone ? '✓' : String(i + 1).padStart(2, '0')}
              </div>

              {/* Label */}
              <div style={s.labelWrap}>
                <span style={{
                  ...s.stepNum,
                  color: isActive ? 'rgba(123,97,255,0.7)' : 'var(--text-tertiary)',
                }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{
                  ...s.label,
                  color: isActive
                    ? 'var(--text-primary)'
                    : isDone
                    ? 'var(--text-secondary)'
                    : 'var(--text-tertiary)',
                  fontWeight: isActive ? 600 : 400,
                }}>
                  {t(`step_${step}` as any)}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Bottom */}
      <div style={s.bottom}>
        <div style={s.sep} />
        <button
          onClick={() => setActivePanel('home')}
          style={s.exitBtn}
        >
          <span style={s.exitIcon}>←</span>
          <span style={s.exitLabel}>Exit Studio</span>
        </button>
      </div>
    </nav>
  )
}

const s: Record<string, React.CSSProperties> = {
  nav: {
    width: '160px',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--surface-panel)',
    borderRight: '1px solid var(--border-subtle)',
    overflow: 'hidden',
  },
  logo: {
    height: '40px',
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
  },
  logoMark: {
    fontSize: '15px',
    background: 'linear-gradient(135deg, #7B61FF, #4D7CFF)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    flexShrink: 0,
  },
  stepList: {
    flex: 1,
    overflowY: 'auto',
    paddingTop: '8px',
    paddingBottom: '8px',
  },
  item: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    height: '44px',
    padding: '0 14px 0 16px',
    transition: 'background-color 0.12s ease',
    userSelect: 'none' as const,
  },
  accentBar: {
    position: 'absolute',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)',
    width: '3px',
    height: '22px',
    background: 'linear-gradient(180deg, #7B61FF, #4D7CFF)',
    borderRadius: '0 3px 3px 0',
  },
  circle: {
    width: '22px',
    height: '22px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '9px',
    fontWeight: 700,
    flexShrink: 0,
    lineHeight: 1,
    fontFamily: 'var(--font-mono)',
    transition: 'all 0.15s ease',
    letterSpacing: '-0.02em',
  },
  labelWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0px',
    minWidth: 0,
    overflow: 'hidden',
  },
  stepNum: {
    fontSize: '9px',
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.04em',
    lineHeight: 1,
    marginBottom: '1px',
  },
  label: {
    fontSize: '12px',
    lineHeight: 1.2,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    transition: 'color 0.15s ease',
    letterSpacing: '-0.01em',
  },
  bottom: {
    flexShrink: 0,
    paddingBottom: '12px',
  },
  sep: {
    height: '1px',
    backgroundColor: 'var(--border-subtle)',
    margin: '0 16px 8px',
  },
  exitBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    height: '36px',
    padding: '0 16px',
    width: '100%',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    opacity: 0.5,
    transition: 'opacity 0.12s ease',
  },
  exitIcon: {
    fontSize: '13px',
    color: 'var(--text-tertiary)',
    flexShrink: 0,
  },
  exitLabel: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
  },
}
