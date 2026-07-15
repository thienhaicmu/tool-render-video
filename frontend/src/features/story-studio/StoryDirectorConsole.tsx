import type { StoryPlanningTrace } from '../../api/story'
import type { StorySource } from './types'

type Props = {
  vi: boolean
  source: StorySource
  progress: StoryPlanningTrace | null
}

const stageGroup = (stage = '') => {
  if (stage.startsWith('understanding')) return 'understanding'
  if (stage.startsWith('writer')) return 'writer'
  if (stage.startsWith('structure')) return 'structure'
  if (stage.startsWith('legacy')) return 'legacy'
  return stage
}

export function StoryDirectorConsole({ vi, source, progress }: Props) {
  const labels: Record<string, string> = vi
    ? {
        understanding: 'Đọc và kiểm chứng dữ kiện',
        writer: 'Sáng tác kịch bản lời kể',
        structure: 'Dựng kế hoạch sản xuất',
        legacy: 'Dựng kế hoạch dự phòng',
      }
    : {
        understanding: 'Read and verify source facts',
        writer: 'Write the narration script',
        structure: 'Build the production plan',
        legacy: 'Build the fallback plan',
      }

  const stages = source === 'idea'
    ? ['writer', 'structure']
    : ['understanding', 'writer', 'structure']
  const active = stageGroup(progress?.phase)
  if ((progress?.compiler_fallback || active === 'legacy') && !stages.includes('legacy')) {
    stages.push('legacy')
  }
  const completed = new Set(
    (progress?.events || [])
      .filter((event) => event.event === 'call_completed' && event.status === 'success')
      .map((event) => stageGroup(event.stage)),
  )
  const routes = Object.entries(progress?.role_routes ?? {})

  return (
    <div className="st-console-backdrop" role="status" aria-live="polite">
      <div className="st-console">
        <div className="st-console-hd">
          <span className="st-console-spin" aria-hidden />
          <span className="st-console-title">
            {progress?.message || (vi ? 'AI Story Director đang chuẩn bị...' : 'AI Story Director is preparing...')}
          </span>
        </div>
        <ol className="st-console-steps">
          {stages.map((stage, index) => {
            const state = active === stage ? 'active' : completed.has(stage) ? 'done' : 'todo'
            return (
              <li key={stage} className={`st-console-step is-${state}`}>
                <span className="st-console-dot">{state === 'done' ? '✓' : index + 1}</span>
                <span>{labels[stage]}</span>
              </li>
            )
          })}
        </ol>
        <div className="st-console-meta">
          {vi ? 'Lượt gọi AI thực tế' : 'Actual AI calls'}: {progress?.actual_llm_calls ?? 0}
        </div>
        {routes.length > 0 && (
          <div className="st-console-routes">
            {routes.map(([role, route]) => (
              <span key={role}>{role}: {route.provider || '?'} / {route.model || '?'}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
