import React, { useState, useRef, useEffect } from 'react'
import './RenderWorkflow.css'
import type { Lang } from '../ClipStudio'
import { useRenderStore } from '../../../stores/renderStore'
import { useRenderSocket } from '../../../hooks/useRenderSocket'
import { prepareSource, getPreviewVideoUrl, cancelRender } from '../../../api/render'
import { getJobParts, getJobQualitySummary } from '../../../api/jobs'
import { BASE_URL } from '../../../api/client'
import type { RenderRequest, JobPart, WsProgressSummary, QualityReport } from '../../../types/api'
import type { PrepareSourceResponse } from '../../../api/render'

// ── i18n ──────────────────────────────────────────────────────────────────────
const T = {
  EN: {
    // Steps
    stepSrc: 'SOURCE',        stepSrcSub: 'Add video',
    stepCfg: 'CONFIGURE',     stepCfgSub: 'Style & options',
    stepRnd: 'RENDERING',     stepRndSub: 'Processing',
    stepRes: 'RESULTS',       stepResSub: 'Your clips',
    // Source screen
    srcHeadline: 'Add Your Video Source',
    srcDesc: 'Upload a local file or paste a YouTube / TikTok URL',
    srcLocalTitle: 'Local File',
    srcLocalDesc: 'Import MP4, MOV, MKV or WEBM from your computer. No internet required.',
    srcYtTitle: 'YouTube / URL',
    srcYtDesc: 'Paste a YouTube, TikTok, Instagram or any supported URL. Auto-downloads at best quality.',
    srcBatchTitle: 'Batch Mode',
    srcBatchDesc: 'Add multiple URLs at once. AI Director processes each one automatically.',
    srcOr: 'OR PASTE URL',
    srcAdded: 'SOURCES ADDED',
    btnAdd: 'ADD',
    btnConfigure: 'CONFIGURE →',
    stepOf: (s: number) => `Step ${s} of 4`,
    // Configure
    cfgQuickPresets: 'QUICK PRESETS',
    cfgFrame: 'FRAME',
    cfgDuration: 'DURATION',
    cfgMinClip: 'Min Clip', cfgMaxClip: 'Max Clip', cfgClipCount: 'Clip Count',
    cfgMotionCrop: 'Motion-Aware Crop', cfgFps: '60 FPS',
    cfgVisualStyle: 'VISUAL STYLE',
    cfgTabAI: 'AI', cfgTabSub: 'SUB', cfgTabNarr: 'NARR', cfgTabOutput: 'OUTPUT',
    cfgPlatform: 'PLATFORM', cfgAIFeatures: 'AI FEATURES',
    cfgAIDirector: 'AI Director', cfgAIDirectorDesc: 'Auto-select best moments',
    cfgMultiVariant: 'Multi-Variant ×3', cfgMultiVariantDesc: 'Generate 3 style variations',
    cfgRenderProfile: 'RENDER PROFILE',
    cfgEnableSub: 'Enable Subtitles', cfgSubStyle: 'STYLE',
    cfgAutoTranslate: 'Auto-Translate', cfgTargetLang: 'TARGET LANGUAGE',
    cfgEnableVoice: 'Enable Voiceover', cfgVoiceSource: 'VOICE SOURCE',
    cfgVoiceSrcAuto: 'Auto (from transcript)', cfgVoiceSrcAutoDesc: 'Read from video transcript',
    cfgVoiceSrcTrans: 'Translated subtitle',   cfgVoiceSrcTransDesc: 'Read from translated subtitles',
    cfgVoiceSrcManual: 'Custom text',          cfgVoiceSrcManualDesc: 'Enter text manually',
    cfgVoiceLang: 'LANGUAGE', cfgVoiceGender: 'VOICE', cfgEngine: 'ENGINE', cfgMixMode: 'MIX MODE',
    cfgSaveFolder: 'SAVE FOLDER', cfgRanking: 'RANKING', cfgAutoExport: 'Auto-export best 3',
    cfgChangeSource: '← CHANGE SOURCE',
    btnBack: '← BACK', btnStartRender: 'START RENDER ▶',
    // Rendering
    rndWaiting: 'Waiting for job…', rndInProgress: 'Rendering in progress…', rndComplete: '✓ Render complete',
    btnCancelRender: 'CANCEL RENDER', btnCancelling: 'CANCELLING…',
    btnViewResults: 'VIEW RESULTS →', btnConfig: '← CONFIG',
    rndAllJobs: 'ALL JOBS', rndLog: 'RENDER LOG',
    rndPhaseDownload: 'DOWNLOAD', rndPhaseAnalyze: 'ANALYZE',
    rndPhaseTranscribe: 'TRANSCRIBE', rndPhaseRender: 'RENDER', rndPhaseDone: 'DONE',
    rndClipsDone: (done: number, total: number) => `${done} / ${total} clips done`,
    rndClipsFailed: (n: number) => `${n} failed`,
    rndStatusDone: 'Done', rndStatusRendering: 'Rendering',
    rndStatusCutting: 'Cutting', rndStatusTranscribing: 'Transcribing',
    rndStatusWaiting: 'Waiting', rndStatusFailed: 'Failed',
    rndPreparing: 'Preparing…',
    // Results
    resClipsRendered: (n: number) => `${n} clips rendered`,
    resClipsReady: (n: number) => `${n} clips ready`,
    resSortViral: 'VIRAL SCORE', resSortDuration: 'DURATION', resSortNewest: 'NEWEST',
    resClipViewer: 'CLIP VIEWER', resViralScore: 'VIRAL SCORE',
    btnPlay: '▶ Play', btnOpen: '📁 Open', btnExport: '↓ Export',
    btnNewRender: 'NEW RENDER +', btnBackRendering: '← RENDERING',
    resNoResults: 'No render results yet', resNoClips: 'No clips rendered successfully',
    resLoading: 'Loading clips…',
  },
  VI: {
    stepSrc: 'NGUỒN',         stepSrcSub: 'Thêm video',
    stepCfg: 'CẤU HÌNH',     stepCfgSub: 'Tùy chọn',
    stepRnd: 'ĐANG RENDER',   stepRndSub: 'Xử lý',
    stepRes: 'KẾT QUẢ',      stepResSub: 'Clip của bạn',
    srcHeadline: 'Thêm Nguồn Video',
    srcDesc: 'Tải file lên hoặc dán link YouTube / TikTok',
    srcLocalTitle: 'File trên máy',
    srcLocalDesc: 'Import MP4, MOV, MKV hoặc WEBM từ máy tính. Không cần internet.',
    srcYtTitle: 'YouTube / URL',
    srcYtDesc: 'Dán link YouTube, TikTok, Instagram. Tự tải về chất lượng tốt nhất.',
    srcBatchTitle: 'Hàng loạt',
    srcBatchDesc: 'Thêm nhiều link cùng lúc. AI Director xử lý và tạo clip tối ưu.',
    srcOr: 'HOẶC DÁN LINK',
    srcAdded: 'NGUỒN ĐÃ THÊM',
    btnAdd: 'THÊM',
    btnConfigure: 'CẤU HÌNH →',
    stepOf: (s: number) => `Bước ${s} / 4`,
    cfgQuickPresets: 'PRESET NHANH',
    cfgFrame: 'KHUNG HÌNH',
    cfgDuration: 'THỜI LƯỢNG',
    cfgMinClip: 'Tối thiểu', cfgMaxClip: 'Tối đa', cfgClipCount: 'Số lượng clip',
    cfgMotionCrop: 'Crop thông minh', cfgFps: '60 FPS',
    cfgVisualStyle: 'PHONG CÁCH',
    cfgTabAI: 'AI', cfgTabSub: 'PHỤ ĐỀ', cfgTabNarr: 'THUYẾT MINH', cfgTabOutput: 'XUẤT',
    cfgPlatform: 'NỀN TẢNG', cfgAIFeatures: 'TÍNH NĂNG AI',
    cfgAIDirector: 'AI Director', cfgAIDirectorDesc: 'Tự chọn khoảnh khắc hay nhất',
    cfgMultiVariant: 'Đa biến thể ×3', cfgMultiVariantDesc: 'Tạo 3 biến thể phong cách',
    cfgRenderProfile: 'CHẾ ĐỘ RENDER',
    cfgEnableSub: 'Bật phụ đề', cfgSubStyle: 'KIỂU',
    cfgAutoTranslate: 'Tự dịch', cfgTargetLang: 'NGÔN NGỮ ĐÍCH',
    cfgEnableVoice: 'Bật thuyết minh', cfgVoiceSource: 'NGUỒN GIỌNG',
    cfgVoiceSrcAuto: 'Tự động (từ transcript)', cfgVoiceSrcAutoDesc: 'Đọc từ transcript video',
    cfgVoiceSrcTrans: 'Subtitle đã dịch',       cfgVoiceSrcTransDesc: 'Đọc từ subtitle đã dịch',
    cfgVoiceSrcManual: 'Nội dung thủ công',      cfgVoiceSrcManualDesc: 'Nhập nội dung tùy chỉnh',
    cfgVoiceLang: 'NGÔN NGỮ', cfgVoiceGender: 'GIỌNG', cfgEngine: 'BỘ ĐỌC', cfgMixMode: 'TRỘN ÂM',
    cfgSaveFolder: 'THƯ MỤC LƯU', cfgRanking: 'SẮP XẾP', cfgAutoExport: 'Tự xuất 3 clip tốt nhất',
    cfgChangeSource: '← ĐỔI NGUỒN',
    btnBack: '← QUAY LẠI', btnStartRender: 'BẮT ĐẦU RENDER ▶',
    rndWaiting: 'Đang chờ job…', rndInProgress: 'Đang render…', rndComplete: '✓ Hoàn thành',
    btnCancelRender: 'HỦY RENDER', btnCancelling: 'ĐANG HỦY…',
    btnViewResults: 'XEM KẾT QUẢ →', btnConfig: '← CẤU HÌNH',
    rndAllJobs: 'TẤT CẢ', rndLog: 'NHẬT KÝ',
    rndPhaseDownload: 'TẢI VỀ', rndPhaseAnalyze: 'PHÂN TÍCH',
    rndPhaseTranscribe: 'PHIÊN ÂM', rndPhaseRender: 'RENDER', rndPhaseDone: 'XONG',
    rndClipsDone: (done: number, total: number) => `${done} / ${total} clip xong`,
    rndClipsFailed: (n: number) => `${n} lỗi`,
    rndStatusDone: 'Xong', rndStatusRendering: 'Render',
    rndStatusCutting: 'Cắt', rndStatusTranscribing: 'Phiên âm',
    rndStatusWaiting: 'Chờ', rndStatusFailed: 'Lỗi',
    rndPreparing: 'Đang chuẩn bị…',
    resClipsRendered: (n: number) => `${n} clip đã render`,
    resClipsReady: (n: number) => `${n} clip sẵn sàng`,
    resSortViral: 'VIRAL', resSortDuration: 'THỜI LƯỢNG', resSortNewest: 'MỚI NHẤT',
    resClipViewer: 'XEM CLIP', resViralScore: 'ĐIỂM VIRAL',
    btnPlay: '▶ Phát', btnOpen: '📁 Mở', btnExport: '↓ Xuất',
    btnNewRender: 'RENDER MỚI +', btnBackRendering: '← RENDER',
    resNoResults: 'Chưa có kết quả render', resNoClips: 'Không có clip nào thành công',
    resLoading: 'Đang tải clip…',
  },
} as const

