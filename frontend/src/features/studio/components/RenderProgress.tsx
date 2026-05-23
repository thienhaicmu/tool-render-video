export interface RenderProgressProps {
  progress: number   // 0–100
  stage: string
  animated?: boolean
}

export function RenderProgress({ progress, stage, animated = false }: RenderProgressProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', width: '100%' }}>
      <div
        style={{
          height: '6px',
          backgroundColor: 'var(--surface-card)',
          borderRadius: 'var(--radius-sm)',
          overflow: 'hidden',
          width: '100%',
        }}
      >
        <div
          className={animated ? 'render-progress--animated' : undefined}
          style={{
            height: '100%',
            width: `${progress}%`,
            backgroundColor: 'var(--accent-primary)',
            borderRadius: 'var(--radius-sm)',
            transition: 'width var(--duration-panel) var(--ease-out)',
          }}
        />
      </div>
      <span
        style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--text-tertiary)',
        }}
      >
        {stage}
      </span>
    </div>
  )
}
