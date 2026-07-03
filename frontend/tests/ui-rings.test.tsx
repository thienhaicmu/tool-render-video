/**
 * ui-rings.test.tsx — WP0.3 smoke tests for the new ring primitives.
 * Covers value clamping + centre-label rendering for ScoreRing/ConicRing.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { ScoreRing } from '../src/components/ui/ScoreRing'
import { ConicRing } from '../src/components/ui/ConicRing'

describe('ScoreRing', () => {
  it('renders the rounded value in the centre', () => {
    const { container } = render(<ScoreRing value={87} />)
    expect(container.textContent).toContain('87')
  })

  it('clamps values above 100', () => {
    const { container } = render(<ScoreRing value={140} />)
    expect(container.textContent).toContain('100')
  })

  it('hides the value when showValue is false', () => {
    const { container } = render(<ScoreRing value={50} showValue={false} />)
    expect(container.textContent).toBe('')
  })
})

describe('ConicRing', () => {
  it('renders the percentage by default', () => {
    const { container } = render(<ConicRing progress={72} />)
    expect(container.textContent).toContain('72%')
  })

  it('clamps negative progress to 0', () => {
    const { container } = render(<ConicRing progress={-10} />)
    expect(container.textContent).toContain('0%')
  })

  it('renders children instead of the percentage when provided', () => {
    const { container } = render(<ConicRing progress={40}><span>step</span></ConicRing>)
    expect(container.textContent).toContain('step')
    expect(container.textContent).not.toContain('40%')
  })

  it('sets an accessible label', () => {
    const { getByRole } = render(<ConicRing progress={33} />)
    expect(getByRole('img').getAttribute('aria-label')).toBe('33%')
  })
})
