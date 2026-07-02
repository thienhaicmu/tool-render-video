/**
 * ConfirmDialog — P0.4 (frontend redesign): in-app replacement for
 * window.confirm. Native OS alert boxes broke the visual language and
 * could only express OK/Cancel; several call sites (e.g. "a render is
 * still running") were cramming three-way choices into two buttons.
 *
 * Imperative API, mirroring how window.confirm was used:
 *
 *   const choice = await confirmDialog({
 *     title: 'Delete job?',
 *     message: 'This cannot be undone.',
 *     buttons: [
 *       { id: 'delete', label: 'Delete', variant: 'danger' },
 *       { id: 'cancel', label: 'Cancel' },
 *     ],
 *   })
 *   if (choice === 'delete') { … }
 *
 * Resolves with the clicked button id, or null on Esc / backdrop click.
 * <ConfirmDialogHost /> must be mounted once (App.tsx does this).
 */
import React, { useEffect } from 'react'
import { create } from 'zustand'

export interface ConfirmButton {
  id: string
  label: string
  /** 'primary' = accent, 'danger' = red, default = neutral outline. */
  variant?: 'primary' | 'danger'
}

export interface ConfirmOptions {
  title: string
  message?: string
  buttons: ConfirmButton[]
}

interface ConfirmState {
  options: ConfirmOptions | null
  _resolve: ((choice: string | null) => void) | null
  open: (options: ConfirmOptions) => Promise<string | null>
  settle: (choice: string | null) => void
}

const useConfirmStore = create<ConfirmState>((set, get) => ({
  options: null,
  _resolve: null,

  open: (options) => {
    // If a dialog is somehow already open, settle it as dismissed first.
    get().settle(null)
    return new Promise<string | null>((resolve) => {
      set({ options, _resolve: resolve })
    })
  },

  settle: (choice) => {
    const { _resolve } = get()
    if (_resolve) _resolve(choice)
    set({ options: null, _resolve: null })
  },
}))

/** Open the confirm dialog. Resolves with the button id or null (dismissed). */
export function confirmDialog(options: ConfirmOptions): Promise<string | null> {
  return useConfirmStore.getState().open(options)
}

const BTN_VARIANT: Record<string, React.CSSProperties> = {
  primary: {
    background: 'var(--accent-primary)',
    border: '1px solid var(--accent-primary)',
    color: '#fff',
  },
  danger: {
    background: 'rgba(239,68,68,.12)',
    border: '1px solid var(--status-error)',
    color: 'var(--status-error)',
  },
  default: {
    background: 'transparent',
    border: '1px solid var(--border-default)',
    color: 'var(--text-secondary)',
  },
}

export function ConfirmDialogHost() {
  const options = useConfirmStore((s) => s.options)
  const settle = useConfirmStore((s) => s.settle)

  useEffect(() => {
    if (!options) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') settle(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [options, settle])

  if (!options) return null

  return (
    <div
      style={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-label={options.title}
      onClick={() => settle(null)}
    >
      <div style={styles.panel} onClick={(e) => e.stopPropagation()}>
        <div style={styles.title}>{options.title}</div>
        {options.message && <div style={styles.message}>{options.message}</div>}
        <div style={styles.buttonRow}>
          {options.buttons.map((b) => (
            <button
              key={b.id}
              autoFocus={b.variant === 'primary'}
              style={{ ...styles.btn, ...BTN_VARIANT[b.variant ?? 'default'] }}
              onClick={() => settle(b.id)}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed', inset: 0, zIndex: 2000,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 24,
  },
  panel: {
    width: 'min(440px, 100%)',
    background: 'var(--surface-panel)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-xl)',
    boxShadow: '0 16px 48px rgba(0,0,0,0.45)',
    padding: '20px 22px 18px',
    display: 'flex', flexDirection: 'column', gap: 10,
  },
  title: {
    fontSize: 14, fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.35,
  },
  message: {
    fontSize: 12,
    color: 'var(--text-secondary)',
    lineHeight: 1.55,
    whiteSpace: 'pre-line',
  },
  buttonRow: {
    display: 'flex', gap: 8, justifyContent: 'flex-end',
    marginTop: 8, flexWrap: 'wrap',
  },
  btn: {
    padding: '7px 16px',
    borderRadius: 'var(--radius-md)',
    fontSize: 12, fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
}
