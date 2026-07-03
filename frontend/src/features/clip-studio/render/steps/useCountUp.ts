/**
 * useCountUp — smoothly tween a displayed number toward a target.
 *
 * Used for the focus card's live progress %, so it glides (easeOutCubic)
 * between the discrete progress updates the pipeline streams instead of
 * snapping — the small polish that makes a number feel "alive" without any
 * gaudy motion. rAF-driven; cancels cleanly on unmount / target change.
 */
import { useEffect, useRef, useState } from 'react'

export function useCountUp(target: number, ms = 550): number {
  const [val, setVal] = useState(target)
  const valRef = useRef(target)
  const rafRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    const from = valRef.current
    const delta = target - from
    if (Math.abs(delta) < 0.5) {
      valRef.current = target
      setVal(target)
      return
    }
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - p, 3) // easeOutCubic
      const next = from + delta * eased
      valRef.current = next
      setVal(next)
      if (p < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [target, ms])

  return val
}
