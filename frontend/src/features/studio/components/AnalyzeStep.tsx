import { useState, useEffect } from 'react'
import { useI18n } from '../../../i18n/useI18n'
import { getPreviewTranscript } from '../../../api/render'
import { EmptyState } from '../../../components/ui/EmptyState'

interface AnalyzeStepProps {
  sessionId: string | null
  sessionTitle: string
  sessionDuration: number
  onContinue: () => void
}

// ── Large progress ring ────────────────────────────────────────────────────────

function ProgressRing({ pct }: { pct: number }) {
  const r = 62
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - pct / 100)
  const isComplete = pct >= 100

  return (
    <div style={{ position: 'relative', width: '152px', height: '152px', flexShrink: 0 }}>
      {/* Glow */}
      <div style={{
        position: 'absolute',
        inset: '-12px',
        borderRadius: '50%',
        background: isComplete
          ? 'radial-gradient(circle, rgba(52,200,120,0.18) 0%, transparent 70%)'
          : 'radial-gradient(circle, rgba(123,97,255,0.2) 0%, transparent 70%)',
        transition: 'background 0.6s ease',
        pointerEvents: 'none',
      }} />
      <svg width="152" height="152" viewBox="0 0 152 152">
        {/* Track */}
        <circle cx="76" cy="76" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
        {/* Fill */}
        <circle
          cx="76" cy="76" r={r}
          fill="none"
          stroke={isComplete ? '#34C878' : 'url(#ringGrad)'}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          transform="rotate(-90 76 76)"
          style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.4s ease' }}
        />
        <defs>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7B61FF" />
            <stop offset="100%" stopColor="#4D7CFF" />
          </linearGradient>
        </defs>
      </svg>
      {/* Center text */}
      <div style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '2px',
      }}>
        {isComplete ? (
          <span style={{ fontSize: '28px', color: '#34C878', lineHeight: 1 }}>✓</span>
        ) : (
          <>
            <span style={{ fontSize: '28px', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', lineHeight: 1, letterSpacing: '-0.03em' }}>
              {pct}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>%</span>
          </>
        )}
      </div>
    </div>
  )
}

// ── Check row item ─────────────────────────────────────────────────────────────

interface CheckItemState {
  label: string
  sublabel: string
  done: boolean
  active: boolean
}

function CheckRow({ item }: { item: CheckItemState }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '10px 14px',
      borderRadius: '10px',
      backgroundColor: item.done
        ? 'rgba(52,200,120,0.05)'
        : item.active
        ? 'rgba(123,97,255,0.06)'
        : 'var(--surface-input)',
      border: '1px solid ' + (
        item.done ? 'rgba(52,200,120,0.2)'
        : item.active ? 'rgba(123,97,255,0.2)'
        : 'var(--border-subtle)'
      ),
      transition: 'all 0.3s ease',
    }}>
      <div style={{
        width: '26px',
        height: '26px',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        backgroundColor: item.done
          ? 'rgba(52,200,120,0.15)'
          : item.active
          ? 'rgba(123,97,255,0.15)'
          : 'var(--surface-panel)',
        border: '1.5px solid ' + (
          item.done ? 'rgba(52,200,120,0.5)'
          : item.active ? 'rgba(123,97,255,0.4)'
          : 'var(--border-subtle)'
        ),
      }}>
        {item.done ? (
          <span style={{ color: '#34C878', fontSize: '11px', fontWeight: 700 }}>✓</span>
        ) : item.active ? (
          <span style={{
            display: 'inline-block',
            width: '10px',
            height: '10px',
            border: '2px solid rgba(123,97,255,0.3)',
            borderTopColor: '#7B61FF',
            borderRadius: '50%',
            animation: 'az-spin 0.8s linear infinite',
          }} />
        ) : (
          <span style={{ color: 'var(--text-tertiary)', fontSize: '10px' }}>○</span>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--text-xs)',
          fontWeight: 500,
          color: item.done ? 'var(--text-primary)' : item.active ? 'var(--text-secondary)' : 'var(--text-tertiary)',
          lineHeight: 1.4,
        }}>
          {item.label}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '1px' }}>
          {item.sublabel}
        </div>
      </div>
    </div>
  )
}

// ── AnalyzeStep ───────────────────────────────────────────────────────────────

interface StepDef {
  labelKey: string
  sublabelKey: string
  doneKey: string
  alwaysInProgress?: boolean
}

