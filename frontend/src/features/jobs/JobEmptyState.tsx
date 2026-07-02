/**
 * JobEmptyState — shown when history list is empty with no active filters.
 */
import { Button } from '@/components/ui/Button'
import { useUIStore } from '@/stores/uiStore'
import { IconFilm } from '@/components/icons'

export function JobEmptyState() {
  const setActivePanel = useUIStore((s) => s.setActivePanel)

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
      <div style={{ opacity: 0.3, color: 'var(--text-tertiary)' }}><IconFilm size={48} /></div>
      <div>
        <p
          style={{
            fontSize: 'var(--font-size-md)',
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
            color: 'var(--color-text-primary)',
            margin: '0 0 var(--space-2) 0',
          }}
        >
          No render jobs yet
        </p>
        <p style={{ fontSize: 'var(--font-size-sm)', margin: 0 }}>
          Your completed and in-progress renders will appear here.
        </p>
      </div>
      <Button
        variant="primary"
        size="md"
        onClick={() => setActivePanel('render')}
      >
        Create first render
      </Button>
    </div>
  )
}
