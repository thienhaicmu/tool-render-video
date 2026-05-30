import { useState, useEffect } from 'react'
import { useEditStore } from '../../../stores/editStore'
import { useI18n } from '../../../i18n/useI18n'
import { getPreviewTranscript, submitRender } from '../../../api/render'
import { mapSegmentsToPlan, formatTimecode, type AIPlanCardData } from '../../../adapters/studioAdapters'
import { EmptyState } from '../../../components/ui/EmptyState'
import type { RenderRequest } from '../../../types/api'

interface PlanStepProps {
  sessionId: string | null
  sessionSourceMode: 'local'
  sessionOutputDir: string
  onRenderStarted: (jobId: string) => void
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
      backgroundColor: accent ? 'rgba(168,85,247,0.08)' : 'var(--surface-card)',
      border: `1px solid ${accent ? 'rgba(168,85,247,0.2)' : 'var(--border-subtle)'}`,
    }}>
      <span style={{
        fontSize: '16px',
        fontWeight: 800,
        color: accent ? '#a855f7' : 'var(--text-primary)',
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

// ── Clip card (Cards view) ─────────────────────────────────────────────────────

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
            <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '16px', marginLeft: '2px' }}>&#9658;</span>
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

        {/* Hook badge */}
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
            }}>&#10003;</div>
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
          {formatTimecode(card.startSec)} &rarr; {formatTimecode(card.endSec)}
        </span>
      </div>
    </div>
  )
}

// ── PlanStep ───────────────────────────────────────────────────────────────────

type ViewMode = 'table' | 'cards'

