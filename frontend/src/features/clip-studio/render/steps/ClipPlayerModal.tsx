/**
 * ClipPlayerModal — P3.A: in-app clip review player.
 *
 * Reviewing 10 clips used to mean 10 browser tabs (the ▶ overlay opened
 * target="_blank"). This modal plays clips in place with keyboard-driven
 * review: ←/→ previous/next clip, ↑/↓ thumbs up/down (feeds AI Director
 * training like the card buttons), Esc closes.
 */
import { useEffect } from 'react'
import type { JobPart, PartRankResult } from '@/types/api'
import type { Strings } from '../i18n'
import { getPartMediaUrl } from '../utils'

export function ClipPlayerModal({
  jobId, parts, index, onNavigate, onClose,
  partScores, partRanks, feedbackRatings, onFeedback, t,
}: {
  jobId: string
  parts: JobPart[]
  index: number
  onNavigate: (i: number) => void
  onClose: () => void
  partScores: Record<number, number>
  partRanks: Record<number, PartRankResult>
  feedbackRatings: Record<number, 1 | -1 | null>
  onFeedback: (partNo: number, rating: 1 | -1, part: JobPart) => void
  t: Strings
}) {
  const part = parts[index]

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowLeft' && index > 0) { onNavigate(index - 1); return }
      if (e.key === 'ArrowRight' && index < parts.length - 1) { onNavigate(index + 1); return }
      if (part && e.key === 'ArrowUp') { e.preventDefault(); onFeedback(part.part_no, 1, part) }
      if (part && e.key === 'ArrowDown') { e.preventDefault(); onFeedback(part.part_no, -1, part) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, parts.length, part, onNavigate, onClose, onFeedback])

  if (!part) return null

  const rank = partRanks[part.part_no]
  const score = rank?.output_rank_score ?? partScores[part.part_no]
  const scoreCol = score === undefined ? 'var(--text-3)'
    : score >= 70 ? 'var(--ok)' : score >= 40 ? 'var(--warn)' : 'var(--fail)'
  const rating = feedbackRatings[part.part_no]
  const title = part.ai_title
    || (part.clip_name ? part.clip_name.replace(/\.mp4$/i, '') : `Clip ${String(part.part_no).padStart(2, '0')}`)
  const durFmt = part.duration
    ? `${Math.floor(part.duration / 60)}:${String(Math.floor(part.duration % 60)).padStart(2, '0')}`
    : null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1900,
        background: 'rgba(0,0,0,0.72)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      role="dialog" aria-modal="true" aria-label={title}
      onClick={onClose}
    >
      <div
        style={{
          display: 'flex', gap: 0, overflow: 'hidden',
          maxWidth: 'min(1100px, 96vw)', maxHeight: '92vh',
          background: 'var(--bg-panel)', border: '1px solid var(--border)',
          borderRadius: 14, boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Video */}
        <div style={{
          background: '#000', display: 'flex', alignItems: 'center',
          justifyContent: 'center', minWidth: 320, maxWidth: '60vw',
        }}>
          <video
            key={part.part_no}
            src={getPartMediaUrl(jobId, part.part_no)}
            controls autoPlay
            style={{ maxWidth: '100%', maxHeight: '92vh', display: 'block' }}
          />
        </div>

        {/* Review rail */}
        <div style={{
          width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column',
          padding: '16px 18px', gap: 12, overflowY: 'auto',
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.35 }}>
                {title}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>
                #{String(part.part_no).padStart(2, '0')}{durFmt ? ` · ${durFmt}` : ''}
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                width: 26, height: 26, border: 'none', borderRadius: 6,
                background: 'transparent', color: 'var(--text-3)',
                fontSize: 16, cursor: 'pointer', lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>

          {score !== undefined && (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 30, fontWeight: 800, color: scoreCol, lineHeight: 1 }}>
                {Math.round(score)}
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{t.resAiQualityScore}</span>
            </div>
          )}

          {rank?.ranking_reason && (
            <div style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.55 }}>
              {rank.ranking_reason}
            </div>
          )}
          {rank?.dominant_signal && (
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              {t.resWhyTop}: <span style={{ color: 'var(--accent)' }}>{rank.dominant_signal.replace(/_/g, ' ')}</span>
            </div>
          )}

          <div style={{ flex: 1 }} />

          {/* Feedback + save */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className={`clip-fb-btn${rating === 1 ? ' active-like' : ''}`}
              title="↑"
              onClick={() => onFeedback(part.part_no, 1, part)}
              style={{ flex: 1, padding: '8px 0', fontSize: 15 }}
            >👍</button>
            <button
              className={`clip-fb-btn${rating === -1 ? ' active-dislike' : ''}`}
              title="↓"
              onClick={() => onFeedback(part.part_no, -1, part)}
              style={{ flex: 1, padding: '8px 0', fontSize: 15 }}
            >👎</button>
          </div>
          <a
            className="clip-save-btn"
            style={{ textAlign: 'center', padding: '8px 0' }}
            href={getPartMediaUrl(jobId, part.part_no)}
            download={part.clip_name || `clip_${part.part_no}.mp4`}
          >
            {t.btnExport}
          </a>

          {/* Prev / next */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              className="btn-xs"
              disabled={index === 0}
              onClick={() => onNavigate(index - 1)}
              style={{ flex: 1, opacity: index === 0 ? 0.4 : 1 }}
            >
              ←
            </button>
            <span style={{ fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
              {index + 1} / {parts.length}
            </span>
            <button
              className="btn-xs"
              disabled={index === parts.length - 1}
              onClick={() => onNavigate(index + 1)}
              style={{ flex: 1, opacity: index === parts.length - 1 ? 0.4 : 1 }}
            >
              →
            </button>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textAlign: 'center' }}>
            ← → · 👍 ↑ · 👎 ↓ · Esc
          </div>
        </div>
      </div>
    </div>
  )
}
