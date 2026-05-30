import { useState, useRef, useEffect } from 'react'
import './RenderWorkflow.css'
import type { Lang } from '../ClipStudio'
import { useRenderStore } from '../../../stores/renderStore'
import { useUIStore } from '../../../stores/uiStore'
import { useRenderSocket } from '../../../hooks/useRenderSocket'
import { prepareSource, cancelRender, cancelPrepareSource, retryRender, resumeRender } from '../../../api/render'
import type { PrepareSourceResponse } from '../../../api/render'
import { getJobParts, getJobQualitySummary, getJobRanking } from '../../../api/jobs'
import type { RenderRequest, JobPart, QualityReport, PartRankResult } from '../../../types/api'
import { useT, ERROR_KIND_KEY, ERROR_FIX_STEPS } from './i18n'
import type { Step, CfgTab, ConfigState, Source } from './types'
import { PRESETS, RATIO_INFO } from './constants'
import { StepConfigure } from './steps/StepConfigure'
import { StepRendering } from './steps/StepRendering'
import { StepResults } from './steps/StepResults'

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
    aiCloudProvider:  (localStorage.getItem('rw_ai_cloud_provider') as 'groq' | 'openai') ?? 'groq',
    aiCloudApiKey:    localStorage.getItem('rw_ai_cloud_api_key') ?? '',
    aiCloudModel:     '',
    aiContentDriven:  false,
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
  const [isRetrying, setIsRetrying]         = useState(false)
  const [rawMsgOpen, setRawMsgOpen]         = useState(false)

  const { submitRender } = useRenderStore()
  const addNotification = useUIStore((s) => s.addNotification)
  const { stage, jobStatus, progress, jobMessage, isTerminal, liveParts, error: wsError, errorKind } = useRenderSocket(jobId)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!jobId || !isTerminal) return
    setQualityLoadFailed(false)
    setPartsLoading(true)
    getJobParts(jobId)
      .then(setParts)
      .finally(() => setPartsLoading(false))
    getJobQualitySummary(jobId, true)
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
    getJobRanking(jobId).then(setPartRanks).catch(() => {})
  }, [jobId, isTerminal])

  // Auto-advance to results after completion (success + partial success)
  useEffect(() => {
    if (!isTerminal || step !== 3) return
    const s = jobStatus ?? ''
    const skipAdvance = s === 'failed' || s === 'interrupted' || s === 'cancelled'
    if (skipAdvance) return
    const timer = setTimeout(() => setStep(4), 1500)
    return () => clearTimeout(timer)
  }, [isTerminal, jobStatus, step])

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
    setSubmitError(null)
    const src = sources[0]
    const payload: RenderRequest = {
      source_mode:       'local',
      source_video_path: src.value,
      output_dir:          cfg.outputDir || 'output',
      aspect_ratio:        RATIO_INFO[cfg.ratio].api,
      min_part_sec:        cfg.minSec,
      max_part_sec:        cfg.maxSec,
      max_export_parts:    cfg.outputCount,
      add_subtitle:                cfg.subEnabled,
      subtitle_style:              cfg.subStyle,
      highlight_per_word:          cfg.subHighlight,
      sub_font_size:               cfg.subFontSize,
      subtitle_translate_enabled:  cfg.subTranslate || undefined,
      subtitle_target_language:    cfg.subTranslate ? cfg.subTranslateLang : undefined,
      subtitle_emphasis:           cfg.subEmphasis ?? undefined,
      part_order:                  cfg.partOrder,
      structure_bias:              cfg.structureBias ?? undefined,
      clip_lock:                   cfg.clipLock.length > 0 ? cfg.clipLock : undefined,
      clip_exclude:                cfg.clipExclude.length > 0 ? cfg.clipExclude : undefined,
      voice_enabled:               cfg.narrEnabled,
      voice_source:        cfg.narrEnabled ? cfg.voiceSource : undefined,
      voice_text:          cfg.narrEnabled && cfg.voiceSource === 'manual' ? cfg.voiceText : undefined,
      voice_language:      cfg.narrEnabled ? cfg.voiceLang as 'vi-VN' | 'ja-JP' | 'en-US' | 'en-GB' : undefined,
      voice_gender:        cfg.narrEnabled ? cfg.voiceGender : undefined,
      tts_engine:          cfg.narrEnabled ? cfg.ttsEngine : undefined,
      voice_mix_mode:      cfg.narrEnabled ? cfg.voiceMixMode : undefined,
      ai_director_enabled:        cfg.aiEnabled,
      ai_analysis_mode:           cfg.aiEnabled ? cfg.aiAnalysisMode : undefined,
      ai_cloud_enabled:           cfg.aiEnabled && cfg.aiAnalysisMode !== 'local' && !!cfg.aiCloudApiKey,
      ai_cloud_provider:          cfg.aiEnabled && cfg.aiAnalysisMode !== 'local' ? cfg.aiCloudProvider : undefined,
      ai_cloud_api_key:           cfg.aiEnabled && cfg.aiAnalysisMode !== 'local' && cfg.aiCloudApiKey ? cfg.aiCloudApiKey : undefined,
      ai_cloud_model:             cfg.aiEnabled && cfg.aiCloudModel ? cfg.aiCloudModel : undefined,
      ai_content_driven_selection: cfg.aiEnabled && (
        cfg.aiContentDriven ||
        (cfg.aiAnalysisMode !== 'local' && !!cfg.aiCloudApiKey)
      ) || undefined,
      multi_variant:       cfg.multiVariant || undefined,
      cta_enabled:         cfg.ctaEnabled || undefined,
      cta_type:            cfg.ctaEnabled ? cfg.ctaType : undefined,
      hook_apply_enabled:  cfg.hookApplyEnabled || undefined,
      hook_overlay_enabled: cfg.hookOverlayEnabled || undefined,
      motion_aware_crop:   cfg.focusMode === 'face' || cfg.focusMode === 'object',
      target_platform:     cfg.platform,
      effect_preset:       cfg.style,
      render_profile:      cfg.renderProfile,
      whisper_model:       cfg.whisperModel !== 'auto' ? cfg.whisperModel : undefined,
      ai_target_market:    cfg.aiMarket || undefined,
      target_duration:     cfg.targetDuration,
      output_count:        cfg.outputCount,
      video_type:          cfg.videoType,
      energy_style:        cfg.energyStyle,
      hook_strength:       cfg.hookStrength,
      reframe_mode:        cfg.focusMode,
      output_language:     cfg.outputLanguage !== 'auto' ? cfg.outputLanguage : undefined,
      narration_style:     cfg.narrationStyle,
      asset_logo_path:     cfg.assetLogoPath ?? undefined,
      asset_intro_path:    cfg.assetIntroPath ?? undefined,
      asset_outro_path:    cfg.assetOutroPath ?? undefined,
      asset_music_profile: cfg.assetMusicProfile ?? undefined,
    }
    try {
      const id = await submitRender(payload)
      setJobId(id)
      setStep(3)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to start render')
    }
  }

  async function handleCancelRender() {
    if (!jobId || isCancelling) return
    setIsCancelling(true)
    try { await cancelRender(jobId) } catch { /* ignore */ }
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
              <div className={`rw-step ${cls}`} onClick={() => n < step && setStep(n)}>
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
              <div className="src-headline">
                <h1>{t.srcHeadline}</h1>
                <p>{t.srcDesc}</p>
              </div>
              <div className="src-cards">
                <div className="src-card highlight" onClick={async () => {
                  const picked = await window.electronAPI?.pickVideoFile?.()
                  if (picked) setSources([{ value: picked }])
                  else fileInputRef.current?.click()
                }}>
                  <div className="src-card-icon">📁</div>
                  <div className="src-card-title">{t.srcLocalTitle}</div>
                  <div className="src-card-desc">{t.srcLocalDesc}</div>
                  <span className="src-card-badge">MP4 · MOV · MKV · WEBM</span>
                </div>
              </div>
              {sources.length > 0 && (
                <div className="src-list">
                  <div className="src-list-head">{t.srcAdded}</div>
                  {sources.map((s, i) => (
                    <div key={i} className="src-item">
                      <div className="src-item-thumb">📄</div>
                      <div className="src-item-info">
                        <div className="src-item-url">{s.value}</div>
                        <div className="src-item-meta">{lang === 'VI' ? 'File trên máy' : 'Local File'}</div>
                      </div>
                      <button className="src-item-del" onClick={() => removeSource(i)}>×</button>
                    </div>
                  ))}
                </div>
              )}
              {prepareError && (
                <div style={{ width: '100%', maxWidth: '760px', padding: '10px 14px', background: 'rgba(232,64,122,.1)', border: '1px solid rgba(232,64,122,.3)', fontSize: '12px', color: 'var(--fail)' }}>
                  ⚠ {prepareError}
                </div>
              )}
            </div>
            <div className="screen-footer">
              <div className="screen-footer-info">{t.stepOf(1)}</div>
              <button className="btn-next" disabled={sources.length === 0} onClick={goToConfigure}>{t.btnConfigure}</button>
            </div>
          </div>

          {/* STEP 2 */}
          <div className={`step-screen${step === 2 ? ' active' : ''}`}>
            <StepConfigure
              cfg={cfg} cfgTab={cfgTab} setCfgTab={setCfgTab}
              setCfgKey={setCfgKey} applyPreset={applyPreset}
              sources={sources} prepareResult={prepareResult}
              pickOutputDir={pickOutputDir} onChangeSource={handleChangeSource} t={t}
            />
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setStep(1)}>{t.btnBack}</button>
              <div className="screen-footer-info">
                {submitError
                  ? <span style={{ color: 'var(--fail)' }}>{submitError}</span>
                  : <span>{t.stepOf(2)}</span>
                }
              </div>
              <button className="btn-next" onClick={handleStartRender}>{t.btnStartRender}</button>
            </div>
          </div>

          {/* STEP 3 */}
          <div className={`step-screen${step === 3 ? ' active' : ''}`}>
            <StepRendering
              jobId={jobId}
              stage={stage ?? ''}
              jobStatus={jobStatus ?? ''}
              progress={progress}
              jobMessage={jobMessage ?? ''}
              isTerminal={isTerminal}
              liveParts={liveParts}
              wsError={wsError}
              t={t}
              aspectRatio={RATIO_INFO[cfg.ratio].api}
              aiAnalysisMode={cfg.aiAnalysisMode}
              aiCloudProvider={cfg.aiCloudProvider}
            />
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
                })() : wsError
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
