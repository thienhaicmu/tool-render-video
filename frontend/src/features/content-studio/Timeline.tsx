/**
 * Timeline.tsx — CM-11 visual scene timeline for the Review phase.
 *
 * A horizontal strip of scene blocks whose width is proportional to each scene's
 * planned duration, coloured by role and flagged by the narration audit. Drag a
 * block onto another to reorder (native HTML5 drag — no dependency; a discrete
 * drop → one state update, so index keys are fine). Click a block to scroll to
 * its editor row. A ruler shows the estimated total vs the target.
 *
 * No sid needed: reorder is a discrete drop (not a live-sorted list), and the
 * render submit reindexes scenes densely — see CM-5 (dropped) rationale.
 */
import { useState } from 'react'
import type { ContentPlan } from '../../api/content'
import { sceneAudit } from './shared'

export function Timeline({ vi, plan, targetDuration, onReorder, onSelect }: {
  vi: boolean
  plan: ContentPlan
  targetDuration: number
  onReorder: (from: number, to: number) => void
  onSelect: (i: number) => void
}) {
  const [dragFrom, setDragFrom] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)
  const total = plan.scenes.reduce((s, sc) => s + (sc.est_duration_sec || 0), 0)
  const denom = total || 1

  return (
    <section className="cs-card cs-timeline">
      <div className="cs-card-hd">
        <span className="cs-card-title">{vi ? '🎬 Dòng thời gian' : '🎬 Timeline'}</span>
        <span className="cs-count">
          ~{total.toFixed(0)}s / {targetDuration}s
        </span>
      </div>
      <div className="cs-tl-track">
        {plan.scenes.map((s, i) => {
          const w = Math.max(5, ((s.est_duration_sec || 0) / denom) * 100)
          const audit = sceneAudit(s)
          const cls = [
            'cs-tl-block',
            `role-${(s.role || 'x').replace(/[^a-z]/gi, '') || 'x'}`,
            dragFrom === i ? 'is-drag' : '',
            over === i && dragFrom !== null && dragFrom !== i ? 'is-over' : '',
            audit.flag === 'overloaded' ? 'is-over-audit' : audit.flag === 'sparse' ? 'is-sparse' : '',
          ].filter(Boolean).join(' ')
          return (
            <div
              key={i}
              className={cls}
              style={{ width: `${w}%` }}
              draggable
              onDragStart={() => setDragFrom(i)}
              onDragEnd={() => { setDragFrom(null); setOver(null) }}
              onDragOver={(e) => { e.preventDefault(); setOver(i) }}
              onDrop={() => {
                if (dragFrom !== null && dragFrom !== i) onReorder(dragFrom, i)
                setDragFrom(null); setOver(null)
              }}
              onClick={() => onSelect(i)}
              title={`${s.scene_title || s.role || (vi ? 'Cảnh' : 'Scene') + ' ' + (i + 1)} · ~${(s.est_duration_sec || 0).toFixed(0)}s`}
            >
              <span className="cs-tl-n">{i + 1}</span>
              {w > 9 && <span className="cs-tl-role">{s.role || ''}</span>}
            </div>
          )
        })}
      </div>
      <div className="cs-hint" style={{ marginTop: 6 }}>
        {vi ? 'Kéo để đổi thứ tự · bấm để tới cảnh · độ rộng = thời lượng'
            : 'Drag to reorder · click to jump · width = duration'}
      </div>
    </section>
  )
}
