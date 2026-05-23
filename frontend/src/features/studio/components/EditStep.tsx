// eslint-disable-next-line @typescript-eslint/no-empty-object-type
interface EditStepProps {
  // no props needed — fully static content
}

export function EditStep(_props: EditStepProps) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
      <div style={{
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
      }}>
        {([
          { label: 'AI clip selection', value: '3 clips selected' },
          { label: 'Subtitles', value: 'Enabled · Pro Karaoke style' },
          { label: 'Format', value: '9:16 Vertical · 60fps' },
          { label: 'Platform', value: 'TikTok optimized' },
        ] as const).map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{label}</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 'var(--weight-medium)' as unknown as number }}>{value}</span>
          </div>
        ))}
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', paddingTop: 'var(--space-2)', borderTop: '1px solid var(--border-subtle)' }}>
          Adjust settings in Edit options below
        </div>
      </div>
    </div>
  )
}
