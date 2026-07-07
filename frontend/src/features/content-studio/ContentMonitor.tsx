/**
 * ContentMonitor.tsx — Content Studio phase 3 (live render monitor) with the
 * "now rendering" scene view + terminal result + publish-metadata generation
 * (CM-9 split). Extracted verbatim from ContentStudio.tsx.
 */
import { useMemo, useState } from 'react'
import type { JobPart } from '@/types/api'
import type { WsLogEvent } from '../../websocket/events'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { Button } from '../../components/ui/Button'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { ConicRing } from '../../components/ui/ConicRing'
import { IconCheck } from '../../components/icons'
import { revealInFolder } from '../../lib/revealInFolder'
import { BASE_URL } from '../../api/client'
import { publishMeta, type ContentPlan, type PublishMeta } from '../../api/content'
import { Stepper, HeroHeader, PublishField } from './shared'
import type { SceneMeta } from './types'

export function ContentMonitor({ jobId, onNew, vi, plan, voiceLang }: {
  jobId: string; onNew: () => void; vi: boolean; plan: ContentPlan | null; voiceLang: string
}) {
  const { stage, jobStatus, jobMessage, progress, liveParts, liveEvents, isTerminal, error } = useRenderSocket(jobId)
  const pct = progress?.overall_progress_percent ?? 0
  const ok = jobStatus === 'completed' || jobStatus === 'completed_with_errors'
  // The finished video — content repoints every scene part at the assembled
  // output, so the first part with an output_file is the deliverable.
  const outputPart = liveParts.find((p) => p.output_file)
  const outputFile = outputPart?.output_file || ''
  const streamUrl = outputPart ? `${BASE_URL}/api/jobs/${jobId}/parts/${outputPart.part_no}/stream` : ''
  const [pubBusy, setPubBusy] = useState(false)
  const [pubMeta, setPubMeta] = useState<PublishMeta | null>(null)
  const [pubErr, setPubErr] = useState<string | null>(null)

  async function genPublish() {
    if (pubBusy || !plan) return
    setPubBusy(true); setPubErr(null)
    try {
      const sample = (plan.scenes || []).slice(0, 6).map((s) => s.narration).join(' ')
      const { meta } = await publishMeta({
        topic: plan.topic, tone: plan.tone, audience: plan.audience,
        voice_language: voiceLang, narration_sample: sample,
      })
      setPubMeta(meta)
    } catch (e) {
      setPubErr(e instanceof Error ? e.message : String(e))
    } finally {
      setPubBusy(false)
    }
  }
  const planReady = useMemo(() => liveEvents.some((e) => (e as { event?: string }).event === 'content.plan.ready'), [liveEvents])

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={3} />
      <HeroHeader icon="🎞️" title={vi ? 'Đang render…' : 'Rendering…'}
        subtitle={jobMessage || stage || ''} />
      <section className="cs-card">
        <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Tiến độ' : 'Progress'}</span></div>
        <ProgressBar value={pct} variant={isTerminal ? (ok ? 'success' : 'error') : 'default'} />
        <div className="cs-hint">
          {vi ? 'Giai đoạn' : 'Stage'}: <b>{stage || '—'}</b>{planReady && <> · {vi ? 'kế hoạch sẵn sàng' : 'plan ready'}</>}
        </div>
      </section>

      <section className="cs-card cs-card--flush cs-live-wrap">
        <ContentLiveView vi={vi} liveParts={liveParts} liveEvents={liveEvents} />
      </section>
      {isTerminal && (
        <section className="cs-card" style={{ borderColor: ok ? 'var(--ok)' : 'var(--fail)' }}>
          <div className="cs-card-hd">
            <span className="cs-card-title" style={{ color: ok ? 'var(--ok)' : 'var(--fail)' }}>
              {ok ? (vi ? '✓ Hoàn thành' : '✓ Done') : (vi ? '✕ Thất bại' : '✕ Failed')}
            </span>
          </div>
          <p className="cs-terminal-msg">{jobMessage || error || ''}</p>

          {ok && streamUrl && (
            <video className="cs-preview" controls src={streamUrl} />
          )}

          <div className="cs-row">
            <Button variant="primary" onClick={onNew}>{vi ? 'Tạo video mới' : 'New content video'}</Button>
            {ok && outputFile && window.electronAPI?.openPath && (
              <>
                <Button variant="secondary" size="sm" onClick={() => window.electronAPI?.openPath?.(outputFile)}>
                  {vi ? '▶ Phát' : '▶ Play'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => revealInFolder(outputFile)}>
                  {vi ? '📁 Mở thư mục' : '📁 Open folder'}
                </Button>
              </>
            )}
            {ok && plan && (
              <Button variant="ghost" size="sm" disabled={pubBusy} onClick={genPublish}>
                {pubBusy ? (vi ? 'Đang tạo…' : 'Generating…') : (vi ? '✨ Tạo tiêu đề/mô tả (AI)' : '✨ Generate title/description (AI)')}
              </Button>
            )}
          </div>
          {pubErr && <div className="cs-hint" style={{ color: 'var(--fail)' }}>{pubErr}</div>}
          {pubMeta && (
            <div className="cs-publish">
              <PublishField vi={vi} label={vi ? 'Tiêu đề' : 'Title'} value={pubMeta.title} />
              <PublishField vi={vi} label={vi ? 'Mô tả' : 'Description'} value={pubMeta.description} multiline />
              <PublishField vi={vi} label={vi ? 'Thẻ' : 'Tags'} value={(pubMeta.tags || []).join(', ')} />
              {typeof pubMeta.thumbnail_scene_index === 'number' && pubMeta.thumbnail_scene_index >= 0 && (
                <div className="cs-hint">
                  {vi ? 'Ảnh bìa gợi ý: cảnh ' : 'Suggested thumbnail: scene '}<b>{pubMeta.thumbnail_scene_index + 1}</b>
                </div>
              )}
            </div>
          )}
        </section>
      )}
      {!isTerminal && <div style={{ marginTop: 'var(--space-3)' }}><Button variant="ghost" onClick={onNew}>{vi ? 'Tạo cái khác' : 'Start another'}</Button></div>}
    </div>
  )
}

