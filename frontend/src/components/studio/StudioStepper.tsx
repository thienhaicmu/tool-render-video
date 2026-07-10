/**
 * StudioStepper.tsx — generic N-step progress indicator (1-based `current`).
 * Mode-agnostic: labels are passed in (already i18n'd by the caller). Tokens only.
 */
export function StudioStepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="st-stepper" role="list">
      {steps.map((label, i) => {
        const n = i + 1
        const active = n === current
        const done = n < current
        return (
          <div key={label} role="listitem"
            className={`st-step${active ? ' is-active' : ''}${done ? ' is-done' : ''}`}>
            <span className="st-step-dot">{done ? '✓' : n}</span>
            <span className="st-step-label">{label}</span>
            {i < steps.length - 1 && <span className="st-step-sep" aria-hidden>›</span>}
          </div>
        )
      })}
    </div>
  )
}
