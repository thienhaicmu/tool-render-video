/**
 * ContentStudio — dedicated Content Studio workflow (render_format="content").
 *
 * A SEPARATE studio from clip-studio's source-video-centric RenderWorkflow.
 * Three phases (the spec's mandatory flow):
 *
 *   script  — paste/import a script + config → "Generate Content Plan"
 *             (POST /api/content/plan; AI Director, no render)
 *   review  — MANDATORY: edit narration / emotion / duration / prompt, add /
 *             delete / reorder scenes → "Approve & Render"
 *             (submitRender with content_plan_override = the edited plan)
 *   monitor — live progress via useRenderSocket (stage, per-scene, terminal)
 *
 * Reuses shared building blocks (renderStore.submitRender, useRenderSocket,
 * RATIO_INFO, i18n, theme CSS vars). The render runs on the SHARED engine — no
 * pipeline duplication.
 *
 * CM-9 (2026-07-07): this file is now the thin orchestrator (state + routing).
 * The phases moved to sibling files: ScriptPhase.tsx, ReviewPhase.tsx (+ SceneRow),
 * ContentMonitor.tsx; shared bits in shared.tsx; types/constants in types.ts.
 * Structure + logic are unchanged from the former single file.
 */
import { useEffect, useRef, useState } from 'react'
import './ContentStudio.css'
import type { RenderRequest } from '@/types/api'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useUIStore } from '../../stores/uiStore'
import { RATIO_INFO } from '../clip-studio/render/constants'
import {
  generateContentPlan, createProject, saveProject, getProject, listProjects, getVisualProviders,
  type ContentPlan, type ContentProjectSummary, type DurationFit, type VisualProviderInfo,
} from '../../api/content'
import { getDefaultOutputDir } from '../../api/outputDir'
import { DEFAULT_CFG, type Config, type Phase } from './types'
import { usePlanHistory } from './usePlanHistory'
import { ScriptPhase } from './ScriptPhase'
import { ReviewPhase } from './ReviewPhase'
import { ContentMonitor } from './ContentMonitor'