export function PlanStep({ sessionId, sessionSourceMode, sessionOutputDir, onRenderStarted }: PlanStepProps) {
  const { t } = useI18n()
  const { settings, addClipLock, clearClipLock } = useEditStore()
  const [cards, setCards] = useState<AIPlanCardData[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set())
  const [hoveredRow, setHoveredRow] = useState<number | null>(null)
  const [view, setView] = useState<ViewMode>('table')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Load transcript on mount / sessionId change
  useEffect(() => {
    if (!sessionId) {
      setCards([])
      return
    }
    setLoading(true)
    setSelectedIndices(new Set())
    clearClipLock()
    setSubmitError(null)

    getPreviewTranscript(sessionId)
      .then((res) => {
        const mapped = mapSegmentsToPlan(res.segments)
        setCards(mapped)
      })
      .catch(() => {
        setCards([])
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // Sync selectedIndices -> clipLock
  useEffect(() => {
    clearClipLock()
    selectedIndices.forEach((i) => {
      const card = cards[i]
      if (card) addClipLock({ start_sec: card.startSec, end_sec: card.endSec })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIndices])

  const toggleSelect = (i: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  const handleSubmit = async () => {
    if (submitting) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      const payload: RenderRequest = {
        source_mode: sessionSourceMode,
        edit_session_id: sessionId,
        output_dir: sessionOutputDir || 'exports',
        target_platform: settings.targetPlatform,
        aspect_ratio: settings.aspectRatio,
        output_fps: settings.outputFps,
        render_profile: settings.renderProfile,
        ai_director_enabled: settings.aiDirectorEnabled,
        max_export_parts: settings.maxExportParts,
        min_part_sec: settings.minPartSec,
        max_part_sec: settings.maxPartSec,
        part_order: settings.partOrder,
        add_subtitle: settings.addSubtitle,
        subtitle_style: settings.subtitleStyle,
        sub_font_size: settings.subFontSize,
        highlight_per_word: settings.highlightPerWord,
        voice_enabled: settings.voiceEnabled,
        voice_language: settings.voiceLanguage,
        voice_gender: settings.voiceGender,
        clip_lock: settings.clipLock && settings.clipLock.length > 0 ? settings.clipLock : null,
      }
      const res = await submitRender(payload)
      onRenderStarted(res.job_id)
    } catch {
      setSubmitError(t('plan_error_submit'))
      setSubmitting(false)
    }
  }

  const totalDurationSec = cards.reduce((sum, c) => sum + (c.endSec - c.startSec), 0)
  const totalMin = Math.floor(totalDurationSec / 60)
  const totalSec = Math.floor(totalDurationSec % 60)
  const highViralCount = cards.filter((c) => c.confidence >= 70).length
  const n = selectedIndices.size

  if (!sessionId) {
    return (
      <div style={s.page}>
        <EmptyState primary={t('plan_empty')} secondary="" />
      </div>
    )
  }

  return (
    <>
      <style>{`
        @keyframes plan-pulse { 0%, 100% { opacity: 0.4 } 50% { opacity: 0.2 } }
        @keyframes plan-spin { to { transform: rotate(360deg); } }
      `}</style>

      <div style={s.page}>
        {/* Header */}
        <div style={s.header}>
          <div style={s.headerLeft}>
            <span style={s.headerTitle}>{t('plan_header')}</span>
            {!loading && cards.length > 0 && (
              <span style={s.countBadge}>{cards.length} {t('plan_clips')}</span>
            )}
          </div>

          {/* View toggle */}
          <div style={s.viewToggle}>
            <button
              style={{ ...s.viewBtn, ...(view === 'table' ? s.viewBtnActive : {}) }}
              onClick={() => setView('table')}
            >
              {t('plan_view_table')}
            </button>
            <button
              style={{ ...s.viewBtn, ...(view === 'cards' ? s.viewBtnActive : {}) }}
              onClick={() => setView('cards')}
            >
              {t('plan_view_cards')}
            </button>
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
            <StatChip value={`${highViralCount}`} label={t('plan_viral_label')} />
            <StatChip value={settings.aspectRatio} label={t('plan_aspect_label')} />
          </div>
        )}

        {/* Content area */}
        {view === 'table' ? (
          /* ── Table view ── */
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
                    const isSelected = selectedIndices.has(i)
                    const isHovered = hoveredRow === i
                    return (
                      <tr
                        key={`${card.startSec}-${card.endSec}`}
                        onMouseEnter={() => setHoveredRow(i)}
                        onMouseLeave={() => setHoveredRow(null)}
                        style={{
                          backgroundColor: isSelected
                            ? 'rgba(168,85,247,0.06)'
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
                            backgroundColor: isSelected ? 'rgba(168,85,247,0.15)' : 'transparent',
                            color: isSelected ? '#a855f7' : 'var(--text-tertiary)',
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
                            borderColor: isSelected ? 'rgba(168,85,247,0.4)' : 'var(--border-subtle)',
                          }}>
                            <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.12)' }}>&#9658;</span>
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
                          <span style={{ color: 'var(--text-tertiary)', opacity: 0.6 }}>&rarr; {formatTimecode(card.endSec)}</span>
                        </td>

                        {/* Score */}
                        <td style={s.td}>
                          <ScoreBar value={card.confidence} />
                        </td>

                        {/* Checkbox */}
                        <td style={{ ...s.td, textAlign: 'center' as const }}>
                          <div
                            onClick={() => toggleSelect(i)}
                            style={{
                              width: '18px',
                              height: '18px',
                              borderRadius: '5px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              margin: '0 auto',
                              cursor: 'pointer',
                              backgroundColor: isSelected ? '#a855f7' : 'var(--surface-input)',
                              border: `1.5px solid ${isSelected ? '#a855f7' : 'var(--border-default)'}`,
                              transition: 'all 0.12s ease',
                            }}
                          >
                            {isSelected && <span style={{ color: '#fff', fontSize: '9px', fontWeight: 800 }}>&#10003;</span>}
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        ) : (
          /* ── Cards view ── */
          <div style={s.cardsGrid}>
            {loading
              ? [0, 1, 2, 3].map((i) => (
                  <div key={i} style={s.cardSkeleton} />
                ))
              : cards.length === 0
              ? (
                  <div style={s.cardsEmpty}>
                    <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>{t('plan_empty')}</span>
                  </div>
                )
              : cards.map((card, i) => (
                  <ClipCard
                    key={`${card.startSec}-${card.endSec}`}
                    card={card}
                    index={i}
                    selected={selectedIndices.has(i)}
                    onToggle={() => toggleSelect(i)}
                  />
                ))
            }
          </div>
        )}

        {/* Footer */}
        <div style={s.footer}>
          <div style={s.footerLeft}>
            {n > 0 ? (
              <span style={s.selectedNote}>
                {n} / {cards.length} {t('plan_clips')} selected
              </span>
            ) : (
              <span style={s.footerHint}>AI will auto-select best clips</span>
            )}
            {submitError && (
              <span style={s.errorNote}>{submitError}</span>
            )}
          </div>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            style={{ ...s.submitBtn, ...(submitting ? s.submitBtnDisabled : {}) }}
          >
            {submitting ? (
              <>
                <span style={s.spinner} />
                {t('plan_submitting')}
              </>
            ) : (
              t('plan_approve_render')
            )}
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
    height: '48px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-panel)',
    gap: 'var(--space-3)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    flex: 1,
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
    color: '#a855f7',
    backgroundColor: 'rgba(168,85,247,0.1)',
    padding: '2px 8px',
    borderRadius: '10px',
    border: '1px solid rgba(168,85,247,0.2)',
  },
  viewToggle: {
    display: 'flex',
    gap: '4px',
    backgroundColor: 'var(--surface-input)',
    borderRadius: '8px',
    padding: '3px',
    flexShrink: 0,
  },
  viewBtn: {
    height: '24px',
    padding: '0 10px',
    border: 'none',
    borderRadius: '6px',
    backgroundColor: 'transparent',
    color: 'var(--text-tertiary)',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background-color 0.12s ease, color 0.12s ease',
  },
  viewBtnActive: {
    backgroundColor: 'var(--surface-card)',
    color: 'var(--text-primary)',
    fontWeight: 600,
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
    flexShrink: 0,
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
  cardsGrid: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-5) var(--space-6)',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))',
    gap: 'var(--space-4)',
    alignContent: 'start',
  },
  cardSkeleton: {
    borderRadius: '12px',
    backgroundColor: 'var(--surface-card)',
    opacity: 0.4,
    animation: 'plan-pulse 1.4s ease-in-out infinite',
    aspectRatio: '9 / 16',
  },
  cardsEmpty: {
    gridColumn: '1 / -1',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '64px 24px',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-6)',
    height: '56px',
    borderTop: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-panel)',
    gap: 'var(--space-4)',
  },
  footerLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  },
  selectedNote: {
    fontSize: '11px',
    color: '#a855f7',
    fontWeight: 600,
  },
  footerHint: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
  },
  errorNote: {
    fontSize: '11px',
    color: '#E05252',
    fontWeight: 500,
  },
  submitBtn: {
    height: '38px',
    padding: '0 20px',
    border: 'none',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
    color: '#fff',
    fontSize: '12px',
    fontWeight: 700,
    cursor: 'pointer',
    boxShadow: '0 0 0 1px rgba(168,85,247,.35), 0 0 16px rgba(168,85,247,.2)',
    transition: 'opacity 0.15s ease',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexShrink: 0,
  },
  submitBtnDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
    boxShadow: 'none',
  },
  spinner: {
    display: 'inline-block',
    width: '12px',
    height: '12px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#fff',
    borderRadius: '50%',
    animation: 'plan-spin 0.75s linear infinite',
  },
}
