/**
 * StoryMonitor — Story v2 phase 3 (live render progress over the cue sheet).
 *
 * F1 scaffold: confirms the render started + links to History. F4 fleshes this
 * out into the live "AI Story Director" console + per-cue monitor (WS stream +
 * /jobs/{id}/story-plan polling fallback). Uses the Studio BASE (F0) only.
 */
import { StudioCard } from '../../components/studio'

export function StoryMonitor({ vi, jobId, onDone, onNew }: {
  vi: boolean
  jobId: string | null
  onDone: () => void
  onNew: () => void
}) {
  return (
    <>
      <StudioCard icon="🎥" title={vi ? 'Đang render' : 'Rendering'}>
        <p className="st-muted">
          {jobId
            ? (vi ? 'Đã bắt đầu render. Màn hình live (console AI + tiến độ theo cue) sẽ có ở F4.'
                  : 'Render started. The live console (AI + per-cue progress) lands in F4.')
            : (vi ? 'Chưa có job.' : 'No job yet.')}
        </p>
        {jobId && <code className="st-code">job: {jobId}</code>}
      </StudioCard>

      <div className="st-actions st-actions--split">
        <button type="button" className="st-btn" onClick={onNew}>
          {vi ? '+ Truyện mới' : '+ New story'}
        </button>
        <button type="button" className="st-btn st-btn--primary" onClick={onDone}>
          {vi ? 'Xem lịch sử ›' : 'Open History ›'}
        </button>
      </div>
    </>
  )
}