export function ContentStudio() {
  const { lang } = useI18n()
  const vi = lang === 'vi'
  const { submitRender } = useRenderStore()

  const [phase, setPhase] = useState<Phase>('script')
  const [script, setScript] = useState('')
  const [cfg, setCfg] = useState<Config>(DEFAULT_CFG)
  // CM-10: plan edits go through an undo/redo command stack. setPlan records an
  // undoable edit; resetPlan installs a NEW plan (generate / draft / new) and
  // clears history so undo can't cross into a different plan.
  const { plan, setPlan, resetPlan, undo, redo, canUndo, canRedo } = usePlanHistory()
  const [durationFit, setDurationFit] = useState<DurationFit | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // CU-1: draft persistence
  const [projectId, setProjectId] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<ContentProjectSummary[]>([])
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  // P3.1: which visual sources are usable (from server env keys) + guards so the
  // free-stock auto-pick fires at most once and never clobbers an opened draft.
  const [providerAvail, setProviderAvail] = useState<Record<string, VisualProviderInfo> | null>(null)
  const autoPickedRef = useRef(false)
  const loadedDraftRef = useRef(false)

  const setCfgKey = <K extends keyof Config>(k: K, v: Config[K]) => setCfg((p) => ({ ...p, [k]: v }))

  // Reattach an active content render when opened from the topbar badge / dock /
  // notification (openRenderMonitor routes content jobs here, not to Clip Studio).
  const contentMonitorJobId = useUIStore((s) => s.contentMonitorJobId)
  const setContentMonitorJobId = useUIStore((s) => s.setContentMonitorJobId)
  useEffect(() => {
    if (!contentMonitorJobId) return
    setJobId(contentMonitorJobId)   // renders <ContentMonitor> for this job
    setContentMonitorJobId(null)
  }, [contentMonitorJobId, setContentMonitorJobId])

  // Load recent drafts once.
  useEffect(() => {
    void listProjects().then((r) => setDrafts(r.projects)).catch(() => {})
  }, [])

  // Prefill the output folder from the saved default (Settings → Output) so a
  // render never silently lands in a relative "output" dir (BUG-3). Only fills
  // when the field is still empty — never clobbers a user/draft choice.
  useEffect(() => {
    void getDefaultOutputDir()
      .then((r) => {
        if (r.is_configured && r.path) setCfg((p) => (p.outputDir ? p : { ...p, outputDir: r.path! }))
      })
      .catch(() => {})
  }, [])

  // P3.1: learn which visual sources are usable (server env keys).
  useEffect(() => {
    void getVisualProviders().then((r) => setProviderAvail(r.providers)).catch(() => {})
  }, [])

  // P3.1: when a free Pexels/Pixabay key is present, auto-select the stock
  // provider so content videos get real footage instead of a solid colour — but
  // only on a fresh session (not after opening a draft, and never overriding a
  // choice the user already made). Fires at most once.
  useEffect(() => {
    if (autoPickedRef.current || loadedDraftRef.current || !providerAvail) return
    if (providerAvail.stock?.available && cfg.visualProvider === 'local') {
      autoPickedRef.current = true
      setCfgKey('visualProvider', 'stock')
    }
  }, [providerAvail, cfg.visualProvider])

  // Autosave (debounced) whenever the script/config/plan changes and there is
  // something worth keeping. Creates the project lazily on first save.
  useEffect(() => {
    if (!plan && !script.trim()) return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      // Draft config is machine-independent — the output folder is a per-machine
      // path (BUG-8), so exclude it (mirrors clip-studio's preset behaviour).
      const { outputDir: _omit, ...cfgNoOut } = cfg
      const body = {
        title: (plan?.topic || script.trim().slice(0, 48) || 'Untitled'),
        script, plan: plan || undefined,
        config: cfgNoOut as unknown as Record<string, unknown>,
        status: (jobId ? 'rendered' : 'draft') as 'draft' | 'rendered',
        last_job_id: jobId || '',
      }
      const p = projectId
        ? saveProject(projectId, body)
        : createProject(body).then(({ id }) => { setProjectId(id) })
      void p.catch(() => {})
    }, 1200)
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current) }
  }, [script, cfg, plan, jobId, projectId])

  async function openDraft(id: string) {
    loadedDraftRef.current = true   // a draft carries its own visual source — no auto-pick
    try {
      const p = await getProject(id)
      setScript(p.script || '')
      // Keep the current (prefilled/chosen) output folder — drafts don't store it.
      if (p.config) setCfg((cur) => ({ ...DEFAULT_CFG, ...(p.config as Partial<Config>), outputDir: cur.outputDir }))
      setProjectId(p.id)
      if (p.plan && p.plan.scenes?.length) { resetPlan(p.plan); setPhase('review') }
      else { resetPlan(null); setPhase('script') }
      setError(null)
    } catch {
      setError(vi ? 'Không mở được bản nháp.' : 'Could not open draft.')
    }
  }

  function buildPayload(planOverride: ContentPlan): RenderRequest {
    const bgValue = cfg.bgKind === 'color' ? cfg.bgColor : cfg.bgAssetPath.trim()
    // Reindex densely so per-scene temp files never collide after edits.
    const reindexed: ContentPlan = {
      ...planOverride,
      scenes: planOverride.scenes.map((s, i) => ({ ...s, index: i })),
    }
    return {
      source_mode: 'local',
      source_video_path: '',
      render_format: 'content',
      content_script: script.trim(),
      content_plan_override: JSON.stringify(reindexed),
      content_background_kind: cfg.bgKind,
      content_background_value: bgValue,
      content_visual_provider: cfg.visualProvider,
      // Only send the Imagen tier when AI images are actually selected; '' lets
      // the backend fall back to its env/standard default.
      content_imagen_tier: cfg.visualProvider === 'ai_image' ? cfg.imagenTier : undefined,
      // P4.1: paid-visual budget cap (0 = unlimited → omit so the backend uses its env default).
      content_ai_budget: cfg.aiBudget > 0 ? cfg.aiBudget : undefined,
      // Send the chosen folder as-is. Empty → backend uses the saved default or
      // returns a clear 400 (no silent relative "output" dir anymore, BUG-3).
      output_dir: cfg.outputDir.trim(),
      aspect_ratio: RATIO_INFO[cfg.ratio].api,
      target_duration: cfg.targetDuration,
      add_subtitle: cfg.subEnabled,
      subtitle_style: cfg.subStyle,
      // Word-by-word (Whisper-aligned) subtitles are opt-in — off = faster
      // sentence-level subtitles (no per-scene Whisper pass).
      highlight_per_word: cfg.subEnabled && cfg.wordByWord ? true : undefined,
      content_bgm_path: cfg.bgmPath.trim() || undefined,
      voice_language: cfg.voiceLang,
      voice_gender: cfg.voiceGender,
      tts_engine: cfg.ttsEngine,
      ai_provider: 'gemini',
    }
  }

  async function handleGeneratePlan() {
    if (!script.trim() || busy) return
    setError(null)
    setBusy(true)
    try {
      const { plan: p, duration_fit } = await generateContentPlan({
        script: script.trim(),
        target_duration: cfg.targetDuration,
        voice_language: cfg.voiceLang,
        tone: cfg.tone || undefined,
      })
      if (!p?.scenes?.length) {
        setError(vi ? 'AI không tạo được kế hoạch. Kiểm tra API key / thử lại.' : 'AI produced no plan. Check API key / retry.')
      } else {
        resetPlan(p)
        setDurationFit(duration_fit ?? null)
        setPhase('review')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleApproveRender() {
    if (!plan || busy) return
    setError(null)
    setBusy(true)
    try {
      if (!cfg.outputDir.trim()) {
        setError(vi ? 'Chưa chọn thư mục lưu video.' : 'Pick a save folder first.')
        setBusy(false)
        return
      }
      if (cfg.bgKind !== 'color' && !cfg.bgAssetPath.trim()) {
        setError(vi ? 'Chưa chọn ảnh/video nền.' : 'Pick a background image/video.')
        setBusy(false)
        return
      }
      // When available (Electron), confirm the folder exists before a long render.
      const exists = await window.electronAPI?.pathExists?.(cfg.outputDir.trim())
      if (exists === false) {
        setError(vi ? `Thư mục lưu không tồn tại: ${cfg.outputDir.trim()}` : `Save folder does not exist: ${cfg.outputDir.trim()}`)
        setBusy(false)
        return
      }
      const id = await submitRender(buildPayload(plan))
      setJobId(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (jobId) {
    return <ContentMonitor jobId={jobId} vi={vi} plan={plan} voiceLang={cfg.voiceLang} onNew={() => {
      setJobId(null); resetPlan(null); setDurationFit(null); setPhase('script'); setError(null)
      setProjectId(null); setScript('')
      void listProjects().then((r) => setDrafts(r.projects)).catch(() => {})
    }} />
  }
  if (phase === 'review' && plan) {
    return (
      <ReviewPhase
        vi={vi} plan={plan} setPlan={setPlan} busy={busy} error={error}
        durationFit={durationFit} visualProvider={cfg.visualProvider} targetDuration={cfg.targetDuration}
        aspectApi={RATIO_INFO[cfg.ratio].api} imagenTier={cfg.imagenTier}
        voice={{ lang: cfg.voiceLang, gender: cfg.voiceGender, engine: cfg.ttsEngine }}
        onBack={() => setPhase('script')} onApprove={handleApproveRender}
        undo={undo} redo={redo} canUndo={canUndo} canRedo={canRedo}
      />
    )
  }
  return (
    <ScriptPhase
      vi={vi} script={script} setScript={setScript} cfg={cfg} setCfgKey={setCfgKey}
      busy={busy} error={error} onGenerate={handleGeneratePlan}
      drafts={drafts} onOpenDraft={openDraft} providerAvail={providerAvail}
    />
  )
}
