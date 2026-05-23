/**
 * JobErrorState — shown when the history fetch fails.
 */
import { Button } from '../../components/ui/Button'

export interface JobErrorStateProps {
  error: string
  onRetry: () => void
}

export function JobErrorState({ error, onRetry }: JobErrorStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-4)',
        padding: 'var(--space-12)',
        color: 'var(--color-text-secondary)',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: '36px', opacity: 0.5 }}>⚠️</div>
      <div>
        <p
          style={{
            fontSize: 'var(--font-size-md)',
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
            color: 'var(--color-error)',
            margin: '0 0 var(--space-2) 0',
          }}
        >
          Failed to load history
        </p>
        <p style={{ fontSize: 'var(--font-size-sm)', margin: 0 }}>
          {error}
        </p>
      </div>
      <Button variant="secondary" size="md" onClick={onRetry}>
        Try again
      </Button>
    </div>
  )
}