type Strings = { [K in keyof typeof T['EN']]: typeof T['EN'][K] extends string ? string : typeof T['EN'][K] }
function useT(lang: Lang): Strings { return T[lang] as Strings }

// ── Types ─────────────────────────────────────────────────────────────────────
type Step = 1 | 2 | 3 | 4
type SourceMode = 'youtube' | 'local'
type Ratio = 'r916' | 'r34' | 'r11'
type CfgTab = 'ai' | 'sub' | 'narr' | 'output'

interface Source { mode: SourceMode; value: string }

interface ConfigState {
  preset:        string
  ratio:         Ratio
  minSec:        number
  maxSec:        number
  clipCount:     number
  style:         string
  platform:      'tiktok' | 'youtube_shorts' | 'instagram_reels'
  aiEnabled:     boolean
  multiVariant:  boolean
  motionCrop:    boolean
  fps60:         boolean
  subEnabled:    boolean
  subStyle:      string
  autoTranslate: boolean
  subtitleLang:  string
  narrEnabled:   boolean
  voiceLang:     string
  voiceGender:   'female' | 'male'
  ttsEngine:     'edge' | 'xtts'
  voiceSource:   'subtitle' | 'translated_subtitle' | 'manual'
  voiceText:     string
  voiceMixMode:  string
  outputDir:     string
  ranking:       'viral' | 'sequential'
  autoExport:    boolean
  renderProfile: 'fast' | 'balanced' | 'quality'
}

// ── Constants ─────────────────────────────────────────────────────────────────
const PRESETS = [
  { id: 'viral',   icon: '🔥', name: 'VIRAL SHORT',  desc: 'TikTok · 9:16 · Bounce sub',  platform: 'tiktok'          as const },
  { id: 'gaming',  icon: '🎮', name: 'GAMING HYPE',   desc: 'YT Short · 9:16 · Gaming sub', platform: 'youtube_shorts'  as const },
  { id: 'clean',   icon: '✨', name: 'CLEAN STORY',   desc: 'Reels · 9:16 · Clean Pro sub', platform: 'instagram_reels' as const },
  { id: 'podcast', icon: '🎙', name: 'PODCAST CLIP',  desc: 'All platforms · Karaoke',       platform: 'tiktok'          as const },
]

const STYLES = [
  { id: 'slay_soft_01',   ico: '✨', label: 'SOFT'    },
  { id: 'slay_pop_01',    ico: '⚡', label: 'POP'     },
  { id: 'story_clean_01', ico: '🎬', label: 'CLEAN'   },
  { id: 'viral_bold',     ico: '💥', label: 'BOLD'    },
  { id: 'dark_cinema',    ico: '🎥', label: 'CINEMA'  },
  { id: 'minimal_white',  ico: '⬜', label: 'MINIMAL' },
]

const SUB_STYLES = [
  { id: 'pro_karaoke',     label: 'KARAOKE'   },
  { id: 'tiktok_bounce_v1',label: 'BOUNCE'    },
  { id: 'viral_bold',      label: 'VIRAL'     },
  { id: 'bold_cap',        label: 'BOLD CAP'  },
  { id: 'story_clean_01',  label: 'STORY'     },
  { id: 'boxed_caption',   label: 'BOXED'     },
  { id: 'clean_pro',       label: 'CLEAN PRO' },
  { id: 'gaming',          label: 'GAMING'    },
]

const RATIO_INFO: Record<Ratio, { label: string; sub: string; api: string }> = {
  r916: { label: '9:16', sub: '1080×1920', api: '9:16' },
  r34:  { label: '3:4',  sub: '1080×1440', api: '3:4'  },
  r11:  { label: '1:1',  sub: '1080×1080', api: '1:1'  },
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function extractYouTubeId(url: string): string | null {
  const m = url.match(/(?:v=|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})/)
  return m?.[1] ?? null
}

function getPartThumbnailUrl(jobId: string, partNo: number): string {
  return `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/thumbnail?t=0.5&w=320`
}

function getPartMediaUrl(jobId: string, partNo: number): string {
  return `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/media`
}

