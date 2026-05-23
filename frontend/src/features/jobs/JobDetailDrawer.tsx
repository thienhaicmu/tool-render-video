/**
 * JobDetailDrawer — right-side panel for a selected job's full detail.
 */
import { type ReactNode, useEffect, useState } from 'react'
import { Badge } from '../../components/ui/Badge'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { JobStatusBadge } from './JobStatusBadge'
import { formatDateTime } from './jobs.utils'
import { getJob } from '../../api/jobs'
import type { JobStatus } from '../../types/api'

export interface JobDetailDrawerProps {
  jobId: string
  onClose: () => void
}

interface ParsedPayload {
  source_mode?: string
  source?: string
  youtube_url?: string
  url?: string
  source_video_path?: string
  path?: string
  target_platform?: string
  aspect_ratio?: string
  subtitle_style?: string
  effect_preset?: string
}

function parsePayload(payloadJson: string): ParsedPayload | null {
  try {
    return JSON.parse(payloadJson) as ParsedPayload
  } catch {
    return null
  }
}

function truncate(str: string, maxLen = 60): string {
  return str.length > maxLen ? str.slice(0, maxLen) + '…' : str
}

function PayloadSection({ payloadJson }: { payloadJson: string }) {
  const [expanded, setExpanded] = useState(false)
  const payload = parsePayload(payloadJson)

  if (!payload) {
    return (
      <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-xs)' }}>
        (no payload)
      </div>
    )
  }

  const sourceMode = payload.source_mode ?? payload.source
  const isYoutube = sourceMode === 'youtube'
  const sourceLabel = isYoutube ? 'YouTube' : 'Local file'
  const sourceValue = isYoutube
    ? (payload.youtube_url ?? payload.url ?? '—')
    : (payload.source_video_path ?? payload.path ?? '—')

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--color-text-secondary)',
          fontSize: 'var(--font-size-sm)',
          cursor: 'pointer',
          padding: '0',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-1)',
          fontFamily: 'var(--font-family-base)',
          fontWeight: 'var(--font-weight-medium)' as unknown as number,
        }}
      >
        {expanded ? '▾' : '▸'} Payload
      </button>
      {expanded && (
        <div
          style={{
            marginTop: 'var(--space-2)',
            padding: 'var(--space-3)',
            backgroundColor: 'var(--color-bg-elevated)',
            borderRadius: 'var(--radius-md)',
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
          }}
        >
          <div><strong>Source:</strong> {sourceLabel}</div>
          <div
            style={{
              wordBreak: 'break-all',
              fontFamily: 'var(--font-family-mono, monospace)',
            }}
          >
            <strong>{isYoutube ? 'URL:' : 'Path:'}</strong>{' '}
            {truncate(String(sourceValue))}
          </div>
          {payload.target_platform && (
            <div><strong>Platform:</strong> {String(payload.target_platform)}</div>
          )}
          {payload.aspect_ratio && (
            <div><strong>Aspect ratio:</strong> {String(payload.aspect_ratio)}</div>
          )}
          {payload.subtitle_style && (
            <div><strong>Subtitle style:</strong> {String(payload.subtitle_style)}</div>
          )}
          {payload.effect_preset && (
            <div><strong>Effect preset:</strong> {String(payload.effect_preset)}</div>
          )}
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 'var(--space-2)',
        padding: 'var(--space-2) 0',
        borderBottom: '1px solid var(--color-border)',
        fontSize: 'var(--font-size-sm)',
      }}
    >
      <span style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--color-text-primary)', textAlign: 'right' }}>{value}</span>
    </div>
  )
}

export function JobDetailDrawer({ jobId, onClose }: JobDetailDrawerProps) {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getJob(jobId)
      .then((data) => { if (!cancelled) { setJob(data); setLoading(false) } })
      .catch((err) => { if (!cancelled) { setError(err.message ?? 'Failed to load job'); setLoading(false) } })
    return () => { cancelled = true }
  }, [jobId])

  function copyJobId() {
    navigator.clipboard.writeText(jobId).catch(() => {})
  }

  return (
    <div
      data-testid="job-detail-drawer"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: 'var(--space-4)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <span
          style={{
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-primary)',
          }}
        >
          Job Details
        </span>
        <button
          onClick={onClose}
          data-testid="drawer-close-btn"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text-secondary)',
            cursor: 'pointer',
            fontSize: '18px',
            padding: 'var(--space-1)',
            lineHeight: 1,
          }}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
        {loading && (
          <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-sm)' }}>
            Loading...
          </div>
        )}

        {error && (
          <div style={{ color: 'var(--color-error)', fontSize: 'var(--font-size-sm)' }}>
            {error}
          </div>
        )}

        {job && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {/* Job ID */}
            <div>
              <div
                style={{
                  fontSize: 'var(--font-size-xs)',
                  color: 'var(--color-text-secondary)',
                  marginBottom: 'var(--space-1)',
                }}
              >
                Job ID
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <code
                  style={{
                    fontSize: 'var(--font-size-xs)',
                    fontFamily: 'var(--font-family-mono, monospace)',
                    color: 'var(--color-text-primary)',
                    backgroundColor: 'var(--color-bg-elevated)',
                    padding: '2px 6px',
                    borderRadius: 'var(--radius-sm)',
                    wordBreak: 'break-all',
                    flex: 1,
                  }}
                >
                  {job.job_id}
                </code>
                <button
                  onClick={copyJobId}
                  title="Copy job ID"
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-text-secondary)',
                    cursor: 'pointer',
                    fontSize: '14px',
                    padding: '2px',
                    flexShrink: 0,
                  }}
                >
                  📋
                </button>
              </div>
            </div>

            {/* Core fields */}
            <div>
              <DetailRow
                label="Kind"
                value={
                  <Badge variant="neutral" size="sm">
                    {job.kind}
                  </Badge>
                }
              />
              <DetailRow
                label="Status"
                value={<JobStatusBadge status={job.status} size="sm" />}
              />
              <DetailRow label="Stage" value={job.stage || '—'} />
              <DetailRow label="Created" value={formatDateTime(job.created_at)} />
              <DetailRow label="Updated" value={formatDateTime(job.updated_at)} />
            </div>

            {/* Progress */}
            <div>
              <div
                style={{
                  fontSize: 'var(--font-size-xs)',
                  color: 'var(--color-text-secondary)',
                  marginBottom: 'var(--space-2)',
                }}
              >
                Progress ({job.progress_percent}%)
              </div>
              <ProgressBar value={job.progress_percent} />
            </div>

            {/* Payload */}
            <PayloadSection payloadJson={job.payload_json} />

            {/* Placeholders */}
            <div
              style={{
                padding: 'var(--space-3)',
                backgroundColor: 'var(--color-bg-elevated)',
                borderRadius: 'var(--radius-md)',
                fontSize: 'var(--font-size-xs)',
                color: 'var(--color-text-secondary)',
                opacity: 0.6,
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-2)',
              }}
            >
              <div>Live progress — available when running</div>
              <div>Quality report — coming in Phase 6.3</div>
              <div>AI trace — coming in Phase 6.3</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
