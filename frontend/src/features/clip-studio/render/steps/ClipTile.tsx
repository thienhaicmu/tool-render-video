/**
 * ClipTile — rich per-clip card for the live render monitor (WP1).
 *
 * Replaces the flat grey `.rs-chip` pills. Each tile is sized to the output
 * aspect ratio and stays "alive" in every state, using only data the pipeline
 * already streams (ClipSlot + per-part thumbnail on done):
 *   • done    → real thumbnail + ✓ chip + duration + hover-play
 *   • active  → ConicRing progress + Cut·Sub·Render micro-pipeline + glow
 *   • waiting → ghost shimmer + "queued"
 *   • failed  → red tint + ✕ + message
 *
 * Clicking a tile focuses it in the Now-Rendering card (RenderStage).
 */
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import { ConicRing } from '@/components/ui/ConicRing'
import { IconCheck, IconX, IconPlay, IconScissors, IconCaptions, IconFilm } from '@/components/icons'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { clipStateKey, STEP_NODES } from './clipState'

const STEP_ICON = {
  cutting: IconScissors,
  transcribing: IconCaptions,
  rendering: IconFilm,
} as const

function fmtDur(sec?: number): string | null {
  if (sec == null || sec <= 0) return null
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
}

export function ClipTile({ slot, jobId, thumbRatio, isFocus, onFocus, t, getStatusLabel }: {
  slot: ClipSlot
  jobId: string | null
  thumbRatio: string
  isFocus: boolean
  onFocus: (partNo: number) => void
  t: Strings
  getStatusLabel: (s: string) => string
}) {
  void t
  const st = clipStateKey(slot.status)
  const pct = st === 'done' ? 100 : st === 'active' ? Math.round(slot.progress_percent) : 0
  const thumbUrl = jobId && st === 'done' ? getPartThumbnailUrl(jobId, slot.part_no) : null
  const durFmt = fmtDur(slot.duration)
  const no = `#${String(slot.part_no).padStart(2, '0')}`
  const activeStepIdx = STEP_NODES.findIndex((n) => n.key === slot.status.toLowerCase())

  return (
    <div
      role="option"
      aria-selected={isFocus}
      tabIndex={0}
      className={`ct ct-${st}${isFocus ? ' ct-focus' : ''}`}
      style={{ aspectRatio: thumbRatio }}
      onClick={() => onFocus(slot.part_no)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus(slot.part_no) } }}
      title={`Clip ${slot.part_no}: ${getStatusLabel(slot.status)}`}
    >
      {st === 'done' && thumbUrl ? (
        <>
          <img
            src={thumbUrl} alt="" className="ct-img"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
          <span className="ct-scrim" />
          <span className="ct-chip ct-chip-done"><IconCheck size={12} /></span>
          {durFmt && <span className="ct-dur">{durFmt}</span>}
          <span className="ct-no-over">{no}</span>
          {jobId && (
            <a
              className="ct-play"
              href={getPartMediaUrl(jobId, slot.part_no)}
              target="_blank" rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              aria-label={`Play clip ${slot.part_no}`}
            >
              <IconPlay size={22} />
            </a>
          )}
        </>
      ) : st === 'active' ? (
        <div className="ct-body ct-body-active">
          <ConicRing progress={pct} size={54} />
          <div className="ct-pipe">
            {STEP_NODES.map((n, i) => {
              const Ico = STEP_ICON[n.key]
              const cls = i < activeStepIdx ? 'past' : i === activeStepIdx ? 'on' : ''
              return <span key={n.key} className={`ct-pipe-node ${cls}`}><Ico size={13} /></span>
            })}
          </div>
          <span className="ct-no-c">{no}</span>
        </div>
      ) : st === 'failed' ? (
        <div className="ct-body ct-body-failed">
          <span className="ct-x"><IconX size={22} /></span>
          <span className="ct-no-c">{no}</span>
          {slot.message && <span className="ct-failmsg">{slot.message}</span>}
        </div>
      ) : (
        <div className="ct-body ct-body-wait">
          <span className="ct-shimmer" />
          <span className="ct-no-c ct-no-dim">{no}</span>
          <span className="ct-wait-lbl">{getStatusLabel(slot.status)}</span>
        </div>
      )}
    </div>
  )
}
