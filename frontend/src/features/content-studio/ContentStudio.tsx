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
import type { RenderRequest } from '@/types/api'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { Button } from '../../components/ui/Button'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { AIChip } from '../../components/ui/AIChip'
import { RATIO_INFO } from '../clip-studio/render/constants'
import type { Ratio } from '../clip-studio/render/types'
import {
  generateContentPlan, previewNarration, createProject, saveProject, getProject, listProjects,
  publishMeta, type ContentPlan, type ContentScene, type ContentProjectSummary, type PublishMeta,
  type DurationFit,
} from '../../api/content'
import { getDefaultOutputDir, putDefaultOutputDir } from '../../api/outputDir'
import { BASE_URL } from '../../api/client'

type BgKind = 'color' | 'image' | 'video'
type ImagenTier = 'fast' | 'standard' | 'ultra'
type Phase = 'script' | 'review'

const RATIOS: Ratio[] = ['r916', 'r11', 'r169']
const VOICE_LANGS = ['vi-VN', 'en-US', 'en-GB', 'ja-JP', 'ko-KR'] as const
const TTS_ENGINES = ['edge', 'xtts', 'gemini'] as const
const SUB_STYLES = ['tiktok_bounce_v1', 'capcut_box', 'opus_pop', 'minimal_clean'] as const
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
  visualProvider: 'local' | 'stock' | 'ai_image' | 'ai_video'
  imagenTier: ImagenTier
  outputDir: string
  tone: string
}

const DEFAULT_CFG: Config = {
  ratio: 'r916', targetDuration: 90, bgKind: 'color', bgColor: '#101820', bgAssetPath: '',
  voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
  subEnabled: true, subStyle: 'tiktok_bounce_v1', wordByWord: true,
  bgmPath: '', visualProvider: 'local', imagenTier: 'standard', outputDir: '', tone: '',
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

  const setCfgKey = <K extends keyof Config>(k: K, v: Config[K]) => setCfg((p) => ({ ...p, [k]: v }))

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
        voice={{ lang: cfg.voiceLang, gender: cfg.voiceGender, engine: cfg.ttsEngine }}
        onBack={() => setPhase('script')} onApprove={handleApproveRender}
      />
    )
  }
  return (
    <ScriptPhase
      vi={vi} script={script} setScript={setScript} cfg={cfg} setCfgKey={setCfgKey}
      busy={busy} error={error} onGenerate={handleGeneratePlan}
      drafts={drafts} onOpenDraft={openDraft}
    />
  )
}

// ── Phase 1: script + config ────────────────────────────────────────────────

