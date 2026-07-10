/**
 * PlanReview — Story v2 phase 2 (review/edit the StoryPlan before render).
 *
 * F1 scaffold: a read-only plan summary + Render / Back. F3 fleshes this out into
 * CharactersPanel · VisualsPanel · TimelineEditor (edit narration / visuals /
 * focus / motion / transition / hooks). Uses the Studio BASE (F0) only.
 */
import { StudioCard } from '../../../components/studio'
import type { StoryPlanV2 } from '../../../api/story'
import type { Aspect, StoryLang } from '../types'

export function PlanReview({ vi, plan, estTotal, busy, onRender, onBack }: {
  vi: boolean
  plan: StoryPlanV2
  setPlan: (p: StoryPlanV2) => void
  estTotal: number
  busy: boolean
  artStyle: string
  aspect: Aspect
  language: StoryLang
  onRender: () => void
  onBack: () => void
}) {
  const mins = Math.floor(estTotal / 60)
  const secs = Math.round(estTotal % 60)
  return (
    <>
      <StudioCard icon="🎬" title={plan.topic || (vi ? 'Kế hoạch truyện' : 'Story plan')}
        aside={vi ? `~${mins}m ${secs}s` : `~${mins}m ${secs}s`}>
        <div className="st-stat-row">
          <Stat n={plan.characters.length} label={vi ? 'Nhân vật' : 'Characters'} />
          <Stat n={plan.visuals.length} label={vi ? 'Key-visual' : 'Key visuals'} />
          <Stat n={plan.timeline.length} label={vi ? 'Phân đoạn' : 'Beats'} />
        </div>
        <p className="st-muted">
          {vi ? 'Trình biên tập nhân vật / hình / timeline sẽ có ở bước F3. Giờ có thể render trực tiếp.'
              : 'The character / visual / timeline editor lands in F3. You can render directly for now.'}
        </p>
      </StudioCard>

      <div className="st-actions st-actions--split">
        <button type="button" className="st-btn" disabled={busy} onClick={onBack}>
          {vi ? '‹ Sửa nguồn' : '‹ Edit source'}
        </button>
        <button type="button" className="st-btn st-btn--primary" disabled={busy} onClick={onRender}>
          {busy ? (vi ? 'Đang gửi…' : 'Submitting…') : (vi ? '🎥 Render' : '🎥 Render')}
        </button>
      </div>
    </>
  )
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div className="st-stat">
      <span className="st-stat-n">{n}</span>
      <span className="st-stat-l">{label}</span>
    </div>
  )
}