// ── Live render: AI Activity Feed + Scene grid (P4) ─────────────────────────

// Scene status helpers (mirror RecapLiveView semantics).
function _lvNorm(s: string | undefined): string { return (s || '').toLowerCase() }
function _lvActive(s: string | undefined): boolean { return ['rendering', 'cutting', 'transcribing'].includes(_lvNorm(s)) }
function _lvDone(s: string | undefined): boolean { return _lvNorm(s) === 'done' }
function _lvFailed(s: string | undefined): boolean { return ['failed', 'cancelled', 'skipped'].includes(_lvNorm(s)) }
function _lvGlyph(s: string | undefined): string {
  if (_lvDone(s)) return '✓'
  if (_lvActive(s)) return '◉'
  if (_lvFailed(s)) return '✕'
  return '○'
}

// ContentLiveView — "Now Rendering" view modelled on RecapLiveView: a LEFT focus
// column (the scene rendering now — ConicRing + title + narration) and a RIGHT
// queue (compact scene rows). Content has no episodes, so the queue is a flat
// scene list. Data comes from liveParts + the content.plan.ready event.
function ContentLiveView({ vi, liveParts, liveEvents }: {
  vi: boolean; liveParts: JobPart[]; liveEvents: WsLogEvent[]
}) {
  const planEv = [...liveEvents].reverse().find((e) => e.event === 'content.plan.ready')
  const metaByN = new Map<number, SceneMeta>(
    (((planEv?.context?.scenes) as SceneMeta[] | undefined) ?? [])
      .filter(Boolean).map((s) => [Number(s.n), s]),
  )
  const parts = liveParts
  if (parts.length === 0) {
    return <div className="cs-hint" style={{ padding: '14px 16px' }}>{vi ? 'Chờ AI lập kế hoạch cảnh…' : 'Waiting for the AI scene plan…'}</div>
  }
  const actives = [...parts].filter((p) => _lvActive(p.status))
    .sort((a, b) => (b.progress_percent ?? 0) - (a.progress_percent ?? 0))
  const focus = actives[0] ?? parts.find((p) => !_lvDone(p.status)) ?? parts[parts.length - 1]
  const doneCount = parts.filter((p) => _lvDone(p.status)).length

  const roleOf = (p: JobPart) => (metaByN.get(p.part_no)?.role || metaByN.get(p.part_no)?.scene_title || `${vi ? 'Cảnh' : 'Scene'} ${p.part_no}`)
  const statusLabel = (p: JobPart) => _lvDone(p.status) ? (vi ? 'Xong' : 'Done')
    : _lvFailed(p.status) ? (vi ? 'Lỗi' : 'Failed')
    : _lvActive(p.status) ? (vi ? 'Đang dựng' : 'Rendering') : (vi ? 'Chờ' : 'Waiting')

  return (
    <div className="cs-live">
      {/* LEFT — the scene being rendered now */}
      <div className="cs-live-focus">
        <div className="cs-live-label">{vi ? 'ĐANG DỰNG CẢNH' : 'BUILDING SCENE'}</div>
        {focus && <ContentFocusCard vi={vi} part={focus} meta={metaByN.get(focus.part_no)} roleLabel={roleOf(focus)} />}
      </div>
      {/* RIGHT — compact scene queue */}
      <div className="cs-live-queue">
        <div className="cs-live-queue-hd">{(vi ? 'Cảnh' : 'Scenes')} {doneCount}/{parts.length}</div>
        <div className="cs-live-rows">
          {parts.map((p) => {
            const st = _lvNorm(p.status)
            const isFocus = focus?.part_no === p.part_no
            return (
              <div key={p.part_no} className={`cs-live-row${isFocus ? ' is-focus' : ''}`}>
                <span className={`cs-live-glyph st-${st}`}>{_lvGlyph(p.status)}</span>
                <div className="cs-live-row-main">
                  <div className="cs-live-row-title"><span className="cs-live-row-n">#{p.part_no}</span> {roleOf(p)}</div>
                  {p.message && <div className="cs-live-row-sub">{p.message}</div>}
                </div>
                <span className={`cs-live-row-pct st-${st}`}>
                  {_lvActive(p.status) && (p.progress_percent ?? 0) > 0 ? `${Math.round(p.progress_percent ?? 0)}%` : statusLabel(p)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function ContentFocusCard({ vi, part, meta, roleLabel }: {
  vi: boolean; part: JobPart; meta?: SceneMeta; roleLabel: string
}) {
  const done = _lvDone(part.status)
  const active = _lvActive(part.status)
  const pct = active ? Math.max(2, Math.round(part.progress_percent ?? 0)) : (done ? 100 : 0)
  const statusLabel = done ? (vi ? 'Xong' : 'Done') : active ? (vi ? 'Đang dựng' : 'Rendering') : (vi ? 'Chờ' : 'Waiting')
  const narr = (meta?.narration || '').trim()
  return (
    <>
      <div className="cs-focus-preview">
        <ConicRing progress={pct} size={76}>{done ? <IconCheck size={24} /> : undefined}</ConicRing>
        <span className="cs-focus-n">#{part.part_no}</span>
        <span className={`cs-focus-status st-${_lvNorm(part.status)}`}>{statusLabel}</span>
      </div>
      <div>
        <div className="cs-focus-title">{roleLabel}</div>
        <div className="cs-focus-sub">{part.message || (vi ? 'Đang xử lý…' : 'Processing…')}</div>
      </div>
      <div className="cs-focus-track"><div className="cs-focus-fill" style={{ width: `${pct}%` }} /></div>
      {narr && <div className="cs-focus-narr">💬 {narr}</div>}
    </>
  )
}
