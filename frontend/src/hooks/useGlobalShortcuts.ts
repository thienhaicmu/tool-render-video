/**
 * useGlobalShortcuts — top-level keyboard shortcuts that work from any
 * screen. Mount once at the app root.
 *
 * Shortcuts (S3.2):
 *   ⌘N / Ctrl+N        → New Render (nav to Clip Studio + reset Step 1)
 *   ⌘, / Ctrl+,        → Open Settings
 *   ?                  → Open Command Palette (alternative trigger to ⌘K)
 *
 * Notes:
 * - ⌘K is owned by CommandPalette.tsx — kept there because the palette
 *   needs to toggle its own state.
 * - When the user is typing into a text input / textarea / select, we
 *   skip shortcuts that produce visible characters (`?`). ⌘N / ⌘,
 *   intercept always since they require the modifier.
 */
import { useEffect } from 'react'
import { useUIStore } from '../stores/uiStore'

function isEditableTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false
  if (t.isContentEditable) return true
  const tag = t.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

export function useGlobalShortcuts() {
  const setActivePanel  = useUIStore((s) => s.setActivePanel)
  const requestNewRender = useUIStore((s) => s.requestNewRender)

  useEffect(() => {
    function onKeydown(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey
      const key = e.key

      // ⌘N — new render
      if (mod && key.toLowerCase() === 'n') {
        e.preventDefault()
        requestNewRender()
        setActivePanel('clip-studio')
        return
      }

      // ⌘, — settings
      if (mod && key === ',') {
        e.preventDefault()
        setActivePanel('settings')
        return
      }

      // ? — open palette (only when not typing)
      if (key === '?' && !isEditableTarget(e.target)) {
        e.preventDefault()
        // Reuse ⌘K via a synthetic event so we don't duplicate the
        // palette open logic — CommandPalette listens for ⌘K on the
        // window. Dispatch a synthetic keydown with metaKey set.
        window.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'k',
          metaKey: true,
          bubbles: true,
        }))
      }
    }
    window.addEventListener('keydown', onKeydown)
    return () => window.removeEventListener('keydown', onKeydown)
  }, [setActivePanel, requestNewRender])
}
