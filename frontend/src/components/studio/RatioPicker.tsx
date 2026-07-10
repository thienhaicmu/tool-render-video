/**
 * RatioPicker.tsx — visual aspect-ratio picker (real proportional frames, not
 * text buttons). Mode-agnostic base; defaults to 16:9 / 9:16 / 1:1 (Story defaults
 * to 16:9). Frame CSS is keyed by the ratio with ':' → '-' so class names stay
 * valid. Tokens only.
 */
export interface RatioOption {
  value: string
  label: string
}

const DEFAULT_RATIOS: RatioOption[] = [
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
  { value: '1:1', label: '1:1' },
]

export function RatioPicker({ value, onChange, options = DEFAULT_RATIOS }: {
  value: string
  onChange: (r: string) => void
  options?: RatioOption[]
}) {
  return (
    <div className="st-ratio-row">
      {options.map((r) => {
        const on = r.value === value
        const key = r.value.replace(':', '-')
        return (
          <button key={r.value} type="button" aria-pressed={on}
            className={`st-ratio${on ? ' is-on' : ''}`} onClick={() => onChange(r.value)}>
            <span className={`st-ratio-frame st-ratio-frame--${key}`} aria-hidden />
            <span className="st-ratio-label">{r.label}</span>
          </button>
        )
      })}
    </div>
  )
}
