/**
 * openRenderMonitor — route an active render job to the RIGHT studio's monitor.
 *
 * A content-mode render (render_format="content") must open in the Content
 * Studio, NOT the Clip Studio. Before this helper, every active-job entry point
 * (topbar badge, active-jobs dock, notifications, command palette) routed all
 * `kind==='render'` jobs to the Clip Studio monitor — so a content render showed
 * up inside the clip render workflow ("why did it jump to Studio?").
 *
 * Accepts either the job object (which carries render_format) or just a job_id
 * (looked up in the jobs store). Falls back to 'clips' when the format is
 * unknown, preserving the previous clip-studio behaviour for clip/recap jobs.
 */
import { useUIStore } from '../stores/uiStore'
import { useJobsStore } from '../stores/jobsStore'

type JobLike = { job_id: string; render_format?: string }

export function openRenderMonitor(jobOrId: string | JobLike): void {
  const ui = useUIStore.getState()
  const jobId = typeof jobOrId === 'string' ? jobOrId : jobOrId.job_id
  let rf: string | undefined = typeof jobOrId === 'string' ? undefined : jobOrId.render_format
  if (!rf) {
    const found = useJobsStore.getState().items.find((j) => j.job_id === jobId) as JobLike | undefined
    rf = found?.render_format
  }
  if ((rf || 'clips') === 'content') {
    ui.setContentMonitorJobId(jobId)
    ui.setActivePanel('content-studio')
  } else {
    ui.setMonitorJobId(jobId)
    ui.setActivePanel('clip-studio')
  }
}