function ScriptPhase({ vi, script, setScript, cfg, setCfgKey, busy, error, onGenerate, drafts, onOpenDraft }: {
  vi: boolean; script: string; setScript: (s: string) => void
  cfg: Config; setCfgKey: <K extends keyof Config>(k: K, v: Config[K]) => void
  busy: boolean; error: string | null; onGenerate: () => void
  drafts: ContentProjectSummary[]; onOpenDraft: (id: string) => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
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
      <div className="cs-header">
        <h1 className="cs-h1">Content Studio</h1>
        <p className="cs-sub">{vi
          ? 'Bước 1 — Viết kịch bản. AI Content Director sẽ lập kế hoạch cảnh + lời kể để bạn duyệt trước khi render.'
          : 'Step 1 — Write the script. The AI Content Director drafts scenes + narration for you to review before rendering.'}</p>
      </div>

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

        <section className="cs-card cs-card--flush">
          <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Cấu hình' : 'Configuration'}</span></div>

          <Field label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
            <div className="cs-seg-row">
              {RATIOS.map((r) => <button key={r} className={seg(cfg.ratio === r)} onClick={() => setCfgKey('ratio', r)}>{RATIO_INFO[r].label}</button>)}
            </div>
          </Field>
          <Field label={vi ? 'Thời lượng mục tiêu (giây)' : 'Target duration (sec)'}>
            <input type="number" min={15} max={600} className="cs-input" value={cfg.targetDuration}
              onChange={(e) => setCfgKey('targetDuration', Math.max(15, Math.min(600, Number(e.target.value) || 90)))} />
          </Field>
          <Field label={vi ? 'Nền' : 'Background'}>
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
          <Field label={vi ? 'Nguồn hình ảnh (AI/Stock — tuỳ chọn)' : 'Visual source (AI/Stock — optional)'}>
            <select className="cs-input" value={cfg.visualProvider} onChange={(e) => setCfgKey('visualProvider', e.target.value as Config['visualProvider'])}>
              <option value="local">{vi ? 'Nền tự chọn (offline)' : 'Chosen background (offline)'}</option>
              <option value="stock">{vi ? 'Ảnh Stock (Pexels/Pixabay — cần API key)' : 'Stock images (Pexels/Pixabay — needs API key)'}</option>
              <option value="ai_image">{vi ? 'Ảnh AI (Imagen/DALL·E — cần API key)' : 'AI Image (Imagen/DALL·E — needs API key)'}</option>
              <option value="ai_video">{vi ? 'Video AI (Veo — cần API key, chậm)' : 'AI Video (Veo — needs API key, slow)'}</option>
            </select>
            {cfg.visualProvider !== 'local' && (
              <div className="cs-hint">
                {vi ? 'Mỗi cảnh sinh/tải ảnh từ "visual prompt". Thiếu key/mạng → tự dùng nền đã chọn.' : 'Each scene fetches/generates an image from its visual prompt. Missing key/network → falls back to your background.'}
              </div>
            )}
          </Field>
          {cfg.visualProvider === 'ai_image' && (
            <Field label={vi ? 'Chất lượng ảnh Imagen 4' : 'Imagen 4 quality'}>
              <div className="cs-seg-row">
                {(['fast', 'standard', 'ultra'] as ImagenTier[]).map((tier) => (
                  <button key={tier} className={seg(cfg.imagenTier === tier)} onClick={() => setCfgKey('imagenTier', tier)}>
                    {tier === 'fast' ? (vi ? 'Nhanh' : 'Fast') : tier === 'standard' ? (vi ? 'Tiêu chuẩn' : 'Standard') : 'Ultra'}
                  </button>
                ))}
              </div>
              <div className="cs-hint">
                {cfg.imagenTier === 'fast'
                  ? (vi ? 'Nhanh & rẻ nhất — hợp bản nháp / nhiều ảnh.' : 'Fastest & cheapest — good for drafts / many images.')
                  : cfg.imagenTier === 'ultra'
                  ? (vi ? 'Chất lượng cao nhất, chậm & tốn key hơn — chỉ 1 ảnh/cảnh.' : 'Highest quality, slower & costs more — 1 image/scene.')
                  : (vi ? 'Cân bằng chất lượng / chi phí (khuyến nghị).' : 'Balanced quality / cost (recommended).')}
              </div>
            </Field>
          )}
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
                  {SUB_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
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
        </section>
      </div>

      <div className="cs-footer">
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" disabled={!charCount || busy} onClick={onGenerate}>
          {busy ? (vi ? 'AI đang phân tích…' : 'AI analyzing…') : (vi ? 'Tạo kế hoạch (AI)' : 'Generate Content Plan')}
        </Button>
      </div>
    </div>
  )
}

// ── Phase 2: review + edit plan ─────────────────────────────────────────────

interface VoiceCfg { lang: string; gender: 'female' | 'male'; engine: string }

function ReviewPhase({ vi, plan, setPlan, busy, error, durationFit, visualProvider, targetDuration, voice, onBack, onApprove }: {
  vi: boolean; plan: ContentPlan; setPlan: (p: ContentPlan) => void
  busy: boolean; error: string | null
  durationFit: DurationFit | null; visualProvider: Config['visualProvider']; targetDuration: number
  voice: VoiceCfg; onBack: () => void; onApprove: () => void
}) {
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
      <div className="cs-header">
        <h1 className="cs-h1">{vi ? 'Duyệt kế hoạch AI' : 'Review AI Plan'}</h1>
        <p className="cs-sub">
          {plan.topic ? <b>{plan.topic}</b> : null}
          {plan.video_style ? ` · ${plan.video_style}` : ''}
          {' · '}{plan.scenes.length} {vi ? 'cảnh' : 'scenes'}
          {' · '}{vi ? 'Sửa lời kể / cảm xúc / thời lượng, thêm-xoá-đổi thứ tự cảnh trước khi render.' : 'Edit narration / emotion / duration, add-remove-reorder before rendering.'}
        </p>
      </div>

      <AiInsights vi={vi} plan={plan} durationFit={durationFit} visualProvider={visualProvider} targetDuration={targetDuration} />

      <div className="cs-scene-list">
        {plan.scenes.map((s, i) => (
          <SceneRow key={i} vi={vi} scene={s} index={i} total={plan.scenes.length} voice={voice}
            onChange={(patch) => updateScene(i, patch)} onRemove={() => removeScene(i)} onMove={(d) => moveScene(i, d)} />
        ))}
        <div><Button variant="ghost" size="sm" onClick={addScene}>+ {vi ? 'Thêm cảnh' : 'Add scene'}</Button></div>
      </div>

      <div className="cs-footer">
        <Button variant="ghost" onClick={onBack} disabled={busy}>{vi ? '← Quay lại kịch bản' : '← Back to script'}</Button>
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" disabled={!canRender} onClick={onApprove}>
          {busy ? (vi ? 'Đang gửi…' : 'Starting…') : (vi ? 'Duyệt & Render' : 'Approve & Render')}
        </Button>
      </div>
    </div>
  )
}

