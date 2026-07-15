/**
 * TimelineEditor — Story v2 review (F3), the ⭐ of the plan editor.
 *
 * The beat list: edit narration · speaker · visual (colour-badged, thumbnail when
 * previewed) · focus · motion · transition · hook + hook text; reorder (▲▼),
 * delete (✕), insert (＋). Shows a per-beat duration estimate + the running total.
 * Studio BASE only — no content-studio.
 */
import { StudioCard } from '../../../components/studio'
import type { StoryPlanV2, Beat, Line, ShotDef } from '../../../api/story'
import { FOCUS, MOTION, TRANSITION, EMOTION, POSE, type StoryLang } from '../types'
import { beatEstSec } from './helpers'

const SHOT_SIZE = ['extreme_wide', 'wide', 'medium', 'close', 'extreme_close']
const SHOT_ANGLE = ['eye_level', 'high', 'low', 'over_shoulder', 'top_down', 'dutch']
const MOTION_INTENT = ['static', 'push_in', 'pull_out', 'track_left', 'track_right', 'reveal']

export function TimelineEditor({ vi, plan, language, colors, previews, onChangeBeat, onChangeShot, onMove, onDelete, onAdd }: {
  vi: boolean
  plan: StoryPlanV2
  language: StoryLang
  colors: Record<string, string>
  previews: Record<string, string>
  onChangeBeat: (id: string, up: Partial<Beat>) => void
  onChangeShot: (id: string, up: Partial<ShotDef>) => void
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
        {plan.timeline.map((b, i) => {
          const shot = (plan.shots ?? []).find((item) => item.id === b.shot_id)
          const scene = (plan.scenes ?? []).find((item) => item.id === shot?.scene_id)
          return (
          <div className="st-tl-row" key={b.id}>
            <div className="st-tl-badge" style={{ background: colors[b.visual_id] || 'var(--border)' }}
              title={b.visual_id}>
              {previews[b.visual_id]
                ? <img src={previews[b.visual_id]} alt={b.visual_id} />
                : <span>{i + 1}</span>}
            </div>

            <div className="st-tl-main">
              {shot && (
                <div className="st-shot-meta">
                  <span>{scene?.id || shot.scene_id}</span>
                  <span>{scene?.purpose || 'scene'}</span>
                  <span>{shot.id}</span>
                </div>
              )}
              {b.lines && b.lines.length ? (
                <LinesEditor vi={vi} lines={b.lines} speakers={speakers}
                  onChange={(lines) => onChangeBeat(b.id, { lines })} />
              ) : (
                <div className="st-tl-narr" style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                  <textarea className="st-textarea st-textarea--sm" rows={2} style={{ flex: 1 }}
                    placeholder={vi ? 'Lời kể…' : 'Narration…'} value={b.narration}
                    onChange={(e) => onChangeBeat(b.id, { narration: e.target.value })} />
                  <button type="button" className="st-icon-btn" title={vi ? 'Tách thành nhiều lượt thoại' : 'Split into dialogue lines'}
                    onClick={() => onChangeBeat(b.id, { lines: [{ speaker_id: b.speaker_id, text: b.narration, emotion: b.emotion || 'normal', pose: b.pose || 'stand' }] })}>
                    💬
                  </button>
                </div>
              )}

              <div className="st-tl-controls">
                {!(b.lines && b.lines.length) && (
                <Sel label={vi ? 'Giọng' : 'Speaker'} value={b.speaker_id}
                  onChange={(v) => onChangeBeat(b.id, { speaker_id: v })}
                  opts={speakers.map((s) => ({ value: s.id, label: s.name }))} />
                )}
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
                {shot && (
                  <>
                    <Sel label={vi ? 'Cỡ cảnh' : 'Shot size'} value={shot.shot_size}
                      onChange={(v) => onChangeShot(shot.id, { shot_size: v })}
                      opts={SHOT_SIZE.map((value) => ({ value, label: value }))} />
                    <Sel label={vi ? 'Góc máy' : 'Angle'} value={shot.angle}
                      onChange={(v) => onChangeShot(shot.id, { angle: v })}
                      opts={SHOT_ANGLE.map((value) => ({ value, label: value }))} />
                    <Sel label={vi ? 'Máy quay' : 'Camera'} value={shot.motion_intent}
                      onChange={(v) => onChangeShot(shot.id, { motion_intent: v })}
                      opts={MOTION_INTENT.map((value) => ({ value, label: value }))} />
                  </>
                )}
                {/* Per-beat speaker expression + gesture — single-line mode only (in
                    multi-line mode emotion/pose live per line inside the LinesEditor). */}
                {!(b.lines && b.lines.length) && b.speaker_id && (
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
          )
        })}
      </div>
    </StudioCard>
  )
}

/** P2 — edit a beat's dialogue lines: one row per turn (speaker · text · emotion),
 * with add/remove. A beat = one shot that may hold several turns. */
function LinesEditor({ vi, lines, speakers, onChange }: {
  vi: boolean
  lines: Line[]
  speakers: { id: string; name: string }[]
  onChange: (lines: Line[]) => void
}) {
  const set = (i: number, up: Partial<Line>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...up } : l)))
  const add = () => onChange([...lines, { speaker_id: '', text: '', emotion: 'normal', pose: 'stand' }])
  const del = (i: number) => onChange(lines.filter((_, j) => j !== i))
  return (
    <div className="st-tl-lines" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {lines.map((l, i) => (
        <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
          <select className="st-select st-select--sm" value={l.speaker_id}
            title={vi ? 'Người nói' : 'Speaker'}
            onChange={(e) => set(i, { speaker_id: e.target.value })}>
            {speakers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <textarea className="st-textarea st-textarea--sm" rows={1} style={{ flex: 1 }}
            placeholder={vi ? 'Lời thoại…' : 'Line…'} value={l.text}
            onChange={(e) => set(i, { text: e.target.value })} />
          <select className="st-select st-select--sm" value={l.emotion || 'normal'}
            title={vi ? 'Cảm xúc' : 'Emotion'}
            onChange={(e) => set(i, { emotion: e.target.value })}>
            {EMOTION.map((em) => <option key={em} value={em}>{em}</option>)}
          </select>
          <button type="button" className="st-icon-btn st-icon-btn--danger"
            disabled={lines.length <= 1} title={vi ? 'Xoá dòng' : 'Delete line'}
            onClick={() => del(i)}>✕</button>
        </div>
      ))}
      <button type="button" className="st-icon-btn" style={{ alignSelf: 'flex-start' }}
        title={vi ? 'Thêm lượt thoại' : 'Add line'} onClick={add}>＋ {vi ? 'thoại' : 'line'}</button>
    </div>
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
