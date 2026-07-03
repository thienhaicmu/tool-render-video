/**
 * pollVisibility — shared gate for the app's polling loops (WP5.4).
 *
 * The app runs several refcounted, shared pollers (jobs history, backend
 * health, system resources) plus the downloader's local poll. None of them
 * need to fetch while the tab is hidden — the user can't see the result and
 * it wastes CPU/network on a desktop app running alongside a render. Each
 * poll tick calls isTabHidden() and skips its fetch when true; the next tick
 * after the tab regains focus resumes normally.
 */
export function isTabHidden(): boolean {
  return typeof document !== 'undefined' && document.hidden
}