function SceneRow({ vi, scene, index, total, voice, onChange, onRemove, onMove }: {
  vi: boolean; scene: ContentScene; index: number; total: number; voice: VoiceCfg
  onChange: (patch: Partial<ContentScene>) => void; onRemove: () => void; onMove: (dir: -1 | 1) => void
}) {
  const [previewing, setPreviewing] = useState(false)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [dur, setDur] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const hasText = !!(scene.narration || '').trim()
  const audit = sceneAudit(scene)

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
      <div className="cs-header">
        <h1 className="cs-h1">{vi ? 'Đang render…' : 'Rendering…'}</h1>
        <p className="cs-sub">{jobMessage || stage || ''}</p>
      </div>
      <section className="cs-card">
        <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Tiến độ' : 'Progress'}</span></div>
        <ProgressBar value={pct} variant={isTerminal ? (ok ? 'success' : 'error') : 'default'} />
        <div className="cs-hint">
          {vi ? 'Giai đoạn' : 'Stage'}: <b>{stage || '—'}</b>{planReady && <> · {vi ? 'kế hoạch sẵn sàng' : 'plan ready'}</>}
        </div>
      </section>
      {liveParts.length > 0 && (
        <section className="cs-card">
          <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Cảnh' : 'Scenes'} ({liveParts.length})</span></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {liveParts.map((p) => (
              <div key={p.part_no} className="cs-part-row">
                <span>#{p.part_no}</span>
                <span className="cs-part-msg">{p.message || p.status}</span>
                <span className={statusClass(p.status)}>{p.status} {p.progress_percent ? `${p.progress_percent}%` : ''}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      {isTerminal && (
        <section className="cs-card" style={{ borderColor: ok ? 'var(--ok)' : 'var(--fail)' }}>
          <div className="cs-card-hd">
            <span className="cs-card-title" style={{ color: ok ? 'var(--ok)' : 'var(--fail)' }}>
              {ok ? (vi ? '✓ Hoàn thành' : '✓ Done') : (vi ? '✕ Thất bại' : '✕ Failed')}
            </span>
          </div>
          <p className="cs-terminal-msg">{jobMessage || error || ''}</p>
          <div className="cs-row">
            <Button variant="primary" onClick={onNew}>{vi ? 'Tạo video mới' : 'New content video'}</Button>
            {ok && plan && (
              <Button variant="ghost" disabled={pubBusy} onClick={genPublish}>
                {pubBusy ? (vi ? 'Đang tạo…' : 'Generating…') : (vi ? 'Tạo tiêu đề/mô tả (AI)' : 'Generate title/description (AI)')}
              </Button>
            )}
          </div>
          {pubErr && <div className="cs-hint" style={{ color: 'var(--fail)' }}>{pubErr}</div>}
          {pubMeta && (
            <div style={{ marginTop: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Field label={vi ? 'Tiêu đề' : 'Title'}>
                <input className="cs-input" readOnly value={pubMeta.title} />
              </Field>
              <Field label={vi ? 'Mô tả' : 'Description'}>
                <textarea className="cs-textarea cs-textarea--sm" readOnly value={pubMeta.description} />
              </Field>
              <Field label={vi ? 'Thẻ' : 'Tags'}>
                <input className="cs-input" readOnly value={(pubMeta.tags || []).join(', ')} />
              </Field>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cs-field">
      <div className="cs-field-label">{label}</div>
      {children}
    </div>
  )
}

function statusClass(status: string): string {
  if (status === 'done') return 'cs-status-ok'
  if (status === 'failed') return 'cs-status-fail'
  if (status === 'rendering') return 'cs-status-run'
  return 'cs-status-idle'
}

function seg(on: boolean): string {
  return `cs-seg${on ? ' is-on' : ''}`
}
