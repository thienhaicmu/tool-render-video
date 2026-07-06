/**
 * ClipSteps — the per-clip Cut → Sub → Render mini-stepper.
 *
 * Surfaces WHICH step a clip is on (data the pipeline already streams via the
 * frozen per-part status) so the queue and focus card aren't a wall of
 * identical "Rendering" pills. Shared by ClipTile (compact row variant) and
 * RenderStage (larger focus variant).
 */
import { Fragment } from 'react'
import { IconCheck } from '@/components/icons'
import { STEP_NODES, stepStates } from './clipState'

export function ClipSteps({ status, variant = 'row' }: {
  status: string
  variant?: 'row' | 'focus'
}) {
  const states = stepStates(status)
  return (
    <div className={`clip-steps clip-steps-${variant}`} aria-hidden="true">
      {STEP_NODES.map((node, i) => (
        <Fragment key={node.key}>
          {i > 0 && (
            <span className={`cs-line${states[i - 1] === 'done' ? ' cs-line-done' : ''}`} />
          )}
          <span className={`cs-node cs-node-${states[i]}`}>
            <span className="cs-dot">
              {states[i] === 'done' && <IconCheck size={variant === 'focus' ? 11 : 8} />}
            </span>
            <span className="cs-lbl">{node.label}</span>
          </span>
        </Fragment>
      ))}
    </div>
  )
}
