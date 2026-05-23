/**
 * JobLoadingState — skeleton placeholder while history is loading.
 */

function SkeletonRow() {
  return (
    <div
      style={{
        padding: 'var(--space-4)',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      <div
        style={{
          height: '16px',
          width: '60%',
          backgroundColor: 'var(--color-bg-elevated)',
          borderRadius: 'var(--radius-sm)',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
      <div
        style={{
          height: '12px',
          width: '40%',
          backgroundColor: 'var(--color-bg-elevated)',
          borderRadius: 'var(--radius-sm)',
          animation: 'pulse 1.5s ease-in-out infinite',
          opacity: 0.7,
        }}
      />
      <div
        style={{
          height: '12px',
          width: '80%',
          backgroundColor: 'var(--color-bg-elevated)',
          borderRadius: 'var(--radius-sm)',
          animation: 'pulse 1.5s ease-in-out infinite',
          opacity: 0.5,
        }}
      />
    </div>
  )
}

export function JobLoadingState() {
  return (
    <div data-testid="job-loading-state">
      <SkeletonRow />
      <SkeletonRow />
      <SkeletonRow />
    </div>
  )
}
