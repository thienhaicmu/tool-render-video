/**
 * useHashRoute — lightweight deep-linking (WP2.2, safe subset).
 *
 * Syncs the URL hash with the top-level panel so refresh / back / forward and
 * shareable links work — WITHOUT touching RenderWorkflow's internal view
 * machine. A `#/monitor/<jobId>` link opens a job's monitor via the EXISTING
 * `monitorJobId` handshake (setActivePanel('clip-studio') + setMonitorJobId),
 * the same path the dock / notifications already use — so no render-flow
 * refactor is required.
 *
 * Hash is written for panel changes only (replaceState, no history spam). The
 * per-job monitor deep-link is read-only (we can't observe RenderWorkflow's
 * internal step to write it back), which is fine — the handshake still lands
 * the user on the right job.
 */
import { useEffect, useRef } from 'react'
import { useUIStore } from '../stores/uiStore'
import type { ActivePanel } from '../stores/uiStore'

const PANEL_TO_SLUG: Partial<Record<ActivePanel, string>> = {
  'clip-studio': 'studio',
  queue: 'queue',
  library: 'library',
  download: 'download',
  editor: 'editor',
  settings: 'settings',
}

const SLUG_TO_PANEL: Record<string, ActivePanel> = {
  studio: 'clip-studio',
  queue: 'queue',
  library: 'library',
  download: 'download',
  editor: 'editor',
  settings: 'settings',
  // Aliases → canonical.
  home: 'library',
  history: 'library',
  render: 'clip-studio',
}

export function useHashRoute() {
  const activePanel = useUIStore((s) => s.activePanel)
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const setMonitorJobId = useUIStore((s) => s.setMonitorJobId)

  // hash → state (mount + browser back/forward).
  useEffect(() => {
    const apply = () => {
      const raw = window.location.hash.replace(/^#\/?/, '')
      if (!raw) return
      const [seg, arg] = raw.split('/')
      if (seg === 'monitor' && arg) {
        setActivePanel('clip-studio')
        setMonitorJobId(decodeURIComponent(arg))
        return
      }
      const panel = SLUG_TO_PANEL[seg]
      if (panel) setActivePanel(panel)
    }
    apply()
    window.addEventListener('hashchange', apply)
    return () => window.removeEventListener('hashchange', apply)
  }, [setActivePanel, setMonitorJobId])

  // state → hash (skip the first run so the initial hash wins).
  const firstRef = useRef(true)
  useEffect(() => {
    if (firstRef.current) { firstRef.current = false; return }
    const slug = PANEL_TO_SLUG[activePanel]
    if (!slug) return
    // Preserve a deeper #/monitor/<id> while the user is still in Studio.
    if (window.location.hash.startsWith('#/monitor/') && activePanel === 'clip-studio') return
    const desired = `#/${slug}`
    if (window.location.hash !== desired) history.replaceState(null, '', desired)
  }, [activePanel])
}
