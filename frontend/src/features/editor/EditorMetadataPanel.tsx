/**
 * EditorMetadataPanel — right-rail metadata for the active editor selection.
 * Shows job ID, part, status, duration, trim summary, copy URL.
 * Future actions (Apply Trim, Re-render, Export) are shown as disabled placeholders.
 */
import { Button } from '../../components/ui/Button'
import { formatTime } from './editor.utils'

export interface EditorMetadataPanelProps {
  jobId: string
  partNo: number
  jobStatus?: string
  durationSec: number
  trimStartSec: number
  trimEndSec: number
  mediaUrl: string
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {})
}

export function EditorMetadataPanel({
  jobId,
  partNo,
  jobStatus,
  durationSec,
  trimStartSec,
  trimEndSec,
  mediaUrl,
}: EditorMetadataPanelProps) {
  const trimDuration = Math.max(0, trimEndSec - trimStartSec)

  return (
    <div
      data-testid="editor-metadata-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        padding: 'var(--space-4)',
        backgroundColor: 'var(--color-bg-elevated)',
        borderRadius: 'var(--radius-md)',
        fontSize: 'var(--font-size-sm)',
      }}
    >
      <div
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          fontWeight: 'var(--font-weight-medium)' as unknown as number,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        Media Info
      </div>

      {/* Job ID */}
      <div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-1)' }}>
          Job ID
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <code
            data-testid="editor-job-id"
            style={{
              fontSize: 'var(--font-size-xs)',
              fontFamily: 'var(--font-family-mono, monospace)',
              color: 'var(--color-text-primary)',
              backgroundColor: 'var(--color-bg-surface)',
              padding: '2px 6px',
              borderRadius: 'var(--radius-sm)',
              wordBreak: 'break-all',
              flex: 1,
              maxWidth: '160px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={jobId}
          >
            {jobId}
          </code>
          <button
            onClick={() => copyToClipboard(jobId)}
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

      {/* Part number */}
      <MetaRow label="Part" value={`Part ${partNo}`} />

      {/* Status */}
      {jobStatus && (
        <MetaRow label="Status" value={<StatusText status={jobStatus} />} />
      )}

      {/* Duration */}
      <MetaRow
        label="Duration"
        value={durationSec > 0 ? formatTime(durationSec) : '—'}
      />

      {/* Trim summary */}
      <div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-1)' }}>
          Trim
        </div>
        <div style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-family-mono, monospace)', fontSize: 'var(--font-size-xs)' }}>
          {formatTime(trimStartSec)} → {formatTime(trimEndSec)}
        </div>
        <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-xs)', marginTop: 'var(--space-1)' }}>
          = {formatTime(trimDuration)}
        </div>
      </div>

      {/* Copy media URL */}
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => copyToClipboard(mediaUrl)}
          data-testid="copy-media-url-btn"
        >
          Copy media URL
        </Button>
      </div>

      {/* Future actions */}
      <div>
        <div
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            marginBottom: 'var(--space-2)',
            paddingTop: 'var(--space-2)',
            borderTop: '1px solid var(--color-border)',
          }}
        >
          Coming in Phase 6.6+
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <Button variant="secondary" size="sm" disabled data-testid="apply-trim-btn">
            Apply Trim
          </Button>
          <Button variant="secondary" size="sm" disabled data-testid="rerender-btn">
            Re-render Selection
          </Button>
          <Button variant="secondary" size="sm" disabled data-testid="export-clip-btn">
            Export Clip
          </Button>
        </div>
      </div>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)' }}>
      <span style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--color-text-primary)', textAlign: 'right' }}>{value}</span>
    </div>
  )
}

function StatusText({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    completed: 'var(--color-success)',
    completed_with_errors: 'var(--color-warning)',
    failed: 'var(--color-error)',
    running: 'var(--color-info)',
    queued: 'var(--color-text-secondary)',
  }
  return (
    <span style={{ color: colorMap[status] ?? 'var(--color-text-secondary)' }}>
      {status}
    </span>
  )
}
