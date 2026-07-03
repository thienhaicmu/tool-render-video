/**
 * NotificationCenter — bell icon + dropdown listing the 50 most recent
 * notifications (S4.7). Persists via uiStore.notificationHistory which
 * is backed by localStorage so a tab reload doesn't blank the list.
 *
 * Unread badge on the bell, mark-as-read on hover into a row, "mark all
 * read" + "clear" actions in the dropdown header. The bell lives in the
 * topbar.
 *
 * The dropdown is PORTALED to document.body and positioned fixed against
 * the bell (2026-07 bugfix): anchoring it inside the topbar trapped it in
 * the topbar's z-index:10 stacking context, so content decorations (e.g.
 * a screen's top gradient rule) painted over its header and clipped the
 * first row. A portal escapes that context entirely.
 */
import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useUIStore } from '../stores/uiStore'
import { useI18n } from '../i18n/useI18n'
import type { Lang } from '../i18n/translations'
import { confirmDialog } from './ui/ConfirmDialog'

function IconBell({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
    </svg>
  )
}

const TYPE_COLOR: Record<string, string> = {
  success: 'var(--color-success, #22c55e)',
  error:   'var(--color-error, #ef4444)',
  warning: 'var(--color-warning, #eab308)',
  info:    'var(--color-info, #3b82f6)',
}

