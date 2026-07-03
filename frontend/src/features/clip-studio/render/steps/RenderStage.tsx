/**
 * RenderStage — clips-mode live view (WP1 redesign).
 *
 * One FOCUS card for the clip rendering right now (large ConicRing progress
 * while active, real thumbnail once done, Cut→Sub→Render pipeline, activity
 * line, per-clip ETA) + a GRID of rich ClipTiles for every clip. Click a tile
 * to focus it. Same visual language as the Results grid so monitor→results
 * reads as one surface.
 *
 * CSS lives in RenderWorkflow.css under `.rs-*` (focus card) and `.ct-*` (tiles).
 */
import React, { useRef, useState } from 'react'
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { ConicRing } from '@/components/ui/ConicRing'
import { IconCheck, IconScissors, IconCaptions, IconFilm, IconPlay } from '@/components/icons'
import { ClipTile } from './ClipTile'
import { clipStateKey, STEP_NODES, activityLabel } from './clipState'

// Re-export so existing consumers (StepRendering) keep importing from here.
export { clipStateKey }

const STEP_ICON = {
  cutting: IconScissors,
  transcribing: IconCaptions,
  rendering: IconFilm,
} as const

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

  // Per-clip ETA — anchored to when the FOCUSED clip entered its active state.
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
  const activeStepIdx = STEP_NODES.findIndex((n) => n.key === focus.status.toLowerCase())
  const activity = focus.message || activityLabel(focus.status, t)
  const thumbUrl = jobId && focusState === 'done' ? getPartThumbnailUrl(jobId, focus.part_no) : null
  const durFmt = fmtDur(focus.duration)

  return (
    <div className="rs-root">
      {/* ── FOCUS CARD ─────────────────────────────────────────────────── */}
      <div className={`rs-focus${focusState === 'active' ? ' rs-focus-live' : ''}`}>
        {/* Preview / progress area */}
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
                  aria-label="Play clip"
                ><IconPlay size={26} /></a>
              )}
            </>
          ) : (
            <div className={`rs-thumb-ph rs-ph-${focusState}`}>
              {focusState === 'active' ? (
                <ConicRing progress={Math.round(pct)} size={92} />
              ) : focusState === 'failed' ? (
                <span className="rs-thumb-x">✕</span>
              ) : (
                <span className="rs-thumb-no">#{String(focus.part_no).padStart(2, '0')}</span>
              )}
            </div>
          )}
        </div>

        {/* Detail column */}
        <div className="rs-body">
          <div className="rs-head">
            <span className={`rs-badge rs-badge-${focusState}`}>
              {focusState === 'active' && <span className="rs-badge-dot" />}
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
                  : 'linear-gradient(90deg, var(--ai-active), var(--accent-primary))',
              }}
            />
          </div>

          {/* Pipeline — line-icon nodes */}
          <div className="rs-pipe">
            {STEP_NODES.map((n, i) => {
              const stt = focusState === 'done' ? 'done'
                : i < activeStepIdx ? 'done'
                : i === activeStepIdx ? 'active'
                : 'pending'
              const Ico = STEP_ICON[n.key]
              return (
                <React.Fragment key={n.key}>
                  <span className={`rs-pipe-node rs-pipe-${stt}`}>
                    {stt === 'done' ? <IconCheck size={12} /> : <Ico size={12} />}
                  </span>
                  <span className={`rs-pipe-lbl rs-pipe-lbl-${stt}`}>{n.label}</span>
                  {i < STEP_NODES.length - 1 && (
                    <span className={`rs-pipe-line${i < activeStepIdx || focusState === 'done' ? ' rs-pipe-line-done' : ''}`} />
                  )}
                </React.Fragment>
              )
            })}
          </div>

          {activity && focusState !== 'done' && (
            <div className={`rs-activity${focusState === 'failed' ? ' rs-activity-fail' : ''}`}>
              {activity}
            </div>
          )}
          {focusState === 'done' && jobId && (
            <a className="rs-preview-link" href={getPartMediaUrl(jobId, focus.part_no)} target="_blank" rel="noreferrer">
              <IconPlay size={12} /> {t.btnPlay.replace('▶ ', '')}
            </a>
          )}
        </div>
      </div>

      {/* ── CLIP GRID ──────────────────────────────────────────────────── */}
      <div className="ct-grid" role="listbox" aria-label="Clips">
        {slots.map((s) => (
          <ClipTile
            key={s.part_no}
            slot={s}
            jobId={jobId}
            thumbRatio={thumbRatio}
            isFocus={s.part_no === focus.part_no}
            onFocus={setFocusOverride}
            t={t}
            getStatusLabel={getStatusLabel}
          />
        ))}
      </div>
    </div>
  )
}
