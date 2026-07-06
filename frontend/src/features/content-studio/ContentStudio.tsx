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
 * P0 redesign (2026-07-04): presentation moved to ContentStudio.css (tokens +
 * hover/focus/transitions + responsive) and shared Button/ProgressBar; the ad-hoc
 * inline `S` style object is gone. Structure + logic are unchanged.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import './ContentStudio.css'
import type { RenderRequest, JobPart } from '@/types/api'
import type { WsLogEvent } from '../../websocket/events'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useUIStore } from '../../stores/uiStore'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { Button } from '../../components/ui/Button'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { AIChip } from '../../components/ui/AIChip'
import { ConicRing } from '../../components/ui/ConicRing'
import { IconCheck } from '../../components/icons'
import { revealInFolder } from '../../lib/revealInFolder'
import { RATIO_INFO } from '../clip-studio/render/constants'
import type { Ratio } from '../clip-studio/render/types'
import {
  generateContentPlan, previewNarration, previewVisual, createProject, saveProject, getProject, listProjects,
  publishMeta, estimateContentCost, getVisualProviders,
  type ContentPlan, type ContentScene, type ContentProjectSummary,
  type PublishMeta, type DurationFit, type ContentEstimate, type VisualProviderInfo,
} from '../../api/content'
import { getDefaultOutputDir, putDefaultOutputDir } from '../../api/outputDir'
import { BASE_URL } from '../../api/client'

type BgKind = 'color' | 'image' | 'video'
type ImagenTier = 'fast' | 'standard' | 'ultra'
type Phase = 'script' | 'review'

const RATIOS: Ratio[] = ['r916', 'r11', 'r169']
const VOICE_LANGS = ['vi-VN', 'en-US', 'en-GB', 'ja-JP', 'ko-KR'] as const
const TTS_ENGINES = ['edge', 'xtts', 'gemini'] as const
// Real CapCut preset ids (ass_capcut.CAPCUT_PRESETS) + 'auto' = let the AI plan
// pick the style. Every option resolves to a distinct, valid style now (P1.1).
const SUB_STYLES = ['auto', 'opus_pop', 'capcut_box', 'punch_green', 'karaoke_clean', 'smooth_premiere'] as const
const EMOTIONS = ['normal', 'excited', 'calm', 'suspense', 'epic', 'sad', 'happy', 'curious', 'motivating', 'surprise'] as const

interface Config {
  ratio: Ratio
  targetDuration: number
  bgKind: BgKind
  bgColor: string
  bgAssetPath: string
  voiceLang: typeof VOICE_LANGS[number]
  voiceGender: 'female' | 'male'
  ttsEngine: typeof TTS_ENGINES[number]
  subEnabled: boolean
  subStyle: string
  wordByWord: boolean
  bgmPath: string
  visualProvider: 'local' | 'stock' | 'ai_image' | 'ai_video' | 'ai_image_free'
  imagenTier: ImagenTier
  aiBudget: number
  outputDir: string
  tone: string
}

const DEFAULT_CFG: Config = {
  ratio: 'r916', targetDuration: 90, bgKind: 'color', bgColor: '#101820', bgAssetPath: '',
  voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
  subEnabled: true, subStyle: 'auto', wordByWord: true,
  bgmPath: '', visualProvider: 'local', imagenTier: 'standard', aiBudget: 0, outputDir: '', tone: '',
}