function fmtDuration(secs: number): string {
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

// ── Toggle component ──────────────────────────────────────────────────────────
function Tog({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return <div className={`tog${checked ? ' on' : ''}`} onClick={() => onChange(!checked)} />
}

// ── Root component ────────────────────────────────────────────────────────────
export function RenderWorkflow({ lang }: { lang: Lang }) {
  const t = useT(lang)
  const [step, setStep]       = useState<Step>(1)
  const [sources, setSources] = useState<Source[]>([])
  const [urlInput, setUrlInput] = useState('')
  const [srcMode, setSrcMode] = useState<SourceMode>('youtube')

  const [prepareResult, setPrepareResult]       = useState<PrepareSourceResponse | null>(null)
  const [isPreparing, setIsPreparing]           = useState(false)
  const [prepareError, setPrepareError]         = useState<string | null>(null)
  const [prepareCancelled, setPrepareCancelled] = useState(false)

  const [cfgTab, setCfgTab] = useState<CfgTab>('ai')
  const [cfg, setCfg] = useState<ConfigState>({
    preset: 'viral', ratio: 'r916', minSec: 15, maxSec: 60, clipCount: 5,
    style: 'slay_soft_01', platform: 'tiktok',
    aiEnabled: true, multiVariant: false, motionCrop: true, fps60: true,
    subEnabled: true, subStyle: 'pro_karaoke', autoTranslate: false, subtitleLang: 'vi',
    narrEnabled: false, voiceLang: 'vi', voiceGender: 'female', ttsEngine: 'edge',
    voiceSource: 'subtitle', voiceText: '', voiceMixMode: 'replace_original',
    outputDir: '', ranking: 'viral', autoExport: true,
    renderProfile: 'balanced',
  })

  const [jobId, setJobId]               = useState<string | null>(null)
  const [submitError, setSubmitError]   = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)

  const [parts, setParts]                   = useState<JobPart[]>([])
  const [partScores, setPartScores]         = useState<Record<number, number>>({})
  const [qualityReports, setQualityReports] = useState<Record<number, QualityReport | null>>({})
  const [partsLoading, setPartsLoading]     = useState(false)

  const { submitRender } = useRenderStore()
  const { stage, jobStatus, progress, jobMessage, isTerminal, liveParts } = useRenderSocket(jobId)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!jobId || !isTerminal) return
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
      .catch(() => {})
  }, [jobId, isTerminal])

  // Auto-advance to results after successful completion
  useEffect(() => {
    if (!isTerminal || step !== 3) return
    const jobFailed = jobStatus?.toLowerCase().includes('fail') || jobStatus === 'cancelled'
    if (jobFailed) return
    const timer = setTimeout(() => setStep(4), 1500)
    return () => clearTimeout(timer)
  }, [isTerminal, jobStatus, step])

  // ── Source actions ──────────────────────────────────────────────────────────
  function addUrl() {
    const v = urlInput.trim()
    if (!v) return
    setSources((p) => [...p, { mode: 'youtube', value: v }])
    setUrlInput('')
  }
  function removeSource(i: number) { setSources((p) => p.filter((_, idx) => idx !== i)) }

  async function goToConfigure() {
    if (sources.length === 0) return
    const src = sources[0]
    setIsPreparing(true)
    setPrepareError(null)
    setPrepareCancelled(false)
    try {
      const result = await prepareSource({
        source_mode: src.mode,
        youtube_url: src.mode === 'youtube' ? src.value : undefined,
        source_video_path: src.mode === 'local' ? src.value : undefined,
      })
      if (prepareCancelled) return
      setPrepareResult(result)
      setCfg((prev) => ({ ...prev, outputDir: result.export_dir || prev.outputDir }))
      setStep(2)
    } catch (e) {
      if (!prepareCancelled) {
        setPrepareError(e instanceof Error ? e.message : 'Failed to prepare source')
      }
    } finally {
      setIsPreparing(false)
    }
  }

  function setCfgKey<K extends keyof ConfigState>(k: K, v: ConfigState[K]) {
    setCfg((p) => ({ ...p, [k]: v }))
  }
  function applyPreset(id: string) {
    const p = PRESETS.find((x) => x.id === id)
    if (!p) return
    setCfg((prev) => ({ ...prev, preset: id, platform: p.platform, ratio: 'r916' }))
  }
  async function pickOutputDir() {
    const ea = (window as Window & { electronAPI?: { pickDirectory?: () => Promise<string | null> } }).electronAPI
    if (ea?.pickDirectory) {
      const dir = await ea.pickDirectory()
      if (dir) setCfgKey('outputDir', dir)
    }
  }

  // ── Render actions ──────────────────────────────────────────────────────────
  async function handleStartRender() {
    setSubmitError(null)
    const src = sources[0]
    const payload: RenderRequest = {
      source_mode:         src.mode,
      youtube_url:         src.mode === 'youtube' ? src.value : undefined,
      source_video_path:   src.mode === 'local'   ? src.value : undefined,
      output_dir:          cfg.outputDir || 'output',
      aspect_ratio:        RATIO_INFO[cfg.ratio].api,
      min_part_sec:        cfg.minSec,
      max_part_sec:        cfg.maxSec,
      max_export_parts:    cfg.clipCount,
      add_subtitle:        cfg.subEnabled,
      subtitle_style:      cfg.subStyle,
      voice_enabled:       cfg.narrEnabled,
      voice_source:        cfg.narrEnabled ? cfg.voiceSource : undefined,
      voice_text:          cfg.narrEnabled && cfg.voiceSource === 'manual' ? cfg.voiceText : undefined,
      ai_director_enabled: cfg.aiEnabled,
      target_platform:     cfg.platform,
      effect_preset:       cfg.style,
      render_profile:      cfg.renderProfile,
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

  function handleNewRender() {
    setStep(1); setSources([]); setJobId(null)
    setPrepareResult(null); setParts([]); setPartScores({})
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
              {sources[0]?.mode === 'youtube'
                ? (lang === 'VI' ? 'Đang tải và xử lý video YouTube…' : 'Downloading and transcoding YouTube video…')
                : (lang === 'VI' ? 'Đang phân tích file video…' : 'Probing local video file…')}
            </div>
            <button className="btn-back" onClick={() => { setPrepareCancelled(true); setIsPreparing(false) }}>
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
                <div className={`src-card${srcMode === 'local' ? ' highlight' : ''}`} onClick={() => { setSrcMode('local'); fileInputRef.current?.click() }}>
                  <div className="src-card-icon">📁</div>
                  <div className="src-card-title">{t.srcLocalTitle}</div>
                  <div className="src-card-desc">{t.srcLocalDesc}</div>
                  <span className="src-card-badge">MP4 · MOV · MKV · WEBM</span>
                </div>
                <div className={`src-card${srcMode === 'youtube' ? ' highlight' : ''}`} onClick={() => setSrcMode('youtube')}>
                  <div className="src-card-icon">🌐</div>
                  <div className="src-card-title">{t.srcYtTitle}</div>
                  <div className="src-card-desc">{t.srcYtDesc}</div>
                  <span className="src-card-badge">YT · TikTok · IG · FB</span>
                </div>
                <div className="src-card" onClick={() => setSrcMode('youtube')}>
                  <div className="src-card-icon">⚡</div>
                  <div className="src-card-title">{t.srcBatchTitle}</div>
                  <div className="src-card-desc">{t.srcBatchDesc}</div>
                  <span className="src-card-badge" style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>PRO FEATURE</span>
                </div>
              </div>
              <div className="src-or"><span>{t.srcOr}</span></div>
              <div className="url-box">
                <input className="url-input-big" placeholder="https://youtube.com/watch?v=…" value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addUrl()} />
                <button className="btn-add" onClick={addUrl}>{t.btnAdd}</button>
              </div>
              {sources.length > 0 && (
                <div className="src-list">
                  <div className="src-list-head">{t.srcAdded}</div>
                  {sources.map((s, i) => (
                    <div key={i} className="src-item">
                      <div className="src-item-thumb">{s.mode === 'youtube' ? '▶' : '📄'}</div>
                      <div className="src-item-info">
                        <div className="src-item-url">{s.value}</div>
                        <div className="src-item-meta">{s.mode === 'youtube' ? 'YouTube URL' : lang === 'VI' ? 'File trên máy' : 'Local File'}</div>
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
              pickOutputDir={pickOutputDir} t={t}
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
              t={t}
            />
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setStep(2)}>{t.btnConfig}</button>
              <div className="screen-footer-info" style={{ gap: '12px' }}>
                {isTerminal
                  ? <span style={{ color: 'var(--ok)' }}>{t.rndComplete}</span>
                  : <span style={{ color: 'var(--accent)' }}>{t.rndInProgress}</span>
                }
              </div>
              {isTerminal
                ? <button className="btn-next" onClick={() => setStep(4)}>{t.btnViewResults}</button>
                : <button className="btn-cancel" onClick={handleCancelRender} disabled={isCancelling}>
                    {isCancelling ? t.btnCancelling : t.btnCancelRender}
                  </button>
              }
            </div>
          </div>

          {/* STEP 4 */}
          <div className={`step-screen${step === 4 ? ' active' : ''}`}>
            <StepResults
              jobId={jobId} parts={parts} partScores={partScores}
              qualityReports={qualityReports}
              loading={partsLoading} t={t}
              aspectRatio={RATIO_INFO[cfg.ratio].api}
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
          if (f) {
            setSrcMode('local')
            setSources([{ mode: 'local', value: (f as File & { path?: string }).path || f.name }])
          }
        }}
      />
    </div>
  )
}

// ── Subtitle preview — visual approximation of each style ────────────────────
function SubtitleDemo({ style }: { style: string }) {
  const baseBox: React.CSSProperties = {
    position: 'absolute', bottom: '20px', left: 0, right: 0,
    textAlign: 'center', padding: '0 10px', pointerEvents: 'none', zIndex: 2,
  }

  const variants: Record<string, React.CSSProperties> = {
    pro_karaoke: {
      fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 700, color: '#fff', letterSpacing: '.5px',
      textShadow: '0 2px 8px rgba(0,0,0,.9), -1px -1px 0 #000, 1px 1px 0 #000',
    },
    tiktok_bounce_v1: {
      fontFamily: 'var(--fh)', fontSize: '17px', fontWeight: 800, color: '#fff', letterSpacing: '1px',
      textShadow: '-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000',
    },
    viral_bold: {
      fontFamily: 'var(--fh)', fontSize: '18px', fontWeight: 900, color: '#FFE500', textTransform: 'uppercase',
      textShadow: '-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000',
    },
    bold_cap: {
      fontFamily: 'var(--fh)', fontSize: '16px', fontWeight: 900, color: '#fff', textTransform: 'uppercase',
      textShadow: '-1px -1px 0 #000, 1px 1px 0 #000, 0 2px 6px rgba(0,0,0,.8)',
    },
    story_clean_01: {
      fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 500, color: '#fff',
      background: 'rgba(0,0,0,.55)', padding: '5px 14px', borderRadius: '2px',
      display: 'inline-block',
    },
    boxed_caption: {
      fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 700, color: '#fff',
      background: '#000', padding: '4px 12px', display: 'inline-block',
    },
    clean_pro: {
      fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 400, color: '#fff',
      textShadow: '0 1px 6px rgba(0,0,0,.9)',
    },
    gaming: {
      fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 700, color: '#00E5C8', letterSpacing: '1px',
      textShadow: '0 0 12px rgba(0,229,200,.8), -1px -1px 0 #000, 1px 1px 0 #000',
    },
  }

  const textStyle = variants[style] ?? variants['pro_karaoke']
  const hlColor: Record<string, string> = {
    pro_karaoke: '#FFD700', tiktok_bounce_v1: '#00E5C8', viral_bold: '#fff',
    bold_cap: '#00E5C8', gaming: '#fff',
  }
  const hlC = hlColor[style] ?? 'var(--cyan)'

  return (
    <div style={baseBox}>
      <span style={textStyle}>
        Đây là{' '}
        <span style={{ color: hlC, WebkitTextFillColor: hlC }}> AI Clip</span>
        {' '}Studio
      </span>
    </div>
  )
}

// ── Step 2 — Configure ────────────────────────────────────────────────────────
function StepConfigure({
  cfg, cfgTab, setCfgTab, setCfgKey, applyPreset,
  sources, prepareResult, pickOutputDir, t,
}: {
  cfg: ConfigState; cfgTab: CfgTab; setCfgTab: (tab: CfgTab) => void
  setCfgKey: <K extends keyof ConfigState>(k: K, v: ConfigState[K]) => void
  applyPreset: (id: string) => void
  sources: Source[]
  prepareResult: PrepareSourceResponse | null
  pickOutputDir: () => void
  t: Strings
}) {
  const src       = sources[0]
  const ratioInfo = RATIO_INFO[cfg.ratio]
  const previewVideoUrl = prepareResult ? getPreviewVideoUrl(prepareResult.session_id) : null
  const ytThumb = src?.mode === 'youtube'
    ? (() => { const id = extractYouTubeId(src.value); return id ? `https://img.youtube.com/vi/${id}/hqdefault.jpg` : null })()
    : null
  const styleLabel = STYLES.find(s => s.id === cfg.style)?.label ?? cfg.style

  return (
    <div className="cfg-screen">
      {/* ── LEFT ── */}
      <div className="cfg-left">

        {/* Source info */}
        <div className="cfg-src-card">
          <div className="cfg-src-thumb">
            {ytThumb
              ? <img src={ytThumb} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : (src?.mode === 'youtube' ? '🎬' : '📁')
            }
          </div>
          <div className="cfg-src-info">
            <div className="cfg-src-name">
              {prepareResult?.title || (src?.value ? src.value.slice(0, 28) + '…' : 'No source')}
            </div>
            <div className="cfg-src-meta">
              {prepareResult ? fmtDuration(prepareResult.duration) : (src?.mode === 'youtube' ? 'YouTube' : 'Local File')}
            </div>
            <button className="cfg-src-change">{t.cfgChangeSource}</button>
          </div>
        </div>

        {/* Quick presets */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">{t.cfgQuickPresets}</div>
          <div className="preset-list">
            {PRESETS.map((p) => (
              <div key={p.id} className={`preset-card${cfg.preset === p.id ? ' on' : ''}`} onClick={() => applyPreset(p.id)}>
                <div className="preset-icon-wrap">{p.icon}</div>
                <div className="preset-info">
                  <div className="preset-name">{p.name}</div>
                  <div className="preset-desc">{p.desc}</div>
                </div>
                <div className="preset-badge-ai">AI</div>
              </div>
            ))}
          </div>
        </div>

        {/* Frame / Ratio */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>{t.cfgFrame}</span>
            <span className="cfg-sec-api">aspect_ratio</span>
          </div>
          <div className="ratio-cards">
            {(['r916', 'r34', 'r11'] as Ratio[]).map((r) => (
              <div key={r} className={`ratio-card${cfg.ratio === r ? ' on' : ''}`} onClick={() => setCfgKey('ratio', r)}>
                <div className={`ratio-vis ${r}-v`} />
                <div className="ratio-lbl">{RATIO_INFO[r].label}</div>
                <div className="ratio-sub">{RATIO_INFO[r].sub}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: '12px' }}>
            <div className="tog-row">
              <span className="tog-lbl">{t.cfgMotionCrop}</span>
              <Tog checked={cfg.motionCrop} onChange={(v) => setCfgKey('motionCrop', v)} />
            </div>
            <div className="tog-row">
              <span className="tog-lbl">{t.cfgFps}</span>
              <Tog checked={cfg.fps60} onChange={(v) => setCfgKey('fps60', v)} />
            </div>
          </div>
        </div>

        {/* Duration */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">{t.cfgDuration}</div>
          <div className="field">
            <div className="fl">
              <span>{t.cfgMinClip}</span>
              <span className="fl-api">min_part_sec</span>
            </div>
            <input type="range" className="range-in" min={5} max={120} value={cfg.minSec}
              onChange={(e) => setCfgKey('minSec', +e.target.value)} />
            <div className="range-vals">
              <span className="range-v">5s</span>
              <span className="range-v">{cfg.minSec}s</span>
              <span className="range-v">120s</span>
            </div>
          </div>
          <div className="field">
            <div className="fl">
              <span>{t.cfgMaxClip}</span>
              <span className="fl-api">max_part_sec</span>
            </div>
            <input type="range" className="range-in" min={10} max={300} value={cfg.maxSec}
              onChange={(e) => setCfgKey('maxSec', +e.target.value)} />
            <div className="range-vals">
              <span className="range-v">10s</span>
              <span className="range-v">{cfg.maxSec}s</span>
              <span className="range-v">300s</span>
            </div>
          </div>
          <div className="field">
            <div className="fl">
              <span>{t.cfgClipCount}</span>
              <span className="fl-api">max_export_parts</span>
            </div>
            <div className="clip-count-row">
              <button className="cnt-btn" onClick={() => setCfgKey('clipCount', Math.max(1, cfg.clipCount - 1))}>−</button>
              <span className="cnt-val">{cfg.clipCount}</span>
              <button className="cnt-btn" onClick={() => setCfgKey('clipCount', Math.min(50, cfg.clipCount + 1))}>+</button>
            </div>
          </div>
        </div>

      </div>{/* /cfg-left */}

      {/* ── CENTER ── */}
      <div className="cfg-center">
        <div className="cfg-center-top">
          <span className="pv-chip ac">{ratioInfo.label} · {ratioInfo.sub}</span>
          <span className="pv-chip cy">{styleLabel}</span>
          <span className="pv-chip">{cfg.platform.replace(/_/g, ' ')}</span>
          <div style={{ flex: 1 }} />
          {cfg.fps60 && <span className="pv-chip">60 FPS</span>}
          <span className="pv-chip">{cfg.minSec}s – {cfg.maxSec}s</span>
          <span className="pv-chip">{cfg.clipCount} clips</span>
        </div>

        <div className="cfg-canvas">
          <div className="pv-grid-bg" />
          <div className={`pv-frame ${cfg.ratio}`}>
            <span className="pvc tl" /><span className="pvc tr" />
            <span className="pvc bl" /><span className="pvc br" />
            {previewVideoUrl ? (
              <video
                key={previewVideoUrl}
                src={previewVideoUrl}
                autoPlay muted loop playsInline
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
              />
            ) : ytThumb ? (
              <img src={ytThumb} alt="thumbnail"
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            ) : (
              <div className="pv-placeholder">
                <span className="pv-play">▶</span>
                <span className="pv-hint">Preview updates as you configure</span>
              </div>
            )}
            {cfg.subEnabled && <SubtitleDemo style={cfg.subStyle} />}
          </div>
        </div>

        <div className="cfg-style-strip">
          <div className="cfg-sec-hd" style={{ marginBottom: '10px' }}>
            <span>{t.cfgVisualStyle}</span>
            <span className="cfg-sec-api">effect_preset</span>
          </div>
          <div className="style-strip-list">
            {STYLES.map((s) => (
              <div key={s.id} className={`style-strip-c${cfg.style === s.id ? ' on' : ''}`}
                onClick={() => setCfgKey('style', s.id)}>
                <div className="style-strip-ico">{s.ico}</div>
                <div className="style-strip-nm">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>{/* /cfg-center */}

      {/* ── RIGHT ── */}
      <div className="cfg-right">
        <div className="cfg-tabs">
          {([
            { id: 'ai' as CfgTab,     label: t.cfgTabAI     },
            { id: 'sub' as CfgTab,    label: t.cfgTabSub    },
            { id: 'narr' as CfgTab,   label: t.cfgTabNarr   },
            { id: 'output' as CfgTab, label: t.cfgTabOutput  },
          ]).map((tab) => (
            <button key={tab.id} className={`cfg-tab${cfgTab === tab.id ? ' on' : ''}`} onClick={() => setCfgTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="cfg-tab-body">
          {/* AI tab */}
          <div className={`cfg-tab-pane${cfgTab === 'ai' ? ' active' : ''}`}>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgPlatform}</span>
                <span className="cfg-sec-api">target_platform</span>
              </div>
              <div className="seg">
                {([
                  { v: 'tiktok' as const,           l: 'TikTok'  },
                  { v: 'youtube_shorts' as const,    l: 'YT Short'},
                  { v: 'instagram_reels' as const,   l: 'Reels'   },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.platform === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('platform', v)}>{l}</div>
                ))}
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">{t.cfgAIFeatures}</div>
              <div className="tog-row">
                <div>
                  <div className="tog-lbl">{t.cfgAIDirector}</div>
                  <div className="tog-desc">{t.cfgAIDirectorDesc}</div>
                </div>
                <Tog checked={cfg.aiEnabled} onChange={(v) => setCfgKey('aiEnabled', v)} />
              </div>
              <div className="tog-row" style={{ marginTop: '10px' }}>
                <div>
                  <div className="tog-lbl">{t.cfgMultiVariant}</div>
                  <div className="tog-desc">{t.cfgMultiVariantDesc}</div>
                </div>
                <Tog checked={cfg.multiVariant} onChange={(v) => setCfgKey('multiVariant', v)} />
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgRenderProfile}</span>
                <span className="cfg-sec-api">render_profile</span>
              </div>
              <select className="sel" value={cfg.renderProfile} onChange={(e) => setCfgKey('renderProfile', e.target.value as ConfigState['renderProfile'])}>
                <option value="fast">Fast</option>
                <option value="balanced">Balanced</option>
                <option value="quality">Quality</option>
              </select>
            </div>
          </div>

          {/* SUB tab */}
          <div className={`cfg-tab-pane${cfgTab === 'sub' ? ' active' : ''}`}>
            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgEnableSub}</span>
                <Tog checked={cfg.subEnabled} onChange={(v) => setCfgKey('subEnabled', v)} />
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgSubStyle}</span>
                <span className="cfg-sec-api">subtitle_style</span>
              </div>
              <div className="sub-grid">
                {SUB_STYLES.map((s) => (
                  <div key={s.id} className={`sub-b${cfg.subStyle === s.id ? ' on' : ''}`}
                    onClick={() => setCfgKey('subStyle', s.id)}>{s.label}</div>
                ))}
              </div>
            </div>
            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgAutoTranslate}</span>
                <Tog checked={cfg.autoTranslate} onChange={(v) => setCfgKey('autoTranslate', v)} />
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgTargetLang}</span>
                <span className="cfg-sec-api">subtitle_target_language</span>
              </div>
              <select className="sel" value={cfg.subtitleLang} onChange={(e) => setCfgKey('subtitleLang', e.target.value)}>
                <option value="vi">🇻🇳 Tiếng Việt</option>
                <option value="en">🇺🇸 English</option>
                <option value="ja">🇯🇵 日本語</option>
              </select>
            </div>
          </div>

          {/* NARR tab */}
          <div className={`cfg-tab-pane${cfgTab === 'narr' ? ' active' : ''}`}>
            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgEnableVoice}</span>
                <Tog checked={cfg.narrEnabled} onChange={(v) => setCfgKey('narrEnabled', v)} />
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgVoiceSource}</span>
                <span className="cfg-sec-api">voice_source</span>
              </div>
              <div className="seg" style={{ flexDirection: 'column', gap: '3px' }}>
                {([
                  { v: 'subtitle' as const,             l: t.cfgVoiceSrcAuto,   d: t.cfgVoiceSrcAutoDesc   },
                  { v: 'translated_subtitle' as const,  l: t.cfgVoiceSrcTrans,  d: t.cfgVoiceSrcTransDesc  },
                  { v: 'manual' as const,               l: t.cfgVoiceSrcManual, d: t.cfgVoiceSrcManualDesc },
                ]).map(({ v, l, d }) => (
                  <div key={v} className={`seg-b${cfg.voiceSource === v ? ' on' : ''}`}
                    style={{ textAlign: 'left', padding: '7px 10px' }}
                    onClick={() => setCfgKey('voiceSource', v)}>
                    <div>{l}</div>
                    <div style={{ fontSize: '9px', color: cfg.voiceSource === v ? 'rgba(255,255,255,.6)' : 'var(--text-3)', marginTop: '1px', fontFamily: 'var(--fb)', fontWeight: 400 }}>{d}</div>
                  </div>
                ))}
              </div>
              {cfg.voiceSource === 'manual' && (
                <div style={{ marginTop: '8px' }}>
                  <textarea
                    className="dir-in"
                    placeholder={t.cfgVoiceSrcManualDesc}
                    value={cfg.voiceText}
                    onChange={(e) => setCfgKey('voiceText', e.target.value)}
                    style={{ width: '100%', minHeight: '80px', resize: 'vertical', fontFamily: 'var(--fb)', fontSize: '12px' }}
                  />
                </div>
              )}
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgVoiceLang}</span>
                <span className="cfg-sec-api">voice_language</span>
              </div>
              <select className="sel" value={cfg.voiceLang} onChange={(e) => setCfgKey('voiceLang', e.target.value)}>
                <option value="vi">🇻🇳 Tiếng Việt</option>
                <option value="en-us">🇺🇸 English (US)</option>
                <option value="en-gb">🇬🇧 English (UK)</option>
                <option value="ja">🇯🇵 日本語</option>
              </select>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgVoiceGender}</span>
                <span className="cfg-sec-api">voice_gender</span>
              </div>
              <div className="seg">
                <div className={`seg-b${cfg.voiceGender === 'female' ? ' on' : ''}`} onClick={() => setCfgKey('voiceGender', 'female')}>♀ Female</div>
                <div className={`seg-b${cfg.voiceGender === 'male'   ? ' on' : ''}`} onClick={() => setCfgKey('voiceGender', 'male')}>♂ Male</div>
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgEngine}</span>
                <span className="cfg-sec-api">tts_engine</span>
              </div>
              <div className="seg">
                <div className={`seg-b${cfg.ttsEngine === 'edge' ? ' on' : ''}`} onClick={() => setCfgKey('ttsEngine', 'edge')} title="Fast, free">Edge TTS</div>
                <div className={`seg-b${cfg.ttsEngine === 'xtts' ? ' on' : ''}`} onClick={() => setCfgKey('ttsEngine', 'xtts')} title="Local AI">XTTS AI</div>
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgMixMode}</span>
                <span className="cfg-sec-api">voice_mix_mode</span>
              </div>
              <select className="sel" value={cfg.voiceMixMode} onChange={(e) => setCfgKey('voiceMixMode', e.target.value)}>
                <option value="replace_original">Replace original audio</option>
                <option value="keep_original_low">Keep original (low)</option>
              </select>
            </div>
          </div>

          {/* OUTPUT tab */}
          <div className={`cfg-tab-pane${cfgTab === 'output' ? ' active' : ''}`}>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgSaveFolder}</span>
                <span className="cfg-sec-api">output_dir</span>
              </div>
              <div className="dir-row">
                <input className="dir-in" type="text" placeholder="D:\Videos\Output" value={cfg.outputDir}
                  onChange={(e) => setCfgKey('outputDir', e.target.value)} />
                <button className="btn-xs" onClick={pickOutputDir} title="Browse">Browse</button>
              </div>
              {prepareResult?.export_dir && (
                <div style={{ fontSize: '10px', color: 'var(--text-3)', marginTop: '6px', wordBreak: 'break-all', lineHeight: 1.5 }}>
                  Default: {prepareResult.export_dir}
                </div>
              )}
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgRanking}</span>
                <span className="cfg-sec-api">part_order</span>
              </div>
              <select className="sel" value={cfg.ranking} onChange={(e) => setCfgKey('ranking', e.target.value as ConfigState['ranking'])}>
                <option value="viral">Viral Score (AI)</option>
                <option value="sequential">Sequential</option>
              </select>
            </div>
            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgAutoExport}</span>
                <Tog checked={cfg.autoExport} onChange={(v) => setCfgKey('autoExport', v)} />
              </div>
            </div>
          </div>
        </div>
      </div>{/* /cfg-right */}
    </div>
  )
}

