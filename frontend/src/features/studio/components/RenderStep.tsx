import { useState } from 'react'
import { submitRender } from '../../../api/render'

interface RenderStepProps {
  sessionId: string | null
  sessionDuration: number
  sessionSourceMode: 'youtube' | 'local'
  sessionOutputDir: string
  onRenderComplete: () => void
}

export function RenderStep({ sessionId, sessionDuration, sessionSourceMode, sessionOutputDir, onRenderComplete }: RenderStepProps) {
  const [renderLoading, setRenderLoading] = useState(false)
  const [renderError, setRenderError] = useState<string | null>(null)

  const handleRenderSubmit = async () => {
    if (!sessionId || !sessionOutputDir) return
    setRenderLoading(true)
    setRenderError(null)
    try {
      await submitRender({
        source_mode: sessionSourceMode,
        output_dir: sessionOutputDir,
        edit_session_id: sessionId,
      })
      onRenderComplete()
    } catch {
      setRenderError('Render could not be submitted — check the queue and try again.')
    } finally {
      setRenderLoading(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
      <div style={{
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--status-success-bg)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
      }}>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)' as unknown as number, color: 'var(--status-success)' }}>
          Ready to Render
        </div>
        {([
          { label: 'Platform', value: 'TikTok Vertical' },
          { label: 'Clips', value: '3 clips selected' },
        ] as const).map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{label}</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 'var(--weight-medium)' as unknown as number }}>{value}</span>
          </div>
        ))}
        {sessionDuration > 0 && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            Est. output: ~{Math.max(15, Math.floor(sessionDuration * 0.12))}s total
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
          {renderError && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--status-error)' }}>
              {renderError}
            </span>
          )}
          <button
            onClick={handleRenderSubmit}
            disabled={renderLoading || !sessionId}
            style={{
              height: '34px',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              backgroundColor: renderLoading || !sessionId
                ? 'var(--surface-card)'
                : 'var(--accent-primary)',
              color: renderLoading || !sessionId
                ? 'var(--text-tertiary)'
                : 'var(--text-primary)',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--weight-medium)' as unknown as number,
              cursor: renderLoading || !sessionId ? 'not-allowed' : 'pointer',
              transition: 'background-color var(--duration-instant) var(--ease-out)',
            }}
          >
            {renderLoading ? 'Submitting…' : 'Submit Render →'}
          </button>
        </div>
      </div>
    </div>
  )
}
