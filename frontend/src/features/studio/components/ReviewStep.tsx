import { useState, useEffect } from 'react'
import { useEditStore } from '../../../stores/editStore'
import { useI18n } from '../../../i18n/useI18n'
import { formatTimecode, type AIPlanCardData } from '../../../adapters/studioAdapters'

interface ReviewStepProps {
  planCards: AIPlanCardData[] | null
  onContinue: () => void
}

// ── Clip card ──────────────────────────────────────────────────────────────────

interface ClipCardProps {
  card: AIPlanCardData
  index: number
  selected: boolean
  onToggle: () => void
}

function ClipCard({ card, index, selected, onToggle }: ClipCardProps) {
  const [hovered, setHovered] = useState(false)
  const score = card.confidence
  const scoreColor = score >= 70 ? '#34C878' : score >= 40 ? '#F5A623' : '#E05252'
  const scoreTier = score >= 80 ? 'High' : score >= 60 ? 'Good' : score >= 40 ? 'Fair' : 'Low'
  const durationSec = Math.round(card.endSec - card.startSec)
  const isHook = card.startSec < 30

  return (
    <div
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: '12px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        cursor: 'pointer',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        transform: hovered ? 'translateY(-2px)' : 'none',
        boxShadow: selected
          ? '0 0 0 2px #34C878, 0 8px 24px rgba(0,0,0,0.4)'
          : hovered
          ? '0 8px 20px rgba(0,0,0,0.35)'
          : '0 2px 8px rgba(0,0,0,0.2)',
        backgroundColor: 'var(--surface-card)',
      }}
    >
      {/* Thumbnail (9:16) */}
      <div style={{ position: 'relative', backgroundColor: '#0A0C11', paddingTop: '177.78%' }}>
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            backgroundColor: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '16px', marginLeft: '2px' }}>▶</span>
          </div>
        </div>

        {/* Index badge */}
        <div style={{
          position: 'absolute',
          top: '8px',
          left: '8px',
          width: '22px',
          height: '22px',
          borderRadius: '50%',
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '10px',
          fontWeight: 700,
          color: 'rgba(255,255,255,0.6)',
          fontFamily: 'var(--font-mono)',
          backdropFilter: 'blur(4px)',
        }}>
          {index + 1}
        </div>

        {/* Hook badge — top right, only for opening clips */}
        {isHook && (
          <div style={{
            position: 'absolute',
            top: '8px',
            right: '8px',
            background: 'linear-gradient(135deg, #F5A623, #E8732A)',
            borderRadius: '5px',
            padding: '2px 5px',
            fontSize: '8.5px',
            fontWeight: 700,
            color: '#fff',
            letterSpacing: '0.04em',
            textTransform: 'uppercase' as const,
          }}>
            Hook
          </div>
        )}

        {/* Viral score badge */}
        <div style={{
          position: 'absolute',
          bottom: '8px',
          right: '8px',
          backgroundColor: 'rgba(0,0,0,0.82)',
          border: `1px solid ${scoreColor}`,
          borderRadius: '7px',
          padding: '3px 7px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          backdropFilter: 'blur(4px)',
          gap: '0',
        }}>
          <span style={{ fontSize: '12px', fontWeight: 800, color: scoreColor, fontFamily: 'var(--font-mono)', lineHeight: 1.1 }}>{score}</span>
          <span style={{ fontSize: '7.5px', fontWeight: 600, color: scoreColor, letterSpacing: '0.05em', opacity: 0.8 }}>VIRAL</span>
        </div>

        {/* Duration badge */}
        <div style={{
          position: 'absolute',
          bottom: '8px',
          left: '8px',
          backgroundColor: 'rgba(0,0,0,0.75)',
          borderRadius: '6px',
          padding: '2px 6px',
          fontSize: '10px',
          color: 'rgba(255,255,255,0.6)',
          fontFamily: 'var(--font-mono)',
          backdropFilter: 'blur(4px)',
        }}>
          {durationSec}s
        </div>

        {/* Selected overlay */}
        {selected && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(52,200,120,0.08)',
          }}>
            <div style={{
              position: 'absolute',
              top: '8px',
              right: isHook ? '44px' : '8px',
              width: '22px',
              height: '22px',
              borderRadius: '50%',
              backgroundColor: '#34C878',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              fontWeight: 800,
              color: '#fff',
            }}>✓</div>
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ padding: '8px 10px 10px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
        <span style={{
          fontSize: '11px',
          fontWeight: 600,
          color: 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' as const,
          lineHeight: 1.3,
        }}>
          {card.title.slice(0, 30)}
        </span>

        {/* Score bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <div style={{
            flex: 1,
            height: '3px',
            borderRadius: '2px',
            backgroundColor: 'rgba(255,255,255,0.06)',
            overflow: 'hidden',
          }}>
            <div style={{
              width: `${score}%`,
              height: '100%',
              borderRadius: '2px',
              background: `linear-gradient(90deg, ${scoreColor}80, ${scoreColor})`,
            }} />
          </div>
          <span style={{ fontSize: '9px', color: scoreColor, fontWeight: 700, flexShrink: 0 }}>{scoreTier}</span>
        </div>

        <span style={{
          fontSize: '10px',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)',
        }}>
          {formatTimecode(card.startSec)} → {formatTimecode(card.endSec)}
        </span>
      </div>
    </div>
  )
}

// ── ReviewStep ────────────────────────────────────────────────────────────────

export function ReviewStep({ planCards, onContinue }: ReviewStepProps) {
  const { t } = useI18n()
  const { addClipLock, clearClipLock } = useEditStore()
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set())

  const cards = planCards ?? []

  useEffect(() => {
    clearClipLock()
    selectedIndices.forEach((i) => {
      const card = cards[i]
      if (card) addClipLock({ start_sec: card.startSec, end_sec: card.endSec })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIndices])

  const toggleCard = (i: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  const n = selectedIndices.size
  const allSelected = n === cards.length && cards.length > 0

  if (cards.length === 0) {
    return (
      <div style={s.page}>
        <div style={s.empty}>
          <span style={{ fontSize: '40px', opacity: 0.12 }}>🎬</span>
          <p style={s.emptyText}>No clips to review. Continue to configure render settings.</p>
          <button onClick={onContinue} style={s.approveBtn}>{t('review_approve_btn')}</button>
        </div>
      </div>
    )
  }

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerLeft}>
          <span style={s.headerTitle}>{t('review_header')}</span>
          {cards.length > 0 && (
            <span style={s.totalBadge}>{cards.length} clips</span>
          )}
        </div>
        <div style={s.headerActions}>
          <button
            onClick={() => setSelectedIndices(new Set(cards.map((_, i) => i)))}
            style={{ ...s.ghostBtn, ...(allSelected ? s.ghostBtnActive : {}) }}
          >
            {t('review_select_all')}
          </button>
          <button
            onClick={() => setSelectedIndices(new Set())}
            style={s.ghostBtn}
          >
            {t('review_deselect')}
          </button>
        </div>
      </div>

      {/* Grid */}
      <div style={s.grid}>
        {cards.map((card, i) => (
          <ClipCard
            key={`${card.startSec}-${card.endSec}`}
            card={card}
            index={i}
            selected={selectedIndices.has(i)}
            onToggle={() => toggleCard(i)}
          />
        ))}
      </div>

      {/* Footer */}
      <div style={s.footer}>
        <div style={s.footerInfo}>
          <span style={s.selectedCount}>
            <span style={{ color: n > 0 ? '#34C878' : 'var(--text-tertiary)', fontWeight: 700 }}>{n}</span>
            <span style={{ color: 'var(--text-secondary)' }}> / {cards.length} clips selected</span>
          </span>
          {n === 0 && (
            <span style={s.footerHint}>Select clips to lock them for render, or continue with AI auto-select</span>
          )}
        </div>
        <button onClick={onContinue} style={s.approveBtn}>
          {t('review_approve_btn')} →
        </button>
      </div>
    </div>
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
  },
  totalBadge: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    backgroundColor: 'var(--surface-input)',
    padding: '2px 8px',
    borderRadius: '10px',
    border: '1px solid var(--border-subtle)',
  },
  headerActions: {
    display: 'flex',
    gap: '6px',
  },
  ghostBtn: {
    height: '28px',
    padding: '0 var(--space-3)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'border-color 0.12s ease, background-color 0.12s ease',
  },
  ghostBtnActive: {
    borderColor: 'rgba(52,200,120,0.4)',
    backgroundColor: 'rgba(52,200,120,0.06)',
    color: '#34C878',
  },
  grid: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-5) var(--space-6)',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))',
    gap: 'var(--space-4)',
    alignContent: 'start',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-4) var(--space-6)',
    borderTop: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-card)',
    gap: 'var(--space-4)',
  },
  footerInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  },
  selectedCount: {
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
  },
  footerHint: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
  },
  approveBtn: {
    height: '40px',
    padding: '0 var(--space-6)',
    border: 'none',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #a855f7 0%, #4d7cff 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    cursor: 'pointer',
    flexShrink: 0,
    letterSpacing: '0.01em',
    boxShadow: '0 3px 10px rgba(168,85,247,0.3)',
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-4)',
  },
  emptyText: {
    margin: 0,
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
    textAlign: 'center' as const,
    maxWidth: '360px',
  },
}
