import { useState, useRef, useEffect } from 'react'
import './RenderWorkflow.css'
import type { Lang } from '../ClipStudio'
import { useRenderStore } from '@/stores/renderStore'
import { useUIStore } from '@/stores/uiStore'
import { useRenderSocket } from '@/hooks/useRenderSocket'
import { prepareSource, cancelRender, cancelPrepareSource, retryRender, resumeRender } from '@/api/render'
import type { PrepareSourceResponse } from '@/api/render'
import { getJobHistory, getJobParts, getJobQualitySummary, getJobRanking } from '@/api/jobs'
import type { RenderRequest, JobPart, QualityReport, PartRankResult } from '@/types/api'
import { useT, ERROR_KIND_KEY, ERROR_FIX_STEPS } from './i18n'
import type { Step, CfgTab, ConfigState, Source } from './types'
import { PRESETS, RATIO_INFO } from './constants'
import { StepConfigure } from './steps/StepConfigure'
import { StepRendering } from './steps/StepRendering'
import { StepResults } from './steps/StepResults'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'

// ── Root component ────────────────────────────────────────────────────────────
export function RenderWorkflow({ lang }: { lang: Lang }) {
  const t = useT(lang)
  const [step, setStep]       = useState<Step>(1)
  const [sources, setSources] = useState<Source[]>([])

  const [prepareResult, setPrepareResult] = useState<PrepareSourceResponse | null>(null)
  const [isPreparing, setIsPreparing]     = useState(false)
  const [prepareError, setPrepareError]   = useState<string | null>(null)
  const prepareCancelledRef               = useRef(false)
  const prepareAbortRef                   = useRef<AbortController | null>(null)
  // isSubmitting locks the Start-Render button while a POST /api/render/process
  // is in flight. Without this, a double-click (or two clicks across a slow
  // network round-trip) submits two identical render jobs with different
  // UUIDs — backend's job_id dedup doesn't catch it because the IDs differ.
  // See bug investigation 2026-06-15 (jobs 68b83de8 + fab6af2b on same source).
  const [isSubmitting, setIsSubmitting]   = useState(false)

  const [cfgTab, setCfgTab] = useState<CfgTab>('ai')
  const [cfg, setCfg] = useState<ConfigState>(() => ({
    preset: 'viral', ratio: 'r916', minSec: 30, maxSec: 60, clipCount: 5,
    style: 'slay_soft_01', platform: 'tiktok', aiMarket: 'us',
    aiEnabled: true, multiVariant: false, ctaEnabled: false, ctaType: 'auto',
    hookApplyEnabled: false, hookOverlayEnabled: false, structureBias: null,
    clipLock: [], clipExclude: [],
    motionCrop: false,
    subEnabled: true, subStyle: 'tiktok_bounce_v1',
    subHighlight: true, subFontSize: 0, subTranslate: false, subTranslateLang: 'en',
    subEmphasis: null, partOrder: 'viral',
    assetLogoPath: null, assetIntroPath: null, assetOutroPath: null, assetMusicProfile: null,
    whisperModel: 'auto',
    narrEnabled: false, voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
    voiceSource: 'subtitle', voiceText: '', voiceMixMode: 'replace_original',
    outputDir: '',
    renderProfile: 'balanced',
    targetDuration: 90, outputCount: 1, videoType: 'auto',
    energyStyle: 'auto', hookStrength: 'balanced', focusMode: 'auto',
    outputLanguage: 'auto', narrationStyle: 'auto',
    subDensity: 'auto', subLanguage: 'auto',
    aiAnalysisMode: 'hybrid',
    aiCloudProvider:  (localStorage.getItem('rw_ai_cloud_provider') as 'gemini' | 'openai' | 'claude') ?? 'gemini',
    aiCloudApiKey:    localStorage.getItem('rw_ai_cloud_api_key') ?? '',
    aiCloudModel:     '',
    aiContentDriven:  false,
    llmEnabled:   true,
    aiProvider:   (localStorage.getItem('rw_ai_provider') as 'gemini' | 'openai' | 'claude') ?? 'gemini',
    llmModel:     '',
    llmLanguage:  'auto',
  }))

  const [jobId, setJobId]               = useState<string | null>(null)
  const [submitError, setSubmitError]   = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)

  const [parts, setParts]                   = useState<JobPart[]>([])
  const [partScores, setPartScores]         = useState<Record<number, number>>({})
  const [partRanks, setPartRanks]           = useState<Record<number, PartRankResult>>({})
  const [qualityReports, setQualityReports] = useState<Record<number, QualityReport | null>>({})
  const [qualityLoadFailed, setQualityLoadFailed] = useState(false)
  const [partsLoading, setPartsLoading]     = useState(false)
  const [allDataLoaded, setAllDataLoaded]   = useState(false)
  const [isRetrying, setIsRetrying]         = useState(false)
  const [rawMsgOpen, setRawMsgOpen]         = useState(false)

  const { submitRender } = useRenderStore()
  const addNotification = useUIStore((s) => s.addNotification)
  const { stage, jobStatus, progress, jobMessage, isTerminal, isReconnecting: wsReconnecting, liveParts, error: wsError, errorKind } = useRenderSocket(jobId)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Auto-reattach to active job on mount ────────────────────────────────────
  // Bug fix 2026-06-15: when the user navigates away from the Rendering
  // screen (e.g. clicks History tab, then comes back to Render), the local
  // jobId is null and they land on Step 1 (Source). Clicking Start Render
  // hits the server dedup with HTTP 409 because the previous job is still
  // running. Detect that on mount and jump straight to the rendering view
  // so the user can monitor / cancel without bouncing through Source.
  useEffect(() => {
    if (jobId) return // already attached
    let cancelled = false
    ;(async () => {
      try {
        const res = await getJobHistory(10, 0)
        if (cancelled) return
        const active = res.items.find(
          (j) => j.status === 'running' || j.status === 'queued',
        )
        if (active) {
          setJobId(active.job_id)
          setStep(3)
        }
      } catch {
        // backend unreachable — let user proceed via normal flow
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!jobId || !isTerminal) return
    setQualityLoadFailed(false)
    setPartsLoading(true)
    setAllDataLoaded(false)

    const withTimeout = <T,>(p: Promise<T>, ms: number): Promise<T | undefined> =>
      Promise.race([p, new Promise<undefined>((resolve) => setTimeout(resolve, ms))])

    const partsP = getJobParts(jobId).then(setParts)
    const qualityP = getJobQualitySummary(jobId, true)
      .then((summary) => {
        const scores: Record<number, number> = {}
        const reports: Record<number, QualityReport | null> = {}
        summary.parts?.forEach((p) => {
          scores[p.part_no] = p.score
          reports[p.part_no] = p.report ?? null
        })
        setPartScores(scores)
        setQualityReports(reports)
      })
      .catch(() => setQualityLoadFailed(true))
    const rankingP = getJobRanking(jobId).then(setPartRanks).catch(() => {})

    Promise.all([
      withTimeout(partsP, 12_000),
      withTimeout(qualityP, 12_000),
      withTimeout(rankingP, 12_000),
    ]).finally(() => {
      setPartsLoading(false)
      setAllDataLoaded(true)
    })
  }, [jobId, isTerminal])

  // Auto-advance to results after completion (success + partial success).
  // Gated on allDataLoaded so parts/quality/ranking are ready before the step change.
  useEffect(() => {
    if (!isTerminal || step !== 3 || !allDataLoaded) return
    const s = jobStatus ?? ''
    const skipAdvance = s === 'failed' || s === 'interrupted' || s === 'cancelled'
    if (skipAdvance) return
    const timer = setTimeout(() => setStep(4), 300)
    return () => clearTimeout(timer)
  }, [isTerminal, jobStatus, step, allDataLoaded])

  // E-2 — toast notification on job terminal
  useEffect(() => {
    if (!isTerminal || !jobId) return
    const s = jobStatus ?? ''
    const doneCount = progress?.completed_parts ?? 0
    if (s === 'completed' || s === 'completed_with_errors' || s === 'partial') {
      addNotification({
        type: 'success',
        title: 'Render complete',
        message: doneCount > 0 ? `${doneCount} clip${doneCount !== 1 ? 's' : ''} ready` : undefined,
      })
    } else if (s === 'failed') {
      addNotification({ type: 'error', title: 'Render failed', message: jobMessage || undefined })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTerminal])

  // ── Source actions ──────────────────────────────────────────────────────────
  function removeSource(i: number) { setSources((p) => p.filter((_, idx) => idx !== i)) }

  async function goToConfigure() {
    if (sources.length === 0) return
    const src = sources[0]
    prepareCancelledRef.current = false
    const abort = new AbortController()
    prepareAbortRef.current = abort
    setIsPreparing(true)
    setPrepareError(null)
    try {
      const result = await prepareSource({
        source_mode: 'local',
        source_video_path: src.value,
      }, abort.signal)
      if (prepareCancelledRef.current) {
        cancelPrepareSource(result.session_id).catch(() => {})
        return
      }
      setPrepareResult(result)
      setCfg((prev) => ({ ...prev, outputDir: result.export_dir || prev.outputDir }))
      setStep(2)
    } catch (e) {
      if (!prepareCancelledRef.current) {
        setPrepareError(e instanceof Error ? e.message : 'Failed to prepare source')
      }
    } finally {
      setIsPreparing(false)
    }
  }

  function handleChangeSource() {
    setSources([])
    setPrepareResult(null)
    setStep(1)
  }

  function setCfgKey<K extends keyof ConfigState>(k: K, v: ConfigState[K]) {
    if (k === 'aiCloudApiKey')   localStorage.setItem('rw_ai_cloud_api_key', v as string)
    if (k === 'aiCloudProvider') localStorage.setItem('rw_ai_cloud_provider', v as string)
    if (k === 'aiProvider')      localStorage.setItem('rw_ai_provider', v as string)
    setCfg((p) => ({ ...p, [k]: v }))
  }
  function applyPreset(id: string) {
    const p = PRESETS.find((x) => x.id === id)
    if (!p) return
    setCfg((prev) => ({ ...prev, preset: id, platform: p.platform, ratio: 'r916' }))
  }
  async function pickOutputDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setCfgKey('outputDir', dir)
  }

  // ── Render actions ──────────────────────────────────────────────────────────
  async function handleStartRender() {
    if (isSubmitting) return  // hard guard against double-submit
    setIsSubmitting(true)
    setSubmitError(null)
    const src = sources[0]
    const payload: RenderRequest = {
      source_mode:       'local',
      source_video_path: src.value,
      output_dir:          cfg.outputDir || 'output',
      aspect_ratio:        RATIO_INFO[cfg.ratio].api,
      min_part_sec:        cfg.minSec,
      max_part_sec:        cfg.maxSec,
      // T1.4 follow-up — Audit 2026-06-08: removed `max_export_parts:
      // cfg.outputCount` from the wire (engine reads `output_count`
      // instead via render_pipeline.py:576). Sending both was wire-
      // duplication; only output_count survives.
      add_subtitle:                cfg.subEnabled,
      subtitle_style:              cfg.subStyle,
      highlight_per_word:          cfg.subHighlight,
      sub_font_size:               cfg.subFontSize,
      subtitle_translate_enabled:  cfg.subTranslate || undefined,
      subtitle_target_language:    cfg.subTranslate ? cfg.subTranslateLang : undefined,
      // T1.4 follow-up — Audit 2026-06-08: removed `part_order:
      // cfg.partOrder`. The BE validator at models/render.py:451-463
      // coerces the value to "viral" then no engine consumer reads it
      // (FINDING-C01 closure). Pure UI deceit on the wire.
      // UP26 Pro Timeline Steering — audit-2026-06-08 closures.
      //   structure_bias    — Strategic-1c (ranking formula re-weight).
      //   subtitle_emphasis — Strategic-1c (sub_font_size multiplier).
      //   clip_lock / clip_exclude — Strategic-1/1b (LLM prompt + local
      //     filter). FE state vars `clipLock` / `clipExclude` carry the
      //     ranges but the FE has no TimeRange editor yet; they remain
      //     API-only until a TimeRange editor lands. `[]` is the
      //     no-op default — sending it has no effect on selection.
      structure_bias:    cfg.structureBias ?? undefined,
      subtitle_emphasis: cfg.subEmphasis ?? undefined,
      voice_enabled:               cfg.narrEnabled,
      voice_source:        cfg.narrEnabled ? cfg.voiceSource : undefined,
      voice_text:          cfg.narrEnabled && cfg.voiceSource === 'manual' ? cfg.voiceText : undefined,
      voice_language:      cfg.narrEnabled ? cfg.voiceLang as 'vi-VN' | 'ja-JP' | 'en-US' | 'en-GB' : undefined,
      voice_gender:        cfg.narrEnabled ? cfg.voiceGender : undefined,
      tts_engine:          cfg.narrEnabled ? cfg.ttsEngine : undefined,
      voice_mix_mode:      cfg.narrEnabled ? cfg.voiceMixMode : undefined,
      // LLM segment selection — canonical llm_* fields. API keys from server .env.
      llm_enabled:  cfg.llmEnabled || undefined,
      ai_provider:  cfg.llmEnabled ? cfg.aiProvider : undefined,
      llm_model:    cfg.llmEnabled && cfg.llmModel ? cfg.llmModel : undefined,
      llm_language: cfg.llmEnabled && cfg.llmLanguage !== 'auto' ? cfg.llmLanguage : undefined,
      multi_variant:       cfg.multiVariant || undefined,
      cta_enabled:         cfg.ctaEnabled || undefined,
      cta_type:            cfg.ctaEnabled ? cfg.ctaType : undefined,
      hook_apply_enabled:  cfg.hookApplyEnabled || undefined,
      hook_overlay_enabled: cfg.hookOverlayEnabled || undefined,
      // T1.4 — Audit 2026-06-08 closure: removed `ai_auto_cut`,
      // `ai_use_semantic_hooks`, `ai_render_influence_enabled`,
      // `ai_beat_pulse_enabled` from the wire (Phase-G zombies — gated
      // by ctx.ai_edit_plan which is hardcoded None at
      // render_pipeline.py:931, so setting these `true` had zero
      // behavioural effect). Sprint 3 3E Subset B's rationale for
      // sending them was to keep new jobs aligned with the BE defaults;
      // now that they're outside the Public surface they can't even
      // reach the BE, so the alignment is automatic.
      motion_aware_crop:   cfg.focusMode === 'face' || cfg.focusMode === 'object',
      target_platform:     cfg.platform,
      effect_preset:       cfg.style,
      render_profile:      cfg.renderProfile,
      whisper_model:       cfg.whisperModel !== 'auto' ? cfg.whisperModel : undefined,
      ai_target_market:    cfg.aiMarket || undefined,
      target_duration:     cfg.targetDuration,
      output_count:        cfg.outputCount,
      video_type:          cfg.videoType,
      hook_strength:       cfg.hookStrength,
      reframe_mode:        cfg.focusMode,
      // T1.4 — Audit 2026-06-08 closure: removed `energy_style`,
      // `output_language`, `narration_style` (v2 vision dead — never
      // consumed by the render engine) and `asset_music_profile`
      // (UP27 — never wired). UI form state for these still exists
      // (cfg.energyStyle / cfg.outputLanguage / cfg.narrationStyle /
      // cfg.assetMusicProfile); cleanup of those form widgets is a
      // follow-up task.
      asset_logo_path:     cfg.assetLogoPath ?? undefined,
      asset_intro_path:    cfg.assetIntroPath ?? undefined,
      asset_outro_path:    cfg.assetOutroPath ?? undefined,
    }
    try {
      const id = await submitRender(payload)
      setJobId(id)
      setStep(3)
      // intentional: do NOT reset isSubmitting on success — step changed
      // to 3 so the Configure-screen button unmounts. Resetting would race
      // with React's commit and let a stray click resubmit before unmount.
    } catch (e) {
      // Extract a user-friendly message. Backend dedup (409) returns a
      // detail string explaining the duplicate is already running; surface
      // it verbatim instead of "API error 409: …".
      let msg = 'Failed to start render'
      let dupJobId: string | null = null
      if (e && typeof e === 'object' && 'status' in e && 'detail' in e) {
        const apiErr = e as { status: number; detail: unknown }
        msg = typeof apiErr.detail === 'string'
          ? apiErr.detail
          : JSON.stringify(apiErr.detail)
        // On 409 dedup the detail looks like:
        //   "A render job for this source is already in progress
        //    (job_id=<uuid>). Wait for it to finish or cancel it first."
        // Extract the uuid and jump straight to that job's rendering
        // screen — re-using the running job is what the user actually
        // wants 99% of the time. They can still cancel from there.
        if (apiErr.status === 409 && typeof apiErr.detail === 'string') {
          const m = apiErr.detail.match(/job_id=([0-9a-f-]{36})/i)
          if (m) dupJobId = m[1]
        }
      } else if (e instanceof Error) {
        msg = e.message
      }
      if (dupJobId) {
        setJobId(dupJobId)
        setStep(3)
        setIsSubmitting(false)
        addNotification({
          type: 'info',
          title: lang === 'VI' ? 'Mở job đang chạy' : 'Opened active job',
          message: lang === 'VI'
            ? 'Job render cho source này đang chạy — đã chuyển sang màn theo dõi.'
            : 'A render for this source is already running — switched to monitor view.',
          duration: 5000,
        })
      } else {
        setSubmitError(msg)
        setIsSubmitting(false)  // re-enable on failure so user can retry
      }
    }
  }

  async function handleCancelRender() {
    if (!jobId || isCancelling) return
    setIsCancelling(true)
    try {
      await cancelRender(jobId)
    } catch { /* ignore */ }
    finally { setIsCancelling(false) }
  }

  async function handleRetryRender() {
    if (!jobId || isRetrying) return
    setIsRetrying(true)
    try {
      const res = await retryRender(jobId)
      setJobId(res.job_id)
      setParts([]); setPartScores({}); setQualityReports({}); setQualityLoadFailed(false)
      setStep(3)
    } catch { /* stay on current step */ }
    finally { setIsRetrying(false) }
  }

  async function handleResumeRender() {
    if (!jobId || isRetrying) return
    setIsRetrying(true)
    try {
      const res = await resumeRender(jobId)
      setJobId(res.job_id)
      setParts([]); setPartScores({}); setQualityReports({}); setQualityLoadFailed(false)
      setStep(3)
    } catch { /* stay on current step */ }
    finally { setIsRetrying(false) }
  }

  function handleNewRender() {
    setStep(1); setSources([]); setJobId(null)
    setPrepareResult(null); setParts([]); setPartScores({}); setQualityReports({})
    // Reset submit guard so the next Start-Render click is accepted.
    // Without this the button stays disabled after returning from Result.
    setIsSubmitting(false)
    setSubmitError(null)
  }

  const stepMeta = [
    { label: t.stepSrc, sub: t.stepSrcSub },
    { label: t.stepCfg, sub: t.stepCfgSub },
    { label: t.stepRnd, sub: t.stepRndSub },
    { label: t.stepRes, sub: t.stepResSub },
  ]
  const doneParts = parts.filter(p => p.status === 'done')

  // ── Step strip ──────────────────────────────────────────────────────────────
  return (
    <div className="rw-root">
      <div className="step-nav">
        {stepMeta.map(({ label, sub }, i) => {
          const n = (i + 1) as Step
          const cls = n === step ? 'active' : n < step ? 'done' : ''
          return (
            <div key={i} style={{ display: 'contents' }}>
              {i > 0 && <div className="rw-step-sep" />}
              <div className={`rw-step ${cls}`} onClick={() => {
                if (n === step) return
                if (n < step) { setStep(n); return }
                // forward navigation: allow returning to step already reached
                if (n === 3 && jobId) setStep(3)
                else if (n === 4 && jobId && isTerminal) setStep(4)
              }}>
                <span className="rw-step-num">{n < step ? '✓' : n}</span>
                <div className="rw-step-info">
                  <div className="rw-step-label">{label}</div>
                  <div className="rw-step-sub">{sub}</div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Preparing overlay */}
      {isPreparing && (
        <div className="step-screen active" style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '20px', background: 'radial-gradient(ellipse at 50% 50%, rgba(123,97,255,.05) 0%, transparent 70%)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', maxWidth: '480px', textAlign: 'center' }}>
            <div style={{ width: '48px', height: '48px', border: '3px solid var(--border-hi)', borderTop: '3px solid var(--accent)', borderRadius: '50%', animation: 'rw-spin 0.8s linear infinite' }} />
            <div style={{ fontFamily: 'var(--fh)', fontSize: '16px', fontWeight: 700, letterSpacing: '1px', background: 'var(--grad)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              {lang === 'VI' ? 'ĐANG CHUẨN BỊ NGUỒN' : 'PREPARING SOURCE'}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-3)', lineHeight: 1.6 }}>
              {lang === 'VI' ? 'Đang phân tích file video…' : 'Probing local video file…'}
            </div>
            <button className="btn-back" onClick={() => { prepareCancelledRef.current = true; prepareAbortRef.current?.abort(); setIsPreparing(false) }}>
              {lang === 'VI' ? 'HỦY' : 'CANCEL'}
            </button>
          </div>
          <style>{`@keyframes rw-spin { to { transform: rotate(360deg) } }`}</style>
        </div>
      )}

      {!isPreparing && (
        <>
          {/* STEP 1 */}
          <div className={`step-screen${step === 1 ? ' active' : ''}`}>
            <div className="src-screen">
              {/* Atmospheric background — violet/pink blobs + grid */}
              <div className="src-bg" aria-hidden="true">
                <div className="src-bg-blob src-bg-blob-1" />
                <div className="src-bg-blob src-bg-blob-2" />
                <div className="src-bg-grid" />
              </div>

              <div className="src-content">
                {/* Eyebrow chip + hero */}
                <div className="src-hero">
                  <span className="src-eyebrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 3l2.4 5.6L20 11l-5.6 2.4L12 19l-2.4-5.6L4 11l5.6-2.4z"/>
                    </svg>
                    {lang === 'VI' ? 'AI sẵn sàng' : 'AI ready to clip'}
                  </span>
                  <h1 className="src-hero-title">
                    {lang === 'VI'
                      ? <>Cắt video dài thành <span className="src-grad-word">clip viral</span>.</>
                      : <>Turn long videos into <span className="src-grad-word">viral clips</span>.</>}
                  </h1>
                  <p className="src-hero-sub">
                    {lang === 'VI'
                      ? 'Thả file lên đây — AI sẽ phân tích, chọn khoảnh khắc hay nhất và xuất clip sẵn sàng cho TikTok, Reels và Shorts.'
                      : 'Drop a file and let AI pick the best moments. Ready for TikTok, Reels and Shorts in minutes.'}
                  </p>
                </div>

                {/* Drop zone — illustrated */}
                <div className="src-cards">
                  <button
                    type="button"
                    className={`src-card highlight${sources.length > 0 ? ' has-file' : ''}`}
                    onClick={async () => {
                      const picked = await window.electronAPI?.pickVideoFile?.()
                      if (picked) setSources([{ value: picked }])
                      else fileInputRef.current?.click()
                    }}
                  >
                    <div className="src-illu" aria-hidden="true">
                      <svg width="120" height="96" viewBox="0 0 120 96" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                          <linearGradient id="gradFrame" x1="0" y1="0" x2="1" y2="1">
                            <stop offset="0" stopColor="#8b5cf6"/>
                            <stop offset="1" stopColor="#ec4899"/>
                          </linearGradient>
                          <linearGradient id="gradPlay" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0" stopColor="#ffffff" stopOpacity="0.95"/>
                            <stop offset="1" stopColor="#ffffff" stopOpacity="0.85"/>
                          </linearGradient>
                          <filter id="dropGlow" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="2"/>
                          </filter>
                        </defs>
                        {/* Back frame */}
                        <rect x="14" y="20" width="68" height="50" rx="10" fill="url(#gradFrame)" opacity="0.30" transform="rotate(-8 48 45)"/>
                        {/* Middle frame */}
                        <rect x="22" y="14" width="72" height="56" rx="11" fill="url(#gradFrame)" opacity="0.55" transform="rotate(-3 58 42)"/>
                        {/* Top frame with play */}
                        <rect x="30" y="10" width="78" height="62" rx="12" fill="url(#gradFrame)"/>
                        <circle cx="69" cy="41" r="18" fill="rgba(255,255,255,0.16)"/>
                        <path d="M64 33l14 8-14 8z" fill="url(#gradPlay)"/>
                        {/* Sparkles */}
                        <g fill="#fff" opacity="0.9">
                          <path d="M104 18l1.5 3.5L109 23l-3.5 1.5L104 28l-1.5-3.5L99 23l3.5-1.5z"/>
                          <path d="M16 70l1 2.4L19.4 73.4l-2.4 1L16 76.8l-1-2.4L12.6 73.4l2.4-1z"/>
                          <circle cx="110" cy="50" r="1.6"/>
                          <circle cx="8" cy="32" r="1.4"/>
                        </g>
                      </svg>
                    </div>
                    <div className="src-card-body">
                      <div className="src-card-title">
                        {lang === 'VI' ? 'Thả file vào đây' : 'Drop your video here'}
                      </div>
                      <div className="src-card-desc">
                        {lang === 'VI' ? 'hoặc bấm để chọn từ máy' : 'or click to browse your computer'}
                      </div>
                    </div>
                    <div className="src-card-meta">
                      <span className="src-card-badge">MP4 · MOV · MKV · WEBM</span>
                      <span className="src-card-dot" aria-hidden="true">·</span>
                      <span className="src-card-hint">{lang === 'VI' ? 'Khuyến nghị ≤ 4K · 2 GB' : 'Recommended ≤ 4K · 2 GB'}</span>
                    </div>
                    <div className="src-card-shine" aria-hidden="true" />
                  </button>
                </div>

                {/* Platform support row */}
                <div className="src-platforms">
                  <span className="src-platforms-label">
                    {lang === 'VI' ? 'Sẵn sàng đăng lên' : 'Ready to publish on'}
                  </span>
                  <div className="src-platforms-list">
                    <span className="src-platform" data-p="youtube">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M23 12s0-3.7-.5-5.5c-.3-1-1-1.8-2-2C18.7 4 12 4 12 4s-6.7 0-8.5.5c-1 .2-1.7 1-2 2C1 8.3 1 12 1 12s0 3.7.5 5.5c.3 1 1 1.8 2 2 1.8.5 8.5.5 8.5.5s6.7 0 8.5-.5c1-.2 1.7-1 2-2 .5-1.8.5-5.5.5-5.5zM10 15.5v-7l6 3.5-6 3.5z"/></svg>
                      YouTube
                    </span>
                    <span className="src-platform" data-p="tiktok">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M16 3v3.4a5 5 0 0 0 4 3.4v3.6a8.6 8.6 0 0 1-4-1.2v7c0 3.5-2.7 5.8-6 5.8-3 0-5.5-2.4-5.5-5.4S7 14 10 14c.5 0 1 .1 1.5.2v3.5c-.5-.2-1-.3-1.5-.3-1.2 0-2.2 1-2.2 2.2 0 1.2 1 2.2 2.2 2.2 1.3 0 2.5-.9 2.5-2.4V3H16z"/></svg>
                      TikTok
                    </span>
                    <span className="src-platform" data-p="instagram">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c2.7 0 3 0 4.1.1 1 0 1.6.2 2 .3.5.2.9.4 1.3.8.4.4.6.8.8 1.3.1.4.3 1 .3 2C20.6 7.6 20.6 8 20.6 12s0 4.4-.1 5.5c0 1-.2 1.6-.3 2-.2.5-.4.9-.8 1.3-.4.4-.8.6-1.3.8-.4.1-1 .3-2 .3-1.1.1-1.4.1-4.1.1s-3 0-4.1-.1c-1 0-1.6-.2-2-.3-.5-.2-.9-.4-1.3-.8-.4-.4-.6-.8-.8-1.3-.1-.4-.3-1-.3-2-.1-1.1-.1-1.4-.1-5.4s0-4.4.1-5.5c0-1 .2-1.6.3-2 .2-.5.4-.9.8-1.3.4-.4.8-.6 1.3-.8.4-.1 1-.3 2-.3C8.6 2 9 2 12 2zm0 5a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm6.4-.3a1.2 1.2 0 1 0-2.4 0 1.2 1.2 0 0 0 2.4 0zM12 9.2a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6z"/></svg>
                      Instagram
                    </span>
                    <span className="src-platform" data-p="facebook">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12a10 10 0 1 0-11.6 9.9V15h-2.5v-3h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.3c-1.2 0-1.6.8-1.6 1.6V12h2.8l-.5 3h-2.3v6.9A10 10 0 0 0 22 12z"/></svg>
                      Facebook
                    </span>
                  </div>
                </div>

                {/* Added file list */}
                {sources.length > 0 && (
                  <div className="src-list">
                    <div className="src-list-head">
                      <span className="src-list-count">{sources.length}</span>
                      <span>{t.srcAdded}</span>
                      <span className="src-list-ok" aria-hidden="true">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M5 12l5 5L20 7"/>
                        </svg>
                        {lang === 'VI' ? 'Sẵn sàng' : 'Ready'}
                      </span>
                    </div>
                    {sources.map((s, i) => {
                      const filename = s.value.split(/[\\/]/).pop() || s.value
                      const folder = s.value.slice(0, s.value.length - filename.length).replace(/[\\/]+$/, '')
                      const ext = (filename.split('.').pop() || '').toUpperCase().slice(0, 4)
                      return (
                        <div key={i} className="src-item">
                          <span className="src-item-thumb" aria-hidden="true">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="2" y="6" width="14" height="12" rx="2"/>
                              <path d="M16 10l6-3v10l-6-3z"/>
                            </svg>
                          </span>
                          <div className="src-item-info">
                            <div className="src-item-url" title={s.value}>{filename}</div>
                            <div className="src-item-meta">
                              {ext && <span className="src-item-tag">{ext}</span>}
                              <span className="src-item-folder" title={folder}>{folder || (lang === 'VI' ? 'File trên máy' : 'Local file')}</span>
                            </div>
                          </div>
                          <button className="src-item-del" onClick={() => removeSource(i)} aria-label="Remove" title={lang === 'VI' ? 'Xoá' : 'Remove'}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M18 6 6 18M6 6l12 12"/>
                            </svg>
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* What happens next — visual step preview */}
                <div className="src-next">
                  <div className="src-next-head">{lang === 'VI' ? 'Các bước tiếp theo' : 'What happens next'}</div>
                  <ol className="src-next-list">
                    <li className="src-next-item">
                      <span className="src-next-num">2</span>
                      <div className="src-next-text">
                        <div className="src-next-title">{lang === 'VI' ? 'Thiết lập' : 'Configure'}</div>
                        <div className="src-next-desc">{lang === 'VI' ? 'Chọn preset, tỷ lệ, kiểu phụ đề' : 'Pick preset, ratio, subtitle style'}</div>
                      </div>
                    </li>
                    <li className="src-next-sep" aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 6l6 6-6 6"/>
                      </svg>
                    </li>
                    <li className="src-next-item">
                      <span className="src-next-num">3</span>
                      <div className="src-next-text">
                        <div className="src-next-title">{lang === 'VI' ? 'AI render' : 'AI render'}</div>
                        <div className="src-next-desc">{lang === 'VI' ? 'AI phân tích & cắt clip' : 'AI analyzes & cuts clips'}</div>
                      </div>
                    </li>
                    <li className="src-next-sep" aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 6l6 6-6 6"/>
                      </svg>
                    </li>
                    <li className="src-next-item">
                      <span className="src-next-num">4</span>
                      <div className="src-next-text">
                        <div className="src-next-title">{lang === 'VI' ? 'Kết quả' : 'Results'}</div>
                        <div className="src-next-desc">{lang === 'VI' ? 'Tải clip về để đăng' : 'Export & publish-ready'}</div>
                      </div>
                    </li>
                  </ol>
                </div>

                {prepareError && (
                  <div className="src-error">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 8v4M12 16h.01"/>
                    </svg>
                    <span>{prepareError}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="screen-footer">
              <div className="screen-footer-info">{t.stepOf(1)}</div>
              <button className="btn-next" disabled={sources.length === 0} onClick={goToConfigure}>{t.btnConfigure}</button>
            </div>
          </div>

          {/* STEP 2 */}
          <div className={`step-screen${step === 2 ? ' active' : ''}`}>
            {/* Sprint 5.7 per-step ErrorBoundary: a render error inside Step 2
                no longer takes down the whole workflow. User stays on the
                page and can navigate to other steps. */}
            <ErrorBoundary>
              <StepConfigure
                cfg={cfg} cfgTab={cfgTab} setCfgTab={setCfgTab}
                setCfgKey={setCfgKey} applyPreset={applyPreset}
                sources={sources} prepareResult={prepareResult}
                pickOutputDir={pickOutputDir} onChangeSource={handleChangeSource} t={t}
              />
            </ErrorBoundary>
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setStep(1)}>{t.btnBack}</button>
              <div className="screen-footer-info">
                {submitError
                  ? <span style={{ color: 'var(--fail)' }}>{submitError}</span>
                  : <span>{t.stepOf(2)}</span>
                }
              </div>
              <button
                className="btn-next"
                disabled={isSubmitting}
                onClick={handleStartRender}
              >
                {isSubmitting ? (lang === 'VI' ? 'Đang gửi…' : 'Starting…') : t.btnStartRender}
              </button>
            </div>
          </div>

          {/* STEP 3 */}
          <div className={`step-screen${step === 3 ? ' active' : ''}`}>
            <ErrorBoundary>
              <StepRendering
                jobId={jobId}
                stage={stage ?? ''}
                jobStatus={jobStatus ?? ''}
                progress={progress}
                jobMessage={jobMessage ?? ''}
                isTerminal={isTerminal}
                liveParts={liveParts}
                wsError={wsError}
                wsReconnecting={wsReconnecting}
                t={t}
                aspectRatio={RATIO_INFO[cfg.ratio].api}
                aiAnalysisMode={cfg.aiAnalysisMode}
                aiCloudProvider={cfg.aiCloudProvider}
              />
            </ErrorBoundary>
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setStep(2)}>{t.btnConfig}</button>
              <div className="screen-footer-info" style={{ gap: '12px' }}>
                {isTerminal ? (() => {
                  const s = jobStatus ?? ''
                  if (s === 'failed' || s === 'interrupted')
                    return <span style={{ color: 'var(--fail)' }}>{s === 'interrupted' ? t.rndInterrupted : t.rndFailed}</span>
                  if (s === 'cancelled')
                    return <span style={{ color: 'var(--text-3)' }}>{t.rndCancelled}</span>
                  if (s === 'completed_with_errors')
                    return <span style={{ color: 'var(--warn)' }}>{t.rndPartial}</span>
                  return <span style={{ color: 'var(--ok)' }}>{t.rndComplete}</span>
                })() : wsReconnecting
                  ? <span style={{ color: 'var(--warn)', fontSize: '11px' }}>↻ {t.rndWsReconnecting}</span>
                  : wsError
                  ? <span style={{ color: 'var(--warn)', fontSize: '11px' }}>{t.rndWsError}</span>
                  : <span style={{ color: 'var(--accent)' }}>{t.rndInProgress}</span>
                }
              </div>
              {isTerminal ? (
                <>
                  {(jobStatus === 'failed') && errorKind && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 11, color: 'var(--error, #e74c3c)', fontWeight: 700, marginBottom: 6 }}>
                        {t[ERROR_KIND_KEY[errorKind]] as string}
                      </div>
                      <ul style={{ margin: '0 0 6px 14px', padding: 0, fontSize: 10, color: 'var(--text-2)', lineHeight: 1.6 }}>
                        {ERROR_FIX_STEPS[errorKind].map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                      {jobMessage && (
                        <div>
                          <button
                            onClick={() => setRawMsgOpen(o => !o)}
                            style={{ fontSize: 9, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
                          >
                            {rawMsgOpen ? 'Hide detail' : 'Show raw error'}
                          </button>
                          {rawMsgOpen && (
                            <pre style={{
                              marginTop: 6, padding: '6px 8px', borderRadius: 5,
                              background: 'rgba(0,0,0,.35)', fontSize: 9, color: 'var(--text-2)',
                              whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 120, overflowY: 'auto',
                            }}>
                              {jobMessage}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {(jobStatus === 'failed') && (
                      <button className="btn-back" onClick={handleRetryRender} disabled={isRetrying}>
                        {isRetrying ? '…' : t.btnRetry}
                      </button>
                    )}
                    {(jobStatus === 'interrupted') && (
                      <button className="btn-back" onClick={handleResumeRender} disabled={isRetrying}>
                        {isRetrying ? '…' : t.btnResume}
                      </button>
                    )}
                    <button className="btn-next" onClick={() => setStep(4)}>{t.btnViewResults}</button>
                  </div>
                </>
              ) : (
                <button className="btn-cancel" onClick={handleCancelRender} disabled={isCancelling}>
                  {isCancelling ? t.btnCancelling : t.btnCancelRender}
                </button>
              )}
            </div>
          </div>

          {/* STEP 4 */}
          <div className={`step-screen${step === 4 ? ' active' : ''}`}>
            <ErrorBoundary>
              <StepResults
                jobId={jobId} parts={parts} partScores={partScores} partRanks={partRanks}
                qualityReports={qualityReports} qualityLoadFailed={qualityLoadFailed}
                loading={partsLoading} t={t}
                aspectRatio={RATIO_INFO[cfg.ratio].api}
                jobStatus={jobStatus ?? ''}
                onRetry={handleRetryRender} isRetrying={isRetrying}
                aiAnalysisMode={cfg.aiAnalysisMode}
                aiCloudProvider={cfg.aiCloudProvider}
                goal={cfg.videoType}
              />
            </ErrorBoundary>
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setStep(3)}>{t.btnBackRendering}</button>
              <div className="screen-footer-info">
                {doneParts.length > 0
                  ? <><span style={{ color: 'var(--ok)' }}>✓ </span><span>{t.resClipsReady(doneParts.length)}</span></>
                  : <span>{t.stepRes}</span>
                }
              </div>
              <button className="btn-next" onClick={handleNewRender}>{t.btnNewRender}</button>
            </div>
          </div>
        </>
      )}

      <input
        ref={fileInputRef} type="file" accept="video/*" style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) setSources([{ value: (f as File & { path?: string }).path || f.name }])
        }}
      />
    </div>
  )
}
