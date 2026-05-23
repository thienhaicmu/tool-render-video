/**
 * QualityTraceRefs — renders AI trace reference pills for a quality report.
 */
import { AI_TRACE_FRIENDLY } from './quality.types'
import { getFriendlyTraceLabel } from './quality.utils'
import './QualityPanel.css'

export interface QualityTraceRefsProps {
  traceRefs: string[]
}

export function QualityTraceRefs({ traceRefs }: QualityTraceRefsProps) {
  return (
    <div className="quality-trace-refs" data-testid="quality-trace-refs">
      <div className="quality-trace-refs-label">AI Trace</div>
      {traceRefs.length === 0 ? (
        <div className="quality-trace-empty">
          No AI trace references linked to this report.
        </div>
      ) : (
        <div className="quality-trace-pills">
          {traceRefs.map((ref, idx) => {
            const isKnown = Boolean(AI_TRACE_FRIENDLY[ref])
            return (
              <span
                key={`${ref}_${idx}`}
                className={`quality-trace-pill${isKnown ? ' quality-trace-pill--known' : ''}`}
              >
                {getFriendlyTraceLabel(ref)}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}
