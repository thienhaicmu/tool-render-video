/**
 * ReviewPhase.tsx — Content Studio phase 2 (review + edit the AI plan) plus the
 * AI Insights summary and the paid-visual cost preflight (CM-9 split). Extracted
 * verbatim from ContentStudio.tsx.
 */
import { useMemo, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { AIChip } from '../../components/ui/AIChip'
import {
  estimateContentCost,
  type ContentPlan, type ContentScene, type DurationFit, type ContentEstimate,
} from '../../api/content'
import { Stepper, HeroHeader, sceneAudit } from './shared'
import { SceneRow } from './SceneRow'
import { _PROVIDER_LABELS, type Config, type VoiceCfg, type VisualCfg } from './types'

export function ReviewPhase({ vi, plan, setPlan, busy, error, durationFit, visualProvider, targetDuration, aspectApi, imagenTier, voice, onBack, onApprove }: {
  vi: boolean; plan: ContentPlan; setPlan: (p: ContentPlan) => void
  busy: boolean; error: string | null
  durationFit: DurationFit | null; visualProvider: Config['visualProvider']; targetDuration: number
  aspectApi: string; imagenTier: string
  voice: VoiceCfg; onBack: () => void; onApprove: () => void
}) {
  const visualCfg: VisualCfg = { provider: visualProvider, aspectApi, style: plan.video_style || '', imagenTier }
  function updateScene(i: number, patch: Partial<ContentScene>) {
    setPlan({ ...plan, scenes: plan.scenes.map((s, idx) => (idx === i ? { ...s, ...patch } : s)) })
  }
  function removeScene(i: number) {
    setPlan({ ...plan, scenes: plan.scenes.filter((_, idx) => idx !== i) })
  }
  function moveScene(i: number, dir: -1 | 1) {
    const j = i + dir
    if (j < 0 || j >= plan.scenes.length) return
    const next = [...plan.scenes]
    ;[next[i], next[j]] = [next[j], next[i]]
    setPlan({ ...plan, scenes: next })
  }
  function addScene() {
    setPlan({ ...plan, scenes: [...plan.scenes, { index: plan.scenes.length, role: 'explain', narration: '', emotion: 'normal', reading_speed: 1.0 }] })
  }

  const canRender = plan.scenes.some((s) => (s.narration || '').trim()) && !busy

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={2} />
      <HeroHeader icon="🎬" title={vi ? 'Duyệt kế hoạch AI' : 'Review AI Plan'}
        subtitle={
          <>
            {plan.topic ? <b>{plan.topic}</b> : null}
            {plan.video_style ? ` · ${plan.video_style}` : ''}
            {' · '}{plan.scenes.length} {vi ? 'cảnh' : 'scenes'}
            {' · '}{vi ? 'Sửa lời kể / cảm xúc / thời lượng, thêm-xoá-đổi thứ tự cảnh trước khi render.' : 'Edit narration / emotion / duration, add-remove-reorder before rendering.'}
          </>
        } />

      <AiInsights vi={vi} plan={plan} durationFit={durationFit} visualProvider={visualProvider} targetDuration={targetDuration} />

      {visualProvider !== 'local' && (
        <CostEstimatePanel vi={vi} plan={plan} visualProvider={visualProvider} targetDuration={targetDuration} />
      )}

      <div className="cs-scene-list">
        {plan.scenes.map((s, i) => (
          <SceneRow key={i} vi={vi} scene={s} index={i} total={plan.scenes.length} voice={voice} visualCfg={visualCfg}
            onChange={(patch) => updateScene(i, patch)} onRemove={() => removeScene(i)} onMove={(d) => moveScene(i, d)} />
        ))}
        <div><Button variant="ghost" size="sm" onClick={addScene}>+ {vi ? 'Thêm cảnh' : 'Add scene'}</Button></div>
      </div>

      <div className="cs-footer">
        <Button variant="ghost" onClick={onBack} disabled={busy}>{vi ? '← Quay lại kịch bản' : '← Back to script'}</Button>
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={!canRender} onClick={onApprove}>
          {busy ? (vi ? 'Đang gửi…' : 'Starting…') : (vi ? 'Duyệt & Render →' : 'Approve & Render →')}
        </Button>
      </div>
    </div>
  )
}

// ── AI Insights (Review) ────────────────────────────────────────────────────

