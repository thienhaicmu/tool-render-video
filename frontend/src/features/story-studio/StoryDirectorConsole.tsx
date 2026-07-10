/**
 * StoryDirectorConsole — the "AI Story Director" planning overlay (F4a).
 *
 * Shown while the ONE super plan call runs (planStory). The call is synchronous
 * (no server progress stream for planning), so — like Content's AiDirectorConsole
 * — this steps through the REAL dependency order on a timer and HOLDS the last
 * step until the parent unmounts it (no fake %). Mode B (idea) prepends an
 * authoring step. Studio BASE tokens only.
 */
import { useEffect, useState } from 'react'
import type { StorySource } from './types'

export function StoryDirectorConsole({ vi, source }: { vi: boolean; source: StorySource }) {
  const steps = (source === 'idea'
    ? (vi ? ['Sáng tác truyện từ ý tưởng', 'Đọc & hiểu truyện', 'Định nghĩa nhân vật', 'Dựng bối cảnh', 'Thiết kế key-visual', 'Viết timeline']
          : ['Authoring the story', 'Reading & understanding', 'Defining characters', 'Building settings', 'Designing key visuals', 'Writing the timeline'])
    : (vi ? ['Đọc & hiểu truyện', 'Định nghĩa nhân vật', 'Dựng bối cảnh', 'Thiết kế key-visual', 'Viết timeline']
          : ['Reading & understanding', 'Defining characters', 'Building settings', 'Designing key visuals', 'Writing the timeline']))

  const [at, setAt] = useState(0)
  useEffect(() => {
    setAt(0)
    // Advance through the steps and HOLD on the last one (the call may still be
    // running) — honest: we never claim "done" here, the parent unmounts us.
    const t = setInterval(() => setAt((i) => Math.min(i + 1, steps.length - 1)), 1200)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source])

  return (
    <div className="st-console-backdrop" role="status" aria-live="polite">
      <div className="st-console">
        <div className="st-console-hd">
          <span className="st-console-spin" aria-hidden />
          <span className="st-console-title">{vi ? 'AI Story Director đang dựng kế hoạch…' : 'AI Story Director is planning…'}</span>
        </div>
        <ol className="st-console-steps">
          {steps.map((s, i) => {
            const state = i < at ? 'done' : i === at ? 'active' : 'todo'
            return (
              <li key={s} className={`st-console-step is-${state}`}>
                <span className="st-console-dot">{i < at ? '✓' : i + 1}</span>
                <span>{s}</span>
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}
