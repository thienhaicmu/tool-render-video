import { useState, useEffect } from 'react'
import { useEditStore } from '../../../stores/editStore'
import { useI18n } from '../../../i18n/useI18n'
import { getPreviewTranscript } from '../../../api/render'
import { mapSegmentsToPlan, formatTimecode, type AIPlanCardData } from '../../../adapters/studioAdapters'

interface PlanStepProps {
  sessionId: string | null
  onCardsLoaded: (cards: AIPlanCardData[] | null) => void
  onContinue: () => void
}

// ── Score bar ──────────────────────────────────────────────────────────────────

function ScoreBar({ value }: { value: number }) {
  const color = value >= 70 ? '#34C878' : value >= 40 ? '#F5A623' : '#E05252'
  const bg = value >= 70 ? 'rgba(52,200,120,0.12)' : value >= 40 ? 'rgba(245,166,35,0.12)' : 'rgba(224,82,82,0.12)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, height: '3px', borderRadius: '2px', backgroundColor: 'var(--surface-input)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${value}%`, backgroundColor: color, borderRadius: '2px', transition: 'width 0.5s ease' }} />
      </div>
      <span style={{
        fontSize: '11px',
        fontFamily: 'var(--font-mono)',
        fontWeight: 700,
        color,
        minWidth: '26px',
        textAlign: 'right' as const,
        backgroundColor: bg,
        padding: '1px 5px',
        borderRadius: '5px',
      }}>
        {value}
      </span>
    </div>
  )
}

// ── Skeleton row ───────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr>
      <td colSpan={6} style={{ padding: '1px 0' }}>
        <div style={{
          height: '68px',
          backgroundColor: 'var(--surface-card)',
          opacity: 0.4,
          animation: 'plan-pulse 1.4s ease-in-out infinite',
        }} />
      </td>
    </tr>
  )
}

// ── Stat chip ──────────────────────────────────────────────────────────────────

function StatChip({ value, label, accent = false }: { value: string; label: string; accent?: boolean }) {
  return (
    <div style={{
      display: 'inline-flex',
      flexDirection: 'column',
      gap: '2px',
      padding: '8px 14px',
      borderRadius: '10px',
      backgroundColor: accent ? 'rgba(123,97,255,0.08)' : 'var(--surface-card)',
      border: `1px solid ${accent ? 'rgba(123,97,255,0.2)' : 'var(--border-subtle)'}`,
    }}>
      <span style={{
        fontSize: '16px',
        fontWeight: 800,
        color: accent ? '#7B61FF' : 'var(--text-primary)',
        fontFamily: 'var(--font-mono)',
        lineHeight: 1.1,
        letterSpacing: '-0.02em',
      }}>
        {value}
      </span>
      <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', letterSpacing: '0.03em', textTransform: 'uppercase' as const }}>
        {label}
      </span>
    </div>
  )
}

// ── PlanStep ───────────────────────────────────────────────────────────────────

export function PlanStep({ sessionId, onCardsLoaded, onContinue }: PlanStepProps) {
  const { t } = useI18n()
  const { settings, addClipLock, removeClipLock, clearClipLock } = useEditStore()
  const [cards, setCards] = useState<AIPlanCardData[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIndices, setSelectedIndices] = useState<number[]>([])
  const [hoveredRow, setHoveredRow] = useState<number | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setCards([])
      onCardsLoaded(null)
      return
    }
    setLoading(true)
    setSelectedIndices([])
    clearClipLock()

    getPreviewTranscript(sessionId)
      .then((res) => {
        const mapped = mapSegmentsToPlan(res.segments)
        setCards(mapped)
        onCardsLoaded(mapped.length > 0 ? mapped : null)
      })
      .catch(() => {
        setCards([])
        onCardsLoaded(null)
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  const totalDurationSec = cards.reduce((sum, c) => sum + (c.endSec - c.startSec), 0)
  const totalMin = Math.floor(totalDurationSec / 60)
  const totalSec = Math.floor(totalDurationSec % 60)
  const highViralCount = cards.filter((c) => c.confidence >= 70).length

  const toggleSelect = (i: number, card: AIPlanCardData) => {
    if (selectedIndices.includes(i)) {
      setSelectedIndices((prev) => prev.filter((j) => j !== i))
      const lockIdx = settings.clipLock?.findIndex(
        (r) => r.start_sec === card.startSec && r.end_sec === card.endSec,
      ) ?? -1
      if (lockIdx >= 0) removeClipLock(lockIdx)
    } else {
      setSelectedIndices((prev) => [...prev, i])
      addClipLock({ start_sec: card.startSec, end_sec: card.endSec })
    }
  }

  return (
    <>
      <style>{`
        @keyframes plan-pulse { 0%, 100% { opacity: 0.4 } 50% { opacity: 0.2 } }
      `}</style>

      <div style={s.page}>
        {/* Header */}
        <div style={s.header}>
          <div style={s.headerLeft}>
            <span style={s.headerTitle}>{t('plan_header')}</span>
            {!loading && cards.length > 0 && (
              <span style={s.countBadge}>{cards.length} clips</span>
            )}
          </div>
          <button style={s.regenBtn} disabled>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.5 15a9 9 0 11-2.8-7.2L23 10"/>
            </svg>
            {t('plan_regenerate')}
          </button>
        </div>

        {/* Stats */}
        {!loading && cards.length > 0 && (
          <div style={s.statsRow}>
            <StatChip value={`${cards.length}`} label={t('plan_clips')} accent />
            <StatChip value={`${totalMin}m ${totalSec}s`} label={t('plan_duration_label')} />
            <StatChip value={`${highViralCount}`} label="High viral" />
            <StatChip value={settings.aspectRatio} label={t('plan_aspect_label')} />
          </div>
        )}

        {/* Table */}
        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={{ ...s.th, width: '36px', textAlign: 'center' as const }}>#</th>
                <th style={{ ...s.th, width: '52px' }}>Clip</th>
                <th style={s.th}>{t('plan_col_topic')}</th>
                <th style={{ ...s.th, width: '110px' }}>{t('plan_col_duration')}</th>
                <th style={{ ...s.th, width: '120px' }}>{t('plan_col_score')}</th>
                <th style={{ ...s.th, width: '40px' }} />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [0, 1, 2, 3].map((i) => <SkeletonRow key={i} />)
              ) : cards.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center' as const, padding: '48px 24px', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
                    {t('plan_empty')}
                  </td>
                </tr>
              ) : (
                cards.map((card, i) => {
                  const isSelected = selectedIndices.includes(i)
                  const isHovered = hoveredRow === i
                  return (
                    <tr
                      key={`${card.startSec}-${card.endSec}`}
                      onMouseEnter={() => setHoveredRow(i)}
                      onMouseLeave={() => setHoveredRow(null)}
                      style={{
                        backgroundColor: isSelected
                          ? 'rgba(123,97,255,0.06)'
                          : isHovered
                          ? 'rgba(255,255,255,0.025)'
                          : 'transparent',
                        transition: 'background-color 0.1s ease',
                        cursor: 'default',
                      }}
                    >
                      {/* # */}
                      <td style={{ ...s.td, color: 'var(--text-tertiary)', fontSize: '11px', fontFamily: 'var(--font-mono)', textAlign: 'center' as const }}>
                        <div style={{
                          width: '22px',
                          height: '22px',
                          borderRadius: '50%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          margin: '0 auto',
                          backgroundColor: isSelected ? 'rgba(123,97,255,0.15)' : 'transparent',
                          color: isSelected ? '#7B61FF' : 'var(--text-tertiary)',
                          fontWeight: isSelected ? 700 : 400,
                          transition: 'all 0.15s ease',
                        }}>
                          {i + 1}
                        </div>
                      </td>

                      {/* Thumbnail */}
                      <td style={s.td}>
                        <div style={{
                          ...s.thumb,
                          borderColor: isSelected ? 'rgba(123,97,255,0.4)' : 'var(--border-subtle)',
                        }}>
                          <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.12)' }}>▶</span>
                        </div>
                      </td>

                      {/* Topic + tags */}
                      <td style={s.td}>
                        <div style={s.topicWrap}>
                          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                            {card.title.slice(0, 52)}
                          </span>
                          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' as const, marginTop: '3px' }}>
                            {card.tags.slice(0, 2).map((tag) => (
                              <span key={tag} style={s.tagPill}>{tag}</span>
                            ))}
                          </div>
                        </div>
                      </td>

                      {/* Duration */}
                      <td style={{ ...s.td, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' as const }}>
                        {formatTimecode(card.startSec)}<br />
                        <span style={{ color: 'var(--text-tertiary)', opacity: 0.6 }}>→ {formatTimecode(card.endSec)}</span>
                      </td>

                      {/* Score */}
                      <td style={s.td}>
                        <ScoreBar value={card.confidence} />
                      </td>

                      {/* Checkbox */}
                      <td style={{ ...s.td, textAlign: 'center' as const }}>
                        <div
                          onClick={() => toggleSelect(i, card)}
                          style={{
                            width: '18px',
                            height: '18px',
                            borderRadius: '5px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '0 auto',
                            cursor: 'pointer',
                            backgroundColor: isSelected ? '#7B61FF' : 'var(--surface-input)',
                            border: `1.5px solid ${isSelected ? '#7B61FF' : 'var(--border-default)'}`,
                            transition: 'all 0.12s ease',
                          }}
                        >
                          {isSelected && <span style={{ color: '#fff', fontSize: '9px', fontWeight: 800 }}>✓</span>}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div style={s.footer}>
          <div style={s.footerLeft}>
            {selectedIndices.length > 0 && (
              <span style={s.selectedNote}>
                {selectedIndices.length} clip{selectedIndices.length !== 1 ? 's' : ''} locked
              </span>
            )}
          </div>
          <button onClick={onContinue} style={s.continueBtn}>
            {t('plan_continue')} →
          </button>
        </div>
      </div>
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
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-6)',
    height: '52px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-card)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  headerTitle: {
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '-0.01em',
  },
  countBadge: {
    fontSize: '11px',
    fontWeight: 600,
    color: '#7B61FF',
    backgroundColor: 'rgba(123,97,255,0.1)',
    padding: '2px 8px',
    borderRadius: '10px',
    border: '1px solid rgba(123,97,255,0.2)',
  },
  regenBtn: {
    height: '30px',
    padding: '0 var(--space-3)',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    border: '1px solid var(--border-subtle)',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: 'var(--text-tertiary)',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'not-allowed',
    opacity: 0.5,
  },
  statsRow: {
    display: 'flex',
    gap: 'var(--space-3)',
    padding: 'var(--space-3) var(--space-6)',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-panel)',
    flexWrap: 'wrap' as const,
    alignItems: 'center',
  },
  tableWrap: {
    flex: 1,
    overflowY: 'auto',
    minHeight: 0,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
  },
  th: {
    position: 'sticky' as const,
    top: 0,
    padding: '9px 12px',
    textAlign: 'left' as const,
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.07em',
    textTransform: 'uppercase' as const,
    color: 'var(--text-tertiary)',
    borderBottom: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--surface-panel)',
    zIndex: 1,
    whiteSpace: 'nowrap' as const,
  },
  td: {
    padding: '10px 12px',
    borderBottom: '1px solid rgba(255,255,255,0.04)',
    verticalAlign: 'middle' as const,
  },
  thumb: {
    width: '38px',
    height: '66px',
    backgroundColor: '#0A0C11',
    borderRadius: '5px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    border: '1px solid',
    transition: 'border-color 0.15s ease',
  },
  topicWrap: {
    display: 'flex',
    flexDirection: 'column',
  },
  tagPill: {
    fontSize: '10px',
    color: 'var(--text-tertiary)',
    backgroundColor: 'var(--surface-input)',
    padding: '1px 6px',
    borderRadius: '6px',
    border: '1px solid var(--border-subtle)',
    fontFamily: 'var(--font-mono)',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-3) var(--space-6)',
    borderTop: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-card)',
  },
  footerLeft: {
    display: 'flex',
    alignItems: 'center',
  },
  selectedNote: {
    fontSize: '11px',
    color: '#7B61FF',
    fontWeight: 600,
  },
  continueBtn: {
    height: '36px',
    padding: '0 var(--space-6)',
    border: 'none',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '0.01em',
    boxShadow: '0 3px 10px rgba(123,97,255,0.3)',
  },
}
