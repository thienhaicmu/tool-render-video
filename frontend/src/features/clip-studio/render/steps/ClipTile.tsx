/**
 * ClipTile — one clip as a dense queue row (desktop render-dashboard redesign).
 *
 * Matches the reference "Queue" table: index · thumbnail · name/spec · status
 * (colored) · progress bar + % · time · action. Uses only data the pipeline
 * already streams (ClipSlot + per-part thumbnail on done). Clicking a row
 * focuses it in the Current-Rendering card (RenderStage).
 */
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import { IconPlay } from '@/components/icons'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { clipStateKey } from './clipState'
import { ClipSteps } from './ClipSteps'

function fmtDur(sec?: number): string | null {
  if (sec == null || sec <= 0) return null
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
}

export function ClipTile({ slot, jobId, isFocus, onFocus, t, getStatusLabel }: {
  slot: ClipSlot
  jobId: string | null
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
  const no = String(slot.part_no).padStart(2, '0')
  const showBar = st === 'active' || st === 'done'

  return (
    <div
      role="option"
      aria-selected={isFocus}
      tabIndex={0}
      className={`ct-row ct-row-${st}${isFocus ? ' ct-row-focus' : ''}`}
      onClick={() => onFocus(slot.part_no)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus(slot.part_no) } }}
      title={`Clip ${slot.part_no}: ${getStatusLabel(slot.status)}`}
    >
      <span className="ct-idx">{slot.part_no}</span>

      <div className="ct-thumb">
        <span className="ct-thumb-ph">{no}</span>
        {thumbUrl && (
          <img
            src={thumbUrl} alt="" className="ct-thumb-img"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        )}
      </div>

      <div className="ct-name">
        <span className="ct-name-main">{slot.name || `Clip ${no}`}</span>
        <span className="ct-name-spec">{slot.name ? `Clip ${no}${durFmt ? ` · ${durFmt}` : ''}` : (durFmt ?? '')}</span>
      </div>

      <ClipSteps status={slot.status} variant="row" />

      <div className="ct-prog">
        <div className="ct-prog-track">
          {showBar && <div className="ct-prog-fill" style={{ width: `${pct}%` }} />}
        </div>
        <span className="ct-prog-pct">{showBar ? `${pct}%` : '—'}</span>
      </div>

      <span className="ct-time">{durFmt ?? '—'}</span>

      <span className="ct-act">
        {st === 'done' && jobId && (
          <a
            className="ct-act-btn"
            href={getPartMediaUrl(jobId, slot.part_no)}
            target="_blank" rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            aria-label={`Play clip ${slot.part_no}`}
          >
            <IconPlay size={15} />
          </a>
        )}
      </span>
    </div>
  )
}
