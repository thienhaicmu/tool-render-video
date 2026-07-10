/**
 * StoryStudio — Story-to-Video v2 workflow (render_format="story").
 *
 * Thin orchestrator over three phases (screens live in sibling files):
 *   input    — source A (paste chapter) / B (idea) + minimal config → "Generate"
 *              (POST /api/story/plan → one super plan call)
 *   review   — review/edit the StoryPlan v2 (characters · key-visuals · timeline)
 *              → "Render" (submitRender with story_plan_override = the edited plan)
 *   monitor  — live render progress (cue sheet)
 *
 * Uses the mode-agnostic Studio BASE (components/studio, F0). Imports NOTHING
 * from content-studio (each studio owns its screens; the base is shared).
 * F1 scaffolds the shell + state; F2/F3/F4 flesh out the three screens.
 */
import { useEffect, useState, type ReactNode } from 'react'
import './StoryStudio.css'
import type { RenderRequest } from '@/types/api'
import { StudioScreen, StudioStepper } from '../../components/studio'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useUIStore } from '../../stores/uiStore'
import { getDefaultOutputDir } from '../../api/outputDir'
import { planStory, type StoryPlanV2 } from '../../api/story'
import {
  DEFAULT_STORY_CFG, VOICE_LOCALE, type StoryConfig, type StoryPhase,
} from './types'
import { InputScreen } from './InputScreen'
import { PlanReview } from './PlanReview'
import { StoryMonitor } from './StoryMonitor'
import { StoryDirectorConsole } from './StoryDirectorConsole'

const STEP: Record<StoryPhase, number> = { input: 1, review: 2, monitor: 3 }

export function StoryStudio() {
  const { lang } = useI18n()
  const vi = lang === 'vi'
  const { submitRender } = useRenderStore()
  const setActivePanel = useUIStore((s) => s.setActivePanel)

  const [phase, setPhase] = useState<StoryPhase>('input')
  const [cfg, setCfg] = useState<StoryConfig>(DEFAULT_STORY_CFG)
  const [plan, setPlan] = useState<StoryPlanV2 | null>(null)
  const [estTotal, setEstTotal] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setKey = <K extends keyof StoryConfig>(k: K, v: StoryConfig[K]) =>
    setCfg((c) => ({ ...c, [k]: v }))
  const hasPicker = typeof window !== 'undefined' && !!window.electronAPI?.pickDirectory

  // Prefill the save folder from the saved default (never clobber a user choice).
  useEffect(() => {
    void getDefaultOutputDir()
      .then((r) => { if (r.is_configured && r.path) setCfg((c) => (c.outputDir ? c : { ...c, outputDir: r.path! })) })
      .catch(() => {})
  }, [])

  async function pickOutputDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setKey('outputDir', dir)
  }

  function fail(e: unknown) { setError(e instanceof Error ? e.message : String(e)) }

  const inputReady = cfg.source === 'paste' ? !!cfg.chapterText.trim() : !!cfg.idea.trim()

  async function onGenerate() {
    if (!inputReady || busy) return
    setBusy(true); setError(null)
    try {
      const r = await planStory({
        source: cfg.source,
        chapter_text: cfg.source === 'paste' ? cfg.chapterText.trim() : undefined,
        idea: cfg.source === 'idea' ? cfg.idea.trim() : undefined,
        duration_sec: cfg.source === 'idea' ? cfg.durationSec : undefined,
        genre: cfg.genre || undefined,
        language: cfg.language,
        art_style: cfg.artStyle || undefined,
        aspect_ratio: cfg.aspect,
        subtitle_mode: cfg.subtitles ? 'hook_only' : 'off',
        series_id: cfg.seriesId || undefined,
        chapter_no: cfg.chapterNo || undefined,
      })
      if (!r.plan?.timeline?.length) {
        setError(vi ? 'AI không dựng được kế hoạch. Kiểm tra API key / thử lại.'
                    : 'AI produced no plan. Check API key / retry.')
      } else {
        setPlan(r.plan)
        setEstTotal(r.estimated_total_sec || 0)
        setPhase('review')
      }
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  function buildPayload(p: StoryPlanV2): RenderRequest {
    return {
      render_format: 'story',
      story_source: cfg.source,
      content_script: cfg.source === 'paste' ? cfg.chapterText.trim() : '',
      story_idea: cfg.source === 'idea' ? cfg.idea.trim() : '',
      story_duration_sec: cfg.source === 'idea' ? cfg.durationSec : 0,
      story_genre: cfg.genre,
      story_art_style: cfg.artStyle,
      story_series_id: cfg.seriesId,
      story_chapter_no: cfg.chapterNo,
      story_plan_override: JSON.stringify(p),
      voice_language: VOICE_LOCALE[cfg.language],
      aspect_ratio: cfg.aspect,
      add_subtitle: cfg.subtitles,
      output_dir: cfg.outputDir,
    } as RenderRequest
  }

  async function onRender() {
    if (!plan || busy) return
    setBusy(true); setError(null)
    try {
      const id = await submitRender(buildPayload(plan))
      setJobId(id)
      setPhase('monitor')
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  function reset() {
    setPlan(null); setJobId(null); setError(null); setEstTotal(0); setPhase('input')
  }

  const steps = vi ? ['Nhập truyện', 'Duyệt kế hoạch', 'Render'] : ['Input', 'Review', 'Render']

  return (
    <StoryStudioShell vi={vi} step={STEP[phase]} steps={steps}>
      {error && <div className="st-alert st-alert--fail" role="alert">{error}</div>}
      {busy && phase === 'input' && <StoryDirectorConsole vi={vi} source={cfg.source} />}
      {phase === 'input' && (
        <InputScreen
          vi={vi} cfg={cfg} setKey={setKey} busy={busy} ready={inputReady}
          hasPicker={hasPicker} pickOutputDir={pickOutputDir} onGenerate={onGenerate}
        />
      )}
      {phase === 'review' && plan && (
        <PlanReview
          vi={vi} plan={plan} setPlan={setPlan} estTotal={estTotal} busy={busy}
          artStyle={cfg.artStyle} aspect={cfg.aspect} language={cfg.language}
          onRender={onRender} onBack={reset}
        />
      )}
      {phase === 'monitor' && (
        <StoryMonitor
          vi={vi} jobId={jobId}
          onDone={() => setActivePanel('history')} onNew={reset}
        />
      )}
    </StoryStudioShell>
  )
}

function StoryStudioShell({ vi, step, steps, children }: {
  vi: boolean; step: number; steps: string[]; children: ReactNode
}) {
  return (
    <StudioScreen
      icon="📖"
      title={vi ? 'Story Studio' : 'Story Studio'}
      subtitle={vi ? 'Truyện → AI hiểu → hình ảnh nhất quán + lời kể → video'
                   : 'Chapter → AI → consistent images + narration → video'}
      stepper={<StudioStepper steps={steps} current={step} />}
    >
      {children}
    </StudioScreen>
  )
}
