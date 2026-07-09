/**
 * StoryboardPhase.tsx — Story Studio phase 3: review + edit the AI storyboard
 * (scenes → shots), then "Approve & Render". Editable narration + image prompt
 * per shot; the edited plan is sent to the render as story_plan_override.
 */
import { Button } from '../../components/ui/Button'
import { HeroHeader } from '../content-studio/shared'
import { _CPS, type AuditFlag } from './types'
import type { StoryPlan, Shot } from '../../api/story'

function shotAudit(sh: Shot): AuditFlag {
  const chars = (sh.narration || '').trim().length
  const est = sh.est_duration_sec ?? 0
  const spd = sh.reading_speed ?? 1
  if (est <= 0 || chars <= 0) return 'none'
  const cap = _CPS * spd * est
  if (cap <= 0) return 'none'
  const load = chars / cap
  if (load > 1.3) return 'overloaded'
  if (load < 0.6) return 'sparse'
  return 'ok'
}

export function StoryboardPhase({ vi, plan, setPlan, estTotal, busy, error, onBack, onRender }: {
  vi: boolean; plan: StoryPlan; setPlan: (p: StoryPlan) => void; estTotal: number
  busy: boolean; error: string | null; onBack: () => void; onRender: () => void
}) {
  const shotCount = plan.scenes.reduce((n, s) => n + s.shots.length, 0)
  const canRender = shotCount > 0 && !busy

  function updateShot(si: number, shi: number, patch: Partial<Shot>) {
    setPlan({
      ...plan,
      scenes: plan.scenes.map((sc, i) => i !== si ? sc : {
        ...sc, shots: sc.shots.map((sh, j) => j !== shi ? sh : { ...sh, ...patch }),
      }),
    })
  }

  return (
    <div className="cs-screen">
      <HeroHeader icon="🎬" title={vi ? 'Storyboard' : 'Storyboard'}
        subtitle={
          <>
            {plan.topic ? <b>{plan.topic}</b> : null}
            {plan.art_style ? ` · ${plan.art_style}` : ''}
            {' · '}{plan.scenes.length} {vi ? 'cảnh' : 'scenes'} · {shotCount} shot
            {estTotal > 0 ? ` · ~${estTotal.toFixed(0)}s` : ''}
            {' · '}{vi ? 'Sửa lời kể / prompt hình trước khi render.' : 'Edit narration / image prompt before rendering.'}
          </>
        } />

      {plan.scenes.map((sc, si) => (
        <section key={si} className="cs-card">
          <div className="st-scene-hd">
            <span className="cs-char-chip">{vi ? 'Cảnh' : 'Scene'} {si + 1}</span>
            {sc.role && <span className="cs-char-chip">{sc.role}</span>}
            {sc.scene_title && <b>{sc.scene_title}</b>}
          </div>
          {sc.shots.map((sh, shi) => {
            const flag = shotAudit(sh)
            return (
              <div key={sh.sid || shi} className="st-shot">
                <div className="st-shot-meta">
                  <span>Shot {shi + 1}</span>
                  <span className="cs-char-chip">{sh.shot_type}</span>
                  {sh.speaker ? <span className="cs-char-chip">🗣 {sh.speaker}</span> : null}
                  {sh.quality_tier ? <span className="cs-char-chip st-tier">{sh.quality_tier}</span> : null}
                  {flag === 'overloaded' && <span className="cs-audit-badge is-over">{vi ? '⚠ Quá tải' : '⚠ Overloaded'}</span>}
                  {flag === 'sparse' && <span className="cs-audit-badge is-sparse">{vi ? 'Thưa' : 'Sparse'}</span>}
                </div>
                <textarea className="cs-textarea cs-textarea--sm" value={sh.narration}
                  onChange={(e) => updateShot(si, shi, { narration: e.target.value })}
                  placeholder={vi ? 'Lời kể…' : 'Narration…'} />
                <textarea className="cs-textarea cs-textarea--sm" style={{ marginTop: 6 }} value={sh.visual_prompt || ''}
                  onChange={(e) => updateShot(si, shi, { visual_prompt: e.target.value })}
                  placeholder={vi ? 'Prompt hình ảnh (tiếng Anh)…' : 'Image prompt (English)…'} />
              </div>
            )
          })}
        </section>
      ))}

      <div className="cs-footer">
        <Button variant="ghost" onClick={onBack} disabled={busy}>{vi ? '← Nhân vật' : '← Characters'}</Button>
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={!canRender} onClick={onRender}>
          {busy ? (vi ? 'Đang gửi…' : 'Starting…') : (vi ? 'Duyệt & Render →' : 'Approve & Render →')}
        </Button>
      </div>
    </div>
  )
}
