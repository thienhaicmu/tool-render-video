/**
 * RenderStage — clips-mode live view: one FOCUS card for the clip being
 * rendered right now (large preview area, animated border, big progress,
 * Cut→Sub→Render pipeline, activity line, per-clip ETA) + a filmstrip of
 * every other clip. Click a filmstrip chip to focus it.
 *
 * Owner-approved redesign (2026-07-02) replacing the flat ClipRow list —
 * same pattern as RecapLiveView's focus card so both render modes read
 * identically. CSS lives in RenderWorkflow.css under `.rs-*`.
 */
import React, { useRef, useState } from 'react'
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import type { JobPartStageEnum } from '@/types/enums'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'

export function clipStateKey(status: string): 'done' | 'failed' | 'active' | 'waiting' {
  const s = status.toLowerCase()
  if (s === 'done') return 'done'
  if (s === 'failed' || s === 'cancelled') return 'failed'
  if (s === 'waiting' || s === 'queued') return 'waiting'
  return 'active'
}

// Activity labels via the Strings table (tool names kept as detail).
function activityLabel(status: string, t: Strings): string {
  switch (status.toLowerCase()) {
    case 'cutting':      return `${t.actCutting} · FFmpeg`
    case 'transcribing': return `${t.actTranscribing} · Whisper AI`
    case 'rendering':    return `${t.actRendering} · FFmpeg`
    default:             return ''
  }
}

const STEP_NODES = [
  { key: 'cutting',      label: 'Cut' },
  { key: 'transcribing', label: 'Sub' },
  { key: 'rendering',    label: 'Render' },
] as const satisfies readonly { key: JobPartStageEnum; label: string }[]

const ACCENT: Record<string, string> = {
  done:    'var(--status-success)',
  failed:  'var(--color-error)',
  active:  'var(--ai-active)',
  waiting: 'var(--status-waiting)',
}

function fmtDur(sec?: number): string | null {
  if (sec == null || sec <= 0) return null
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
}

