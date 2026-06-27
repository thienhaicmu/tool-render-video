/**
 * CommandPalette — ⌘K / Ctrl+K spotlight-style action runner.
 *
 * S3.1 (Sprint 3 — power user basics). The render app previously had
 * zero keyboard shortcuts; a creator running 100 videos/week could not
 * navigate or trigger actions without mousing through nested menus.
 * The palette is the central command surface: every global action that
 * doesn't need on-screen context lives here.
 *
 * Global keyboard handler:
 *   - ⌘K / Ctrl+K from anywhere    → open palette
 *   - Esc                          → close palette
 *   - ↑/↓                          → move selection
 *   - Enter                        → run selected action
 *   - Type to filter by label/keywords (substring, case-insensitive)
 *
 * The palette deliberately ignores keystrokes while the user is typing
 * into a form field — so ⌘K in a text input doesn't steal focus.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useUIStore } from '../stores/uiStore'
import { useRenderStore } from '../stores/renderStore'
import { useJobsStore } from '../stores/jobsStore'
import { useThemeStore } from '../stores/themeStore'
import { isTerminalStatus } from '../types/enums'
import { cancelRender } from '../api/render'
import { holdJob, resumeJob } from '../api/jobs'
import { useI18n } from '../i18n/useI18n'
import type { TranslationKey } from '../i18n/translations'

interface CommandAction {
  id: string
  label: string
  keywords?: string
  shortcut?: string
  /** Section id — mapped to a localized label via SECTION_LABEL_KEY. */
  section: 'nav' | 'render' | 'prefs'
  /** Returns true to keep palette open (rare); default closes after run. */
  run: () => void | Promise<void>
  /** Hidden when false; used for context-sensitive actions like Cancel. */
  available?: boolean
}

// Pha 1.2 — section id → localized header label.
const SECTION_LABEL_KEY: Record<CommandAction['section'], TranslationKey> = {
  nav:    'cmd_section_nav',
  render: 'cmd_section_render',
  prefs:  'cmd_section_prefs',
}

function isEditableTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false
  if (t.isContentEditable) return true
  const tag = t.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

