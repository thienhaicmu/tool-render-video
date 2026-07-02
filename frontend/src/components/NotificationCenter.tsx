/**
 * NotificationCenter — bell icon + dropdown listing the 50 most recent
 * notifications (S4.7). Persists via uiStore.notificationHistory which
 * is backed by localStorage so a tab reload doesn't blank the list.
 *
 * Unread badge on the bell, mark-as-read on hover into a row, "mark all
 * read" + "clear" actions in the dropdown header. The bell is meant to
 * live in the topbar — both AppShell.Topbar and ClipStudio.cs-topbar
 * mount it.
 */
import { useState, useRef, useEffect } from 'react'
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
  const wrapperRef = useRef<HTMLDivElement>(null)

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

  // Close on outside click.
  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (!wrapperRef.current) return
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div ref={wrapperRef} style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        onClick={() => setOpen((p) => !p)}
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

      {open && (
        <div style={{
          position: 'absolute', top: 32, right: 0,
          width: 320, maxHeight: 420,
          background: 'var(--surface-panel, #1d1f23)',
          border: '1px solid var(--border-subtle, rgba(255,255,255,.08))',
          borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,.4)',
          display: 'flex', flexDirection: 'column',
          zIndex: 1500,
        }}>
          <div style={{
            padding: '10px 12px',
            borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,.08))',
            display: 'flex', alignItems: 'center', gap: 8,
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

          <div style={{ overflowY: 'auto', flex: 1 }}>
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
        </div>
      )}
    </div>
  )
}