// Pha 1.2 — lang-aware relative time. Minute unit differs (vi "p" for
// phút, en "m"); ``ago`` is the localized trailing word.
function formatRelative(ts: number, lang: Lang, ago: string): string {
  const diff = Date.now() - ts
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s ${ago}`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}${lang === 'vi' ? 'p' : 'm'} ${ago}`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ${ago}`
  const day = Math.floor(hr / 24)
  return `${day}d ${ago}`
}

export function NotificationCenter() {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(false)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const history                  = useUIStore((s) => s.notificationHistory)
  const markNotificationRead     = useUIStore((s) => s.markNotificationRead)
  const markAllNotificationsRead = useUIStore((s) => s.markAllNotificationsRead)
  const clearNotificationHistory = useUIStore((s) => s.clearNotificationHistory)
  const setMonitorJobId          = useUIStore((s) => s.setMonitorJobId)
  const setActivePanel           = useUIStore((s) => s.setActivePanel)

  // P1.4 — entries carrying a jobId deep-link to that job's surface.
  function openEntry(jobId: string, kind?: 'render' | 'download') {
    setOpen(false)
    if (kind === 'download') {
      setActivePanel('download')
      return
    }
    setMonitorJobId(jobId)
    setActivePanel('clip-studio')
  }

  const unreadCount = history.filter((n) => !n.read).length

  function toggle() {
    if (!open && btnRef.current) setRect(btnRef.current.getBoundingClientRect())
    setOpen((p) => !p)
  }

  // Close on outside click (bell + portaled menu both count as "inside").
  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      const target = e.target as Node
      if (btnRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      setOpen(false)
    }
    // Re-anchor / dismiss on viewport changes so the fixed menu never drifts.
    function onReflow() { setOpen(false) }
    document.addEventListener('mousedown', onClick)
    window.addEventListener('resize', onReflow)
    window.addEventListener('scroll', onReflow, true)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('resize', onReflow)
      window.removeEventListener('scroll', onReflow, true)
    }
  }, [open])

  const menu = open && rect ? createPortal(
    <div
      ref={menuRef}
      style={{
        position: 'fixed',
        top: rect.bottom + 6,
        right: Math.max(8, window.innerWidth - rect.right),
        width: 320,
        maxHeight: Math.min(420, window.innerHeight - rect.bottom - 24),
        background: 'var(--surface-panel, #1d1f23)',
        border: '1px solid var(--border-subtle, rgba(255,255,255,.08))',
        borderRadius: 8,
        boxShadow: '0 8px 24px rgba(0,0,0,.4)',
        display: 'flex', flexDirection: 'column',
        zIndex: 2000,
      }}
    >
      <div style={{
        padding: '10px 12px',
        borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,.08))',
        display: 'flex', alignItems: 'center', gap: 8,
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary, var(--text-1))', flex: 1 }}>
          {t('notif_title')}
          {unreadCount > 0 && (
            <span style={{ marginLeft: 6, color: 'var(--text-tertiary, var(--text-3))', fontWeight: 500 }}>
              ({unreadCount} {t('notif_unread_suffix')})
            </span>
          )}
        </span>
        {history.length > 0 && (
          <>
            <button
              onClick={markAllNotificationsRead}
              disabled={unreadCount === 0}
              style={{
                fontSize: 10, fontWeight: 600,
                padding: '3px 8px', borderRadius: 5,
                border: '1px solid var(--border)', background: 'transparent',
                color: unreadCount === 0 ? 'var(--text-tertiary)' : 'var(--text-secondary)',
                cursor: unreadCount === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              {t('notif_mark_all')}
            </button>
            <button
              onClick={async () => {
                const choice = await confirmDialog({
                  title: t('notif_clear_confirm'),
                  buttons: [
                    { id: 'clear', label: t('notif_clear'), variant: 'danger' },
                    { id: 'cancel', label: t('dock_cancel') },
                  ],
                })
                if (choice === 'clear') clearNotificationHistory()
              }}
              style={{
                fontSize: 10, fontWeight: 600,
                padding: '3px 8px', borderRadius: 5,
                border: '1px solid var(--border)', background: 'transparent',
                color: 'var(--text-secondary)', cursor: 'pointer',
              }}
            >
              {t('notif_clear')}
            </button>
          </>
        )}
      </div>

      <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
        {history.length === 0 ? (
          <div style={{ padding: '24px 16px', textAlign: 'center', fontSize: 11, color: 'var(--text-tertiary)' }}>
            {t('notif_empty')}
          </div>
        ) : (
          history.map((n) => {
            const color = TYPE_COLOR[n.type] || 'var(--text-2)'
            const clickable = !!n.jobId
            return (
              <div
                key={n.id}
                onMouseEnter={() => { if (!n.read) markNotificationRead(n.id) }}
                onClick={() => { if (n.jobId) openEntry(n.jobId, n.kind) }}
                title={clickable ? (n.kind === 'download' ? t('nav_download') : t('dock_open_detail')) : undefined}
                style={{
                  padding: '10px 12px',
                  borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,.05))',
                  display: 'grid',
                  gridTemplateColumns: '8px 1fr auto',
                  gap: 10,
                  background: n.read ? 'transparent' : 'rgba(var(--text-rgb, 255,255,255),.02)',
                  cursor: clickable ? 'pointer' : 'default',
                }}
              >
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  marginTop: 5,
                  background: n.read ? 'transparent' : color,
                }} />
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    fontSize: 11, fontWeight: 600,
                    color: 'var(--text-primary, var(--text-1))',
                    wordBreak: 'break-word',
                  }}>
                    {n.title}
                  </div>
                  {n.message && (
                    <div style={{
                      fontSize: 10,
                      color: 'var(--text-secondary, var(--text-2))',
                      marginTop: 2, wordBreak: 'break-word',
                    }}>
                      {n.message}
                    </div>
                  )}
                </div>
                <span style={{
                  fontSize: 9, color: 'var(--text-tertiary, var(--text-3))',
                  whiteSpace: 'nowrap',
                }}>
                  {formatRelative(n.created_at, lang, t('notif_ago'))}
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>,
    document.body,
  ) : null

  return (
    <div style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        ref={btnRef}
        onClick={toggle}
        title={t('notif_title')}
        aria-label={t('notif_title')}
        style={{
          position: 'relative',
          width: 28, height: 28,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: 'none', background: 'transparent',
          color: 'var(--text-secondary, var(--text-2))',
          cursor: 'pointer', borderRadius: 6,
        }}
      >
        <IconBell />
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute', top: 2, right: 2,
            minWidth: 14, height: 14, padding: '0 3px',
            background: 'var(--color-error, #ef4444)',
            color: '#fff', fontSize: 8, fontWeight: 700,
            borderRadius: 7, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            lineHeight: 1,
          }}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
      {menu}
    </div>
  )
}