// ── Step 3 — Rendering ────────────────────────────────────────────────────────

type ClipSlot = { part_no: number; status: string; progress_percent: number }

function buildClipSlots(liveParts: JobPart[], progress: WsProgressSummary | null): ClipSlot[] {
  if (liveParts.length > 0) {
    return liveParts.map((p) => ({ part_no: p.part_no, status: p.status, progress_percent: p.progress_percent ?? 0 }))
  }
  if (!progress) return []
  const slots: ClipSlot[] = []
  const active = progress.active_parts ?? []
  let no = 1
  for (let i = 0; i < progress.completed_parts; i++) slots.push({ part_no: no++, status: 'done', progress_percent: 100 })
  active.forEach((a) => slots.push({ part_no: a.part_no, status: a.status, progress_percent: a.progress_percent }))
  for (let i = 0; i < progress.failed_parts; i++) slots.push({ part_no: no++, status: 'failed', progress_percent: 0 })
  for (let i = 0; i < progress.pending_parts; i++) slots.push({ part_no: no++, status: 'waiting', progress_percent: 0 })
  return slots
}

function getActivePhaseIdx(stage: string, jobStatus: string): number {
  const s = (stage || jobStatus).toLowerCase()
  if (s === 'done') return 4
  if (s.includes('render') || s.includes('writing')) return 3
  if (s.includes('transcrib')) return 2
  if (s.includes('scene') || s.includes('segment')) return 1
  if (s.includes('download')) return 0
  return -1
}

