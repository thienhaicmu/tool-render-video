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
import { useEffect, useRef, useState, type ReactNode } from 'react'
import './StoryStudio.css'
import type { RenderRequest } from '@/types/api'
import { StudioScreen, StudioStepper } from '../../components/studio'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useUIStore } from '../../stores/uiStore'
import { getDefaultOutputDir } from '../../api/outputDir'
import { planStory, type StoryPlanV2 } from '../../api/story'
import {
  listStoryProjects, saveStoryProject, getStoryProject, deleteStoryProject,
  type StoryProjectListItem,
} from '../../api/storyProjects'
import {
  DEFAULT_STORY_CFG, VOICE_LOCALE, type StoryConfig, type StoryPhase,
} from './types'
import { InputScreen } from './InputScreen'
import { PlanReview } from './PlanReview'
import { StoryMonitor } from './StoryMonitor'
import { StoryDirectorConsole } from './StoryDirectorConsole'
import { ProjectBar, type SaveTag } from './ProjectBar'

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
  const [notice, setNotice] = useState<string | null>(null)

  // SP2 — project persistence (save / autosave / open / delete).
  const [projectId, setProjectId] = useState('')
  const [projectName, setProjectName] = useState('')
  const [projects, setProjects] = useState<StoryProjectListItem[]>([])
  const [saveTag, setSaveTag] = useState<SaveTag>('idle')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const skipAutosave = useRef(false)   // set while opening/new so we don't re-save the loaded state

  // SP3 — undo/redo for PLAN edits (Review). Undo/redo call setPlan directly, so they
  // never re-record; only edits routed through recordPlan push history.
  const hist = useRef<{ past: (StoryPlanV2 | null)[]; future: (StoryPlanV2 | null)[] }>({ past: [], future: [] })
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const resetHistory = () => { hist.current = { past: [], future: [] }; setCanUndo(false); setCanRedo(false) }

  const setKey = <K extends keyof StoryConfig>(k: K, v: StoryConfig[K]) =>
    setCfg((c) => ({ ...c, [k]: v }))
  const hasPicker = typeof window !== 'undefined' && !!window.electronAPI?.pickDirectory
  const hasVideoPicker = typeof window !== 'undefined' && !!window.electronAPI?.pickVideoFile

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

  async function pickBaseVideo() {
    const f = await window.electronAPI?.pickVideoFile?.()
    if (f) setKey('baseVideoPath', f)
  }

  // ── SP2: project list + autosave + open/new/delete ──────────────────────────
  const refreshProjects = () => void listStoryProjects().then((r) => setProjects(r.projects || [])).catch(() => {})
  useEffect(() => { refreshProjects() }, [])

  const hasContent = !!(cfg.chapterText.trim() || cfg.idea.trim() || plan)
  useEffect(() => {
    if (skipAutosave.current) { skipAutosave.current = false; return }
    if (!hasContent || phase === 'monitor') return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    setSaveTag('saving')
    saveTimer.current = setTimeout(() => {
      void saveStoryProject({
        id: projectId || undefined,
        name: projectName || (cfg.source === 'idea' ? cfg.idea : cfg.chapterText).trim().slice(0, 40),
        language: cfg.language, source: cfg.source,
        config: cfg as unknown as Record<string, unknown>,
        plan: plan ?? null, status: plan ? 'ready' : 'draft',
      }).then((r) => {
        if (!projectId) setProjectId(r.id)
        setSaveTag('saved'); refreshProjects()
      }).catch(() => setSaveTag('idle'))
    }, 1500)
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg, plan, projectName])

  async function openProject(id: string) {
    try {
      const p = await getStoryProject(id)
      skipAutosave.current = true
      setCfg({ ...DEFAULT_STORY_CFG, ...(p.config as Partial<StoryConfig>) })
      setPlan((p.plan as StoryPlanV2 | null) ?? null)
      setProjectId(p.id); setProjectName(p.name || ''); resetHistory()
      setError(null); setNotice(null); setJobId(null); setEstTotal(0)
      setPhase(p.plan ? 'review' : 'input'); setSaveTag('saved')
    } catch (e) { fail(e) }
  }

  function newProject() {
    skipAutosave.current = true
    setCfg(DEFAULT_STORY_CFG); setPlan(null); setProjectId(''); setProjectName(''); resetHistory()
    setJobId(null); setError(null); setNotice(null); setEstTotal(0); setSaveTag('idle'); setPhase('input')
  }

  async function removeProject(id: string) {
    try {
      await deleteStoryProject(id)
      if (id === projectId) newProject()
      refreshProjects()
    } catch (e) { fail(e) }
  }

  // Route Review plan edits through here so each edit is undoable (caps at 40 steps).
  function recordPlan(next: StoryPlanV2) {
    hist.current.past.push(plan)
    if (hist.current.past.length > 40) hist.current.past.shift()
    hist.current.future = []
    setCanUndo(true); setCanRedo(false)
    setPlan(next)
  }
  function undoPlan() {
    if (!hist.current.past.length) return
    hist.current.future.unshift(plan)
    const prev = hist.current.past.pop() ?? null
    setPlan(prev)
    setCanUndo(hist.current.past.length > 0); setCanRedo(true)
  }
  function redoPlan() {
    if (!hist.current.future.length) return
    hist.current.past.push(plan)
    const nxt = hist.current.future.shift() ?? null
    setPlan(nxt)
    setCanUndo(true); setCanRedo(hist.current.future.length > 0)
  }

  // Duplicate the current session into a NEW saved project (FE-only clone).
  async function duplicateProject() {
    try {
      const copyName = (projectName || (vi ? 'Truyện' : 'Story')) + (vi ? ' (bản sao)' : ' (copy)')
      const r = await saveStoryProject({
        name: copyName, language: cfg.language, source: cfg.source,
        config: cfg as unknown as Record<string, unknown>,
        plan: plan ?? null, status: plan ? 'ready' : 'draft',
      })
      skipAutosave.current = true
      setProjectId(r.id); setProjectName(copyName); refreshProjects()
    } catch (e) { fail(e) }
  }

  function fail(e: unknown) { setError(e instanceof Error ? e.message : String(e)) }

  const inputReady = cfg.source === 'paste' ? !!cfg.chapterText.trim() : !!cfg.idea.trim()

  async function onGenerate() {
    if (!inputReady || busy) return
    setBusy(true); setError(null); setNotice(null)
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
        setPlan(r.plan); resetHistory()
        setEstTotal(r.estimated_total_sec || 0)
        if (r.source_truncated) {
          const n = (r.source_chars ?? 0).toLocaleString()
          const lim = (r.source_char_limit ?? 0).toLocaleString()
          setNotice(vi
            ? `Nguồn dài ${n} ký tự — chỉ ${lim} ký tự đầu được dùng, phần cuối bị lược. Cân nhắc tách chương để không mất nội dung.`
            : `Source is ${n} chars — only the first ${lim} were used; the tail was cut. Consider splitting the chapter so no content is lost.`)
        }
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
      story_image_provider: cfg.imageProvider,
      story_base_video_path: cfg.baseVideoPath,
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
    setPlan(null); setJobId(null); setError(null); setNotice(null); setEstTotal(0); setPhase('input')
  }

  const steps = vi ? ['Nhập truyện', 'Duyệt kế hoạch', 'Render'] : ['Input', 'Review', 'Render']

  return (
    <StoryStudioShell vi={vi} step={STEP[phase]} steps={steps}>
      {phase !== 'monitor' && (
        <ProjectBar
          vi={vi} name={projectName} saveTag={saveTag} projects={projects}
          canUndo={canUndo && phase === 'review'} canRedo={canRedo && phase === 'review'}
          onUndo={undoPlan} onRedo={redoPlan} onDuplicate={duplicateProject}
          onName={setProjectName} onOpen={openProject} onNew={newProject}
          onDelete={removeProject} onRefresh={refreshProjects}
        />
      )}
      {error && <div className="st-alert st-alert--fail" role="alert">{error}</div>}
      {notice && <div className="st-alert st-alert--warn" role="status">{notice}</div>}
      {busy && phase === 'input' && <StoryDirectorConsole vi={vi} source={cfg.source} />}
      {phase === 'input' && (
        <InputScreen
          vi={vi} cfg={cfg} setKey={setKey} busy={busy} ready={inputReady}
          hasPicker={hasPicker} pickOutputDir={pickOutputDir} onGenerate={onGenerate}
          hasVideoPicker={hasVideoPicker} pickBaseVideo={pickBaseVideo}
        />
      )}
      {phase === 'review' && plan && (
        <PlanReview
          vi={vi} plan={plan} setPlan={recordPlan} estTotal={estTotal} busy={busy}
          artStyle={cfg.artStyle} aspect={cfg.aspect} language={cfg.language}
          imageProvider={cfg.imageProvider} onImageProvider={(p) => setKey('imageProvider', p)}
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
