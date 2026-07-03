/**
 * Toggle — canonical accessible switch primitive (WP3).
 *
 * A real `role="switch"` control (keyboard + SR), token-styled, for new code.
 * The Configure screen's existing `Tog` was upgraded in place to the same a11y
 * contract; this is the shared primitive the rest of the app should adopt.
 */
export interface ToggleProps {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
  disabled?: boolean
}

export function Toggle({ checked, onChange, label, disabled }: ToggleProps) {
  const set = () => { if (!disabled) onChange(!checked) }
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={set}
      style={{
        position: 'relative', width: 38, height: 22, flexShrink: 0,
        borderRadius: 999, padding: 0, cursor: disabled ? 'not-allowed' : 'pointer',
        border: '1px solid',
        borderColor: checked ? 'var(--accent-primary)' : 'var(--border-default)',
        background: checked ? 'var(--accent-primary)' : 'var(--surface-input)',
        transition: 'background .2s, border-color .2s',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <span
        style={{
          position: 'absolute', top: 2, left: checked ? 18 : 2,
          width: 16, height: 16, borderRadius: '50%',
          background: checked ? '#fff' : 'var(--text-tertiary)',
          transition: 'left .2s, background .2s',
        }}
      />
    </button>
  )
}
