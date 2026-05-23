import { EmptyState } from '../../../components/ui/EmptyState'

interface AnalyzeStepProps {
  sessionId: string | null
  sessionTitle: string
  sessionDuration: number
}

export function AnalyzeStep({ sessionId, sessionTitle, sessionDuration }: AnalyzeStepProps) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
      {sessionId === null ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState primary="Source not prepared" secondary="Go back to Source step" />
        </div>
      ) : (
        <div style={{
          backgroundColor: 'var(--surface-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span style={{ color: 'var(--status-success)', fontSize: 'var(--text-sm)' }}>✓</span>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)', fontWeight: 'var(--weight-medium)' as unknown as number }}>
              {sessionTitle || 'Source prepared'}
            </span>
          </div>
          {sessionDuration > 0 && (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
              Duration: {Math.floor(sessionDuration / 60)}m {Math.floor(sessionDuration % 60)}s
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span style={{ color: 'var(--ai-active)', fontSize: 'var(--text-sm)' }}>·</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>Transcript building</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span style={{ color: 'var(--ai-active)', fontSize: 'var(--text-sm)' }}>·</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>AI moments detection</span>
          </div>
        </div>
      )}
    </div>
  )
}
