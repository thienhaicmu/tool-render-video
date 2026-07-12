/**
 * TimelineEditor — Story v2 review (F3), the ⭐ of the plan editor.
 *
 * The beat list: edit narration · speaker · visual (colour-badged, thumbnail when
 * previewed) · focus · motion · transition · hook + hook text; reorder (▲▼),
 * delete (✕), insert (＋). Shows a per-beat duration estimate + the running total.
 * Studio BASE only — no content-studio.
 */
import { StudioCard } from '../../../components/studio'
import type { StoryPlanV2, Beat } from '../../../api/story'
import { FOCUS, MOTION, TRANSITION, EMOTION, POSE, type StoryLang } from '../types'
import { beatEstSec } from './helpers'

export function TimelineEditor({ vi, plan, language, colors, previews, onChangeBeat, onMove, onDelete, onAdd }: {
  vi: boolean
  plan: StoryPlanV2
  language: StoryLang
  colors: Record<string, string>
  previews: Record<string, string>
  onChangeBeat: (id: string, up: Partial<Beat>) => void
  onMove: (id: string, dir: -1 | 1) => void
  onDelete: (id: string) => void
  onAdd: (afterId: string) => void
}) {
  const total = plan.timeline.reduce((s, b) => s + beatEstSec(b, language) + Math.max(0, b.pause_after || 0), 0)
  const speakers = [{ id: '', name: vi ? 'Người kể' : 'Narrator' },
    ...plan.characters.map((c) => ({ id: c.id, name: c.name || c.id }))]

  return (
    <StudioCard icon="🎞️" title={vi ? 'Timeline (phân đoạn)' : 'Timeline (beats)'}
      aside={`${plan.timeline.length} · ~${Math.floor(total / 60)}m ${Math.round(total % 60)}s`}>
      <div className="st-tl">
        {plan.timeline.map((b, i) => (
          <div className="st-tl-row" key={b.id}>
            <div className="st-tl-badge" style={{ background: colors[b.visual_id] || 'var(--border)' }}
              title={b.visual_id}>
              {previews[b.visual_id]
                ? <img src={previews[b.visual_id]} alt={b.visual_id} />
                : <span>{i + 1}</span>}
            </div>

            <div className="st-tl-main">
              <textarea className="st-textarea st-textarea--sm" rows={2}
                placeholder={vi ? 'Lời kể…' : 'Narration…'} value={b.narration}
                onChange={(e) => onChangeBeat(b.id, { narration: e.target.value })} />

              <div className="st-tl-controls">
                <Sel label={vi ? 'Giọng' : 'Speaker'} value={b.speaker_id}
                  onChange={(v) => onChangeBeat(b.id, { speaker_id: v })}
                  opts={speakers.map((s) => ({ value: s.id, label: s.name }))} />
                <Sel label={vi ? 'Hình' : 'Visual'} value={b.visual_id}
                  onChange={(v) => onChangeBeat(b.id, { visual_id: v })}
                  opts={plan.visuals.map((v) => ({ value: v.id, label: v.id }))} />
                <Sel label={vi ? 'Khung' : 'Focus'} value={b.focus}
                  onChange={(v) => onChangeBeat(b.id, { focus: v })}
                  opts={FOCUS.map((f) => ({ value: f, label: f }))} />
                <Sel label={vi ? 'Chuyển động' : 'Motion'} value={b.motion}
                  onChange={(v) => onChangeBeat(b.id, { motion: v })}
                  opts={MOTION.map((m) => ({ value: m, label: m }))} />
                <Sel label={vi ? 'Chuyển cảnh' : 'Transition'} value={b.transition_in}
                  onChange={(v) => onChangeBeat(b.id, { transition_in: v })}
                  opts={TRANSITION.map((t) => ({ value: t, label: t }))} />
                {/* Per-beat speaker expression + gesture — only relevant when a character speaks. */}
                {b.speaker_id && (
                  <>
                    <Sel label={vi ? 'Cảm xúc' : 'Emotion'} value={b.emotion || 'normal'}
                      onChange={(v) => onChangeBeat(b.id, { emotion: v })}
                      opts={EMOTION.map((e) => ({ value: e, label: e }))} />
                    <Sel label={vi ? 'Tư thế' : 'Pose'} value={b.pose || 'stand'}
                      onChange={(v) => onChangeBeat(b.id, { pose: v })}
                      opts={POSE.map((p) => ({ value: p, label: p }))} />
                  </>
                )}
                <label className="st-tl-hook">
                  <input type="checkbox" checked={b.hook}
                    onChange={(e) => onChangeBeat(b.id, { hook: e.target.checked })} />
                  {vi ? 'Hook' : 'Hook'}
                </label>
              </div>

              {b.hook && (
                <input className="st-input st-input--sm" placeholder={vi ? 'Chữ hook trên màn hình…' : 'On-screen hook text…'}
                  value={b.hook_text} onChange={(e) => onChangeBeat(b.id, { hook_text: e.target.value })} />
              )}
            </div>

            <div className="st-tl-side">
              <span className="st-tl-sec">{beatEstSec(b, language).toFixed(1)}s</span>
              <div className="st-tl-ops">
                <button type="button" className="st-icon-btn" title={vi ? 'Lên' : 'Up'}
                  disabled={i === 0} onClick={() => onMove(b.id, -1)}>▲</button>
                <button type="button" className="st-icon-btn" title={vi ? 'Xuống' : 'Down'}
                  disabled={i === plan.timeline.length - 1} onClick={() => onMove(b.id, 1)}>▼</button>
                <button type="button" className="st-icon-btn" title={vi ? 'Thêm dưới' : 'Add below'}
                  onClick={() => onAdd(b.id)}>＋</button>
                <button type="button" className="st-icon-btn st-icon-btn--danger" title={vi ? 'Xoá' : 'Delete'}
                  disabled={plan.timeline.length <= 1} onClick={() => onDelete(b.id)}>✕</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </StudioCard>
  )
}

function Sel({ label, value, onChange, opts }: {
  label: string
  value: string
  onChange: (v: string) => void
  opts: { value: string; label: string }[]
}) {
  return (
    <label className="st-tl-sel">
      <span>{label}</span>
      <select className="st-select st-select--sm" value={value} onChange={(e) => onChange(e.target.value)}>
        {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}
