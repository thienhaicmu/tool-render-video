import React, { useState, useEffect, useCallback } from 'react'
import type { JobPart, QualityReport, PartRankResult } from '@/types/api'
import { getJobAiSummary, deletePartOutput } from '@/api/jobs'
import { StoryModelCard } from '@/features/jobs/StoryModelCard'
import type { JobAiSummary, HybridAnalysis } from '@/api/jobs'
import {
  submitClipFeedback,
  getClipFeedback,
  deleteClipFeedback,
} from '@/api/feedback'
import type { Strings } from '../i18n'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { confirmDialog } from '@/components/ui/ConfirmDialog'

function aiTier(score: number): { label: string; cls: string } {
  if (score >= 85) return { label: 'VIRAL READY', cls: 'tier-viral' }
  if (score >= 70) return { label: 'HIGH IMPACT', cls: 'tier-high' }
  if (score >= 55) return { label: 'GOOD', cls: 'tier-good' }
  return { label: 'REVIEW', cls: 'tier-review' }
}

function ScoreRingSm({ score }: { score: number }) {
  const r = 13, circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  const col = score >= 70 ? 'var(--ok)' : score >= 40 ? 'var(--warn)' : 'var(--fail)'
  return (
    <div className="sr-wrap">
      <svg width="34" height="34" viewBox="0 0 34 34" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="17" cy="17" r={r} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="3.5" />
        <circle cx="17" cy="17" r={r} fill="none" stroke={col} strokeWidth="3.5"
          strokeDasharray={`${fill} ${circ}`} strokeLinecap="round" />
      </svg>
      <span className="sr-num" style={{ color: col }}>{Math.round(score)}</span>
    </div>
  )
}

function ScoreRingLg({ score }: { score: number }) {
  const r = 28, circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  const col = score >= 70 ? 'var(--ok)' : score >= 40 ? 'var(--warn)' : 'var(--fail)'
  const tier = aiTier(score)
  return (
    <div className="srl-wrap">
      <div style={{ position: 'relative', width: 68, height: 68, flexShrink: 0 }}>
        <svg width="68" height="68" viewBox="0 0 68 68" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="34" cy="34" r={r} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="6" />
          <circle cx="34" cy="34" r={r} fill="none" stroke={col} strokeWidth="6"
            strokeDasharray={`${fill} ${circ}`} strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.5s ease' }} />
        </svg>
        <div className="srl-num" style={{ color: col }}>{Math.round(score)}</div>
      </div>
      <div className="srl-info">
        <div className={`res-ai-tier ${tier.cls}`}>{tier.label}</div>
        <div className="srl-sub">AI Quality Score</div>
      </div>
    </div>
  )
}

function HybridAnalysisBadge({
  hybrid, fallbackMode, fallbackProvider,
}: {
  hybrid?: HybridAnalysis
  fallbackMode?: string
  fallbackProvider?: string
}) {
  if (hybrid && Object.keys(hybrid).length > 0) {
    const src = hybrid.source
    const pct = Math.round(hybrid.confidence * 100)
    const label =
      src === 'cloud'  ? `☁ Cloud AI · ${pct}%` :
      src === 'hybrid' ? `⚡ Hybrid AI · ${pct}%` :
                         `💻 Local AI · ${pct}%`
    const cls = src === 'cloud' ? 'vtag-blue' : src === 'hybrid' ? 'vtag-purple' : 'vtag-teal'
    const title = `${hybrid.clips_analyzed} clips analyzed${hybrid.warnings.length ? ' · ' + hybrid.warnings.join(', ') : ''}`
    return <span className={`res-vtag ${cls}`} title={title}>{label}</span>
  }
  if (!fallbackMode) return null
  const label =
    fallbackMode === 'hybrid' ? '⚡ Hybrid AI' :
    fallbackMode === 'cloud'  ? `☁ Cloud${fallbackProvider ? ' · ' + fallbackProvider : ''}` :
                                '💻 Local AI'
  const cls = fallbackMode === 'cloud' ? 'vtag-blue' : fallbackMode === 'hybrid' ? 'vtag-purple' : 'vtag-teal'
  return <span className={`res-vtag ${cls}`}>{label}</span>
}

