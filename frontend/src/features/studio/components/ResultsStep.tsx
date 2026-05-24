import { useState, useEffect } from 'react'
import { getJobParts } from '../../../api/jobs'
import { mapPartsToReviewCards } from '../../../adapters/studioAdapters'
import { BASE_URL } from '../../../api/client'
import { useI18n } from '../../../i18n/useI18n'
import type { ReviewCardData } from '../types'

interface ResultsStepProps {
  jobId: string | null
  sessionOutputDir: string
  onNewProject: () => void
}

// ── Result card ────────────────────────────────────────────────────────────────

interface ResultCardProps {
  card: ReviewCardData
  jobId: string
  index: number
}

function ResultCard({ card, jobId, index }: ResultCardProps) {
  const [thumbError, setThumbError] = useState(false)
  const [hovered, setHovered] = useState(false)
  const partNo = parseInt(card.id)
  const thumbSrc = `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/thumbnail?t=0.5&w=320`

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: '12px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        cursor: 'default',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        transform: hovered ? 'translateY(-2px)' : 'none',
        boxShadow: hovered
          ? '0 12px 28px rgba(0,0,0,0.45)'
          : '0 2px 8px rgba(0,0,0,0.2)',
        backgroundColor: 'var(--surface-card)',
      }}
    >
      {/* Thumbnail (9:16) */}
      <div style={{ position: 'relative', backgroundColor: '#0A0C11', paddingTop: '177.78%' }}>
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
          {!thumbError ? (
            <img
              src={thumbSrc}
              alt={card.clipLabel}
              onError={() => setThumbError(true)}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
          ) : (
            <div style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
              gap: '8px',
            }}>
              <span style={{ fontSize: '28px', opacity: 0.15 }}>▶</span>
              <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.15)' }}>No preview</span>
            </div>
          )}
        </div>

        {/* Index badge */}
        <div style={{
          position: 'absolute',
          top: '8px',
          left: '8px',
          width: '22px',
          height: '22px',
          borderRadius: '50%',
          backgroundColor: 'rgba(0,0,0,0.75)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '10px',
          fontWeight: 700,
          color: 'rgba(255,255,255,0.7)',
          fontFamily: 'var(--font-mono)',
          backdropFilter: 'blur(4px)',
        }}>
          {index + 1}
        </div>

        {/* Format badge */}
        <div style={{
          position: 'absolute',
          bottom: '8px',
          right: '8px',
          backgroundColor: 'rgba(0,0,0,0.75)',
          borderRadius: '6px',
          padding: '2px 6px',
          fontSize: '10px',
          fontWeight: 600,
          color: 'rgba(255,255,255,0.6)',
          backdropFilter: 'blur(4px)',
        }}>
          MP4
        </div>

        {/* Hover overlay */}
        {hovered && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(123,97,255,0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: '50%',
              backgroundColor: 'rgba(123,97,255,0.9)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '16px',
              color: '#fff',
            }}>▶</div>
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ padding: '8px 10px 10px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
        <span style={{
          fontSize: '11px',
          fontWeight: 600,
          color: 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' as const,
          lineHeight: 1.3,
        }}>
          {card.clipLabel}
        </span>
        <span style={{
          fontSize: '10px',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' as const,
        }}>
          {card.reasoning}
        </span>
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '1px' }}>
          1080p · Vertical
        </span>
      </div>
    </div>
  )
}

// ── ResultsStep ───────────────────────────────────────────────────────────────

export function ResultsStep({ jobId, sessionOutputDir, onNewProject }: ResultsStepProps) {
  const { t } = useI18n()
  const [cards, setCards] = useState<ReviewCardData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!jobId) { setLoading(false); return }
    getJobParts(jobId)
      .then((parts) => setCards(mapPartsToReviewCards(parts)))
      .catch(() => setCards([]))
      .finally(() => setLoading(false))
  }, [jobId])

  const openFolder = async () => {
    const api = (window as any).electronAPI
    if (api?.openPath && sessionOutputDir) {
      await api.openPath(sessionOutputDir)
    } else {
      alert('Open folder: ' + (sessionOutputDir || 'output directory'))
    }
  }

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerLeft}>
          <div style={s.successIcon}>✓</div>
          <div>
            <div style={s.headerTitle}>{t('results_complete')}</div>
            {!loading && cards.length > 0 && (
              <div style={s.headerSub}>{cards.length} video{cards.length !== 1 ? 's' : ''} ready to use</div>
            )}
          </div>
        </div>
        <div style={s.headerActions}>
          <button onClick={openFolder} style={s.folderBtn}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
            {t('results_open_folder')}
          </button>
          <button style={{ ...s.folderBtn, opacity: 0.4, cursor: 'not-allowed' }} disabled>
            {t('results_share')}
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div style={s.loadingWrap}>
          <span style={{
            display: 'inline-block',
            width: '20px',
            height: '20px',
            border: '2.5px solid rgba(123,97,255,0.3)',
            borderTopColor: '#7B61FF',
            borderRadius: '50%',
            animation: 'res-spin 0.8s linear infinite',
          }} />
          <span style={s.loadingText}>Loading results…</span>
        </div>
      ) : cards.length === 0 ? (
        <div style={s.loadingWrap}>
          <span style={{ fontSize: '40px', opacity: 0.1 }}>🎬</span>
          <span style={s.loadingText}>{t('results_no_clips')}</span>
        </div>
      ) : (
        <div style={s.grid}>
          {cards.map((card, i) => (
            <ResultCard key={card.id} card={card} jobId={jobId!} index={i} />
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={s.footer}>
        <span style={s.footerSummary}>
          {loading ? '' : `${t('results_total')}: ${cards.length} video${cards.length !== 1 ? 's' : ''}`}
        </span>
        <button onClick={onNewProject} style={s.newProjectBtn}>
          {t('results_new_project')}
        </button>
      </div>

      <style>{`@keyframes res-spin { to { transform: rotate(360deg); } }`}</style>
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
    padding: 'var(--space-4) var(--space-6)',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-card)',
    flexWrap: 'wrap' as const,
    gap: 'var(--space-3)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  successIcon: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    backgroundColor: 'rgba(52,200,120,0.15)',
    border: '2px solid rgba(52,200,120,0.4)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#34C878',
    fontSize: '16px',
    fontWeight: 700,
    flexShrink: 0,
  },
  headerTitle: {
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.3,
  },
  headerSub: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    marginTop: '1px',
  },
  headerActions: {
    display: 'flex',
    gap: '6px',
  },
  folderBtn: {
    height: '32px',
    padding: '0 var(--space-3)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '8px',
    backgroundColor: 'var(--surface-input)',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
  },
  loadingWrap: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-3)',
  },
  loadingText: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
  },
  grid: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-5) var(--space-6)',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
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
  },
  footerSummary: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
  },
  newProjectBtn: {
    height: '38px',
    padding: '0 var(--space-6)',
    border: 'none',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    cursor: 'pointer',
    boxShadow: '0 3px 10px rgba(123,97,255,0.3)',
  },
}