function clipStateKey(status: string): 'done' | 'failed' | 'active' | 'waiting' {
  const s = status.toLowerCase()
  if (s === 'done') return 'done'
  if (s === 'failed' || s === 'cancelled') return 'failed'
  if (s === 'waiting' || s === 'queued') return 'waiting'
  return 'active'
}

// Per-step activity descriptions shown under active clip rows
const ACTIVITY_LABELS: Record<string, string> = {
  cutting:      'Extracting video segment · FFmpeg',
  transcribing: 'Generating subtitles · Whisper AI',
  rendering:    'Encoding clip · FFmpeg NVENC',
}

// Step icons for the step-progress indicator inside each clip
const STEP_NODES = [
  { key: 'cutting',      label: 'Cut' },
  { key: 'transcribing', label: 'Sub' },
  { key: 'rendering',    label: 'Render' },
]

function ClipRow({ slot, statusLabel }: { slot: ClipSlot; statusLabel: string }) {
  const state   = clipStateKey(slot.status)
  const pct     = slot.progress_percent
  const isDone  = state === 'done'
  const isFail  = state === 'failed'
  const isWait  = state === 'waiting'
  const isActive = state === 'active'
  const activity = ACTIVITY_LABELS[slot.status.toLowerCase()] ?? ''

  // Which step node is active/done inside this clip row
  const activeStepIdx = STEP_NODES.findIndex((n) => n.key === slot.status.toLowerCase())

  return (
    <div className={`rndv-row rndv-row-${state}`}>
      {/* Left accent bar */}
      <div className="rndv-row-accent" />

      <div className="rndv-row-body">
        {/* Top line: number badge · status badge · bar · pct */}
        <div className="rndv-row-top">
          <div className="rndv-clip-num">#{slot.part_no}</div>

          <div className={`rndv-badge rndv-badge-${state}`}>
            {isActive && <span className="rndv-live-dot" />}
            {isDone && <span className="rndv-check">✓</span>}
            {isFail && <span className="rndv-fail-x">✕</span>}
            <span className="rndv-badge-label">{statusLabel}</span>
          </div>

          {/* Progress bar */}
          <div className="rndv-bar-wrap">
            <div className="rndv-bar-track">
              <div
                className={`rndv-bar-fill rndv-bar-${state}`}
                style={{ width: `${isDone ? 100 : isFail || isWait ? 0 : pct}%` }}
              />
            </div>
          </div>

          {/* Percentage / status indicator */}
          <div className={`rndv-pct rndv-pct-${state}`}>
            {isDone ? '100%' : isFail ? 'ERR' : isWait ? '—' : `${pct}%`}
          </div>
        </div>

        {/* Active clip: step nodes + activity label */}
        {isActive && (
          <div className="rndv-row-detail">
            {/* Mini step nodes */}
            <div className="rndv-steps">
              {STEP_NODES.map((n, i) => {
                const stepState = i < activeStepIdx ? 'done' : i === activeStepIdx ? 'active' : 'pending'
                return (
                  <React.Fragment key={n.key}>
                    <div className={`rndv-step rndv-step-${stepState}`}>
                      <div className="rndv-step-dot">
                        {stepState === 'done' ? '✓' : stepState === 'active' ? <span className="rndv-step-pulse" /> : null}
                      </div>
                      <span className="rndv-step-label">{n.label}</span>
                    </div>
                    {i < STEP_NODES.length - 1 && (
                      <div className={`rndv-step-line${i < activeStepIdx ? ' done' : ''}`} />
                    )}
                  </React.Fragment>
                )
              })}
            </div>
            {/* Activity text */}
            {activity && <div className="rndv-activity">{activity}</div>}
          </div>
        )}
      </div>
    </div>
  )
}