function AiInsights({ vi, plan, durationFit, visualProvider, targetDuration }: {
  vi: boolean; plan: ContentPlan; durationFit: DurationFit | null
  visualProvider: Config['visualProvider']; targetDuration: number
}) {
  const audit = useMemo(() => {
    let over = 0, sparse = 0, rated = 0
    for (const s of plan.scenes) {
      const { flag } = sceneAudit(s)
      if (flag === 'none') continue
      rated++
      if (flag === 'overloaded') over++
      else if (flag === 'sparse') sparse++
    }
    return { over, sparse, rated, weak: over > 0 || (rated > 0 && sparse / rated > 0.4) }
  }, [plan])
  const chars = (plan.story_bible?.characters || []).filter((c) => (c.name || c.id))
  const estTotal = plan.scenes.reduce((sum, s) => sum + (s.est_duration_sec || 0), 0)

  return (
    <section className="cs-card cs-insights">
      <div className="cs-card-hd"><span className="cs-card-title">{vi ? '✨ AI đã làm gì' : '✨ What the AI did'}</span></div>
      <div className="cs-insight-list">
        {durationFit?.changed ? (
          <div className="cs-insight">
            <AIChip variant="applied" label={vi ? 'Chỉnh nhịp đọc' : 'Paced to target'} />
            <span>{vi ? 'Điều chỉnh tốc độ đọc để vừa mục tiêu' : 'Adjusted reading speed to hit the target'}:{' '}
              <b>{durationFit.before_sec.toFixed(0)}s → {durationFit.after_sec.toFixed(0)}s</b>
              {durationFit.applied_scale ? ` (×${durationFit.applied_scale})` : ''}</span>
          </div>
        ) : (
          <div className="cs-insight">
            <AIChip variant="advisory" label={vi ? 'Thời lượng' : 'Duration'} />
            <span>{vi ? 'Ước tính' : 'Estimated'} <b>~{estTotal.toFixed(0)}s</b> {vi ? '/ mục tiêu' : '/ target'} {targetDuration}s</span>
          </div>
        )}

        {(plan.topic || chars.length > 0) && (
          <div className="cs-insight">
            <AIChip variant="applied" label={vi ? 'Hiểu nội dung' : 'Understood'} />
            <span>
              {plan.topic ? <><b>{plan.topic}</b>{plan.video_style ? ` · ${plan.video_style}` : ''}</> : null}
              {chars.length > 0 && <>{' · '}{vi ? 'Nhân vật' : 'Characters'}: {chars.map((c, i) => (
                <span key={i} className="cs-char-chip">{c.name || c.id}</span>
              ))}</>}
            </span>
          </div>
        )}

        {audit.rated > 0 && (
          <div className="cs-insight">
            <AIChip variant={audit.weak ? 'advisory' : 'applied'} label={vi ? 'Kiểm tra lời kể' : 'Narration check'} />
            <span>
              {audit.weak
                ? (vi ? `${audit.over} cảnh quá tải, ${audit.sparse} cảnh thưa — chỉnh lời kể/thời lượng bên dưới.`
                      : `${audit.over} overloaded, ${audit.sparse} sparse — tweak narration/duration below.`)
                : (vi ? 'Lời kể cân đối với thời lượng từng cảnh.' : "Narration length matches each scene's duration.")}
            </span>
          </div>
        )}

        {visualProvider !== 'local' && (
          <div className="cs-insight">
            <AIChip variant="advisory" label={vi ? 'Nguồn ảnh' : 'Visuals'} />
            <span>{vi ? 'Dùng nguồn ảnh AI/Stock — cần API key. Thiếu key/mạng → tự dùng nền đã chọn.'
                       : 'Using an AI/Stock visual source — needs an API key. Missing key/network → falls back to your background.'}</span>
          </div>
        )}
      </div>
    </section>
  )
}

// ── Cost preflight (Review, paid visual providers) ──────────────────────────

function CostEstimatePanel({ vi, plan, visualProvider, targetDuration }: {
  vi: boolean; plan: ContentPlan; visualProvider: Config['visualProvider']; targetDuration: number
}) {
  const [busy, setBusy] = useState(false)
  const [est, setEst] = useState<ContentEstimate | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function run() {
    if (busy) return
    setBusy(true); setErr(null)
    try {
      const r = await estimateContentCost({
        plan, visual_provider: visualProvider, target_duration: targetDuration, budget_cap: 0,
      })
      setEst(r)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="cs-card cs-cost">
      <div className="cs-card-hd">
        <span className="cs-card-title">{vi ? '💰 Chi phí AI ước tính' : '💰 Estimated AI cost'}</span>
        <Button variant="ghost" size="sm" disabled={busy} onClick={run}>
          {busy ? (vi ? 'Đang tính…' : 'Estimating…') : est ? (vi ? 'Tính lại' : 'Recalculate') : (vi ? 'Ước tính' : 'Estimate')}
        </Button>
      </div>
      {err && <div className="cs-hint" style={{ color: 'var(--fail)' }}>{err}</div>}
      {!est && !err && (
        <div className="cs-hint">
          {vi ? 'Bấm "Ước tính" để xem chi phí ảnh AI trước khi render (không gọi API trả phí).'
              : 'Click "Estimate" to preview the AI image cost before rendering (no paid API call).'}
        </div>
      )}
      {est && (
        <div className="cs-cost-body">
          <div className="cs-cost-total">
            <span
              className="cs-cost-num"
              title={vi
                ? 'Ước tính tương đối dựa trên chi phí trung bình mỗi ảnh/clip AI — không phải hoá đơn chính xác. Nguồn local/stock không tính phí.'
                : 'Rough estimate from average per-asset AI cost — not a precise bill. local/stock sources are free.'}
            >~${est.estimated_cost.toFixed(2)}</span>
            <span className="cs-cost-sub">{est.scenes} {vi ? 'cảnh' : 'scenes'} · ~{est.estimated_duration_sec.toFixed(0)}s</span>
          </div>
          <div className="cs-row" style={{ gap: 6 }}>
            {Object.entries(est.by_provider).map(([prov, n]) => (
              <span key={prov} className="cs-char-chip">{_PROVIDER_LABELS[prov] || prov}: {n}</span>
            ))}
          </div>
          {est.estimated_cost === 0 ? (
            <div className="cs-hint">{vi ? 'Miễn phí — mọi cảnh dùng nguồn không tính phí (local/stock).' : 'Free — every scene uses a no-cost source (local/stock).'}</div>
          ) : (
            <div className="cs-hint">{vi ? '≈ ước tính tương đối (chi phí trung bình mỗi ảnh/clip AI) — không phải hoá đơn chính xác.' : '≈ rough estimate (average per-asset AI cost) — not a precise bill.'}</div>
          )}
        </div>
      )}
    </section>
  )
}