// Sprint 5.7: wrapped in React.memo at export below. See StepConfigure for rationale.
function StepResultsBase({
  jobId, parts, partScores, partRanks, qualityReports, qualityLoadFailed,
  loading, t, aspectRatio, jobStatus, jobMessage, onRetry, isRetrying,
  aiAnalysisMode, aiCloudProvider, goal,
}: {
  jobId: string | null
  parts: JobPart[]
  partScores: Record<number, number>
  partRanks: Record<number, PartRankResult>
  qualityReports: Record<number, QualityReport | null>
  qualityLoadFailed: boolean
  loading: boolean
  t: Strings
  aspectRatio: string
  jobStatus: string
  jobMessage: string
  onRetry: () => void
  isRetrying: boolean
  aiAnalysisMode?: string
  aiCloudProvider?: string
  goal?: string
}) {
  const [selectedPart, setSelectedPart] = useState<JobPart | null>(null)
  const [sortMode, setSortMode] = useState<'viral' | 'duration' | 'newest'>('viral')
  const [aiSummary, setAiSummary] = useState<JobAiSummary | null>(null)
  const [aiSummaryOpen, setAiSummaryOpen] = useState(false)
  const [deletedOutputs, setDeletedOutputs] = useState<Set<number>>(new Set())
  const [feedbackRatings, setFeedbackRatings] = useState<Record<number, 1 | -1 | null>>({})

  const handleFeedback = useCallback(async (partNo: number, rating: 1 | -1, part: JobPart) => {
    if (!jobId) return
    const current = feedbackRatings[partNo]
    const newRating = current === rating ? null : rating
    setFeedbackRatings(prev => ({ ...prev, [partNo]: newRating }))
    try {
      if (newRating === null) {
        await deleteClipFeedback(jobId, partNo)
      } else {
        await submitClipFeedback(jobId, partNo, {
          rating: newRating,
          goal: goal ?? '',
          channel_code: '',
          hook_type: 'none',
          clip_type: 'unknown',
          start_sec: 0,
          end_sec: part.duration ?? 0,
          duration_sec: part.duration ?? 0,
        })
      }
    } catch { /* fire-and-forget — UI already updated */ }
  }, [jobId, feedbackRatings, goal])

  // Restore ratings from server when job changes
  useEffect(() => {
    if (!jobId) return
    const doneParts = parts.filter(p => p.status === 'done')
    doneParts.forEach(async (p) => {
      try {
        const record = await getClipFeedback(jobId, p.part_no)
        if (record?.rating) {
          setFeedbackRatings(prev => ({ ...prev, [p.part_no]: record.rating }))
        }
      } catch { /* ignore */ }
    })
  }, [jobId])

  async function handleDeleteOutput(partNo: number) {
    if (!jobId) return
    const choice = await confirmDialog({
      title: `Delete output file for clip #${partNo}?`,
      message: 'The rendered video file will be removed from disk. This cannot be undone.',
      buttons: [
        { id: 'delete', label: 'Delete file', variant: 'danger' },
        { id: 'cancel', label: 'Cancel' },
      ],
    })
    if (choice !== 'delete') return
    try {
      await deletePartOutput(jobId, partNo)
      setDeletedOutputs(prev => new Set([...prev, partNo]))
    } catch { /* file may already be gone */ }
  }

  useEffect(() => {
    if (!jobId) return
    getJobAiSummary(jobId).then(s => { if (s.available) setAiSummary(s) }).catch(() => {})
  }, [jobId])

  const doneParts  = parts.filter((p) => p.status === 'done')
  const failedParts = parts.filter((p) => p.status === 'failed')
  const sortedDone = [...doneParts].sort((a, b) =>
    sortMode === 'duration'
      ? (b.duration ?? 0) - (a.duration ?? 0)
      : sortMode === 'newest'
        ? b.part_no - a.part_no
        : Object.keys(partRanks).length > 0
          ? (partRanks[a.part_no]?.output_rank ?? 999) - (partRanks[b.part_no]?.output_rank ?? 999)
          : (partScores[b.part_no] ?? 0) - (partScores[a.part_no] ?? 0)
  )

  const outputDir = (() => {
    const f = doneParts[0]?.output_file
    if (!f) return null
    const sep = f.includes('\\') ? '\\' : '/'
    return f.substring(0, f.lastIndexOf(sep)) || null
  })()

  const openOutputFolder = async () => {
    if (outputDir) await window.electronAPI?.openPath?.(outputDir)
  }

  const selScore  = selectedPart ? partScores[selectedPart.part_no] : undefined
  const selRank   = selectedPart ? partRanks[selectedPart.part_no] : undefined
  const selReport = selectedPart ? qualityReports[selectedPart.part_no] : undefined

  const fmtMetric = (v: unknown): string => {
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
    if (typeof v === 'boolean') return v ? 'Yes' : 'No'
    return String(v ?? '—')
  }

  const SEV_COL: Record<string, string> = {
    critical: 'var(--fail)', error: '#f97316', warning: 'var(--warn)', info: 'var(--cyan)',
  }

  const thumbRatio = aspectRatio.replace(':', '/')
  const bestScore = Object.values(partScores).length > 0 ? Math.max(...Object.values(partScores)) : 0
  const totalDurSec = doneParts.reduce((s, p) => s + (p.duration ?? 0), 0)
  const totalDurFmt = `${Math.floor(totalDurSec / 60)}:${String(Math.floor(totalDurSec % 60)).padStart(2, '0')}`
  const fmtDur = (sec: number | null | undefined): string => {
    if (!sec) return ''
    return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
  }

  if (!jobId) {
    return (
      <div className="res-screen">
        <div className="res-left">
          <div className="rw-empty"><span className="rw-empty-icon">📭</span>{t.resNoResults}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="res-screen">
      {/* ── LEFT ── */}
      <div className="res-left">

        {/* Hero banner — failed-state vs success-state */}
        {jobStatus === 'failed' ? (
          <div className="res-hero res-hero-failed">
            <div className="res-hero-bg" />
            <div className="res-hero-content">
              <div className="res-hero-left">
                <div className="res-complete-row">
                  <div className="res-complete-icon res-failed-icon">✕</div>
                  <div>
                    <div className="res-kicker res-kicker-failed">Render Failed</div>
                    <div className="res-hero-title">
                      {jobMessage.includes('ai_emission_empty')
                        ? 'AI providers unavailable — check API keys in Configure → AI panel → Test connection'
                        : (jobMessage || 'No clips produced')}
                    </div>
                  </div>
                </div>
              </div>
              <div className="res-hero-right">
                <button className="res-export-btn" onClick={onRetry} disabled={isRetrying}>
                  {isRetrying ? '…' : t.btnRetry}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="res-hero">
            <div className="res-hero-bg" />
            <div className="res-hero-content">
              <div className="res-hero-left">
                <div className="res-complete-row">
                  <div className="res-complete-icon">✓</div>
                  <div>
                    <div className="res-kicker">Render Complete</div>
                    <div className="res-hero-title">
                      {doneParts.length} clip{doneParts.length !== 1 ? 's' : ''} ready to publish
                    </div>
                  </div>
                </div>
                <div className="res-vtags">
                  {bestScore >= 75 && <span className="res-vtag vtag-green">🔥 High engagement</span>}
                  {doneParts.some(p => p.hook_score > 65) && <span className="res-vtag vtag-purple">⚡ Hook detected</span>}
                  <HybridAnalysisBadge
                    hybrid={aiSummary?.hybrid_analysis}
                    fallbackMode={aiAnalysisMode}
                    fallbackProvider={aiCloudProvider}
                  />
                </div>
              </div>
              <div className="res-hero-right">
                <div className="res-kpi-row">
                  <div className="res-kpi green">
                    <strong>{bestScore > 0 ? Math.round(bestScore) : '—'}</strong>
                    <span>Top Score</span>
                  </div>
                  <div className="res-kpi blue">
                    <strong>{doneParts.length}</strong>
                    <span>Clips</span>
                  </div>
                  <div className="res-kpi">
                    <strong>{totalDurFmt}</strong>
                    <span>Total</span>
                  </div>
                </div>
                {outputDir && (
                  <button className="res-export-btn" onClick={openOutputFolder}>Open Folder</button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Partial failure warning */}
        {jobStatus === 'completed_with_errors' && failedParts.length > 0 && (
          <div style={{ padding: '8px 16px', background: 'rgba(234,179,8,.1)', borderBottom: '1px solid rgba(234,179,8,.2)', fontSize: '11px', color: 'var(--warn)', display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
            <span>⚠ {failedParts.length} clip{failedParts.length !== 1 ? 's' : ''} failed — {doneParts.length} rendered successfully</span>
            <button className="btn-xs" style={{ color: 'var(--fail)', borderColor: 'rgba(232,64,122,.4)', marginLeft: 'auto' }}
              onClick={onRetry} disabled={isRetrying}>
              {isRetrying ? '…' : t.btnRetry}
            </button>
          </div>
        )}

        {/* AI Summary card
            Audit FINDING-BR11 closure (Batch 10C 2026-06-06):
            - aiSummary.ai_status === 'no_result' → render nothing (job had no
              AI data persisted, so the card would be entirely empty).
            - ai_status === 'no_ranking' / 'degraded' → render a compact card
              with the backend-supplied status_message so the user knows
              WHY the analysis is empty instead of seeing a blank panel. */}
        {aiSummary && aiSummary.ai_status !== 'no_result' && (
          aiSummary.ai_status && aiSummary.ai_status !== 'ok' ? (
            <div
              style={{
                borderBottom: '1px solid var(--border)', flexShrink: 0,
                padding: '10px 16px', display: 'flex', alignItems: 'flex-start', gap: 8,
                fontSize: 11, color: 'var(--text-3)',
              }}
              data-testid="ai-summary-degraded"
            >
              <span style={{ color: 'var(--warn)', fontSize: 13 }}>⚠</span>
              <div>
                <div style={{ fontWeight: 700, color: 'var(--text-2)', marginBottom: 2 }}>
                  AI Analysis Unavailable
                </div>
                <div style={{ lineHeight: 1.5 }}>
                  {aiSummary.status_message || 'AI analysis is not available for this render.'}
                </div>
              </div>
            </div>
          ) : (
          <div style={{ borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
            <button
              onClick={() => setAiSummaryOpen(o => !o)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 16px', background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textAlign: 'left',
              }}
            >
              <span style={{ color: 'var(--accent)', fontSize: 13 }}>✦</span>
              AI Analysis
              {aiSummary.confidence_tier && (
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 99, marginLeft: 4,
                  background: aiSummary.confidence_tier === 'strong' ? 'rgba(52,200,120,.15)' : 'rgba(234,179,8,.12)',
                  color: aiSummary.confidence_tier === 'strong' ? 'var(--status-success)' : 'var(--confidence-mid)',
                }}>
                  {aiSummary.confidence_tier}
                </span>
              )}
              {aiSummary.best_score !== null && (
                <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 'auto' }}>
                  Best: #{aiSummary.best_part_no} · {aiSummary.best_score}%
                </span>
              )}
              <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: aiSummary.best_score !== null ? 0 : 'auto' }}>
                {aiSummaryOpen ? '▲' : '▼'}
              </span>
            </button>

            {aiSummaryOpen && (
              <div style={{ padding: '0 16px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>

                {aiSummary.best_reason && (
                  <div style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.5 }}>
                    <span style={{ color: 'var(--accent)', marginRight: 4 }}>★</span>
                    {aiSummary.best_reason}
                    {aiSummary.score_margin !== null && (
                      <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 6 }}>
                        (+{aiSummary.score_margin.toFixed(1)} vs #2)
                      </span>
                    )}
                  </div>
                )}

                {typeof aiSummary.story === 'object' && (aiSummary.story as Record<string,unknown>)['description'] != null && (
                  <div style={{ fontSize: 10, color: 'var(--text-3)', lineHeight: 1.5, borderLeft: '2px solid var(--accent)', paddingLeft: 8 }}>
                    {String((aiSummary.story as Record<string,unknown>)['description'])}
                  </div>
                )}

                {/* R2/Phase 3b — whole-film StoryModel (Story Intelligence).
                    Renders nothing when the job didn't run with it enabled. */}
                <StoryModelCard storyModel={aiSummary.story_model} />

                {aiSummary.ranking_summary.length > 0 && (
                  <div>
                    <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 5 }}>
                      Clip Ranking
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {aiSummary.ranking_summary.map(r => (
                        <div key={r.part_no} style={{
                          display: 'flex', alignItems: 'center', gap: 8, fontSize: 10,
                          padding: '3px 8px', borderRadius: 5,
                          background: r.is_best_clip ? 'rgba(var(--accent-rgb,.15),0.15)' : 'rgba(255,255,255,.03)',
                        }}>
                          <span style={{ width: 14, textAlign: 'center', fontWeight: 700, color: r.rank === 1 ? 'var(--accent)' : 'var(--text-3)' }}>#{r.rank}</span>
                          <span style={{ color: 'var(--text-2)' }}>Part {r.part_no}</span>
                          <span style={{ fontWeight: 700, color: r.score >= 75 ? 'var(--ok)' : r.score >= 50 ? 'var(--warn)' : 'var(--text-3)' }}>{r.score}%</span>
                          {r.dominant_signal && <span style={{ color: 'var(--text-3)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.dominant_signal.replace(/_/g, ' ')}</span>}
                          {r.is_best_clip && <span style={{ fontSize: 9, color: 'var(--accent)', fontWeight: 700 }}>BEST</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {aiSummary.rejected_count > 0 && (
                  <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                    {aiSummary.rejected_count} segment{aiSummary.rejected_count !== 1 ? 's' : ''} evaluated but not selected
                  </div>
                )}

                {aiSummary.output_ranking_warning && (
                  <div style={{ fontSize: 10, color: 'var(--warn)' }}>⚠ {aiSummary.output_ranking_warning}</div>
                )}

              </div>
            )}
          </div>
          )
        )}

        {/* Sort / count bar */}
        <div className="res-bar">
          <span className="res-count">{t.resClipsRendered(doneParts.length)}</span>
          <div className="res-sort">
            <button className={`sort-btn${sortMode === 'viral' ? ' on' : ''}`} onClick={() => setSortMode('viral')}>{t.resSortViral}</button>
            <button className={`sort-btn${sortMode === 'duration' ? ' on' : ''}`} onClick={() => setSortMode('duration')}>{t.resSortDuration}</button>
            <button className={`sort-btn${sortMode === 'newest' ? ' on' : ''}`} onClick={() => setSortMode('newest')}>{t.resSortNewest}</button>
          </div>
        </div>

        {loading ? (
          <div className="rw-empty">
            <div style={{ width: 32, height: 32, border: '2px solid var(--border-hi)', borderTop: '2px solid var(--accent)', borderRadius: '50%', animation: 'rw-spin 0.8s linear infinite' }} />
            {t.resLoading}
          </div>
        ) : doneParts.length === 0 ? (
          <div className="rw-empty"><span className="rw-empty-icon">📭</span>{t.resNoClips}</div>
        ) : (
          <div className="clip-cards-row">
            {sortedDone.map((part, i) => {
              const rank       = partRanks[part.part_no]
              const qualScore  = partScores[part.part_no]
              const dispScore  = rank?.output_rank_score ?? qualScore
              const thumbUrl   = getPartThumbnailUrl(jobId, part.part_no)
              const isSelected = selectedPart?.part_no === part.part_no
              const tier       = dispScore !== undefined ? aiTier(dispScore) : null
              const durFmt     = fmtDur(part.duration)
              const scoreCol   = dispScore !== undefined
                ? (dispScore >= 70 ? 'var(--ok)' : dispScore >= 50 ? 'var(--warn)' : 'var(--fail)')
                : ''
              const isBest     = rank?.is_best_clip === true

              return (
                <div
                  key={part.part_no}
                  className={`clip-card2${isBest ? ' is-top' : ''}${isSelected ? ' selected' : ''}`}
                  onClick={() => setSelectedPart(isSelected ? null : part)}
                >
                  <div className="clip-thumb2" style={{ aspectRatio: thumbRatio }}>
                    <img src={thumbUrl} alt={`Clip ${part.part_no}`}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
                    {isBest
                      ? <div className="clip-rank" style={{ background: 'linear-gradient(135deg,#f59e0b,#f97316)', color: '#000' }}>★ BEST</div>
                      : <div className="clip-rank">#{rank?.output_rank ?? i + 1}</div>
                    }
                    {dispScore !== undefined && (
                      <div className="clip-score-ring">
                        <ScoreRingSm score={Math.round(dispScore)} />
                      </div>
                    )}
                    {durFmt && <div className="clip-dur-badge">{durFmt}</div>}
                    <div className="clip-overlay">
                      <a href={getPartMediaUrl(jobId, part.part_no)} target="_blank" rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}>
                        <button className="clip-ov-btn">▶</button>
                      </a>
                      <a href={getPartMediaUrl(jobId, part.part_no)}
                        download={part.clip_name || `clip_${part.part_no}.mp4`}
                        onClick={(e) => e.stopPropagation()}>
                        <button className="clip-ov-btn">⬇</button>
                      </a>
                    </div>
                  </div>

                  <div className="clip-info2">
                    <div className="clip-info2-top">
                      <span className="clip-num-lbl2">
                        {(part.ai_title ) || (part.clip_name ? part.clip_name.replace(/\.mp4$/i, '') : `Clip ${String(part.part_no).padStart(2, '0')}`)}
                      </span>
                      {(part.source === 'llm' || part.source === 'groq') && (
                        <span style={{
                          fontSize: 7, fontWeight: 700, padding: '1px 6px', borderRadius: 99, flexShrink: 0,
                          background: 'rgba(168,85,247,.15)', color: '#a855f7',
                          letterSpacing: '.05em', textTransform: 'uppercase', border: '1px solid rgba(168,85,247,.3)',
                        }}>
                          AI
                        </span>
                      )}
                      {tier && <span className={`clip-ai-badge ${tier.cls}`}>{tier.label}</span>}
                      {rank?.confidence_tier && (
                        <span style={{
                          fontSize: 7, fontWeight: 700, padding: '1px 5px', borderRadius: 99, flexShrink: 0,
                          background: rank.confidence_tier === 'strong' ? 'rgba(52,200,120,.12)' : 'rgba(234,179,8,.1)',
                          color: rank.confidence_tier === 'strong' ? 'var(--status-success)' : 'var(--confidence-mid)',
                          letterSpacing: '.05em', textTransform: 'uppercase',
                        }}>
                          {rank.confidence_tier === 'strong' ? 'STRONG' : rank.confidence_tier === 'worth_testing' ? 'TEST' : 'EXP'}
                        </span>
                      )}
                    </div>
                    {dispScore !== undefined && (
                      <div className="clip-score-bar-track">
                        <div className="clip-score-bar-fill" style={{ width: `${dispScore}%`, background: scoreCol }} />
                      </div>
                    )}
                    {(part.ai_reason ) && (
                      <div style={{ fontSize: 9, color: 'rgba(168,85,247,.85)', marginTop: 2, lineHeight: 1.3, fontStyle: 'italic' }}>
                        {part.ai_reason}
                      </div>
                    )}
                    {rank?.ranking_reason && (
                      <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 2, lineHeight: 1.3 }}>{rank.ranking_reason}</div>
                    )}
                    {rank?.dominant_signal && (
                      <div style={{ fontSize: 8, marginTop: 3, color: 'rgba(168,85,247,.75)', fontWeight: 700, letterSpacing: '.02em' }}>
                        ↑ {rank.dominant_signal.replace(/_/g, ' ')}
                      </div>
                    )}
                    {rank?.suppressed_signals && rank.suppressed_signals.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, marginTop: 2 }}>
                        {rank.suppressed_signals.slice(0, 2).map((s, i) => (
                          <span key={i} style={{
                            fontSize: 7, padding: '1px 4px', borderRadius: 99,
                            background: 'rgba(239,68,68,.1)', color: 'rgba(239,68,68,.6)',
                          }}>
                            ↓ {s.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                    {!rank && (part.hook_score > 0 || part.viral_score > 0) && (
                      <div className="clip-scores-row">
                        {part.hook_score > 0 && <span className="clip-score-pill hook">Hook {Math.round(part.hook_score)}%</span>}
                        {part.viral_score > 0 && <span className="clip-score-pill viral">Viral {Math.round(part.viral_score)}%</span>}
                      </div>
                    )}
                    <div className="clip-actions2">
                      <a className="clip-save-btn"
                        href={getPartMediaUrl(jobId, part.part_no)}
                        download={`clip_${part.part_no}.mp4`}
                        onClick={(e) => e.stopPropagation()}>
                        Save
                      </a>
                      <button
                        title="Good clip"
                        className={`clip-fb-btn${feedbackRatings[part.part_no] === 1 ? ' active-like' : ''}`}
                        onClick={(e) => { e.stopPropagation(); handleFeedback(part.part_no, 1, part) }}
                      >👍</button>
                      <button
                        title="Bad clip"
                        className={`clip-fb-btn${feedbackRatings[part.part_no] === -1 ? ' active-dislike' : ''}`}
                        onClick={(e) => { e.stopPropagation(); handleFeedback(part.part_no, -1, part) }}
                      >👎</button>
                      {part.output_file && (
                        <button
                          title="Copy path"
                          onClick={(e) => {
                            e.stopPropagation()
                            navigator.clipboard.writeText(part.output_file).catch(() => {})
                          }}
                          style={{
                            fontSize: 10, padding: '2px 7px', borderRadius: 5,
                            border: '1px solid var(--border)', background: 'var(--bg-hover)',
                            color: 'var(--text-3)', cursor: 'pointer',
                          }}
                        >
                          Copy
                        </button>
                      )}
                      {part.output_file && !deletedOutputs.has(part.part_no) && (
                        <button
                          title="Open folder"
                          onClick={(e) => {
                            e.stopPropagation()
                            const f = part.output_file
                            const sep = f.includes('\\') ? '\\' : '/'
                            const dir = f.substring(0, f.lastIndexOf(sep)) || f
                            window.electronAPI?.openPath?.(dir)
                          }}
                          style={{
                            fontSize: 10, padding: '2px 7px', borderRadius: 5,
                            border: '1px solid var(--border)', background: 'var(--bg-hover)',
                            color: 'var(--text-3)', cursor: 'pointer',
                          }}
                        >
                          📂
                        </button>
                      )}
                      {part.output_file && !deletedOutputs.has(part.part_no) && (
                        <button
                          title="Delete output file"
                          onClick={(e) => { e.stopPropagation(); handleDeleteOutput(part.part_no) }}
                          style={{
                            fontSize: 10, padding: '2px 7px', borderRadius: 5,
                            border: '1px solid rgba(232,64,122,.3)', background: 'rgba(232,64,122,.08)',
                            color: 'var(--fail)', cursor: 'pointer',
                          }}
                        >
                          🗑
                        </button>
                      )}
                      {deletedOutputs.has(part.part_no) && (
                        <span style={{ fontSize: 9, color: 'var(--text-3)', padding: '2px 5px' }}>deleted</span>
                      )}
                      <button className="clip-more-btn" title="Details"
                        onClick={(e) => { e.stopPropagation(); setSelectedPart(isSelected ? null : part) }}>
                        ···
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {failedParts.length > 0 && (
          <div style={{ margin: '12px 16px 0', padding: '10px 12px', background: 'rgba(232,64,122,.07)', border: '1px solid rgba(232,64,122,.2)', borderRadius: '6px' }}>
            <div style={{ fontSize: '10px', fontFamily: 'var(--fh)', letterSpacing: '1px', color: 'var(--fail)', marginBottom: '8px' }}>
              {t.resFailedParts} ({failedParts.length})
            </div>
            {failedParts.map((p) => (
              <div key={p.part_no} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '4px 0', borderTop: '1px solid rgba(232,64,122,.1)', fontSize: '11px' }}>
                <span style={{ color: 'var(--fail)', fontFamily: 'var(--fh)', minWidth: 28 }}>#{String(p.part_no).padStart(2, '0')}</span>
                <span style={{ color: 'var(--text-3)', lineHeight: 1.4 }}>{p.message || t.resNoReason}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Detail panel ── */}
      <div className={`player-panel${selectedPart ? '' : ' collapsed'}`}>
        <div className="player-hd">
          <span className="player-hd-title">
            {selectedPart ? `Clip #${String(selectedPart.part_no).padStart(2, '0')}` : t.resClipViewer}
          </span>
          <button className="player-close" onClick={() => setSelectedPart(null)}>✕</button>
        </div>

        <div className="player-video-area">
          {selectedPart ? (
            <>
              <div className="player-frame" style={{ aspectRatio: thumbRatio }}>
                <video
                  key={selectedPart.part_no}
                  src={getPartMediaUrl(jobId, selectedPart.part_no)}
                  controls
                  style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
                />
              </div>

              {(selRank?.output_rank_score ?? selScore) !== undefined && (
                <ScoreRingLg score={selRank?.output_rank_score ?? selScore!} />
              )}

              {selRank && (
                <div className="player-section">
                  <div className="player-section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    AI Rank Score
                    {selRank.confidence_tier && (
                      <span style={{
                        fontSize: 8, fontWeight: 700, padding: '1px 6px', borderRadius: 99,
                        background: selRank.confidence_tier === 'strong' ? 'rgba(52,200,120,.15)' : 'rgba(234,179,8,.12)',
                        color: selRank.confidence_tier === 'strong' ? 'var(--status-success)' : 'var(--confidence-mid)',
                        letterSpacing: '.05em',
                      }}>
                        {selRank.confidence_tier === 'strong' ? 'STRONG' : selRank.confidence_tier === 'worth_testing' ? 'WORTH TESTING' : 'EXPERIMENTAL'}
                      </span>
                    )}
                    {selRank.score_margin !== undefined && (
                      <span style={{ fontSize: 9, color: 'var(--text-3)', marginLeft: 'auto' }}>
                        +{selRank.score_margin.toFixed(1)} vs #2
                      </span>
                    )}
                  </div>
                  {selRank.ranking_reason && (
                    <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 8, lineHeight: 1.4 }}>{selRank.ranking_reason}</div>
                  )}
                  <div className="player-score-bars">
                    {([
                      ['Viral',     selRank.ranking_components.segment_viral_score, 'psb-viral'],
                      ['Hook',      selRank.ranking_components.hook_score,           'psb-hook'],
                      ['Retention', selRank.ranking_components.retention_score,      'psb-motion'],
                      ['Speech',    selRank.ranking_components.speech_density_score, 'psb-hook'],
                      ['Market',    selRank.ranking_components.market_score,         'psb-viral'],
                      ['Duration',  selRank.ranking_components.duration_fit_score,   'psb-motion'],
                    ] as [string, number, string][]).map(([label, val, cls]) => (
                      <div key={label} className="psb-row">
                        <span className="psb-label">{label}</span>
                        <div className="psb-track">
                          <div className={`psb-fill ${cls}`} style={{ width: `${val}%` }} />
                        </div>
                        <span className="psb-val">{Math.round(val)}%</span>
                      </div>
                    ))}
                  </div>
                  {(selRank.dominant_signal || (selRank.suppressed_signals && selRank.suppressed_signals.length > 0) || selRank.ranking_components.content_type_hint) && (
                    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {selRank.dominant_signal && (
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                          Dominant: <span style={{ color: 'var(--accent)' }}>{selRank.dominant_signal.replace(/_/g, ' ')}</span>
                        </div>
                      )}
                      {selRank.suppressed_signals && selRank.suppressed_signals.length > 0 && (
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                          Suppressed:{' '}
                          {selRank.suppressed_signals.map((s, i) => (
                            <span key={i} style={{
                              display: 'inline-block', marginRight: 4, padding: '1px 6px',
                              borderRadius: 99, background: 'rgba(239,68,68,.1)',
                              color: 'rgba(239,68,68,.7)', fontSize: 9,
                            }}>
                              {s.replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      )}
                      {selRank.ranking_components.content_type_hint && (
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                          Content type: <span style={{ color: 'var(--text-2)' }}>{selRank.ranking_components.content_type_hint.replace(/_/g, ' ')}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {!selRank && selectedPart && (selectedPart.hook_score > 0 || selectedPart.viral_score > 0 || selectedPart.motion_score > 0) && (
                <div className="player-score-bars">
                  {selectedPart.hook_score > 0 && (
                    <div className="psb-row">
                      <span className="psb-label">Hook</span>
                      <div className="psb-track">
                        <div className="psb-fill psb-hook" style={{ width: `${selectedPart.hook_score}%` }} />
                      </div>
                      <span className="psb-val">{Math.round(selectedPart.hook_score)}%</span>
                    </div>
                  )}
                  {selectedPart.viral_score > 0 && (
                    <div className="psb-row">
                      <span className="psb-label">Viral</span>
                      <div className="psb-track">
                        <div className="psb-fill psb-viral" style={{ width: `${selectedPart.viral_score}%` }} />
                      </div>
                      <span className="psb-val">{Math.round(selectedPart.viral_score)}%</span>
                    </div>
                  )}
                  {selectedPart.motion_score > 0 && (
                    <div className="psb-row">
                      <span className="psb-label">Motion</span>
                      <div className="psb-track">
                        <div className="psb-fill psb-motion" style={{ width: `${selectedPart.motion_score}%` }} />
                      </div>
                      <span className="psb-val">{Math.round(selectedPart.motion_score)}%</span>
                    </div>
                  )}
                </div>
              )}

              <div className="player-section">
                <div className="player-section-title">AI Analysis</div>

                {selReport && selReport.issues.length > 0 ? (
                  <div className="player-issues">
                    {selReport.issues.map((iss, i) => (
                      <div key={i} className="player-issue-row">
                        <span className="player-issue-dot" style={{ background: SEV_COL[iss.severity] ?? '#888' }} />
                        <div>
                          <div className="player-issue-msg">{iss.message}</div>
                          {iss.recommended_action && (
                            <div className="player-issue-action">{iss.recommended_action}</div>
                          )}
                        </div>
                        <span className="player-issue-sev" style={{ color: SEV_COL[iss.severity] ?? '#888' }}>
                          {iss.severity}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : selReport ? (
                  <div className="player-all-ok">✓ No issues — all quality checks passed</div>
                ) : qualityLoadFailed ? (
                  <div className="player-no-data" style={{ color: 'var(--warn)' }}>⚠ {t.qualityLoadFailed}</div>
                ) : (
                  <div className="player-no-data">Quality data loading…</div>
                )}
              </div>

              {selReport && Object.keys(selReport.metrics).length > 0 && (
                <div className="player-section">
                  <div className="player-section-title">Metrics</div>
                  <div className="player-metrics-grid">
                    {Object.entries(selReport.metrics)
                      .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
                      .map(([k, v]) => (
                        <div key={k} className="player-metric-cell">
                          <div className="player-metric-key">{k.replace(/_/g, ' ')}</div>
                          <div className="player-metric-val">{fmtMetric(v)}</div>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              <div className="player-btns">
                <a className="player-btn" href={getPartMediaUrl(jobId, selectedPart.part_no)} target="_blank" rel="noreferrer">{t.btnPlay}</a>
                <a className="player-btn primary" href={getPartMediaUrl(jobId, selectedPart.part_no)} download={`clip_${selectedPart.part_no}.mp4`}>{t.btnExport}</a>
              </div>
            </>
          ) : (
            <div className="player-placeholder">🎬</div>
          )}
        </div>
      </div>
    </div>
  )
}

export const StepResults = React.memo(StepResultsBase)