export function ContentStudio() {
  const { lang } = useI18n()
  const vi = lang === 'vi'
  const { submitRender } = useRenderStore()

  const [phase, setPhase] = useState<Phase>('script')
  const [script, setScript] = useState('')
  const [cfg, setCfg] = useState<Config>(DEFAULT_CFG)
  const [plan, setPlan] = useState<ContentPlan | null>(null)
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
      if (p.plan && p.plan.scenes?.length) { setPlan(p.plan); setPhase('review') }
      else { setPlan(null); setPhase('script') }
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
        setPlan(p)
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
      setJobId(null); setPlan(null); setDurationFit(null); setPhase('script'); setError(null)
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

// ── Phase 1: script + config ────────────────────────────────────────────────

function ScriptPhase({ vi, script, setScript, cfg, setCfgKey, busy, error, onGenerate, drafts, onOpenDraft, providerAvail }: {
  vi: boolean; script: string; setScript: (s: string) => void
  cfg: Config; setCfgKey: <K extends keyof Config>(k: K, v: Config[K]) => void
  busy: boolean; error: string | null; onGenerate: () => void
  drafts: ContentProjectSummary[]; onOpenDraft: (id: string) => void
  providerAvail: Record<string, VisualProviderInfo> | null
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  // P3.1: per-source availability tag for the Visual-source dropdown.
  const availTag = (p: string): string => {
    const a = providerAvail?.[p]
    if (!a) return ''
    if (a.available) return a.free ? (vi ? ' — ✓ miễn phí' : ' — ✓ free') : (vi ? ' — ✓ sẵn sàng' : ' — ✓ ready')
    return vi ? ' — cần key' : ' — needs key'
  }
  const charCount = script.trim().length
  const hasPicker = typeof window !== 'undefined' && !!window.electronAPI?.pickDirectory
  const [defaultSaved, setDefaultSaved] = useState(false)

  async function pickOutputDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) { setCfgKey('outputDir', dir); setDefaultSaved(false) }
  }
  async function saveAsDefaultDir() {
    if (!cfg.outputDir.trim()) return
    try { await putDefaultOutputDir(cfg.outputDir.trim()); setDefaultSaved(true) } catch { /* ignore */ }
  }

  function importFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => setScript(String(r.result || ''))
    r.readAsText(f)
    e.target.value = ''
  }

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={1} />
      <HeroHeader icon="✨" title="Content Studio"
        subtitle={vi
          ? 'Biến kịch bản thành video — AI lo cảnh, lời kể & hình ảnh để bạn duyệt trước khi render.'
          : 'Turn a script into a video — the AI drafts scenes, narration & visuals for you to review before rendering.'} />

      {drafts.length > 0 && (
        <section className="cs-card">
          <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Bản nháp gần đây' : 'Recent drafts'}</span></div>
          <div className="cs-draft-row">
            {drafts.slice(0, 8).map((d) => (
              <button key={d.id} className="cs-draft-chip" onClick={() => onOpenDraft(d.id)} title={d.updated_at}>
                <b>{d.title || (vi ? 'Không tên' : 'Untitled')}</b>
                <span className="cs-draft-meta">
                  {' · '}{d.scenes} {vi ? 'cảnh' : 'sc'}{d.status === 'rendered' ? ' ✓' : ''}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="cs-grid">
        <section className="cs-card cs-card--flush">
          <div className="cs-card-hd">
            <span className="cs-card-title">{vi ? 'Kịch bản' : 'Script'}</span>
            <span className="cs-count">{charCount} {vi ? 'ký tự' : 'chars'}</span>
          </div>
          <textarea className="cs-textarea" value={script} onChange={(e) => setScript(e.target.value)}
            placeholder={vi
              ? 'Dán kịch bản / bài viết / tin tức…\n\nVí dụ: "Hôm nay chúng ta tìm hiểu vì sao Napoleon thất bại ở Waterloo."'
              : 'Paste your script / article / news…\n\ne.g. "Today we explore why Napoleon lost at Waterloo."'} />
          <div className="cs-row">
            <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()}>{vi ? 'Nhập .txt / .md' : 'Import .txt / .md'}</Button>
            {script && <Button variant="ghost" size="sm" onClick={() => setScript('')}>{vi ? 'Xoá' : 'Clear'}</Button>}
            <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain" hidden onChange={importFile} />
          </div>
        </section>

        <div className="cs-config-col">
          <SectionCard icon="🎨" title={vi ? 'Định dạng' : 'Format'}>
            <Field label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
              <RatioPreview value={cfg.ratio} onChange={(r) => setCfgKey('ratio', r)} />
            </Field>
            <Field label={vi ? 'Thời lượng mục tiêu' : 'Target duration'}>
              <DurationSlider value={cfg.targetDuration} onChange={(v) => setCfgKey('targetDuration', v)} />
            </Field>
          </SectionCard>

          <SectionCard icon="🖼️" title={vi ? 'Hình ảnh' : 'Visuals'}>
            <Field label={vi ? 'Nguồn hình ảnh' : 'Visual source'}>
              <select className="cs-input" value={cfg.visualProvider} onChange={(e) => setCfgKey('visualProvider', e.target.value as Config['visualProvider'])}>
                <option value="local">{(vi ? 'Nền tự chọn (offline)' : 'Chosen background (offline)') + availTag('local')}</option>
                <option value="stock">{(vi ? 'Ảnh Stock (Pexels/Pixabay)' : 'Stock images (Pexels/Pixabay)') + availTag('stock')}</option>
                <option value="ai_image_free">{(vi ? 'Ảnh AI (Pollinations — miễn phí)' : 'AI Image (Pollinations — free)') + availTag('ai_image_free')}</option>
                <option value="ai_image">{(vi ? 'Ảnh AI (Imagen/DALL·E, trả phí)' : 'AI Image (Imagen/DALL·E, paid)') + availTag('ai_image')}</option>
                <option value="ai_video">{(vi ? 'Video AI (Veo, trả phí, chậm)' : 'AI Video (Veo, paid, slow)') + availTag('ai_video')}</option>
              </select>
              {providerAvail?.stock?.available && cfg.visualProvider === 'local' && (
                <div className="cs-hint">
                  {vi ? '💡 Bạn đã có key Pexels — chọn "Ảnh Stock" để có ảnh thật miễn phí thay nền màu.' : '💡 Pexels key detected — pick "Stock images" for free real footage instead of a solid background.'}
                </div>
              )}
              {cfg.visualProvider === 'ai_image_free' && (
                <div className="cs-hint">
                  {vi
                    ? '⚠️ Prompt từng cảnh (do AI viết, bám nội dung) được gửi tới dịch vụ bên thứ 3 (Pollinations) để tạo ảnh. Miễn phí, không cần key.'
                    : '⚠️ Each scene\'s AI-written (story-grounded) prompt is sent to a third-party service (Pollinations) to generate the image. Free, no key.'}
                </div>
              )}
              {cfg.visualProvider !== 'local' && (
                <div className="cs-hint">
                  {vi ? 'Mỗi cảnh lấy ảnh theo nội dung. Thiếu key/mạng → tự dùng nền đã chọn.' : 'Each scene fetches an image by its content. Missing key/network → falls back to your background.'}
                </div>
              )}
            </Field>
            {cfg.visualProvider === 'ai_image' && (
              <Field label={vi ? 'Chất lượng ảnh AI' : 'AI image quality'}>
                <div className="cs-seg-row">
                  {(['fast', 'standard', 'ultra'] as ImagenTier[]).map((tier) => (
                    <button key={tier} className={seg(cfg.imagenTier === tier)} onClick={() => setCfgKey('imagenTier', tier)}>
                      {tier === 'fast' ? (vi ? 'Nhanh' : 'Fast') : tier === 'standard' ? (vi ? 'Tiêu chuẩn' : 'Standard') : 'Ultra'}
                    </button>
                  ))}
                </div>
                <div className="cs-hint">
                  {cfg.imagenTier === 'fast'
                    ? (vi ? 'Imagen 4 Fast — cần key có Imagen 4.' : 'Imagen 4 Fast — needs Imagen 4 access.')
                    : cfg.imagenTier === 'ultra'
                    ? (vi ? 'Imagen 4 Ultra — cao nhất, cần key có Imagen 4.' : 'Imagen 4 Ultra — top quality, needs Imagen 4 access.')
                    : (vi ? 'Imagen 3 (mặc định, phổ biến). Cần key Gemini có bật billing.' : 'Imagen 3 (default, broadly available). Needs a billing-enabled Gemini key.')}
                </div>
              </Field>
            )}
            {(cfg.visualProvider === 'ai_image' || cfg.visualProvider === 'ai_video') && (
              <Field label={vi ? 'Trần chi phí AI ($)' : 'AI budget cap ($)'}>
                <input
                  className="cs-input" type="number" min={0} step={0.05}
                  value={cfg.aiBudget || ''}
                  onChange={(e) => setCfgKey('aiBudget', Math.max(0, Number(e.target.value) || 0))}
                  placeholder={vi ? '0 = không giới hạn' : '0 = unlimited'}
                />
                <div className="cs-hint">
                  {vi
                    ? 'Ước tính tương đối — khi vượt trần, các cảnh sau tự hạ về nguồn rẻ hơn/miễn phí. 0 = không giới hạn.'
                    : 'Relative estimate — once exceeded, later scenes downgrade to a cheaper/free source. 0 = unlimited.'}
                </div>
              </Field>
            )}
            <Field label={vi ? 'Nền (khi không có ảnh)' : 'Background (fallback)'}>
              <div className="cs-seg-row">
                {(['color', 'image', 'video'] as BgKind[]).map((k) => (
                  <button key={k} className={seg(cfg.bgKind === k)} onClick={() => setCfgKey('bgKind', k)}>
                    {k === 'color' ? (vi ? 'Màu' : 'Color') : k === 'image' ? (vi ? 'Ảnh' : 'Image') : 'Video'}
                  </button>
                ))}
              </div>
              {cfg.bgKind === 'color' ? (
                <div className="cs-row cs-row--top">
                  <input type="color" className="cs-color-swatch" value={cfg.bgColor} onChange={(e) => setCfgKey('bgColor', e.target.value)} />
                  <input className="cs-input" value={cfg.bgColor} onChange={(e) => setCfgKey('bgColor', e.target.value)} />
                </div>
              ) : (
                <input className="cs-input cs-row--top" value={cfg.bgAssetPath} onChange={(e) => setCfgKey('bgAssetPath', e.target.value)}
                  placeholder={vi ? 'Đường dẫn file trên máy…' : 'Local file path…'} />
              )}
            </Field>
          </SectionCard>

          <SectionCard icon="🎙️" title={vi ? 'Giọng & Phụ đề' : 'Voice & Subtitles'}>
            <Field label={vi ? 'Giọng đọc' : 'Voice'}>
              <div className="cs-row">
                <select className="cs-input" value={cfg.voiceLang} onChange={(e) => setCfgKey('voiceLang', e.target.value as typeof VOICE_LANGS[number])}>
                  {VOICE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
                <select className="cs-input" value={cfg.voiceGender} onChange={(e) => setCfgKey('voiceGender', e.target.value as 'female' | 'male')}>
                  <option value="female">{vi ? 'Nữ' : 'Female'}</option>
                  <option value="male">{vi ? 'Nam' : 'Male'}</option>
                </select>
                <select className="cs-input" value={cfg.ttsEngine} onChange={(e) => setCfgKey('ttsEngine', e.target.value as typeof TTS_ENGINES[number])}>
                  {TTS_ENGINES.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
                </select>
              </div>
            </Field>
            <Field label={vi ? 'Phụ đề' : 'Subtitles'}>
              <div className="cs-row">
                <button className={seg(cfg.subEnabled)} onClick={() => setCfgKey('subEnabled', !cfg.subEnabled)}>{cfg.subEnabled ? (vi ? 'Bật' : 'On') : (vi ? 'Tắt' : 'Off')}</button>
                {cfg.subEnabled && (
                  <select className="cs-input" value={cfg.subStyle} onChange={(e) => setCfgKey('subStyle', e.target.value)}>
                    {SUB_STYLES.map((s) => <option key={s} value={s}>{s === 'auto' ? (vi ? 'Tự động (AI chọn)' : 'Auto (AI picks)') : s}</option>)}
                  </select>
                )}
                {cfg.subEnabled && (
                  <label className="cs-mini-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <input type="checkbox" checked={cfg.wordByWord} onChange={(e) => setCfgKey('wordByWord', e.target.checked)} />
                    {vi ? 'Chữ động (Whisper)' : 'Word-by-word (Whisper)'}
                  </label>
                )}
              </div>
              {cfg.subEnabled && cfg.wordByWord && (
                <div className="cs-hint">
                  {vi ? '⚠ Chữ động chạy Whisper cho MỖI cảnh — render chậm hơn đáng kể. Tắt để phụ đề theo câu (nhanh hơn).' : '⚠ Word-by-word runs Whisper per scene — noticeably slower. Turn off for faster sentence-level subtitles.'}
                </div>
              )}
            </Field>
          </SectionCard>

          <SectionCard icon="⚙️" title={vi ? 'Khác' : 'More'}>
            <Field label={vi ? 'Nhạc nền (tuỳ chọn)' : 'Background music (optional)'}>
              <input className="cs-input" value={cfg.bgmPath} onChange={(e) => setCfgKey('bgmPath', e.target.value)}
                placeholder={vi ? 'Đường dẫn file nhạc… (tự ducking dưới giọng đọc)' : 'Music file path… (auto-ducked under narration)'} />
            </Field>
            <Field label={vi ? 'Thư mục lưu *' : 'Save folder *'}>
              <div className="cs-row">
                <input className="cs-input" value={cfg.outputDir}
                  onChange={(e) => { setCfgKey('outputDir', e.target.value); setDefaultSaved(false) }}
                  placeholder={vi ? 'Chọn nơi lưu video…' : 'Choose where to save…'} />
                {hasPicker && (
                  <Button variant="secondary" size="sm" onClick={pickOutputDir}>{vi ? '📁 Chọn…' : '📁 Browse…'}</Button>
                )}
              </div>
              {cfg.outputDir.trim() ? (
                <div className="cs-row cs-row--top">
                  <Button variant="ghost" size="sm" disabled={defaultSaved} onClick={saveAsDefaultDir}>
                    {defaultSaved ? (vi ? '✓ Đã đặt mặc định' : '✓ Set as default') : (vi ? 'Đặt làm mặc định' : 'Set as default')}
                  </Button>
                </div>
              ) : (
                <div className="cs-hint">{vi ? '⚠ Chưa chọn thư mục — bắt buộc trước khi render.' : '⚠ No folder chosen — required before rendering.'}</div>
              )}
              {!hasPicker && (
                <div className="cs-hint">{vi ? 'Nút chọn thư mục chỉ có trong app desktop — nhập đường dẫn tay khi dùng trình duyệt.' : 'The folder picker is desktop-app only — type a path when using the browser.'}</div>
              )}
            </Field>
          </SectionCard>
        </div>
      </div>

      <div className="cs-footer">
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={!charCount || busy} onClick={onGenerate}>
          {busy ? (vi ? 'AI đang phân tích…' : 'AI analyzing…') : (vi ? '✨ Tạo kế hoạch (AI) →' : '✨ Generate Content Plan →')}
        </Button>
      </div>

      {busy && <AiDirectorConsole vi={vi} />}
    </div>
  )
}

// ── Phase 2: review + edit plan ─────────────────────────────────────────────

interface VoiceCfg { lang: string; gender: 'female' | 'male'; engine: string }
interface VisualCfg { provider: string; aspectApi: string; style: string; imagenTier: string }

function ReviewPhase({ vi, plan, setPlan, busy, error, durationFit, visualProvider, targetDuration, aspectApi, imagenTier, voice, onBack, onApprove }: {
  vi: boolean; plan: ContentPlan; setPlan: (p: ContentPlan) => void
  busy: boolean; error: string | null
  durationFit: DurationFit | null; visualProvider: Config['visualProvider']; targetDuration: number
  aspectApi: string; imagenTier: string
  voice: VoiceCfg; onBack: () => void; onApprove: () => void
}) {
  const visualCfg: VisualCfg = { provider: visualProvider, aspectApi, style: plan.video_style || '', imagenTier }
  function updateScene(i: number, patch: Partial<ContentScene>) {
    setPlan({ ...plan, scenes: plan.scenes.map((s, idx) => (idx === i ? { ...s, ...patch } : s)) })
  }
  function removeScene(i: number) {
    setPlan({ ...plan, scenes: plan.scenes.filter((_, idx) => idx !== i) })
  }
  function moveScene(i: number, dir: -1 | 1) {
    const j = i + dir
    if (j < 0 || j >= plan.scenes.length) return
    const next = [...plan.scenes]
    ;[next[i], next[j]] = [next[j], next[i]]
    setPlan({ ...plan, scenes: next })
  }
  function addScene() {
    setPlan({ ...plan, scenes: [...plan.scenes, { index: plan.scenes.length, role: 'explain', narration: '', emotion: 'normal', reading_speed: 1.0 }] })
  }

  const canRender = plan.scenes.some((s) => (s.narration || '').trim()) && !busy

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={2} />
      <HeroHeader icon="🎬" title={vi ? 'Duyệt kế hoạch AI' : 'Review AI Plan'}
        subtitle={
          <>
            {plan.topic ? <b>{plan.topic}</b> : null}
            {plan.video_style ? ` · ${plan.video_style}` : ''}
            {' · '}{plan.scenes.length} {vi ? 'cảnh' : 'scenes'}
            {' · '}{vi ? 'Sửa lời kể / cảm xúc / thời lượng, thêm-xoá-đổi thứ tự cảnh trước khi render.' : 'Edit narration / emotion / duration, add-remove-reorder before rendering.'}
          </>
        } />

      <AiInsights vi={vi} plan={plan} durationFit={durationFit} visualProvider={visualProvider} targetDuration={targetDuration} />

      {visualProvider !== 'local' && (
        <CostEstimatePanel vi={vi} plan={plan} visualProvider={visualProvider} targetDuration={targetDuration} />
      )}

      <div className="cs-scene-list">
        {plan.scenes.map((s, i) => (
          <SceneRow key={i} vi={vi} scene={s} index={i} total={plan.scenes.length} voice={voice} visualCfg={visualCfg}
            onChange={(patch) => updateScene(i, patch)} onRemove={() => removeScene(i)} onMove={(d) => moveScene(i, d)} />
        ))}
        <div><Button variant="ghost" size="sm" onClick={addScene}>+ {vi ? 'Thêm cảnh' : 'Add scene'}</Button></div>
      </div>

      <div className="cs-footer">
        <Button variant="ghost" onClick={onBack} disabled={busy}>{vi ? '← Quay lại kịch bản' : '← Back to script'}</Button>
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={!canRender} onClick={onApprove}>
          {busy ? (vi ? 'Đang gửi…' : 'Starting…') : (vi ? 'Duyệt & Render →' : 'Approve & Render →')}
        </Button>
      </div>
    </div>
  )
}

function SceneRow({ vi, scene, index, total, voice, visualCfg, onChange, onRemove, onMove }: {
  vi: boolean; scene: ContentScene; index: number; total: number; voice: VoiceCfg; visualCfg: VisualCfg
  onChange: (patch: Partial<ContentScene>) => void; onRemove: () => void; onMove: (dir: -1 | 1) => void
}) {
  const [previewing, setPreviewing] = useState(false)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [dur, setDur] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const hasText = !!(scene.narration || '').trim()
  const audit = sceneAudit(scene)

  // C1: per-scene visual preview.
  const [vImg, setVImg] = useState<string | null>(null)      // shown image URL
  const [vNote, setVNote] = useState<string | null>(null)    // "fell back to background" / error
  const [vBusy, setVBusy] = useState(false)
  const vSeed = useRef(0)
  const hasPrompt = !!(scene.visual_prompt || '').trim()
  const canVisual = visualCfg.provider !== 'local' && hasPrompt

  async function doVisual(regen: boolean) {
    if (!canVisual || vBusy) return
    if (regen) vSeed.current += 1
    setVBusy(true); setVNote(null)
    try {
      const r = await previewVisual({
        prompt: (scene.visual_prompt || '').trim(),
        provider: visualCfg.provider, aspect_ratio: visualCfg.aspectApi,
        seed: vSeed.current, style: visualCfg.style,
        negative_prompt: scene.negative_prompt || '',
        imagen_tier: visualCfg.provider === 'ai_image' ? visualCfg.imagenTier : undefined,
      })
      if (r.kind === 'image' && r.url) {
        setVImg(BASE_URL + r.url + `?t=${Date.now()}`)   // bust cache on regen
        if (r.provider !== visualCfg.provider) {
          setVNote(vi ? `Đã dùng nguồn "${r.provider}" (nguồn chọn không tạo được).` : `Used "${r.provider}" (chosen source unavailable).`)
        }
      } else {
        setVImg(null)
        setVNote(vi ? 'Nguồn không tạo được ảnh — khi render sẽ dùng nền màu.' : 'No image produced — the render will use a background colour.')
      }
    } catch (err) {
      setVNote(err instanceof Error ? err.message : String(err))
    } finally {
      setVBusy(false)
    }
  }

  async function doPreview() {
    if (!hasText || previewing) return
    setPreviewErr(null); setPreviewing(true)
    try {
      const r = await previewNarration({
        text: (scene.narration || '').trim(),
        voice_language: voice.lang, voice_gender: voice.gender,
        tts_engine: voice.engine, reading_speed: scene.reading_speed ?? 1,
      })
      setDur(r.duration_sec)
      if (audioRef.current) audioRef.current.pause()
      const a = new Audio(BASE_URL + r.url)
      audioRef.current = a
      void a.play().catch(() => {})
    } catch (err) {
      setPreviewErr(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <section className="cs-card cs-card--flush">
      <div className="cs-card-hd">
        <input className="cs-input cs-scene-title-input" value={scene.scene_title || ''} placeholder={`${vi ? 'Cảnh' : 'Scene'} ${index + 1}`}
          onChange={(e) => onChange({ scene_title: e.target.value })} />
        {audit.flag === 'overloaded' && (
          <span className="cs-audit-badge is-over" title={vi ? 'Lời kể dài hơn thời lượng — TTS sẽ bị hụt/tràn. Rút gọn hoặc tăng thời lượng.' : 'Narration too long for the duration — TTS will rush/overflow. Shorten it or raise the duration.'}>
            {vi ? '⚠ Quá tải' : '⚠ Overloaded'}
          </span>
        )}
        {audit.flag === 'sparse' && (
          <span className="cs-audit-badge is-sparse" title={vi ? 'Lời kể ngắn so với thời lượng — sẽ có khoảng lặng. Thêm lời hoặc giảm thời lượng.' : 'Narration short for the duration — expect silence. Add narration or lower the duration.'}>
            {vi ? 'Thưa' : 'Sparse'}
          </span>
        )}
        <div className="cs-row" style={{ gap: 4 }}>
          <button className={`cs-icon-btn${hasText ? ' is-accent' : ''}`} title={vi ? 'Nghe thử giọng' : 'Preview voice'}
            disabled={!hasText || previewing} onClick={doPreview}>{previewing ? '…' : '🔊'}</button>
          {canVisual && (
            <button className="cs-icon-btn is-accent"
              title={(visualCfg.provider === 'ai_image' || visualCfg.provider === 'ai_video')
                ? (vi ? 'Xem thử ảnh — TỐN PHÍ mỗi lần (Imagen/Veo)' : 'Preview image — PAID per call (Imagen/Veo)')
                : (vi ? 'Xem thử ảnh (miễn phí)' : 'Preview image (free)')}
              disabled={vBusy} onClick={() => doVisual(false)}>{vBusy ? '…' : '🖼️'}</button>
          )}
          <button className="cs-icon-btn" title="Up" disabled={index === 0} onClick={() => onMove(-1)}>↑</button>
          <button className="cs-icon-btn" title="Down" disabled={index === total - 1} onClick={() => onMove(1)}>↓</button>
          <button className="cs-icon-btn is-danger" title="Delete" onClick={onRemove}>✕</button>
        </div>
      </div>
      <textarea className="cs-textarea cs-textarea--sm" value={scene.narration}
        placeholder={vi ? 'Lời kể…' : 'Narration…'} onChange={(e) => onChange({ narration: e.target.value })} />
      <div className="cs-row">
        <label className="cs-mini-label">{vi ? 'Cảm xúc' : 'Emotion'}
          <select className="cs-input-sm" value={scene.emotion || 'normal'} onChange={(e) => onChange({ emotion: e.target.value })}>
            {EMOTIONS.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
          </select>
        </label>
        <label className="cs-mini-label">{vi ? 'Tốc độ' : 'Speed'}
          <input type="number" step={0.05} min={0.5} max={2} className="cs-input-sm" value={scene.reading_speed ?? 1}
            onChange={(e) => onChange({ reading_speed: Number(e.target.value) || 1 })} />
        </label>
        <label className="cs-mini-label">{vi ? 'Thời lượng (s)' : 'Dur (s)'}
          <input type="number" step={0.5} min={0} className="cs-input-sm" value={scene.est_duration_sec ?? 0}
            onChange={(e) => onChange({ est_duration_sec: Number(e.target.value) || 0 })} />
        </label>
        <label className="cs-mini-label" style={{ flex: 1, minWidth: 200 }}>{vi ? 'Visual prompt' : 'Visual prompt'}
          <input className="cs-input-sm" value={scene.visual_prompt || ''} onChange={(e) => onChange({ visual_prompt: e.target.value })}
            placeholder={vi ? 'Mô tả hình ảnh cho scene này…' : 'Image/video prompt for this scene…'} />
        </label>
      </div>
      {/* C1: per-scene visual preview (image + regenerate). */}
      {(vImg || vNote) && (
        <div style={{ marginTop: 8 }}>
          {vImg && <img src={vImg} alt="" style={{ maxWidth: 160, maxHeight: 280, borderRadius: 8, display: 'block' }} />}
          <div className="cs-row" style={{ gap: 8, alignItems: 'center', marginTop: 6 }}>
            {vImg && (
              <button className="cs-icon-btn" title={vi ? 'Tạo lại ảnh' : 'Regenerate image'}
                disabled={vBusy} onClick={() => doVisual(true)}>{vBusy ? '…' : '🔄'}</button>
            )}
            {vNote && <span className="cs-hint" style={{ margin: 0, color: vImg ? undefined : 'var(--warn, #d6a200)' }}>{vNote}</span>}
          </div>
        </div>
      )}
      {/* CS-E: per-scene background (Asset Manager). "" = dùng nền chung của project. */}
      <div className="cs-row cs-row--top" style={{ alignItems: 'flex-end' }}>
        <label className="cs-mini-label">{vi ? 'Nền riêng' : 'Scene background'}
          <select className="cs-input-sm" value={scene.visual_source || ''}
            onChange={(e) => onChange({ visual_source: e.target.value as ContentScene['visual_source'] })}>
            <option value="">{vi ? 'Nền chung' : 'Project default'}</option>
            <option value="color">{vi ? 'Màu' : 'Color'}</option>
            <option value="image">{vi ? 'Ảnh' : 'Image'}</option>
            <option value="video">Video</option>
          </select>
        </label>
        {scene.visual_source === 'color' && (
          <label className="cs-mini-label">{vi ? 'Màu' : 'Color'}
            <input type="color" className="cs-color-swatch" value={scene.visual_path || '#101820'} onChange={(e) => onChange({ visual_path: e.target.value })} />
          </label>
        )}
        {(scene.visual_source === 'image' || scene.visual_source === 'video') && (
          <label className="cs-mini-label" style={{ flex: 1, minWidth: 200 }}>{vi ? 'Đường dẫn file' : 'File path'}
            <input className="cs-input-sm" value={scene.visual_path || ''} onChange={(e) => onChange({ visual_path: e.target.value })}
              placeholder={vi ? 'Đường dẫn ảnh/video trên máy…' : 'Local image/video path…'} />
          </label>
        )}
        {scene.visual_source === 'image' && (
          <label className="cs-mini-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={!!scene.ken_burns} onChange={(e) => onChange({ ken_burns: e.target.checked })} />
            Ken Burns
          </label>
        )}
      </div>
      {(dur != null || previewErr) && (
        <div className="cs-hint" style={{ color: previewErr ? 'var(--fail)' : undefined }}>
          {previewErr ? previewErr : `${vi ? 'Giọng ~' : 'Voice ~'}${(dur ?? 0).toFixed(1)}s`}
        </div>
      )}
    </section>
  )
}

// ── Phase 3: live monitor ───────────────────────────────────────────────────

function ContentMonitor({ jobId, onNew, vi, plan, voiceLang }: {
  jobId: string; onNew: () => void; vi: boolean; plan: ContentPlan | null; voiceLang: string
}) {
  const { stage, jobStatus, jobMessage, progress, liveParts, liveEvents, isTerminal, error } = useRenderSocket(jobId)
  const pct = progress?.overall_progress_percent ?? 0
  const ok = jobStatus === 'completed' || jobStatus === 'completed_with_errors'
  // The finished video — content repoints every scene part at the assembled
  // output, so the first part with an output_file is the deliverable.
  const outputPart = liveParts.find((p) => p.output_file)
  const outputFile = outputPart?.output_file || ''
  const streamUrl = outputPart ? `${BASE_URL}/api/jobs/${jobId}/parts/${outputPart.part_no}/stream` : ''
  const [pubBusy, setPubBusy] = useState(false)
  const [pubMeta, setPubMeta] = useState<PublishMeta | null>(null)
  const [pubErr, setPubErr] = useState<string | null>(null)

  async function genPublish() {
    if (pubBusy || !plan) return
    setPubBusy(true); setPubErr(null)
    try {
      const sample = (plan.scenes || []).slice(0, 6).map((s) => s.narration).join(' ')
      const { meta } = await publishMeta({
        topic: plan.topic, tone: plan.tone, audience: plan.audience,
        voice_language: voiceLang, narration_sample: sample,
      })
      setPubMeta(meta)
    } catch (e) {
      setPubErr(e instanceof Error ? e.message : String(e))
    } finally {
      setPubBusy(false)
    }
  }
  const planReady = useMemo(() => liveEvents.some((e) => (e as { event?: string }).event === 'content.plan.ready'), [liveEvents])

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={3} />
      <HeroHeader icon="🎞️" title={vi ? 'Đang render…' : 'Rendering…'}
        subtitle={jobMessage || stage || ''} />
      <section className="cs-card">
        <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Tiến độ' : 'Progress'}</span></div>
        <ProgressBar value={pct} variant={isTerminal ? (ok ? 'success' : 'error') : 'default'} />
        <div className="cs-hint">
          {vi ? 'Giai đoạn' : 'Stage'}: <b>{stage || '—'}</b>{planReady && <> · {vi ? 'kế hoạch sẵn sàng' : 'plan ready'}</>}
        </div>
      </section>

      <section className="cs-card cs-card--flush cs-live-wrap">
        <ContentLiveView vi={vi} liveParts={liveParts} liveEvents={liveEvents} />
      </section>
      {isTerminal && (
        <section className="cs-card" style={{ borderColor: ok ? 'var(--ok)' : 'var(--fail)' }}>
          <div className="cs-card-hd">
            <span className="cs-card-title" style={{ color: ok ? 'var(--ok)' : 'var(--fail)' }}>
              {ok ? (vi ? '✓ Hoàn thành' : '✓ Done') : (vi ? '✕ Thất bại' : '✕ Failed')}
            </span>
          </div>
          <p className="cs-terminal-msg">{jobMessage || error || ''}</p>

          {ok && streamUrl && (
            <video className="cs-preview" controls src={streamUrl} />
          )}

          <div className="cs-row">
            <Button variant="primary" onClick={onNew}>{vi ? 'Tạo video mới' : 'New content video'}</Button>
            {ok && outputFile && window.electronAPI?.openPath && (
              <>
                <Button variant="secondary" size="sm" onClick={() => window.electronAPI?.openPath?.(outputFile)}>
                  {vi ? '▶ Phát' : '▶ Play'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => revealInFolder(outputFile)}>
                  {vi ? '📁 Mở thư mục' : '📁 Open folder'}
                </Button>
              </>
            )}
            {ok && plan && (
              <Button variant="ghost" size="sm" disabled={pubBusy} onClick={genPublish}>
                {pubBusy ? (vi ? 'Đang tạo…' : 'Generating…') : (vi ? '✨ Tạo tiêu đề/mô tả (AI)' : '✨ Generate title/description (AI)')}
              </Button>
            )}
          </div>
          {pubErr && <div className="cs-hint" style={{ color: 'var(--fail)' }}>{pubErr}</div>}
          {pubMeta && (
            <div className="cs-publish">
              <PublishField vi={vi} label={vi ? 'Tiêu đề' : 'Title'} value={pubMeta.title} />
              <PublishField vi={vi} label={vi ? 'Mô tả' : 'Description'} value={pubMeta.description} multiline />
              <PublishField vi={vi} label={vi ? 'Thẻ' : 'Tags'} value={(pubMeta.tags || []).join(', ')} />
              {typeof pubMeta.thumbnail_scene_index === 'number' && pubMeta.thumbnail_scene_index >= 0 && (
                <div className="cs-hint">
                  {vi ? 'Ảnh bìa gợi ý: cảnh ' : 'Suggested thumbnail: scene '}<b>{pubMeta.thumbnail_scene_index + 1}</b>
                </div>
              )}
            </div>
          )}
        </section>
      )}
      {!isTerminal && <div style={{ marginTop: 'var(--space-3)' }}><Button variant="ghost" onClick={onNew}>{vi ? 'Tạo cái khác' : 'Start another'}</Button></div>}
    </div>
  )
}

// ── AI Insights (Review) ────────────────────────────────────────────────────

// Client-side mirror of the backend narration_audit so the badges stay accurate
// as the user edits narration / speed / duration in Review. Same thresholds as
// ContentPlan.narration_audit (chars vs capacity at ~15 chars/sec × speed).
const _CPS = 15
type AuditFlag = 'overloaded' | 'sparse' | 'ok' | 'none'
function sceneAudit(s: ContentScene): { load: number | null; flag: AuditFlag } {
  const chars = (s.narration || '').trim().length
  const est = s.est_duration_sec ?? 0
  const spd = s.reading_speed ?? 1
  if (est <= 0 || chars <= 0) return { load: null, flag: 'none' }
  const cap = _CPS * spd * est
  const load = cap > 0 ? chars / cap : null
  if (load == null) return { load: null, flag: 'none' }
  if (load > 1.3) return { load, flag: 'overloaded' }
  if (load < 0.6) return { load, flag: 'sparse' }
  return { load, flag: 'ok' }
}

function AiInsights({ vi, plan, durationFit, visualProvider, targetDuration }: {
  vi: boolean; plan: ContentPlan; durationFit: DurationFit | null
  visualProvider: Config['visualProvider']; targetDuration: number
}) {
  const audit = useMemo(() => {
    let over = 0, sparse = 0, rated = 0
    for (const s of plan.scenes) {
      const { flag } = sceneAudit(s)
      if (flag === 'none') continue
      rated++
      if (flag === 'overloaded') over++
      else if (flag === 'sparse') sparse++
    }
    return { over, sparse, rated, weak: over > 0 || (rated > 0 && sparse / rated > 0.4) }
  }, [plan])
  const chars = (plan.story_bible?.characters || []).filter((c) => (c.name || c.id))
  const estTotal = plan.scenes.reduce((sum, s) => sum + (s.est_duration_sec || 0), 0)

  return (
    <section className="cs-card cs-insights">
      <div className="cs-card-hd"><span className="cs-card-title">{vi ? '✨ AI đã làm gì' : '✨ What the AI did'}</span></div>
      <div className="cs-insight-list">
        {durationFit?.changed ? (
          <div className="cs-insight">
            <AIChip variant="applied" label={vi ? 'Chỉnh nhịp đọc' : 'Paced to target'} />
            <span>{vi ? 'Điều chỉnh tốc độ đọc để vừa mục tiêu' : 'Adjusted reading speed to hit the target'}:{' '}
              <b>{durationFit.before_sec.toFixed(0)}s → {durationFit.after_sec.toFixed(0)}s</b>
              {durationFit.applied_scale ? ` (×${durationFit.applied_scale})` : ''}</span>
          </div>
        ) : (
          <div className="cs-insight">
            <AIChip variant="advisory" label={vi ? 'Thời lượng' : 'Duration'} />
            <span>{vi ? 'Ước tính' : 'Estimated'} <b>~{estTotal.toFixed(0)}s</b> {vi ? '/ mục tiêu' : '/ target'} {targetDuration}s</span>
          </div>
        )}

        {(plan.topic || chars.length > 0) && (
          <div className="cs-insight">
            <AIChip variant="applied" label={vi ? 'Hiểu nội dung' : 'Understood'} />
            <span>
              {plan.topic ? <><b>{plan.topic}</b>{plan.video_style ? ` · ${plan.video_style}` : ''}</> : null}
              {chars.length > 0 && <>{' · '}{vi ? 'Nhân vật' : 'Characters'}: {chars.map((c, i) => (
                <span key={i} className="cs-char-chip">{c.name || c.id}</span>
              ))}</>}
            </span>
          </div>
        )}

        {audit.rated > 0 && (
          <div className="cs-insight">
            <AIChip variant={audit.weak ? 'advisory' : 'applied'} label={vi ? 'Kiểm tra lời kể' : 'Narration check'} />
            <span>
              {audit.weak
                ? (vi ? `${audit.over} cảnh quá tải, ${audit.sparse} cảnh thưa — chỉnh lời kể/thời lượng bên dưới.`
                      : `${audit.over} overloaded, ${audit.sparse} sparse — tweak narration/duration below.`)
                : (vi ? 'Lời kể cân đối với thời lượng từng cảnh.' : "Narration length matches each scene's duration.")}
            </span>
          </div>
        )}

        {visualProvider !== 'local' && (
          <div className="cs-insight">
            <AIChip variant="advisory" label={vi ? 'Nguồn ảnh' : 'Visuals'} />
            <span>{vi ? 'Dùng nguồn ảnh AI/Stock — cần API key. Thiếu key/mạng → tự dùng nền đã chọn.'
                       : 'Using an AI/Stock visual source — needs an API key. Missing key/network → falls back to your background.'}</span>
          </div>
        )}
      </div>
    </section>
  )
}

// ── Cost preflight (Review, paid visual providers) ──────────────────────────

const _PROVIDER_LABELS: Record<string, string> = {
  local: 'Local', stock: 'Stock', ai_image_free: 'Pollinations', ai_image: 'Imagen', ai_video: 'Veo',
}

function CostEstimatePanel({ vi, plan, visualProvider, targetDuration }: {
  vi: boolean; plan: ContentPlan; visualProvider: Config['visualProvider']; targetDuration: number
}) {
  const [busy, setBusy] = useState(false)
  const [est, setEst] = useState<ContentEstimate | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function run() {
    if (busy) return
    setBusy(true); setErr(null)
    try {
      const r = await estimateContentCost({
        plan, visual_provider: visualProvider, target_duration: targetDuration, budget_cap: 0,
      })
      setEst(r)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="cs-card cs-cost">
      <div className="cs-card-hd">
        <span className="cs-card-title">{vi ? '💰 Chi phí AI ước tính' : '💰 Estimated AI cost'}</span>
        <Button variant="ghost" size="sm" disabled={busy} onClick={run}>
          {busy ? (vi ? 'Đang tính…' : 'Estimating…') : est ? (vi ? 'Tính lại' : 'Recalculate') : (vi ? 'Ước tính' : 'Estimate')}
        </Button>
      </div>
      {err && <div className="cs-hint" style={{ color: 'var(--fail)' }}>{err}</div>}
      {!est && !err && (
        <div className="cs-hint">
          {vi ? 'Bấm "Ước tính" để xem chi phí ảnh AI trước khi render (không gọi API trả phí).'
              : 'Click "Estimate" to preview the AI image cost before rendering (no paid API call).'}
        </div>
      )}
      {est && (
        <div className="cs-cost-body">
          <div className="cs-cost-total">
            <span
              className="cs-cost-num"
              title={vi
                ? 'Ước tính tương đối dựa trên chi phí trung bình mỗi ảnh/clip AI — không phải hoá đơn chính xác. Nguồn local/stock không tính phí.'
                : 'Rough estimate from average per-asset AI cost — not a precise bill. local/stock sources are free.'}
            >~${est.estimated_cost.toFixed(2)}</span>
            <span className="cs-cost-sub">{est.scenes} {vi ? 'cảnh' : 'scenes'} · ~{est.estimated_duration_sec.toFixed(0)}s</span>
          </div>
          <div className="cs-row" style={{ gap: 6 }}>
            {Object.entries(est.by_provider).map(([prov, n]) => (
              <span key={prov} className="cs-char-chip">{_PROVIDER_LABELS[prov] || prov}: {n}</span>
            ))}
          </div>
          {est.estimated_cost === 0 ? (
            <div className="cs-hint">{vi ? 'Miễn phí — mọi cảnh dùng nguồn không tính phí (local/stock).' : 'Free — every scene uses a no-cost source (local/stock).'}</div>
          ) : (
            <div className="cs-hint">{vi ? '≈ ước tính tương đối (chi phí trung bình mỗi ảnh/clip AI) — không phải hoá đơn chính xác.' : '≈ rough estimate (average per-asset AI cost) — not a precise bill.'}</div>
          )}
        </div>
      )}
    </section>
  )
}

// ── AI Director console (planning overlay, P5) ──────────────────────────────

const _DIRECTOR_STEPS_VI = [
  'Đọc & hiểu kịch bản',
  'Xác định chủ đề · giọng · khán giả',
  'Chia cảnh theo ý nghĩa',
  'Viết lời kể + cảm xúc + nhịp đọc',
  'Cân chỉnh thời lượng',
]
const _DIRECTOR_STEPS_EN = [
  'Reading & understanding the script',
  'Detecting topic · tone · audience',
  'Splitting into meaningful scenes',
  'Writing narration + emotion + pacing',
  'Fitting the duration',
]

// Shown while POST /api/content/plan is in flight. /plan is a single synchronous
// call with no sub-events, so we walk the AI's REAL internal steps on a timer
// and hold on the last one until the plan returns (this component unmounts) —
// honest progress framing, never a fake percentage.
function AiDirectorConsole({ vi }: { vi: boolean }) {
  const steps = vi ? _DIRECTOR_STEPS_VI : _DIRECTOR_STEPS_EN
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 1300)
    return () => clearInterval(id)
  }, [steps.length])
  return (
    <div className="cs-director-overlay">
      <div className="cs-director">
        <div className="cs-director-hd">
          <span className="cs-director-orb" />
          <div>
            <div className="cs-director-title">AI Content Director</div>
            <div className="cs-director-sub">{vi ? 'Đang lập kế hoạch video…' : 'Planning your video…'}</div>
          </div>
        </div>
        <ol className="cs-director-steps">
          {steps.map((label, i) => {
            const state = i < step ? 'done' : i === step ? 'active' : 'pending'
            return (
              <li key={i} className={`cs-director-step is-${state}`}>
                <span className="cs-director-mark">
                  {state === 'done' ? '✓' : state === 'active' ? <span className="cs-feed-spinner" /> : ''}
                </span>
                <span>{label}</span>
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}

// ── Live render: AI Activity Feed + Scene grid (P4) ─────────────────────────

// Icon + tone for a live render event so the feed reads as "what the AI is
// doing", not a raw log. Falls back to the backend's own message text.
// Scene status helpers (mirror RecapLiveView semantics).
function _lvNorm(s: string | undefined): string { return (s || '').toLowerCase() }
function _lvActive(s: string | undefined): boolean { return ['rendering', 'cutting', 'transcribing'].includes(_lvNorm(s)) }
function _lvDone(s: string | undefined): boolean { return _lvNorm(s) === 'done' }
function _lvFailed(s: string | undefined): boolean { return ['failed', 'cancelled', 'skipped'].includes(_lvNorm(s)) }
function _lvGlyph(s: string | undefined): string {
  if (_lvDone(s)) return '✓'
  if (_lvActive(s)) return '◉'
  if (_lvFailed(s)) return '✕'
  return '○'
}

interface SceneMeta { n: number; role?: string; narration?: string; scene_title?: string }

// ContentLiveView — "Now Rendering" view modelled on RecapLiveView: a LEFT focus
// column (the scene rendering now — ConicRing + title + narration) and a RIGHT
// queue (compact scene rows). Content has no episodes, so the queue is a flat
// scene list. Data comes from liveParts + the content.plan.ready event.
function ContentLiveView({ vi, liveParts, liveEvents }: {
  vi: boolean; liveParts: JobPart[]; liveEvents: WsLogEvent[]
}) {
  const planEv = [...liveEvents].reverse().find((e) => e.event === 'content.plan.ready')
  const metaByN = new Map<number, SceneMeta>(
    (((planEv?.context?.scenes) as SceneMeta[] | undefined) ?? [])
      .filter(Boolean).map((s) => [Number(s.n), s]),
  )
  const parts = liveParts
  if (parts.length === 0) {
    return <div className="cs-hint" style={{ padding: '14px 16px' }}>{vi ? 'Chờ AI lập kế hoạch cảnh…' : 'Waiting for the AI scene plan…'}</div>
  }
  const actives = [...parts].filter((p) => _lvActive(p.status))
    .sort((a, b) => (b.progress_percent ?? 0) - (a.progress_percent ?? 0))
  const focus = actives[0] ?? parts.find((p) => !_lvDone(p.status)) ?? parts[parts.length - 1]
  const doneCount = parts.filter((p) => _lvDone(p.status)).length

  const roleOf = (p: JobPart) => (metaByN.get(p.part_no)?.role || metaByN.get(p.part_no)?.scene_title || `${vi ? 'Cảnh' : 'Scene'} ${p.part_no}`)
  const statusLabel = (p: JobPart) => _lvDone(p.status) ? (vi ? 'Xong' : 'Done')
    : _lvFailed(p.status) ? (vi ? 'Lỗi' : 'Failed')
    : _lvActive(p.status) ? (vi ? 'Đang dựng' : 'Rendering') : (vi ? 'Chờ' : 'Waiting')

  return (
    <div className="cs-live">
      {/* LEFT — the scene being rendered now */}
      <div className="cs-live-focus">
        <div className="cs-live-label">{vi ? 'ĐANG DỰNG CẢNH' : 'BUILDING SCENE'}</div>
        {focus && <ContentFocusCard vi={vi} part={focus} meta={metaByN.get(focus.part_no)} roleLabel={roleOf(focus)} />}
      </div>
      {/* RIGHT — compact scene queue */}
      <div className="cs-live-queue">
        <div className="cs-live-queue-hd">{(vi ? 'Cảnh' : 'Scenes')} {doneCount}/{parts.length}</div>
        <div className="cs-live-rows">
          {parts.map((p) => {
            const st = _lvNorm(p.status)
            const isFocus = focus?.part_no === p.part_no
            return (
              <div key={p.part_no} className={`cs-live-row${isFocus ? ' is-focus' : ''}`}>
                <span className={`cs-live-glyph st-${st}`}>{_lvGlyph(p.status)}</span>
                <div className="cs-live-row-main">
                  <div className="cs-live-row-title"><span className="cs-live-row-n">#{p.part_no}</span> {roleOf(p)}</div>
                  {p.message && <div className="cs-live-row-sub">{p.message}</div>}
                </div>
                <span className={`cs-live-row-pct st-${st}`}>
                  {_lvActive(p.status) && (p.progress_percent ?? 0) > 0 ? `${Math.round(p.progress_percent ?? 0)}%` : statusLabel(p)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function ContentFocusCard({ vi, part, meta, roleLabel }: {
  vi: boolean; part: JobPart; meta?: SceneMeta; roleLabel: string
}) {
  const done = _lvDone(part.status)
  const active = _lvActive(part.status)
  const pct = active ? Math.max(2, Math.round(part.progress_percent ?? 0)) : (done ? 100 : 0)
  const statusLabel = done ? (vi ? 'Xong' : 'Done') : active ? (vi ? 'Đang dựng' : 'Rendering') : (vi ? 'Chờ' : 'Waiting')
  const narr = (meta?.narration || '').trim()
  return (
    <>
      <div className="cs-focus-preview">
        <ConicRing progress={pct} size={76}>{done ? <IconCheck size={24} /> : undefined}</ConicRing>
        <span className="cs-focus-n">#{part.part_no}</span>
        <span className={`cs-focus-status st-${_lvNorm(part.status)}`}>{statusLabel}</span>
      </div>
      <div>
        <div className="cs-focus-title">{roleLabel}</div>
        <div className="cs-focus-sub">{part.message || (vi ? 'Đang xử lý…' : 'Processing…')}</div>
      </div>
      <div className="cs-focus-track"><div className="cs-focus-fill" style={{ width: `${pct}%` }} /></div>
      {narr && <div className="cs-focus-narr">💬 {narr}</div>}
    </>
  )
}

// ── shared bits ─────────────────────────────────────────────────────────────

function Stepper({ vi, step }: { vi: boolean; step: 1 | 2 | 3 }) {
  const labels = vi ? ['Kịch bản', 'Duyệt kế hoạch', 'Render'] : ['Script', 'Review', 'Render']
  return (
    <div className="cs-stepper">
      {labels.map((l, i) => {
        const n = (i + 1) as 1 | 2 | 3
        const active = n === step
        const done = n < step
        const cls = `cs-step${active ? ' is-active' : ''}${done ? ' is-done' : ''}`
        return (
          <div key={l} className={cls}>
            <span className="cs-step-dot">{done ? '✓' : n}</span>
            {l}{i < 2 && <span className="cs-step-sep">›</span>}
          </div>
        )
      })}
    </div>
  )
}

// V2 Bold — gradient hero header (icon + bold title + subtitle). Shared across
// the Compose / Review / Render screens. Strings are passed in (already i18n'd
// by callers) and all colours come from tokens → dark + light both work.
function HeroHeader({ icon, title, subtitle }: { icon: string; title: string; subtitle?: React.ReactNode }) {
  return (
    <div className="cs-hero">
      <div className="cs-hero-row">
        <span className="cs-hero-icon" aria-hidden>{icon}</span>
        <div>
          <h1 className="cs-hero-h1">{title}</h1>
          {subtitle != null && <p className="cs-hero-sub">{subtitle}</p>}
        </div>
      </div>
    </div>
  )
}

// V2 Bold — a grouped config section with an icon chip + bold title.
function SectionCard({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <section className="cs-section">
      <div className="cs-section-hd">
        <span className="cs-section-icon" aria-hidden>{icon}</span>
        <span className="cs-section-title">{title}</span>
      </div>
      {children}
    </section>
  )
}

// V2 Bold — visual aspect-ratio picker (real frames instead of 3 text buttons).
function RatioPreview({ value, onChange }: { value: Ratio; onChange: (r: Ratio) => void }) {
  return (
    <div className="cs-ratio-row">
      {RATIOS.map((r) => (
        <button key={r} type="button" className={`cs-ratio${value === r ? ' is-on' : ''}`} onClick={() => onChange(r)}>
          <span className={`cs-ratio-frame cs-ratio-frame--${r}`} />
          <span className="cs-ratio-label">{RATIO_INFO[r].label}</span>
        </button>
      ))}
    </div>
  )
}

// V2 Bold — target-duration slider with a live value pill.
function DurationSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="cs-dur">
      <input className="cs-dur-range" type="range" min={15} max={600} step={5}
        value={value} onChange={(e) => onChange(Math.max(15, Math.min(600, Number(e.target.value) || 90)))} />
      <span className="cs-dur-val">{value}s</span>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cs-field">
      <div className="cs-field-label">{label}</div>
      {children}
    </div>
  )
}

function PublishField({ vi, label, value, multiline }: {
  vi: boolean; label: string; value: string; multiline?: boolean
}) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }
  return (
    <div className="cs-field">
      <div className="cs-field-label cs-pub-label">
        <span>{label}</span>
        <button className="cs-copy-btn" onClick={copy} disabled={!value}>
          {copied ? (vi ? '✓ Đã copy' : '✓ Copied') : (vi ? 'Copy' : 'Copy')}
        </button>
      </div>
      {multiline
        ? <textarea className="cs-textarea cs-textarea--sm" readOnly value={value} />
        : <input className="cs-input" readOnly value={value} />}
    </div>
  )
}

function seg(on: boolean): string {
  return `cs-seg${on ? ' is-on' : ''}`
}
