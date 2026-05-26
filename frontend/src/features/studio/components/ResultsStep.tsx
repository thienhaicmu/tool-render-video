import { useState, useEffect, useRef } from 'react'
import { getJobParts, getJobPartQuality } from '../../../api/jobs'
import { BASE_URL } from '../../../api/client'
import { useI18n } from '../../../i18n/useI18n'
import type { JobPart, QualityReport } from '../../../types/api'

interface ResultsStepProps {
  jobId: string | null
  sessionOutputDir: string
  onNewProject: () => void
}

// ── Score helpers ──────────────────────────────────────────────────────────────

function scoreColor(n: number) {
  return n >= 80 ? '#34C878' : n >= 60 ? '#fbbf24' : '#E05252'
}

function scoreLabel(n: number) {
  return n >= 85 ? 'Excellent' : n >= 70 ? 'Good' : n >= 55 ? 'Fair' : 'Poor'
}

const SEV_COLOR: Record<string, string> = {
  critical: '#E05252',
  error: '#f97316',
  warning: '#fbbf24',
  info: '#60a5fa',
}

// ── Clip sidebar row ───────────────────────────────────────────────────────────

function ClipRow({
  part,
  jobId,
  selected,
  qualityScore,
  onClick,
}: {
  part: JobPart
  jobId: string
  selected: boolean
  qualityScore: number | null
  onClick: () => void
}) {
  const [thumbError, setThumbError] = useState(false)
  const thumbSrc = `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${part.part_no}/thumbnail?t=0.5&w=80`

  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 10px',
        cursor: 'pointer',
        borderRadius: '8px',
        backgroundColor: selected ? 'rgba(168,85,247,0.1)' : 'transparent',
        border: `1px solid ${selected ? 'rgba(168,85,247,0.3)' : 'transparent'}`,
        transition: 'all 0.15s ease',
        marginBottom: '2px',
      }}
    >
      {/* Mini vertical thumbnail */}
      <div style={{
        width: '32px',
        height: '56px',
        borderRadius: '5px',
        overflow: 'hidden',
        flexShrink: 0,
        backgroundColor: '#0A0C11',
        border: `1px solid ${selected ? 'rgba(168,85,247,0.4)' : 'var(--border-subtle)'}`,
      }}>
        {!thumbError ? (
          <img
            src={thumbSrc}
            alt=""
            onError={() => setThumbError(true)}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        ) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: '10px', opacity: 0.2, color: '#fff' }}>▶</span>
          </div>
        )}
      </div>

      {/* Label */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: '11px',
          fontWeight: selected ? 700 : 500,
          color: selected ? 'var(--text-primary)' : 'var(--text-secondary)',
          marginBottom: '2px',
        }}>
          Clip {part.part_no}
        </div>
        <div style={{
          fontSize: '9px',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' as const,
        }}>
          {part.output_file?.split(/[/\\]/).pop()?.replace(/^.*?(\d+[^.]*\.mp4)$/i, '$1') ?? '—'}
        </div>
      </div>

      {/* Quality score badge */}
      {qualityScore !== null && (
        <div style={{
          width: '26px',
          height: '26px',
          borderRadius: '50%',
          backgroundColor: `${scoreColor(qualityScore)}1a`,
          border: `1.5px solid ${scoreColor(qualityScore)}55`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '8px',
          fontWeight: 800,
          color: scoreColor(qualityScore),
          flexShrink: 0,
          fontFamily: 'var(--font-mono)',
        }}>
          {qualityScore}
        </div>
      )}
    </div>
  )
}

// ── Score ring ─────────────────────────────────────────────────────────────────

function ScoreRing({ score }: { score: number }) {
  const r = 28
  const circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  const col = scoreColor(score)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
      <div style={{ position: 'relative', width: '68px', height: '68px', flexShrink: 0 }}>
        <svg width="68" height="68" viewBox="0 0 68 68" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="34" cy="34" r={r} fill="none" stroke="var(--surface-input)" strokeWidth="6" />
          <circle
            cx="34" cy="34" r={r}
            fill="none"
            stroke={col}
            strokeWidth="6"
            strokeDasharray={`${fill} ${circ}`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.6s ease' }}
          />
        </svg>
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '15px',
          fontWeight: 800,
          color: col,
          fontFamily: 'var(--font-mono)',
        }}>
          {score}
        </div>
      </div>
      <div>
        <div style={{ fontSize: '15px', fontWeight: 700, color: col }}>{scoreLabel(score)}</div>
        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>AI Quality Score</div>
        <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '1px' }}>{score}/100</div>
      </div>
    </div>
  )
}

// ── Detail panel ───────────────────────────────────────────────────────────────

