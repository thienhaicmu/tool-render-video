/**
 * EditorLoadingState — skeleton shown while job parts are being fetched.
 */
export function EditorLoadingState() {
  return (
    <div
      data-testid="editor-loading-state"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        padding: 'var(--space-6)',
      }}
    >
      {/* Video skeleton */}
      <div
        style={{
          background: 'var(--color-bg-elevated)',
          borderRadius: 'var(--radius-md)',
          height: '280px',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
      {/* Controls skeleton */}
      <div
        style={{
          background: 'var(--color-bg-elevated)',
          borderRadius: 'var(--radius-md)',
          height: '80px',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
    </div>
  )
}
