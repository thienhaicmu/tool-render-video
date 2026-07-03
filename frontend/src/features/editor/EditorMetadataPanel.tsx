/**
 * EditorMetadataPanel — right-rail metadata and action panel for the editor.
 * Provides Apply Trim, Re-render Selection, and Export Clip actions.
 */
import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { formatTime } from './editor.utils'
import { useUIStore } from '@/stores/uiStore'
import { trimJobPart, rerenderSelection, exportClip } from '@/api/editing'
import { IconClipboard } from '@/components/icons'
import { _formatApiError } from '@/lib/errors'

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
  const addNotification = useUIStore((s) => s.addNotification)
  const setActivePanel = useUIStore((s) => s.setActivePanel)

  const [trimLoading, setTrimLoading] = useState(false)
  const [rerenderLoading, setRerenderLoading] = useState(false)
  const [exportLoading, setExportLoading] = useState(false)
  const [exportDir, setExportDir] = useState('')

  const trimDuration = Math.max(0, trimEndSec - trimStartSec)
  const hasTrim = trimDuration >= 1.0 && trimDuration < durationSec

  async function handleApplyTrim() {
    if (!hasTrim) return
    setTrimLoading(true)
    try {
      const result = await trimJobPart(jobId, partNo, {
        start_sec: trimStartSec,
        end_sec: trimEndSec,
        output_mode: 'new_job',
      })
      addNotification({
        type: 'success',
        title: 'Trim applied',
        message: `Saved ${result.duration_sec.toFixed(1)}s clip`,
      })
      // WP4 — reveal the trimmed file's folder.
      if (result.output_file) {
        const sep = result.output_file.includes('\\') ? '\\' : '/'
        const dir = result.output_file.slice(0, result.output_file.lastIndexOf(sep))
        if (dir) window.electronAPI?.openPath?.(dir)
      }
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Trim failed',
        message: _formatApiError(err),
      })
    } finally {
      setTrimLoading(false)
    }
  }

  async function handleRerender() {
    if (!hasTrim) return
    setRerenderLoading(true)
    try {
      const result = await rerenderSelection(jobId, partNo, {
        start_sec: trimStartSec,
        end_sec: trimEndSec,
      })
      // WP4 — land on the canonical Queue panel (was the deprecated 'history'
      // alias) where the new render job is watchable, and make the toast
      // deep-link to it.
      addNotification({
        type: 'success',
        title: 'Re-render queued',
        message: 'Track it in the Queue.',
        jobId: result.new_job_id,
        kind: 'render',
      })
      setActivePanel('queue')
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Re-render failed',
        message: _formatApiError(err),
      })
    } finally {
      setRerenderLoading(false)
    }
  }

  async function handleBrowseDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setExportDir(dir)
  }

  async function handleExport() {
    const dest = exportDir.trim()
    if (!dest) {
      addNotification({ type: 'error', title: 'Export failed', message: 'Enter a destination directory path' })
      return
    }
    setExportLoading(true)
    try {
      const result = await exportClip(jobId, partNo, { destination_dir: dest })
      addNotification({
        type: 'success',
        title: 'Export complete',
        message: `Saved to ${result.destination_dir}`,
      })
      // WP4 — reveal the exported file, matching the Results export UX.
      window.electronAPI?.openPath?.(result.destination_dir)
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Export failed',
        message: _formatApiError(err),
      })
    } finally {
      setExportLoading(false)
    }
  }

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
            <IconClipboard size={14} />
          </button>
        </div>
      </div>

      {/* Part number */}
      <MetaRow label="Clip" value={`Clip ${partNo}`} />

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

      {/* Actions */}
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
          Actions
          {!hasTrim && durationSec > 0 && (
            <span style={{ marginLeft: 'var(--space-2)', color: 'var(--color-text-muted)' }}>
              (set trim range first)
            </span>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <Button
            variant="secondary"
            size="sm"
            disabled={!hasTrim || trimLoading}
            onClick={handleApplyTrim}
            data-testid="apply-trim-btn"
          >
            {trimLoading ? 'Trimming…' : 'Apply Trim'}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!hasTrim || rerenderLoading}
            onClick={handleRerender}
            data-testid="rerender-btn"
          >
            {rerenderLoading ? 'Queuing…' : 'Re-render Selection'}
          </Button>

          {/* Export: destination dir input + Browse + button */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
              <input
                type="text"
                placeholder="Destination folder path"
                value={exportDir}
                onChange={(e) => setExportDir(e.target.value)}
                data-testid="export-dir-input"
                style={{
                  padding: '4px 8px',
                  backgroundColor: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-text-primary)',
                  fontSize: 'var(--font-size-xs)',
                  flex: 1,
                  minWidth: 0,
                  boxSizing: 'border-box',
                }}
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBrowseDir}
                data-testid="export-browse-btn"
              >
                Browse
              </Button>
            </div>
            <Button
              variant="secondary"
              size="sm"
              disabled={exportLoading || !exportDir.trim()}
              onClick={handleExport}
              data-testid="export-clip-btn"
            >
              {exportLoading ? 'Exporting…' : 'Export Clip'}
            </Button>
          </div>
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
