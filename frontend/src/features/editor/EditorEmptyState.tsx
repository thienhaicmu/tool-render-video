/**
 * EditorEmptyState — shown when no media is selected.
 */
import { Button } from '../../components/ui/Button'
import { useUIStore } from '../../stores/uiStore'

export function EditorEmptyState() {
  const setActivePanel = useUIStore((s) => s.setActivePanel)

  return (
    <div
      data-testid="editor-empty-state"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 'var(--space-4)',
        color: 'var(--color-text-secondary)',
        textAlign: 'center',
        padding: 'var(--space-8)',
      }}
    >
      <div style={{ fontSize: '48px', opacity: 0.4 }}>▶</div>
      <div>
        <div
          style={{
            fontSize: 'var(--font-size-lg)',
            color: 'var(--color-text-primary)',
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
            marginBottom: 'var(--space-2)',
          }}
        >
          No media selected
        </div>
        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
          Open a completed job from History to preview it here.
        </div>
      </div>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setActivePanel('history')}
        data-testid="go-to-history-btn"
      >
        Go to History
      </Button>
    </div>
  )
}
