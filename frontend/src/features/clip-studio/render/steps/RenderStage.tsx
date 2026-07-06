/**
 * RenderStage — clips-mode live monitor (desktop render-dashboard redesign).
 *
 * Modeled 1:1 on a desktop render-dashboard reference:
 *   • "Current Rendering" card — landscape thumbnail + title + status pill +
 *     progress bar + a spread stats row (ETA · Elapsed · Progress · Duration).
 *   • "Queue" — the clip list as dense rows (index · thumb · name · status ·
 *     progress · time · action), see ClipTile.
 * Dark surface, single purple accent, status colors. Every number derives from
 * data the pipeline already streams (ClipSlot + per-part thumbnail on done).
 */
import { useEffect, useRef, useState } from 'react'
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { IconPlay } from '@/components/icons'
import { ClipTile } from './ClipTile'
import { ClipSteps } from './ClipSteps'
import { useCountUp } from './useCountUp'
import { clipStateKey, activityLabel } from './clipState'

// Re-export so existing consumers (StepRendering) keep importing from here.
export { clipStateKey }

function fmtDur(sec?: number): string | null {
  if (sec == null || sec <= 0) return null
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
}

function fmtClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function RenderStage({ slots, jobId, thumbRatio, t, getStatusLabel }: {
  slots: ClipSlot[]
  jobId: string | null
  thumbRatio: string
  t: Strings
  getStatusLabel: (s: string) => string
}) {
  void thumbRatio
  const [focusOverride, setFocusOverride] = useState<number | null>(null)

  const auto =
    slots.find((s) => clipStateKey(s.status) === 'active')
    ?? slots.find((s) => clipStateKey(s.status) === 'waiting')
    ?? slots[slots.length - 1]
  const focus = slots.find((s) => s.part_no === focusOverride) ?? auto

  const startRef = useRef<{ no: number; at: number } | null>(null)
  const focusState = focus ? clipStateKey(focus.status) : 'waiting'
  if (focus && focusState === 'active') {
    if (startRef.current?.no !== focus.part_no) startRef.current = { no: focus.part_no, at: Date.now() }
  } else {
    startRef.current = null
  }

  const [, setTick] = useState(0)
  useEffect(() => {
    if (focusState !== 'active') return
    const id = setInterval(() => setTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [focusState, focus?.part_no])

  const pct = focusState === 'done' ? 100 : focusState === 'active' ? focus.progress_percent : 0
  const shownPct = Math.round(useCountUp(pct))

  let elapsedLabel: string | null = null
  let etaLabel: string | null = null
  if (focus && focusState === 'active' && startRef.current) {
    const elapsed = (Date.now() - startRef.current.at) / 1000
    elapsedLabel = fmtClock(elapsed)
    if (pct > 5 && pct < 100 && elapsed >= 3) {
      const remain = Math.round(elapsed * (100 - pct) / pct)
      if (remain >= 1 && remain <= 3600) etaLabel = fmtClock(remain)
    }
  }

  if (!focus) return null

  const thumbUrl = jobId && focusState === 'done' ? getPartThumbnailUrl(jobId, focus.part_no) : null
  const durFmt = fmtDur(focus.duration)
  const no = String(focus.part_no).padStart(2, '0')

  const stats: Array<[string, string]> = [
    ['ETA', etaLabel ?? '—'],
    ['Elapsed', elapsedLabel ?? '—'],
    ['Progress', `${shownPct}%`],
    ['Duration', durFmt ?? '—'],
  ]

  return (
    <div className="rs-root">
      {/* ── Current Rendering ──────────────────────────────────────────── */}
      <div className="rs-focus">
        <div className={`rs-thumb rs-thumb-${focusState}`}>
          <span className="rs-thumb-ph"><span>{no}</span></span>
          {thumbUrl && (
            <img
              src={thumbUrl} alt="" className="rs-thumb-img"
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
            />
          )}
          {thumbUrl && jobId && (
            <a
              className="rs-thumb-play"
              href={getPartMediaUrl(jobId, focus.part_no)}
              target="_blank" rel="noreferrer" aria-label="Play clip"
            ><IconPlay size={18} /></a>
          )}
        </div>

        <div className="rs-info">
          <div className="rs-info-top">
            <span className="rs-title" title={focus.name || `Clip ${focus.part_no}`}>{focus.name || `Clip ${focus.part_no}`}</span>
            <span className={`rs-badge rs-badge-${focusState}`}>{getStatusLabel(focus.status)}</span>
          </div>

          <div className="rs-steps-row">
            <ClipSteps status={focus.status} variant="focus" />
            {activityLabel(focus.status, t) && (
              <span className="rs-activity">{activityLabel(focus.status, t)}</span>
            )}
          </div>

          <div className="rs-prog-row">
            <div className="rs-bar">
              <div
                className={`rs-bar-fill${focusState === 'active' ? ' rs-bar-live' : ''}`}
                style={{
                  width: `${pct}%`,
                  background: focusState === 'failed' ? 'var(--mon-fail)' : undefined,
                }}
              />
            </div>
            <span className="rs-pct">{shownPct}%</span>
          </div>

          <div className="rs-stats">
            {stats.map(([k, v]) => (
              <div key={k} className="rs-stat">
                <span className="rs-stat-k">{k}</span>
                <span className="rs-stat-v">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Queue ──────────────────────────────────────────────────────── */}
      <div className="ct-list" role="listbox" aria-label="Clips">
        {slots.map((s) => (
          <ClipTile
            key={s.part_no}
            slot={s}
            jobId={jobId}
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