const STEPS: StepDef[] = [
  { labelKey: 'analyze_transcript',   sublabelKey: 'analyze_transcript_building', doneKey: 'analyze_transcript_ready' },
  { labelKey: 'analyze_section',      sublabelKey: 'analyze_moments_detecting',   doneKey: 'analyze_moments_done' },
  { labelKey: 'analyze_topics_found', sublabelKey: 'analyze_scanning',            doneKey: 'analyze_topics_found' },
  { labelKey: 'analyze_viral_found',  sublabelKey: 'analyze_scanning',            doneKey: 'analyze_viral_found' },
  { labelKey: 'analyze_hook_found',   sublabelKey: 'analyze_scanning',            doneKey: 'analyze_hook_found', alwaysInProgress: true },
]

export function AnalyzeStep({ sessionId, sessionTitle, sessionDuration, onContinue }: AnalyzeStepProps) {
  const { t } = useI18n()
  const [transcriptReady, setTranscriptReady] = useState(false)
  const [pct, setPct] = useState(15)

  useEffect(() => {
    if (!sessionId) return
    setTranscriptReady(false)
    setPct(15)
    const check = async () => {
      try {
        const res = await getPreviewTranscript(sessionId)
        if (res.segments.length > 0) setTranscriptReady(true)
      } catch { /* not ready */ }
    }
    check()
    const id = window.setInterval(check, 3000)
    return () => window.clearInterval(id)
  }, [sessionId])

  useEffect(() => {
    if (transcriptReady) { setPct(100); return }
    const id = window.setInterval(() => {
      setPct((p) => (p < 95 ? p + Math.ceil((95 - p) / 12) : p))
    }, 600)
    return () => window.clearInterval(id)
  }, [transcriptReady])

  if (!sessionId) {
    return (
      <div style={s.page}>
        <EmptyState primary={t('analyze_no_session')} secondary={t('analyze_no_session_sub')} />
      </div>
    )
  }

  const durationText = sessionDuration > 0
    ? `${Math.floor(sessionDuration / 60)}m ${Math.floor(sessionDuration % 60)}s`
    : null

  const items: CheckItemState[] = STEPS.map((step, i) => {
    const stepDoneCount = transcriptReady ? STEPS.length : Math.floor(pct / 25)
    const isDone = i < stepDoneCount && !step.alwaysInProgress
    return {
      label: t(step.labelKey as any),
      sublabel: isDone ? t(step.doneKey as any) : step.alwaysInProgress ? '…' : t(step.sublabelKey as any),
      done: transcriptReady && !step.alwaysInProgress && i < 4,
      active: !isDone,
    }
  })

  return (
    <>
      <style>{`@keyframes az-spin { to { transform: rotate(360deg); } }`}</style>
      <div style={s.page}>
        {/* Top header bar */}
        <div style={s.headerBar}>
          <div style={s.headerLeft}>
            <span style={s.headerTitle}>
              {transcriptReady ? t('analyze_complete') : t('analyze_scanning')}
            </span>
            {durationText && (
              <span style={s.durationBadge}>{durationText}</span>
            )}
          </div>
          {transcriptReady ? (
            <div style={s.completeBadge}>
              <span style={{ color: '#34C878', fontSize: '12px' }}>✓</span>
              <span>Analysis complete</span>
            </div>
          ) : (
            <div style={s.aiChip}>
              <span style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: '#7B61FF',
                boxShadow: '0 0 8px rgba(123,97,255,0.8)',
                animation: 'az-pulse 2s ease-in-out infinite',
              }} />
              <span>AI Director</span>
            </div>
          )}
        </div>

        {/* Body */}
        <div style={s.body}>
          <div style={s.centerCol}>
            {/* Ring */}
            <ProgressRing pct={pct} />

            {/* Status label */}
            <div style={s.statusWrap}>
              <p style={s.statusTitle}>
                {transcriptReady ? 'Video Analyzed' : (sessionTitle ? `Analyzing: ${sessionTitle.slice(0, 36)}` : 'Analyzing video…')}
              </p>
              <p style={s.statusSub}>
                {transcriptReady
                  ? 'AI Director has finished analyzing. Review the plan below.'
                  : 'AI Director is processing your content to find the best clips.'}
              </p>
            </div>

            {/* Checklist */}
            <div style={s.checklist}>
              {items.map((item, i) => (
                <CheckRow key={i} item={item} />
              ))}
            </div>

            {/* Insights (when done) */}
            {transcriptReady && (
              <div style={s.insightsBox}>
                <div style={s.insightsHeader}>
                  <span style={s.insightsIcon}>✦</span>
                  <span style={s.insightsTitle}>AI Insights</span>
                </div>
                <div style={s.tagsRow}>
                  {['#productivity', '#ai-tools', '#tips', '#mindset'].map((tag) => (
                    <span key={tag} style={s.tag}>{tag}</span>
                  ))}
                </div>
                <div style={s.insightsList}>
                  <div style={s.insightItem}>
                    <span style={s.insightDot} />
                    <span>{t('analyze_topics_found')}</span>
                  </div>
                  <div style={s.insightItem}>
                    <span style={s.insightDot} />
                    <span>{t('analyze_viral_found')}</span>
                  </div>
                  <div style={s.insightItem}>
                    <span style={s.insightDot} />
                    <span>{t('analyze_hook_found')}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={s.footer}>
          {transcriptReady ? (
            <button onClick={onContinue} style={s.primaryBtn}>
              {t('analyze_view_plan')} →
            </button>
          ) : (
            <button onClick={onContinue} style={s.skipBtn}>
              {t('analyze_skip')}
            </button>
          )}
        </div>
      </div>
      <style>{`
        @keyframes az-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </>
  )
}

const s: Record<string, React.CSSProperties> = {
  page: {
    flex: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--surface-base)',
  },
  headerBar: {
    height: '52px',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-6)',
    borderBottom: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--surface-card)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  headerTitle: {
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  durationBadge: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
    backgroundColor: 'var(--surface-input)',
    padding: '2px 8px',
    borderRadius: '6px',
    border: '1px solid var(--border-subtle)',
  },
  aiChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '7px',
    padding: '5px 12px',
    borderRadius: '20px',
    backgroundColor: 'rgba(123,97,255,0.1)',
    border: '1px solid rgba(123,97,255,0.25)',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    color: '#7B61FF',
  },
  completeBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '7px',
    padding: '5px 12px',
    borderRadius: '20px',
    backgroundColor: 'rgba(52,200,120,0.1)',
    border: '1px solid rgba(52,200,120,0.25)',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    color: '#34C878',
  },
  body: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    justifyContent: 'center',
    padding: 'var(--space-6) var(--space-6)',
  },
  centerCol: {
    width: '100%',
    maxWidth: '540px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 'var(--space-5)',
    paddingBottom: 'var(--space-4)',
  },
  statusWrap: {
    textAlign: 'center' as const,
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  statusTitle: {
    margin: 0,
    fontSize: 'var(--text-base)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '-0.01em',
  },
  statusSub: {
    margin: 0,
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
    lineHeight: 1.6,
    maxWidth: '380px',
  },
  checklist: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  insightsBox: {
    width: '100%',
    backgroundColor: 'var(--surface-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '12px',
    padding: 'var(--space-4)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  insightsHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '7px',
  },
  insightsIcon: {
    fontSize: '12px',
    background: 'linear-gradient(135deg, #7B61FF, #4D7CFF)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  insightsTitle: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    color: 'var(--text-tertiary)',
  },
  tagsRow: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '6px',
  },
  tag: {
    fontSize: '11px',
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-subtle)',
    padding: '2px 8px',
    borderRadius: '10px',
    border: '1px solid rgba(77,124,255,0.2)',
  },
  insightsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  insightItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    fontSize: 'var(--text-xs)',
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
  },
  insightDot: {
    width: '5px',
    height: '5px',
    borderRadius: '50%',
    backgroundColor: '#7B61FF',
    marginTop: '5px',
    flexShrink: 0,
  },
  footer: {
    flexShrink: 0,
    padding: 'var(--space-4) var(--space-6)',
    borderTop: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--surface-card)',
    display: 'flex',
    justifyContent: 'flex-end',
  },
  primaryBtn: {
    height: '40px',
    padding: '0 var(--space-6)',
    border: 'none',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '0.01em',
    boxShadow: '0 4px 12px rgba(123,97,255,0.3)',
  },
  skipBtn: {
    height: '40px',
    padding: '0 var(--space-6)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '10px',
    backgroundColor: 'transparent',
    color: 'var(--text-tertiary)',
    fontSize: 'var(--text-sm)',
    cursor: 'pointer',
  },
}