function StepRendering({
  jobId, stage, jobStatus, progress, jobMessage, isTerminal, liveParts, t,
}: {
  jobId: string | null; stage: string; jobStatus: string
  progress: WsProgressSummary | null; jobMessage: string
  isTerminal: boolean; liveParts: JobPart[]; t: Strings
}) {
  const pct         = progress?.overall_progress_percent ?? 0
  const doneCount   = progress?.completed_parts ?? 0
  const totalCount  = progress?.total_parts ?? liveParts.length
  const failedCount = progress?.failed_parts ?? 0

  const startRef = useRef<number>(Date.now())
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (isTerminal) return
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000)
    return () => clearInterval(id)
  }, [isTerminal])
  const mm = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const ss = (elapsed % 60).toString().padStart(2, '0')

  const phases = [
    { key: 'download',   label: t.rndPhaseDownload },
    { key: 'analyze',    label: t.rndPhaseAnalyze },
    { key: 'transcribe', label: t.rndPhaseTranscribe },
    { key: 'render',     label: t.rndPhaseRender },
    { key: 'done',       label: t.rndPhaseDone },
  ]
  const activePhaseIdx = getActivePhaseIdx(stage, jobStatus)
  const clipSlots      = buildClipSlots(liveParts, progress)

  function getStatusLabel(s: string): string {
    const sl = s.toLowerCase()
    if (sl === 'done') return t.rndStatusDone
    if (sl === 'rendering') return t.rndStatusRendering
    if (sl === 'cutting') return t.rndStatusCutting
    if (sl === 'transcribing') return t.rndStatusTranscribing
    if (sl === 'failed' || sl === 'cancelled') return t.rndStatusFailed
    return t.rndStatusWaiting
  }

  const isFailed   = jobStatus?.toLowerCase().includes('fail') || jobStatus?.toLowerCase() === 'cancelled'
  const displayMsg = jobMessage
    || (isTerminal ? (isFailed ? '✕ ' + t.rndStatusFailed : '✓ ' + t.rndComplete) : t.rndPreparing)

  return (
    <div className="rnd-screen">

      {/* ── Compact header: pipeline + overall bar ── */}
      <div className="rndv-header">
        {/* Pipeline nodes */}
        <div className="rndv-pipeline">
          {phases.map((ph, idx) => {
            const state = idx < activePhaseIdx ? 'done' : idx === activePhaseIdx ? 'active' : 'pending'
            return (
              <React.Fragment key={ph.key}>
                <div className={`rndv-phase rndv-phase-${state}`}>
                  <div className="rndv-phase-dot">
                    {state === 'done' ? '✓' : state === 'active' ? <span className="rndv-phase-pulse" /> : idx + 1}
                  </div>
                  <span className="rndv-phase-label">{ph.label}</span>
                </div>
                {idx < phases.length - 1 && (
                  <div className={`rndv-phase-line${idx < activePhaseIdx ? ' done' : ''}`} />
                )}
              </React.Fragment>
            )
          })}
        </div>

        {/* Overall progress row */}
        <div className="rndv-overall">
          <div className="rndv-overall-left">
            <span className="rndv-overall-pct">{Math.round(pct)}<span className="rndv-overall-sym">%</span></span>
            <div className="rndv-overall-meta">
              {totalCount > 0 && (
                <span className="rndv-overall-clips">
                  {t.rndClipsDone(doneCount, totalCount)}
                  {failedCount > 0 && <span className="rndv-clips-failed"> · {t.rndClipsFailed(failedCount)}</span>}
                </span>
              )}
              <span className="rndv-overall-msg">{displayMsg}</span>
            </div>
          </div>
          <div className="rndv-overall-right">
            <div className="rndv-overall-bar-track">
              <div className="rndv-overall-bar-fill" style={{ width: `${pct}%` }} />
            </div>
            {!isTerminal && jobId && <span className="rndv-elapsed">{mm}:{ss}</span>}
          </div>
        </div>
      </div>

      {/* ── Per-clip rows ── */}
      {clipSlots.length === 0 ? (
        <div className="rnd-waiting-msg">
          <span className="rnd-waiting-dot" />
          {t.rndPreparing}
        </div>
      ) : (
        <div className="rndv-clip-list">
          {clipSlots.map((slot) => (
            <ClipRow key={slot.part_no} slot={slot} statusLabel={getStatusLabel(slot.status)} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Step 4 — Results ──────────────────────────────────────────────────────────

function aiTier(score: number): { label: string; cls: string } {
  if (score >= 85) return { label: 'VIRAL READY', cls: 'tier-viral' }
  if (score >= 70) return { label: 'HIGH IMPACT', cls: 'tier-high' }
  if (score >= 55) return { label: 'GOOD', cls: 'tier-good' }
  return { label: 'REVIEW', cls: 'tier-review' }
}

function ScoreRingSm({ score }: { score: number }) {
  const r = 13, circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  const col = score >= 70 ? 'var(--ok)' : score >= 40 ? 'var(--warn)' : 'var(--fail)'
  return (
    <div className="sr-wrap">
      <svg width="34" height="34" viewBox="0 0 34 34" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="17" cy="17" r={r} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="3.5" />
        <circle cx="17" cy="17" r={r} fill="none" stroke={col} strokeWidth="3.5"
          strokeDasharray={`${fill} ${circ}`} strokeLinecap="round" />
      </svg>
      <span className="sr-num" style={{ color: col }}>{Math.round(score)}</span>
    </div>
  )
}

function ScoreRingLg({ score }: { score: number }) {
  const r = 28, circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  const col = score >= 70 ? 'var(--ok)' : score >= 40 ? 'var(--warn)' : 'var(--fail)'
  const tier = aiTier(score)
  return (
    <div className="srl-wrap">
      <div style={{ position: 'relative', width: 68, height: 68, flexShrink: 0 }}>
        <svg width="68" height="68" viewBox="0 0 68 68" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="34" cy="34" r={r} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="6" />
          <circle cx="34" cy="34" r={r} fill="none" stroke={col} strokeWidth="6"
            strokeDasharray={`${fill} ${circ}`} strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.5s ease' }} />
        </svg>
        <div className="srl-num" style={{ color: col }}>{Math.round(score)}</div>
      </div>
      <div className="srl-info">
        <div className={`res-ai-tier ${tier.cls}`}>{tier.label}</div>
        <div className="srl-sub">AI Quality Score</div>
      </div>
    </div>
  )
}

function StepResults({
  jobId, parts, partScores, qualityReports, loading, t, aspectRatio,
}: {
  jobId: string | null
  parts: JobPart[]
  partScores: Record<number, number>
  qualityReports: Record<number, QualityReport | null>
  loading: boolean
  t: Strings
  aspectRatio: string
}) {
  const [selectedPart, setSelectedPart] = useState<JobPart | null>(null)
  const doneParts  = parts.filter((p) => p.status === 'done')
  const failedParts = parts.filter((p) => p.status === 'failed')
  const sortedDone = [...doneParts].sort((a, b) => (partScores[b.part_no] ?? 0) - (partScores[a.part_no] ?? 0))

  const outputDir = (() => {
    const f = doneParts[0]?.output_file
    if (!f) return null
    const sep = f.includes('\\') ? '\\' : '/'
    return f.substring(0, f.lastIndexOf(sep)) || null
  })()

  const openOutputFolder = async () => {
    const api = (window as any).electronAPI
    if (api?.openPath && outputDir) await api.openPath(outputDir)
  }

  const selScore  = selectedPart ? partScores[selectedPart.part_no] : undefined
  const selReport = selectedPart ? qualityReports[selectedPart.part_no] : undefined

  const fmtMetric = (v: unknown): string => {
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
    if (typeof v === 'boolean') return v ? 'Yes' : 'No'
    return String(v ?? '—')
  }

  const SEV_COL: Record<string, string> = {
    critical: 'var(--fail)', error: '#f97316', warning: 'var(--warn)', info: 'var(--cyan)',
  }

  // '9:16' → '9/16', '3:4' → '3/4', '1:1' → '1/1'
  const thumbRatio = aspectRatio.replace(':', '/')

  if (!jobId) {
    return (
      <div className="res-screen">
        <div className="res-left">
          <div className="rw-empty"><span className="rw-empty-icon">📭</span>{t.resNoResults}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="res-screen">
      {/* ── Clip grid ── */}
      <div className="res-left">
        <div className="res-toolbar">
          <div className="res-count">
            {t.resClipsRendered(doneParts.length)}
            {failedParts.length > 0 && (
              <span style={{ color: 'var(--fail)', marginLeft: 8, fontSize: 11 }}>· {failedParts.length} failed</span>
            )}
          </div>
          <div className="res-sort">
            <button className="sort-btn on">{t.resSortViral}</button>
            <button className="sort-btn">{t.resSortDuration}</button>
          </div>
        </div>

        {outputDir && (
          <div className="res-output-banner">
            <span className="res-output-icon">📁</span>
            <span className="res-output-path" title={outputDir}>{outputDir}</span>
            <button className="res-open-btn" onClick={openOutputFolder}>Open Folder</button>
          </div>
        )}

        {loading ? (
          <div className="rw-empty">
            <div style={{ width: 32, height: 32, border: '2px solid var(--border-hi)', borderTop: '2px solid var(--accent)', borderRadius: '50%', animation: 'rw-spin 0.8s linear infinite' }} />
            {t.resLoading}
          </div>
        ) : doneParts.length === 0 ? (
          <div className="rw-empty">
            <span className="rw-empty-icon">📭</span>{t.resNoClips}
          </div>
        ) : (
          <div className="clip-grid-area">
            {sortedDone.map((part, i) => {
              const score     = partScores[part.part_no]
              const report    = qualityReports[part.part_no]
              const thumbUrl  = getPartThumbnailUrl(jobId, part.part_no)
              const isBest    = i === 0
              const isSelected = selectedPart?.part_no === part.part_no
              const tier      = score !== undefined ? aiTier(score) : null
              const issueCount = report?.issues?.length ?? 0

              return (
                <div
                  key={part.part_no}
                  className={`clip-card${isSelected ? ' selected' : ''}`}
                  onClick={() => setSelectedPart(isSelected ? null : part)}
                >
                  {/* Thumbnail — aspect ratio matches the rendered output */}
                  <div className="clip-thumb" style={{ aspectRatio: thumbRatio }}>
                    <img src={thumbUrl} alt={`Clip ${part.part_no}`}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />

                    {/* Top-left: BEST badge */}
                    {isBest && <span className="clip-best">BEST</span>}

                    {/* Top-right: AI score ring */}
                    {score !== undefined && (
                      <div className="clip-score-ring">
                        <ScoreRingSm score={score} />
                      </div>
                    )}

                    {/* Hover overlay */}
                    <div className="clip-overlay">
                      <a href={getPartMediaUrl(jobId, part.part_no)} target="_blank" rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}>
                        <button className="clip-ov-btn">▶</button>
                      </a>
                      <a href={getPartMediaUrl(jobId, part.part_no)} download={`clip_${part.part_no}.mp4`}
                        onClick={(e) => e.stopPropagation()}>
                        <button className="clip-ov-btn">⬇</button>
                      </a>
                    </div>
                  </div>

                  {/* Info bar */}
                  <div className="clip-info">
                    <div className="clip-row-top">
                      <span className="clip-num-lbl">#{String(part.part_no).padStart(2, '0')}</span>
                      {tier && <span className={`clip-ai-badge ${tier.cls}`}>{tier.label}</span>}
                    </div>

                    {/* Hook / Viral score pills */}
                    {(part.hook_score > 0 || part.viral_score > 0) && (
                      <div className="clip-scores-row">
                        {part.hook_score > 0 && (
                          <span className="clip-score-pill hook">
                            Hook {Math.round(part.hook_score)}%
                          </span>
                        )}
                        {part.viral_score > 0 && (
                          <span className="clip-score-pill viral">
                            Viral {Math.round(part.viral_score)}%
                          </span>
                        )}
                      </div>
                    )}

                    {issueCount > 0 ? (
                      <div className="clip-issue-row">
                        <span className="clip-issue-dot" />
                        {issueCount} issue{issueCount > 1 ? 's' : ''}
                      </div>
                    ) : report ? (
                      <div className="clip-ok-row">✓ Passed</div>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── Detail panel ── */}
      <div className={`player-panel${selectedPart ? '' : ' collapsed'}`}>
        <div className="player-hd">
          <span className="player-hd-title">
            {selectedPart ? `Clip #${String(selectedPart.part_no).padStart(2, '0')}` : t.resClipViewer}
          </span>
          <button className="player-close" onClick={() => setSelectedPart(null)}>✕</button>
        </div>

        <div className="player-video-area">
          {selectedPart ? (
            <>
              {/* Video — same aspect ratio as the rendered clip */}
              <div className="player-frame" style={{ aspectRatio: thumbRatio }}>
                <video
                  key={selectedPart.part_no}
                  src={getPartMediaUrl(jobId, selectedPart.part_no)}
                  controls
                  style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
                />
              </div>

              {/* Score ring + tier */}
              {selScore !== undefined && <ScoreRingLg score={selScore} />}

              {/* Hook / Viral / Motion score bars */}
              {selectedPart && (selectedPart.hook_score > 0 || selectedPart.viral_score > 0 || selectedPart.motion_score > 0) && (
                <div className="player-score-bars">
                  {selectedPart.hook_score > 0 && (
                    <div className="psb-row">
                      <span className="psb-label">Hook</span>
                      <div className="psb-track">
                        <div className="psb-fill psb-hook" style={{ width: `${selectedPart.hook_score}%` }} />
                      </div>
                      <span className="psb-val">{Math.round(selectedPart.hook_score)}%</span>
                    </div>
                  )}
                  {selectedPart.viral_score > 0 && (
                    <div className="psb-row">
                      <span className="psb-label">Viral</span>
                      <div className="psb-track">
                        <div className="psb-fill psb-viral" style={{ width: `${selectedPart.viral_score}%` }} />
                      </div>
                      <span className="psb-val">{Math.round(selectedPart.viral_score)}%</span>
                    </div>
                  )}
                  {selectedPart.motion_score > 0 && (
                    <div className="psb-row">
                      <span className="psb-label">Motion</span>
                      <div className="psb-track">
                        <div className="psb-fill psb-motion" style={{ width: `${selectedPart.motion_score}%` }} />
                      </div>
                      <span className="psb-val">{Math.round(selectedPart.motion_score)}%</span>
                    </div>
                  )}
                </div>
              )}

              {/* AI analysis section */}
              <div className="player-section">
                <div className="player-section-title">AI Analysis</div>

                {/* Issues */}
                {selReport && selReport.issues.length > 0 ? (
                  <div className="player-issues">
                    {selReport.issues.map((iss, i) => (
                      <div key={i} className="player-issue-row">
                        <span className="player-issue-dot" style={{ background: SEV_COL[iss.severity] ?? '#888' }} />
                        <div>
                          <div className="player-issue-msg">{iss.message}</div>
                          {iss.recommended_action && (
                            <div className="player-issue-action">{iss.recommended_action}</div>
                          )}
                        </div>
                        <span className="player-issue-sev" style={{ color: SEV_COL[iss.severity] ?? '#888' }}>
                          {iss.severity}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : selReport ? (
                  <div className="player-all-ok">✓ No issues — all quality checks passed</div>
                ) : (
                  <div className="player-no-data">Quality data loading…</div>
                )}
              </div>

              {/* Metrics grid */}
              {selReport && Object.keys(selReport.metrics).length > 0 && (
                <div className="player-section">
                  <div className="player-section-title">Metrics</div>
                  <div className="player-metrics-grid">
                    {Object.entries(selReport.metrics)
                      .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
                      .map(([k, v]) => (
                        <div key={k} className="player-metric-cell">
                          <div className="player-metric-key">{k.replace(/_/g, ' ')}</div>
                          <div className="player-metric-val">{fmtMetric(v)}</div>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="player-btns">
                <a className="player-btn" href={getPartMediaUrl(jobId, selectedPart.part_no)} target="_blank" rel="noreferrer">{t.btnPlay}</a>
                <a className="player-btn primary" href={getPartMediaUrl(jobId, selectedPart.part_no)} download={`clip_${selectedPart.part_no}.mp4`}>{t.btnExport}</a>
              </div>
            </>
          ) : (
            <div className="player-placeholder">🎬</div>
          )}
        </div>
      </div>
    </div>
  )
}
