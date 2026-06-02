/**
 * EditorErrorState — shown when loading job parts fails.
 */
import { Button } from '@/components/ui/Button'

export interface EditorErrorStateProps {
  error: string
  onRetry?: () => void
}

export function EditorErrorState({ error, onRetry }: EditorErrorStateProps) {
  return (
    <div
      data-testid="editor-error-state"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 'var(--space-4)',
        padding: 'var(--space-8)',
        textAlign: 'center',
      }}
    >
      <div style={{ color: 'var(--color-error)', fontSize: 'var(--font-size-sm)' }}>
        {error}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} data-testid="editor-retry-btn">
          Retry
        </Button>
      )}
    </div>
  )
}
