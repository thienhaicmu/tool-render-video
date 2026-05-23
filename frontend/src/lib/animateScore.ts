/**
 * animateScore — count-up animation for score display elements.
 * Pure utility, no React imports.
 * Source: docs/design/motion.md
 */

/**
 * Animates the text content of an element from 0 to the target value.
 * Uses requestAnimationFrame with an ease-out cubic curve.
 *
 * @param el       - The DOM element whose textContent will be updated.
 * @param target   - The final numeric score (0–100).
 * @param duration - Animation duration in milliseconds (default: 400ms).
 */
export function animateScore(
  el: HTMLElement,
  target: number,
  duration: number = 400
): void {
  const start = performance.now()
  function tick(now: number): void {
    const elapsed = now - start
    const progress = Math.min(elapsed / duration, 1)
    // ease-out curve: 1 - (1 - t)^3
    const eased = 1 - Math.pow(1 - progress, 3)
    el.textContent = String(Math.round(eased * target))
    if (progress < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}
