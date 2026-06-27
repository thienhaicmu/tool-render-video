/**
 * InterruptedJobsBanner — Pha 5B.
 *
 * After a server/app restart, jobs left running/queued are marked
 * 'interrupted' (manager.recover_pending_render_jobs). Previously the user
 * had to Resume each one individually from History. This banner surfaces them
 * on the main surface and offers a one-click "Resume all".
 *
 * FE-only — loops the existing `resumeRender` endpoint. Dismissable for the
 * session; re-reads the shared jobs poll so it disappears once resumed.
 */
import { useState, type CSSProperties } from 'react'
import { useActiveJobs } from '../../stores/jobsStore'
import { useUIStore } from '../../stores/uiStore'
import { useI18n } from '../../i18n/useI18n'
import { resumeRender } from '../../api/render'

export function InterruptedJobsBanner() {
  const { items, refresh } = useActiveJobs()
  const { t } = useI18n()
  const addNotification = useUIStore((s) => s.addNotification)
  const [dismissed, setDismissed] = useState(false)
  const [busy, setBusy] = useState(false)

  const interrupted = items.filter((j) => j.kind === 'render' && j.status === 'interrupted')
  if (dismissed || interrupted.length === 0) return null

  async function resumeAll() {
    setBusy(true)
    let ok = 0
    let fail = 0
    for (const j of interrupted) {
      try {
        await resumeRender(j.job_id)
        ok++
      } catch {
        fail++
      }
    }
    addNotification({
      type: fail > 0 ? 'warning' : 'success',
      title: t('resume_all_done'),
      message: fail > 0 ? `${ok}/${interrupted.length}` : undefined,
    })
    setDismissed(true)
    setBusy(false)
    void refresh()
  }

  return (
    <div style={styles.banner} role="status">
      <span style={{ fontSize: 14 }}>⏯</span>
      <span style={{ fontWeight: 600 }}>
        {interrupted.length} {t('interrupted_jobs')}
      </span>
      <span style={{ flex: 1 }} />
      <button style={styles.primary} disabled={busy} onClick={resumeAll}>
        {busy ? '…' : t('resume_all')}
      </button>
      <button style={styles.dismiss} disabled={busy} onClick={() => setDismissed(true)}>
        {t('banner_dismiss')}
      </button>
    </div>
  )
}

const styles: Record<string, CSSProperties> = {
  banner: {
    display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    padding: '8px 16px', flexShrink: 0, fontSize: 12,
    background: 'rgba(234,179,8,.14)',
    borderBottom: '1px solid rgba(234,179,8,.3)',
    color: 'var(--status-warning, #b45309)',
  },
  primary: {
    padding: '4px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700,
    border: '1px solid var(--accent-primary)', background: 'var(--accent-primary)',
    color: '#fff', cursor: 'pointer',
  },
  dismiss: {
    padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
    border: '1px solid var(--border-default)', background: 'transparent',
    color: 'var(--text-secondary)', cursor: 'pointer',
  },
}