export function RenderStage({ slots, jobId, thumbRatio, t, getStatusLabel }: {
  slots: ClipSlot[]
  jobId: string | null
  thumbRatio: string
  t: Strings
  getStatusLabel: (s: string) => string
}) {
  const [focusOverride, setFocusOverride] = useState<number | null>(null)

  const auto =
    slots.find((s) => clipStateKey(s.status) === 'active')
    ?? slots.find((s) => clipStateKey(s.status) === 'waiting')
    ?? slots[slots.length - 1]
  const focus = slots.find((s) => s.part_no === focusOverride) ?? auto

  // Per-clip ETA — anchored to when the FOCUSED clip entered its active
  // state (reset whenever a different clip takes focus / turns active).
  const startRef = useRef<{ no: number; at: number } | null>(null)
  const focusState = focus ? clipStateKey(focus.status) : 'waiting'
  if (focus && focusState === 'active') {
    if (startRef.current?.no !== focus.part_no) startRef.current = { no: focus.part_no, at: Date.now() }
  } else {
    startRef.current = null
  }
  let etaLabel: string | null = null
  if (focus && focusState === 'active' && startRef.current) {
    const pct = focus.progress_percent
    const elapsed = (Date.now() - startRef.current.at) / 1000
    if (pct > 5 && pct < 100 && elapsed >= 3) {
      const remain = Math.round(elapsed * (100 - pct) / pct)
      if (remain >= 1 && remain <= 3600) {
        etaLabel = remain < 60 ? `~${remain}s` : `~${Math.floor(remain / 60)}:${String(remain % 60).padStart(2, '0')}`
      }
    }
  }

  if (!focus) return null

  const pct = focusState === 'done' ? 100 : focusState === 'active' ? focus.progress_percent : 0
  const accent = ACCENT[focusState]
  const activeStepIdx = STEP_NODES.findIndex((n) => n.key === focus.status.toLowerCase())
  const activity = focus.message || activityLabel(focus.status, t)
  const thumbUrl = jobId && focusState === 'done' ? getPartThumbnailUrl(jobId, focus.part_no) : null
  const durFmt = fmtDur(focus.duration)

  return (
    <div className="rs-root">
      {/* ── FOCUS CARD ─────────────────────────────────────────────────── */}
      <div className={`rs-focus${focusState === 'active' ? ' rs-focus-live' : ''}`}>
        {/* Preview area */}
        <div className="rs-thumb" style={{ aspectRatio: thumbRatio }}>
          {thumbUrl ? (
            <>
              <img
                src={thumbUrl} alt=""
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              />
              {jobId && (
                <a
                  className="rs-thumb-play"
                  href={getPartMediaUrl(jobId, focus.part_no)}
                  target="_blank" rel="noreferrer"
                >▶</a>
              )}
            </>
          ) : (
            <div className={`rs-thumb-ph rs-ph-${focusState}`}>
              <span className="rs-thumb-no">#{String(focus.part_no).padStart(2, '0')}</span>
              {focusState === 'active' && (
                <span className="rs-thumb-pct">{Math.round(pct)}%</span>
              )}
              {focusState === 'failed' && <span className="rs-thumb-x">✕</span>}
            </div>
          )}
        </div>

        {/* Detail column */}
        <div className="rs-body">
          <div className="rs-head">
            <span className={`rs-badge rs-badge-${focusState}`} style={{ color: accent }}>
              {focusState === 'active' && <span className="rs-badge-dot" style={{ background: accent }} />}
              {getStatusLabel(focus.status)}
            </span>
            <span className="rs-title">
              Clip #{String(focus.part_no).padStart(2, '0')}
              {durFmt && <span className="rs-dur"> · {durFmt}</span>}
            </span>
            {etaLabel && <span className="rs-eta" title="ETA">{etaLabel}</span>}
          </div>

          <div className="rs-bar">
            <div
              className="rs-bar-fill"
              style={{
                width: `${pct}%`,
                background: focusState === 'failed'
                  ? 'var(--color-error)'
                  : `linear-gradient(90deg, ${accent}, var(--accent-primary))`,
              }}
            />
          </div>

          {/* Pipeline */}
          <div className="rs-pipe">
            {STEP_NODES.map((n, i) => {
              const st = focusState === 'done' ? 'done'
                : i < activeStepIdx ? 'done'
                : i === activeStepIdx ? 'active'
                : 'pending'
              const col = st === 'done' ? 'var(--status-success)' : st === 'active' ? 'var(--ai-active)' : 'var(--status-waiting)'
              return (
                <React.Fragment key={n.key}>
                  <span className="rs-pipe-node" style={{ borderColor: col, background: st === 'done' ? col : 'transparent' }}>
                    {st === 'done' && <span className="rs-pipe-check">✓</span>}
                    {st === 'active' && <span className="rs-pipe-pulse" style={{ background: col }} />}
                  </span>
                  <span className="rs-pipe-lbl" style={{ color: col, fontWeight: st === 'active' ? 700 : 500 }}>{n.label}</span>
                  {i < STEP_NODES.length - 1 && <span className="rs-pipe-line" style={{ background: i < activeStepIdx || focusState === 'done' ? 'var(--status-success)' : 'var(--border)' }} />}
                </React.Fragment>
              )
            })}
          </div>

          {activity && focusState !== 'done' && (
            <div className="rs-activity" style={{ color: focusState === 'failed' ? 'var(--fail)' : 'var(--text-3)' }}>
              {activity}
            </div>
          )}
          {focusState === 'done' && jobId && (
            <a className="rs-preview-link" href={getPartMediaUrl(jobId, focus.part_no)} target="_blank" rel="noreferrer">
              ▶ {t.btnPlay.replace('▶ ', '')}
            </a>
          )}
        </div>
      </div>

      {/* ── FILMSTRIP ──────────────────────────────────────────────────── */}
      <div className="rs-strip" role="listbox" aria-label="Clips">
        {slots.map((s) => {
          const st = clipStateKey(s.status)
          const isFocus = s.part_no === focus.part_no
          return (
            <button
              key={s.part_no}
              className={`rs-chip rs-chip-${st}${isFocus ? ' rs-chip-focus' : ''}`}
              onClick={() => setFocusOverride(s.part_no)}
              title={`Clip ${s.part_no}: ${getStatusLabel(s.status)}`}
              role="option"
              aria-selected={isFocus}
            >
              {/* key forces remount on state change → pop animation plays */}
              <span key={st} className={`rs-chip-glyph${st === 'done' ? ' rs-pop' : ''}`}>
                {st === 'done' ? '✓' : st === 'failed' ? '✕' : st === 'active' ? '▶' : '○'}
              </span>
              <span className="rs-chip-no">#{String(s.part_no).padStart(2, '0')}</span>
              {st === 'active' && <span className="rs-chip-pct">{Math.round(s.progress_percent)}%</span>}
              {st === 'active' && (
                <span className="rs-chip-bar"><span style={{ width: `${s.progress_percent}%` }} /></span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