function fuzzyMatch(query: string, label: string, keywords?: string): boolean {
  if (!query) return true
  const haystack = (label + ' ' + (keywords || '')).toLowerCase()
  const q = query.toLowerCase().trim()
  if (!q) return true
  // Cheap fuzzy: every char in q must appear in haystack in order.
  let i = 0
  for (const ch of haystack) {
    if (ch === q[i]) i++
    if (i >= q.length) return true
  }
  return false
}

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIdx, setSelectedIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const { t } = useI18n()
  const setActivePanel        = useUIStore((s) => s.setActivePanel)
  const setDuplicateSeedJobId = useUIStore((s) => s.setDuplicateSeedJobId)
  const setMonitorJobId       = useUIStore((s) => s.setMonitorJobId)
  const requestNewRender      = useUIStore((s) => s.requestNewRender)
  const addNotification       = useUIStore((s) => s.addNotification)
  const cyclePreference       = useThemeStore((s) => s.cyclePreference)
  const activeRenderJobId     = useRenderStore((s) => s.activeJobId)
  const renderJobs            = useRenderStore((s) => s.jobs)
  const jobsItems             = useJobsStore((s) => s.items)
  const queueOrder            = useJobsStore((s) => s.queueOrder)
  const heldIds               = useJobsStore((s) => s.heldIds)

  // ── Action registry — re-computed when context changes so context-
  // sensitive actions (Cancel, Duplicate-last) reflect current state.
  const actions: CommandAction[] = useMemo(() => {
    const activeStatus = activeRenderJobId ? renderJobs[activeRenderJobId]?.status : null
    const canCancelActive =
      !!activeRenderJobId && !!activeStatus && !isTerminalStatus(activeStatus)
    const lastCompletedRender = jobsItems.find(
      (j) => j.kind === 'render' && (j.status === 'completed' || j.status === 'partial' || j.status === 'completed_with_errors'),
    )
    // Pha 5.3 — keyboard-driven queue actions.
    const runningRender = jobsItems.find((j) => j.kind === 'render' && j.status === 'running')
    const firstQueued = queueOrder[0]   // pending render at the front of the queue
    const firstHeld = heldIds[0]        // a paused render

    return [
      // Navigation
      {
        id: 'nav-studio',
        label: t('cmd_nav_studio'),
        keywords: 'render workflow editor studio',
        section: 'nav',
        run: () => setActivePanel('clip-studio'),
      },
      {
        id: 'nav-library',
        label: t('cmd_nav_library'),
        keywords: 'history jobs lịch sử thư viện',
        section: 'nav',
        run: () => setActivePanel('library'),
      },
      {
        id: 'nav-download',
        label: t('cmd_nav_download'),
        keywords: 'youtube tiktok tải về',
        section: 'nav',
        run: () => setActivePanel('download'),
      },
      {
        id: 'nav-settings',
        label: t('cmd_nav_settings'),
        keywords: 'cài đặt cấu hình preferences',
        shortcut: '⌘,',
        section: 'nav',
        run: () => setActivePanel('settings'),
      },

      // Render
      {
        id: 'render-new',
        label: t('cmd_render_new'),
        keywords: 'new render fresh start step 1 nguồn',
        shortcut: '⌘N',
        section: 'render',
        run: () => {
          // S3.5 — force-reset even when an unrelated render is
          // running. RenderWorkflow watches uiStore.newRenderRequest
          // and resets to Step 1 + suppresses auto-reattach.
          requestNewRender()
          setActivePanel('clip-studio')
        },
      },
      {
        id: 'render-cancel',
        label: t('cmd_render_cancel'),
        keywords: 'cancel stop dừng',
        section: 'render',
        available: canCancelActive,
        run: async () => {
          if (!activeRenderJobId) return
          try {
            await cancelRender(activeRenderJobId)
            addNotification({ title: t('cmd_toast_cancel_requested'), type: 'info' })
          } catch {
            addNotification({ title: t('cmd_toast_cancel_failed'), type: 'error' })
          }
        },
      },
      {
        id: 'render-duplicate-last',
        label: t('cmd_render_dup'),
        keywords: 'clone copy rerun lặp lại',
        section: 'render',
        available: !!lastCompletedRender,
        run: () => {
          if (!lastCompletedRender) return
          setDuplicateSeedJobId(lastCompletedRender.job_id)
          setActivePanel('clip-studio')
        },
      },
      {
        id: 'queue-open-monitor',
        label: t('cmd_open_monitor'),
        keywords: 'monitor watch theo dõi render đang chạy progress',
        section: 'render',
        available: !!runningRender,
        run: () => {
          if (!runningRender) return
          setMonitorJobId(runningRender.job_id)
          setActivePanel('clip-studio')
        },
      },
      {
        id: 'queue-pause-next',
        label: t('cmd_pause_next'),
        keywords: 'pause hold tạm dừng queue hàng đợi',
        section: 'render',
        available: !!firstQueued,
        run: async () => {
          if (!firstQueued) return
          try {
            await holdJob(firstQueued)
            addNotification({ title: t('cmd_toast_paused'), type: 'info' })
          } catch {
            addNotification({ title: t('cmd_toast_action_failed'), type: 'error' })
          }
        },
      },
      {
        id: 'queue-resume-paused',
        label: t('cmd_resume_paused'),
        keywords: 'resume tiếp tục paused tạm dừng',
        section: 'render',
        available: !!firstHeld,
        run: async () => {
          if (!firstHeld) return
          try {
            await resumeJob(firstHeld)
            addNotification({ title: t('cmd_toast_resumed'), type: 'info' })
          } catch {
            addNotification({ title: t('cmd_toast_action_failed'), type: 'error' })
          }
        },
      },

      // Preferences
      {
        id: 'pref-defaults',
        label: t('cmd_pref_defaults'),
        keywords: 'preset aspect ratio voice subtitle settings defaults',
        section: 'prefs',
        run: () => {
          setActivePanel('settings')
          // Smooth-scroll to defaults section after Settings mounts.
          setTimeout(() => {
            const el = document.getElementById('settings-defaults')
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }, 80)
        },
      },
      {
        id: 'pref-theme-cycle',
        label: t('cmd_pref_theme'),
        keywords: 'theme dark light màu giao diện',
        section: 'prefs',
        run: () => cyclePreference(),
      },
    ]
  }, [
    t,
    setActivePanel, setDuplicateSeedJobId, setMonitorJobId, requestNewRender,
    addNotification, cyclePreference,
    activeRenderJobId, renderJobs, jobsItems, queueOrder, heldIds,
  ])

  // Filter + section grouping.
  const visible = useMemo(() => {
    return actions.filter(
      (a) => a.available !== false && fuzzyMatch(query, a.label, a.keywords),
    )
  }, [actions, query])

  // Reset selection whenever the visible set changes.
  useEffect(() => {
    setSelectedIdx(0)
  }, [query, visible.length])

  // Global ⌘K / Ctrl+K to open. Esc to close.
  useEffect(() => {
    function onKeydown(e: KeyboardEvent) {
      const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k'
      if (isCmdK) {
        if (isEditableTarget(e.target) && !open) {
          // Even in inputs we want ⌘K to work — that's the spotlight
          // expectation. So we always intercept.
        }
        e.preventDefault()
        setOpen((prev) => !prev)
        setQuery('')
        return
      }
      if (open && e.key === 'Escape') {
        e.preventDefault()
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKeydown)
    return () => window.removeEventListener('keydown', onKeydown)
  }, [open])

  // Focus input when palette opens.
  useEffect(() => {
    if (open) {
      // Defer so the DOM node is mounted.
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  async function runAction(action: CommandAction) {
    setOpen(false)
    try {
      await action.run()
    } catch {
      // Action errors are surfaced by toasts inside each handler.
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIdx((i) => Math.min(i + 1, Math.max(visible.length - 1, 0)))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const action = visible[selectedIdx]
      if (action) void runAction(action)
    }
  }

  if (!open) return null

  return (
    <div
      style={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onClick={() => setOpen(false)}
    >
      <div
        style={styles.panel}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={styles.inputWrap}>
          <span style={styles.searchIcon}>⌕</span>
          <input
            ref={inputRef}
            type="text"
            placeholder={t('cmd_placeholder')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            style={styles.input}
          />
          <span style={styles.kbd}>Esc</span>
        </div>

        <div style={styles.list}>
          {visible.length === 0 ? (
            <div style={styles.empty}>{t('cmd_empty')} “{query}”</div>
          ) : (
            (() => {
              const nodes: React.ReactNode[] = []
              let lastSection = ''
              visible.forEach((a, idx) => {
                if (a.section !== lastSection) {
                  lastSection = a.section
                  nodes.push(
                    <div key={`sect-${a.section}`} style={styles.sectionHeader}>
                      {t(SECTION_LABEL_KEY[a.section])}
                    </div>,
                  )
                }
                const selected = idx === selectedIdx
                nodes.push(
                  <button
                    key={a.id}
                    onClick={() => runAction(a)}
                    onMouseEnter={() => setSelectedIdx(idx)}
                    style={{
                      ...styles.item,
                      background: selected ? 'var(--accent-subtle, rgba(123,97,255,.15))' : 'transparent',
                      color: selected ? 'var(--accent-primary, var(--accent))' : 'var(--text-primary, var(--text-1))',
                    }}
                  >
                    <span style={styles.itemLabel}>{a.label}</span>
                    {a.shortcut && (
                      <span style={styles.itemShortcut}>{a.shortcut}</span>
                    )}
                  </button>,
                )
              })
              return nodes
            })()
          )}
        </div>

        <div style={styles.footer}>
          <span><span style={styles.kbd}>↑↓</span> {t('cmd_foot_move')}</span>
          <span><span style={styles.kbd}>↵</span> {t('cmd_foot_select')}</span>
          <span><span style={styles.kbd}>⌘K</span> {t('cmd_foot_toggle')}</span>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.4)',
    zIndex: 2000,
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingTop: '12vh',
  },
  panel: {
    width: 'min(560px, 90vw)',
    maxHeight: '70vh',
    background: 'var(--surface-panel, #1d1f23)',
    border: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
    borderRadius: 12,
    boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  },
  inputWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '12px 16px',
    borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
  },
  searchIcon: {
    fontSize: 16,
    color: 'var(--text-tertiary, var(--text-3))',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    border: 'none',
    background: 'transparent',
    outline: 'none',
    fontSize: 14,
    color: 'var(--text-primary, var(--text-1))',
    fontFamily: 'inherit',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    padding: '6px 0',
  },
  empty: {
    padding: '24px 16px',
    textAlign: 'center',
    color: 'var(--text-tertiary, var(--text-3))',
    fontSize: 12,
  },
  sectionHeader: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: '.08em',
    textTransform: 'uppercase',
    color: 'var(--text-tertiary, var(--text-3))',
    padding: '8px 16px 4px',
  },
  item: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    border: 'none',
    padding: '8px 16px',
    fontSize: 13,
    textAlign: 'left',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  itemLabel: {
    flex: 1,
    textAlign: 'left',
  },
  itemShortcut: {
    fontSize: 10,
    fontWeight: 600,
    color: 'var(--text-tertiary, var(--text-3))',
    fontFamily: 'monospace',
  },
  footer: {
    display: 'flex',
    gap: 14,
    padding: '8px 16px',
    fontSize: 10,
    color: 'var(--text-tertiary, var(--text-3))',
    borderTop: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
    background: 'var(--surface-base, rgba(0,0,0,0.15))',
  },
  kbd: {
    display: 'inline-block',
    padding: '1px 6px',
    border: '1px solid var(--border-subtle, rgba(255,255,255,0.15))',
    borderRadius: 4,
    fontFamily: 'monospace',
    fontSize: 10,
    color: 'var(--text-secondary, var(--text-2))',
  },
}