function DetailPanel({ part, jobId }: { part: JobPart; jobId: string }) {
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [qualityLoading, setQualityLoading] = useState(false)
  const [qualityError, setQualityError] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  const videoSrc = `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${part.part_no}/media`
  const filename = part.output_file?.split(/[/\\]/).pop() ?? `clip_${part.part_no}.mp4`

  useEffect(() => {
    setQuality(null)
    setQualityError(false)
    setQualityLoading(true)
    getJobPartQuality(jobId, part.part_no)
      .then(setQuality)
      .catch(() => setQualityError(true))
      .finally(() => setQualityLoading(false))
  }, [jobId, part.part_no])

  const fmtMetric = (v: unknown): string => {
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
    if (typeof v === 'boolean') return v ? 'Yes' : 'No'
    return String(v ?? '—')
  }

  const metricEntries = quality
    ? Object.entries(quality.metrics).filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
    : []

  return (
    <div style={{ flex: 1, overflow: 'hidden', overflowY: 'auto', display: 'flex', gap: '24px', padding: '20px 24px', alignItems: 'flex-start' }}>

      {/* ── Video player column ── */}
      <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
        <div style={{
          width: '200px',
          borderRadius: '14px',
          overflow: 'hidden',
          backgroundColor: '#000',
          border: '1px solid var(--border-default)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        }}>
          <video
            ref={videoRef}
            src={videoSrc}
            controls
            playsInline
            style={{
              width: '100%',
              display: 'block',
              aspectRatio: '9/16',
              objectFit: 'contain',
              backgroundColor: '#000',
            }}
          />
        </div>

        {/* Filename + open button */}
        <div style={{ width: '200px', textAlign: 'center' as const }}>
          <div style={{
            fontSize: '9px',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap' as const,
            marginBottom: '6px',
          }}>
            {filename}
          </div>
          <a
            href={videoSrc}
            download={filename}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              height: '28px',
              padding: '0 12px',
              borderRadius: '6px',
              border: '1px solid var(--border-default)',
              color: 'var(--text-secondary)',
              fontSize: '10px',
              fontWeight: 600,
              textDecoration: 'none',
              backgroundColor: 'transparent',
              cursor: 'pointer',
            }}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download
          </a>
        </div>
      </div>

      {/* ── Quality report column ── */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>

        {/* Score card */}
        <div style={card}>
          <SectionLabel>AI Evaluation</SectionLabel>
          {qualityLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-tertiary)', fontSize: '12px', padding: '4px 0' }}>
              <span style={{
                display: 'inline-block', width: '14px', height: '14px',
                border: '2px solid rgba(168,85,247,0.3)', borderTopColor: '#a855f7',
                borderRadius: '50%', animation: 'res-spin 0.8s linear infinite',
              }} />
              Analyzing clip…
            </div>
          )}
          {qualityError && (
            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', padding: '4px 0' }}>Quality report unavailable</div>
          )}
          {quality && <ScoreRing score={Math.round(quality.score)} />}
        </div>

        {/* Issues */}
        {quality && quality.issues.length > 0 && (
          <div style={card}>
            <SectionLabel>Issues · {quality.issues.length}</SectionLabel>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {quality.issues.map((issue, i) => {
                const col = SEV_COLOR[issue.severity] ?? '#999'
                const icon = issue.severity === 'critical' ? '✕' : issue.severity === 'error' ? '!' : issue.severity === 'warning' ? '⚠' : 'i'
                return (
                  <div key={i} style={{
                    display: 'flex',
                    gap: '10px',
                    padding: '9px 12px',
                    borderRadius: '8px',
                    backgroundColor: `${col}10`,
                    border: `1px solid ${col}28`,
                  }}>
                    <div style={{
                      width: '18px',
                      height: '18px',
                      borderRadius: '50%',
                      backgroundColor: `${col}20`,
                      border: `1.5px solid ${col}55`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '9px',
                      fontWeight: 800,
                      color: col,
                      flexShrink: 0,
                      marginTop: '1px',
                    }}>
                      {icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                          {issue.message}
                        </span>
                        <span style={{
                          fontSize: '8px',
                          fontWeight: 700,
                          color: col,
                          textTransform: 'uppercase' as const,
                          letterSpacing: '0.05em',
                          flexShrink: 0,
                          padding: '1px 5px',
                          borderRadius: '4px',
                          backgroundColor: `${col}18`,
                        }}>
                          {issue.severity}
                        </span>
                      </div>
                      {issue.recommended_action && (
                        <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', lineHeight: 1.4 }}>
                          {issue.recommended_action}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* No issues */}
        {quality && quality.issues.length === 0 && (
          <div style={{
            ...card,
            backgroundColor: 'rgba(52,200,120,0.05)',
            border: '1px solid rgba(52,200,120,0.2)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                width: '22px', height: '22px', borderRadius: '50%',
                backgroundColor: 'rgba(52,200,120,0.15)',
                border: '1.5px solid rgba(52,200,120,0.4)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '10px', color: '#34C878', fontWeight: 700,
              }}>✓</div>
              <div>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#34C878' }}>No issues found</div>
                <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '1px' }}>All quality checks passed</div>
              </div>
            </div>
          </div>
        )}

        {/* Metrics grid */}
        {metricEntries.length > 0 && (
          <div style={card}>
            <SectionLabel>Metrics</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))', gap: '10px' }}>
              {metricEntries.map(([k, v]) => (
                <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <div style={{ fontSize: '9px', color: 'var(--text-tertiary)', textTransform: 'uppercase' as const, letterSpacing: '0.06em' }}>
                    {k.replace(/_/g, ' ')}
                  </div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                    {fmtMetric(v)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Small helpers ──────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '10px',
      fontWeight: 700,
      color: 'var(--text-tertiary)',
      letterSpacing: '0.08em',
      textTransform: 'uppercase' as const,
      marginBottom: '12px',
    }}>
      {children}
    </div>
  )
}

const card: React.CSSProperties = {
  padding: '16px',
  borderRadius: '12px',
  backgroundColor: 'var(--surface-card)',
  border: '1px solid var(--border-subtle)',
}

// ── ResultsStep ────────────────────────────────────────────────────────────────

export function ResultsStep({ jobId, sessionOutputDir, onNewProject }: ResultsStepProps) {
  const { t } = useI18n()
  const [parts, setParts] = useState<JobPart[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<number | null>(null)
  const [qualityScores, setQualityScores] = useState<Record<number, number>>({})

  useEffect(() => {
    if (!jobId) { setLoading(false); return }
    getJobParts(jobId)
      .then((ps) => {
        const done = ps.filter((p) => p.status === 'done')
        setParts(done)
        if (done.length > 0) setSelected(done[0].part_no)
        // Preload quality scores for sidebar badges
        done.forEach((p) => {
          getJobPartQuality(jobId, p.part_no)
            .then((q) => setQualityScores((prev) => ({ ...prev, [p.part_no]: Math.round(q.score) })))
            .catch(() => {})
        })
      })
      .catch(() => setParts([]))
      .finally(() => setLoading(false))
  }, [jobId])

  const openFolder = async () => {
    const api = (window as any).electronAPI
    if (api?.openPath && sessionOutputDir) {
      await api.openPath(sessionOutputDir)
    } else {
      alert('Open folder: ' + (sessionOutputDir || 'output directory'))
    }
  }

  const selectedPart = parts.find((p) => p.part_no === selected) ?? null

  return (
    <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--surface-base)' }}>

      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 var(--space-6)',
        height: '48px',
        borderBottom: '1px solid var(--border-subtle)',
        flexShrink: 0,
        backgroundColor: 'var(--surface-panel)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '26px', height: '26px', borderRadius: '50%',
            backgroundColor: 'rgba(52,200,120,0.15)',
            border: '2px solid rgba(52,200,120,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#34C878', fontSize: '11px', fontWeight: 700,
          }}>✓</div>
          <div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
              {t('results_complete')}
            </div>
            {!loading && (
              <div style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>
                {parts.length} clip{parts.length !== 1 ? 's' : ''} ready to use
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          <button onClick={openFolder} style={btnStyle}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
            {t('results_open_folder')}
          </button>
          <button
            onClick={onNewProject}
            style={{ ...btnStyle, background: 'linear-gradient(135deg, #a855f7, #4d7cff)', color: '#fff', border: 'none', boxShadow: '0 0 12px rgba(168,85,247,0.25)' }}
          >
            {t('results_new_project')}
          </button>
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
          <span style={{ display: 'inline-block', width: '18px', height: '18px', border: '2.5px solid rgba(168,85,247,0.3)', borderTopColor: '#a855f7', borderRadius: '50%', animation: 'res-spin 0.8s linear infinite' }} />
          <span style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>Loading results…</span>
        </div>
      ) : parts.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.1 }}>
            <rect x="2" y="2" width="20" height="20" rx="3"/>
            <polygon points="10 8 16 12 10 16 10 8"/>
          </svg>
          <span style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>{t('results_no_clips')}</span>
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>

          {/* Clip sidebar */}
          <div style={{
            width: '190px',
            flexShrink: 0,
            overflowY: 'auto',
            borderRight: '1px solid var(--border-subtle)',
            padding: '12px 8px',
            backgroundColor: 'var(--surface-panel)',
          }}>
            <div style={{
              fontSize: '9px',
              fontWeight: 700,
              color: 'var(--text-tertiary)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase' as const,
              padding: '0 4px',
              marginBottom: '8px',
            }}>
              Clips · {parts.length}
            </div>
            {parts.map((p) => (
              <ClipRow
                key={p.part_no}
                part={p}
                jobId={jobId!}
                selected={p.part_no === selected}
                qualityScore={qualityScores[p.part_no] ?? null}
                onClick={() => setSelected(p.part_no)}
              />
            ))}
          </div>

          {/* Detail panel */}
          {selectedPart && jobId && (
            <DetailPanel key={selectedPart.part_no} part={selectedPart} jobId={jobId} />
          )}
        </div>
      )}

      <style>{`@keyframes res-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  height: '32px',
  padding: '0 12px',
  border: '1px solid var(--border-default)',
  borderRadius: '8px',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
  fontSize: '11px',
  fontWeight: 600,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '5px',
}
