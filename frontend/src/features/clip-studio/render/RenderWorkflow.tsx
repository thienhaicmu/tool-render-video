import React, { useState, useRef, useEffect } from 'react'
import './RenderWorkflow.css'
import type { Lang } from '../ClipStudio'
import { useRenderStore } from '../../../stores/renderStore'
import { useRenderSocket } from '../../../hooks/useRenderSocket'
import { prepareSource, getPreviewVideoUrl, cancelRender, cancelPrepareSource, retryRender, resumeRender, getPreviewTranscript } from '../../../api/render'
import type { TranscriptSegment } from '../../../api/render'
import { getJobParts, getJobQualitySummary } from '../../../api/jobs'
import { uploadFile } from '../../../api/upload'
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
    cfgCTAEnable: 'Call to Action', cfgCTAEnableDesc: 'Append a CTA at the end of each clip',
    cfgCTAType: 'CTA TYPE',
    cfgCTAAuto: 'Auto', cfgCTAComment: 'Comment', cfgCTAPart2: 'Part 2', cfgCTAFollow: 'Follow',
    cfgClipLock: 'CLIP LOCK', cfgClipLockDesc: 'Force-include these time ranges',
    cfgClipExclude: 'CLIP EXCLUDE', cfgClipExcludeDesc: 'Never include these time ranges',
    cfgRangeStart: 'Start (s)', cfgRangeEnd: 'End (s)', cfgAddRange: '+ ADD',
    cfgHookApply: 'Hook Intro', cfgHookApplyDesc: 'Apply AI-selected hook at clip start',
    cfgHookOverlay: 'Hook Overlay', cfgHookOverlayDesc: 'Add branded overlay to hook segment',
    cfgStructureBias: 'STRUCTURE BIAS', cfgBiasOff: 'Off',
    cfgBiasHook: 'Hook', cfgBiasBalanced: 'Balanced', cfgBiasStory: 'Story',
    cfgSubEmphasis: 'SUBTITLE EMPHASIS', cfgEmphasisOff: 'Off',
    cfgEmphasisSubtle: 'Subtle', cfgEmphasisBalanced: 'Balanced', cfgEmphasisAggressive: 'Aggressive',
    cfgSrcQuality: 'DOWNLOAD QUALITY', cfgSrcQualityStd: '1080p', cfgSrcQualityHigh: '1440p', cfgSrcQualityBest: 'Best',
    cfgAssets: 'CREATOR ASSETS',
    cfgAssetLogo: 'Logo / Watermark', cfgAssetLogoDesc: 'PNG/JPEG corner overlay',
    cfgAssetIntro: 'Intro Sting', cfgAssetIntroDesc: 'Short clip prepended to each output',
    cfgAssetOutro: 'Outro / Bumper', cfgAssetOutroDesc: 'Bumper clip appended to each output',
    cfgAssetMusicProfile: 'MUSIC PROFILE',
    cfgAssetMusicOff: 'Off', cfgAssetMusicClean: 'Clean', cfgAssetMusicEnergetic: 'Energetic', cfgAssetMusicSoft: 'Soft',
    cfgAssetUpload: 'Upload', cfgAssetReplace: 'Replace',
    cfgWhisperModel: 'TRANSCRIPTION MODEL',
    cfgWhisperAuto: 'Auto', cfgWhisperTiny: 'Tiny', cfgWhisperBase: 'Base', cfgWhisperSmall: 'Small', cfgWhisperMedium: 'Medium',
    cfgRenderProfile: 'RENDER PROFILE',
    cfgEnableSub: 'Enable Subtitles', cfgSubStyle: 'STYLE',
    cfgHighlightWord: 'Highlight Per Word', cfgFontSize: 'Font Size',
    cfgAutoTranslate: 'Auto-Translate', cfgTargetLang: 'TARGET LANGUAGE',
    cfgEnableVoice: 'Enable Voiceover', cfgVoiceSource: 'VOICE SOURCE',
    cfgVoiceSrcAuto: 'Auto (from transcript)', cfgVoiceSrcAutoDesc: 'Read from video transcript',
    cfgVoiceSrcTrans: 'Translated subtitle',   cfgVoiceSrcTransDesc: 'Read from translated subtitles',
    cfgVoiceSrcManual: 'Custom text',          cfgVoiceSrcManualDesc: 'Enter text manually',
    cfgVoiceLang: 'LANGUAGE', cfgVoiceGender: 'VOICE', cfgEngine: 'ENGINE', cfgMixMode: 'MIX MODE',
    cfgSaveFolder: 'SAVE FOLDER', cfgRanking: 'RANKING', cfgAutoExport: 'Auto-export best 3',
    cfgChangeSource: '← CHANGE SOURCE',
    cfgPartOrder: 'PART ORDER', cfgOrderViral: 'Viral First', cfgOrderSeq: 'Sequential',
    cfgTranscript: 'TRANSCRIPT PREVIEW', cfgTranscriptLoad: 'Load preview…', cfgTranscriptEmpty: 'No transcript available',
    btnBack: '← BACK', btnStartRender: 'START RENDER ▶',
    // Rendering
    rndWaiting: 'Waiting for job…', rndInProgress: 'Rendering in progress…', rndComplete: '✓ Render complete',
    rndFailed: '✗ Render failed', rndCancelled: '✗ Render cancelled',
    rndPartial: '⚠ Partial success', rndInterrupted: '✗ Interrupted',
    rndWsError: 'Connection lost — check job history for status',
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
    resFailedParts: 'Failed Clips', resNoReason: 'No detail available',
    btnRetry: 'RETRY FAILED', btnResume: 'RESUME',
    qualityLoadFailed: 'Quality data could not be loaded',
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
    cfgCTAEnable: 'Kêu gọi hành động', cfgCTAEnableDesc: 'Thêm CTA vào cuối mỗi clip',
    cfgCTAType: 'LOẠI CTA',
    cfgCTAAuto: 'Tự động', cfgCTAComment: 'Bình luận', cfgCTAPart2: 'Phần 2', cfgCTAFollow: 'Theo dõi',
    cfgClipLock: 'KHÓA ĐOẠN', cfgClipLockDesc: 'Bắt buộc giữ các khoảng thời gian này',
    cfgClipExclude: 'LOẠI TRỪ ĐOẠN', cfgClipExcludeDesc: 'Không bao giờ dùng các khoảng này',
    cfgRangeStart: 'Bắt đầu (s)', cfgRangeEnd: 'Kết thúc (s)', cfgAddRange: '+ THÊM',
    cfgHookApply: 'Hook Intro', cfgHookApplyDesc: 'Áp dụng hook AI vào đầu clip',
    cfgHookOverlay: 'Hook Overlay', cfgHookOverlayDesc: 'Thêm overlay thương hiệu vào đoạn hook',
    cfgStructureBias: 'ĐỊNH HƯỚNG CẤU TRÚC', cfgBiasOff: 'Tắt',
    cfgBiasHook: 'Hook', cfgBiasBalanced: 'Cân bằng', cfgBiasStory: 'Câu chuyện',
    cfgSubEmphasis: 'NHẤN MẠNH PHỤ ĐỀ', cfgEmphasisOff: 'Tắt',
    cfgEmphasisSubtle: 'Nhẹ', cfgEmphasisBalanced: 'Cân bằng', cfgEmphasisAggressive: 'Mạnh',
    cfgSrcQuality: 'CHẤT LƯỢNG TẢI', cfgSrcQualityStd: '1080p', cfgSrcQualityHigh: '1440p', cfgSrcQualityBest: 'Tốt nhất',
    cfgAssets: 'TÀI NGUYÊN CREATOR',
    cfgAssetLogo: 'Logo / Watermark', cfgAssetLogoDesc: 'Overlay góc PNG/JPEG',
    cfgAssetIntro: 'Intro', cfgAssetIntroDesc: 'Clip ngắn thêm vào đầu mỗi output',
    cfgAssetOutro: 'Outro / Bumper', cfgAssetOutroDesc: 'Clip kết thêm vào cuối mỗi output',
    cfgAssetMusicProfile: 'PROFILE NHẠC',
    cfgAssetMusicOff: 'Tắt', cfgAssetMusicClean: 'Nhẹ nhàng', cfgAssetMusicEnergetic: 'Năng động', cfgAssetMusicSoft: 'Mềm',
    cfgAssetUpload: 'Tải lên', cfgAssetReplace: 'Thay',
    cfgWhisperModel: 'MODEL PHIÊN ÂM',
    cfgWhisperAuto: 'Tự động', cfgWhisperTiny: 'Tiny', cfgWhisperBase: 'Base', cfgWhisperSmall: 'Small', cfgWhisperMedium: 'Medium',
    cfgRenderProfile: 'CHẾ ĐỘ RENDER',
    cfgEnableSub: 'Bật phụ đề', cfgSubStyle: 'KIỂU',
    cfgHighlightWord: 'Tô sáng từng từ', cfgFontSize: 'Cỡ chữ',
    cfgAutoTranslate: 'Tự dịch', cfgTargetLang: 'NGÔN NGỮ ĐÍCH',
    cfgEnableVoice: 'Bật thuyết minh', cfgVoiceSource: 'NGUỒN GIỌNG',
    cfgVoiceSrcAuto: 'Tự động (từ transcript)', cfgVoiceSrcAutoDesc: 'Đọc từ transcript video',
    cfgVoiceSrcTrans: 'Subtitle đã dịch',       cfgVoiceSrcTransDesc: 'Đọc từ subtitle đã dịch',
    cfgVoiceSrcManual: 'Nội dung thủ công',      cfgVoiceSrcManualDesc: 'Nhập nội dung tùy chỉnh',
    cfgVoiceLang: 'NGÔN NGỮ', cfgVoiceGender: 'GIỌNG', cfgEngine: 'BỘ ĐỌC', cfgMixMode: 'TRỘN ÂM',
    cfgSaveFolder: 'THƯ MỤC LƯU', cfgRanking: 'SẮP XẾP', cfgAutoExport: 'Tự xuất 3 clip tốt nhất',
    cfgChangeSource: '← ĐỔI NGUỒN',
    cfgPartOrder: 'THỨ TỰ CLIP', cfgOrderViral: 'Viral trước', cfgOrderSeq: 'Tuần tự',
    cfgTranscript: 'XEM TRANSCRIPT', cfgTranscriptLoad: 'Tải preview…', cfgTranscriptEmpty: 'Không có transcript',
    btnBack: '← QUAY LẠI', btnStartRender: 'BẮT ĐẦU RENDER ▶',
    rndWaiting: 'Đang chờ job…', rndInProgress: 'Đang render…', rndComplete: '✓ Hoàn thành',
    rndFailed: '✗ Render thất bại', rndCancelled: '✗ Đã hủy',
    rndPartial: '⚠ Hoàn thành một phần', rndInterrupted: '✗ Bị gián đoạn',
    rndWsError: 'Mất kết nối — kiểm tra lịch sử job',
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
    resFailedParts: 'Clip thất bại', resNoReason: 'Không có chi tiết',
    btnRetry: 'THỬ LẠI', btnResume: 'TIẾP TỤC',
    qualityLoadFailed: 'Không tải được dữ liệu chất lượng',
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
  aiMarket:      string
  aiEnabled:          boolean
  multiVariant:       boolean
  ctaEnabled:         boolean
  ctaType:            'auto' | 'comment' | 'part_2' | 'follow'
  hookApplyEnabled:   boolean
  hookOverlayEnabled: boolean
  structureBias:      'hook' | 'balanced' | 'story' | null
  clipLock:           Array<{ start_sec: number; end_sec: number }>
  clipExclude:        Array<{ start_sec: number; end_sec: number }>
  motionCrop:         boolean
  subEnabled:       boolean
  subStyle:         string
  subHighlight:     boolean
  subFontSize:      number
  subTranslate:     boolean
  subTranslateLang: 'vi' | 'en' | 'ja'
  subEmphasis:      'subtle' | 'balanced' | 'aggressive' | null
  sourceQualityMode: 'standard_1080' | 'high_1440' | 'best_available'
  assetLogoPath:     string | null
  assetIntroPath:    string | null
  assetOutroPath:    string | null
  assetMusicProfile: 'clean' | 'energetic' | 'soft' | null
  whisperModel:      string
  partOrder:       'viral' | 'sequential'
  narrEnabled:   boolean
  voiceLang:     string
  voiceGender:   'female' | 'male'
  ttsEngine:     'edge' | 'xtts'
  voiceSource:   'subtitle' | 'translated_subtitle' | 'manual'
  voiceText:     string
  voiceMixMode:  'replace_original' | 'keep_original_low'
  outputDir:     string
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
  { id: 'social_bright',  ico: '💥', label: 'BRIGHT'  },
  { id: 'cinematic_soft', ico: '🎥', label: 'CINEMA'  },
  { id: 'high_contrast',  ico: '⬜', label: 'BOLD'    },
]

const SUB_STYLES = [
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

  const [prepareResult, setPrepareResult] = useState<PrepareSourceResponse | null>(null)
  const [isPreparing, setIsPreparing]     = useState(false)
  const [prepareError, setPrepareError]   = useState<string | null>(null)
  const prepareCancelledRef               = useRef(false)
  const prepareAbortRef                   = useRef<AbortController | null>(null)

  const [cfgTab, setCfgTab] = useState<CfgTab>('ai')
  const [cfg, setCfg] = useState<ConfigState>({
    preset: 'viral', ratio: 'r916', minSec: 15, maxSec: 60, clipCount: 5,
    style: 'slay_soft_01', platform: 'tiktok', aiMarket: 'us',
    aiEnabled: true, multiVariant: false, ctaEnabled: false, ctaType: 'auto',
    hookApplyEnabled: false, hookOverlayEnabled: false, structureBias: null,
    clipLock: [], clipExclude: [],
    motionCrop: true,
    subEnabled: true, subStyle: 'tiktok_bounce_v1',
    subHighlight: true, subFontSize: 28, subTranslate: false, subTranslateLang: 'en',
    subEmphasis: null, partOrder: 'viral',
    sourceQualityMode: 'standard_1080',
    assetLogoPath: null, assetIntroPath: null, assetOutroPath: null, assetMusicProfile: null,
    whisperModel: 'auto',
    narrEnabled: false, voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
    voiceSource: 'subtitle', voiceText: '', voiceMixMode: 'replace_original',
    outputDir: '',
    renderProfile: 'balanced',
  })

  const [jobId, setJobId]               = useState<string | null>(null)
  const [submitError, setSubmitError]   = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)

  const [parts, setParts]                   = useState<JobPart[]>([])
  const [partScores, setPartScores]         = useState<Record<number, number>>({})
  const [qualityReports, setQualityReports] = useState<Record<number, QualityReport | null>>({})
  const [qualityLoadFailed, setQualityLoadFailed] = useState(false)
  const [partsLoading, setPartsLoading]     = useState(false)
  const [isRetrying, setIsRetrying]         = useState(false)

  const { submitRender } = useRenderStore()
  const { stage, jobStatus, progress, jobMessage, isTerminal, liveParts, error: wsError } = useRenderSocket(jobId)
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

  // ── Source actions ──────────────────────────────────────────────────────────
  function addUrl() {
    const v = urlInput.trim()
    if (!v) return
    setSources((p) => [...p, { mode: 'youtube' as const, value: v }])
    setUrlInput('')
  }
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
        source_mode: src.mode,
        youtube_url: src.mode === 'youtube' ? src.value : undefined,
        source_video_path: src.mode === 'local' ? src.value : undefined,
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
      source_mode:          src.mode,
      source_quality_mode:  src.mode === 'youtube' ? cfg.sourceQualityMode : undefined,
      youtube_url:          src.mode === 'youtube' ? src.value : undefined,
      source_video_path:    src.mode === 'local'   ? src.value : undefined,
      output_dir:          cfg.outputDir || 'output',
      aspect_ratio:        RATIO_INFO[cfg.ratio].api,
      min_part_sec:        cfg.minSec,
      max_part_sec:        cfg.maxSec,
      max_export_parts:    cfg.clipCount,
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
      ai_director_enabled: cfg.aiEnabled,
      multi_variant:       cfg.multiVariant || undefined,
      cta_enabled:         cfg.ctaEnabled || undefined,
      cta_type:            cfg.ctaEnabled ? cfg.ctaType : undefined,
      hook_apply_enabled:  cfg.hookApplyEnabled || undefined,
      hook_overlay_enabled: cfg.hookOverlayEnabled || undefined,
      motion_aware_crop:   cfg.motionCrop,
      target_platform:     cfg.platform,
      effect_preset:       cfg.style,
      render_profile:      cfg.renderProfile,
      whisper_model:       cfg.whisperModel !== 'auto' ? cfg.whisperModel : undefined,
      ai_target_market:    cfg.aiMarket || undefined,
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
              {sources[0]?.mode === 'youtube'
                ? (lang === 'VI' ? 'Đang tải và xử lý video YouTube…' : 'Downloading and transcoding YouTube video…')
                : (lang === 'VI' ? 'Đang phân tích file video…' : 'Probing local video file…')}
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
                <div className={`src-card${srcMode === 'local' ? ' highlight' : ''}`} onClick={async () => {
                  setSrcMode('local')
                  const api = (window as any).electronAPI
                  if (api?.pickVideoFile) {
                    const picked = await api.pickVideoFile()
                    if (picked) setSources([{ mode: 'local', value: picked }])
                  } else {
                    fileInputRef.current?.click()
                  }
                }}>
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
              {srcMode === 'youtube' && (
                <div style={{ width: '100%', maxWidth: '760px', marginTop: '12px' }}>
                  <div className="cfg-sec-hd" style={{ marginBottom: '6px' }}>
                    <span>{t.cfgSrcQuality}</span>
                    <span className="cfg-sec-api">source_quality_mode</span>
                  </div>
                  <div className="seg">
                    {([
                      { v: 'standard_1080' as const, l: t.cfgSrcQualityStd },
                      { v: 'high_1440'     as const, l: t.cfgSrcQualityHigh },
                      { v: 'best_available' as const, l: t.cfgSrcQualityBest },
                    ]).map(({ v, l }) => (
                      <div key={v} className={`seg-b${cfg.sourceQualityMode === v ? ' on' : ''}`}
                        onClick={() => setCfg((prev) => ({ ...prev, sourceQualityMode: v }))}>{l}</div>
                    ))}
                  </div>
                </div>
              )}
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
              jobId={jobId} parts={parts} partScores={partScores}
              qualityReports={qualityReports} qualityLoadFailed={qualityLoadFailed}
              loading={partsLoading} t={t}
              aspectRatio={RATIO_INFO[cfg.ratio].api}
              jobStatus={jobStatus ?? ''}
              onRetry={handleRetryRender} isRetrying={isRetrying}
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

// ── TranscriptPreview — lazy-loaded in Step 2 configure left panel ────────────
function TranscriptPreview({ sessionId, t }: { sessionId: string; t: Strings }) {
  const [segs, setSegs] = useState<TranscriptSegment[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)

  async function load() {
    if (segs !== null || loading) return
    setLoading(true)
    try {
      const res = await getPreviewTranscript(sessionId)
      setSegs(res.segments ?? [])
    } catch {
      setSegs([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="cfg-section" style={{ marginTop: '4px' }}>
      <div className="cfg-sec-hd" style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => { setOpen((v) => !v); if (!open) load() }}>
        <span>{t.cfgTranscript}</span>
        <span style={{ fontSize: '10px', color: 'var(--text-3)' }}>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div style={{ maxHeight: '160px', overflowY: 'auto', marginTop: '6px' }}>
          {loading ? (
            <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>{t.cfgTranscriptLoad}</div>
          ) : !segs?.length ? (
            <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>{t.cfgTranscriptEmpty}</div>
          ) : (
            segs.slice(0, 20).map((s, i) => (
              <div key={i} style={{ display: 'flex', gap: '8px', padding: '3px 0', fontSize: '11px', borderTop: i > 0 ? '1px solid var(--border)' : 'none' }}>
                <span style={{ color: 'var(--text-3)', minWidth: '42px', fontFamily: 'var(--fb)' }}>{s.start.toFixed(1)}s</span>
                <span style={{ color: 'var(--text-1)', lineHeight: 1.4 }}>{s.text}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── RangeListEditor — add/remove time ranges for clip_lock / clip_exclude ────
function RangeListEditor({
  label, desc, apiKey, ranges, onChange, t,
}: {
  label: string; desc: string; apiKey: string
  ranges: Array<{ start_sec: number; end_sec: number }>
  onChange: (v: Array<{ start_sec: number; end_sec: number }>) => void
  t: Strings
}) {
  function add() {
    onChange([...ranges, { start_sec: 0, end_sec: 30 }])
  }
  function remove(i: number) {
    onChange(ranges.filter((_, idx) => idx !== i))
  }
  function update(i: number, key: 'start_sec' | 'end_sec', val: number) {
    const next = ranges.map((r, idx) => idx === i ? { ...r, [key]: val } : r)
    onChange(next)
  }

  return (
    <div className="cfg-section">
      <div className="cfg-sec-hd">
        <span>{label}</span>
        <span className="cfg-sec-api">{apiKey}</span>
      </div>
      {ranges.length === 0 && (
        <div className="tog-desc" style={{ marginBottom: '6px' }}>{desc}</div>
      )}
      {ranges.map((r, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flex: 1 }}>
            <input type="number" className="dir-in" min={0} step={0.5}
              style={{ width: '72px', textAlign: 'center', fontSize: '11px' }}
              value={r.start_sec}
              onChange={(e) => update(i, 'start_sec', Math.max(0, +e.target.value))} />
            <span style={{ color: 'var(--text-3)', fontSize: '10px' }}>→</span>
            <input type="number" className="dir-in" min={0} step={0.5}
              style={{ width: '72px', textAlign: 'center', fontSize: '11px' }}
              value={r.end_sec}
              onChange={(e) => update(i, 'end_sec', Math.max(r.start_sec + 0.5, +e.target.value))} />
            <span style={{ color: 'var(--text-3)', fontSize: '10px' }}>s</span>
          </div>
          <button className="btn-xs" onClick={() => remove(i)} style={{ opacity: 0.6 }}>×</button>
        </div>
      ))}
      <button className="btn-xs" onClick={add} style={{ marginTop: '2px' }}>{t.cfgAddRange}</button>
    </div>
  )
}

// ── AssetPicker — file upload row for creator asset paths ────────────────────
function AssetPicker({
  label, desc, accept, value, onChange,
}: {
  label: string; desc: string; accept: string
  value: string | null; onChange: (path: string | null) => void
}) {
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadFile(file)
      onChange(res.path)
    } catch {
      onChange(null)
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0' }}>
      <div style={{ flex: 1, minWidth: 0, marginRight: '8px' }}>
        <div className="tog-lbl">{label}</div>
        {value ? (
          <div style={{ fontSize: '10px', color: 'var(--ok)', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            ✓ {value.split(/[\\/]/).pop()}
          </div>
        ) : (
          <div className="tog-desc">{desc}</div>
        )}
      </div>
      <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
        <input ref={inputRef} type="file" accept={accept} style={{ display: 'none' }} onChange={handleFile} />
        <button className="btn-xs" onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? '…' : value ? '↺' : '↑'}
        </button>
        {value && (
          <button className="btn-xs" onClick={() => onChange(null)} style={{ opacity: 0.6 }}>×</button>
        )}
      </div>
    </div>
  )
}

// ── Step 2 — Configure ────────────────────────────────────────────────────────
function StepConfigure({
  cfg, cfgTab, setCfgTab, setCfgKey, applyPreset,
  sources, prepareResult, pickOutputDir, onChangeSource, t,
}: {
  cfg: ConfigState; cfgTab: CfgTab; setCfgTab: (tab: CfgTab) => void
  setCfgKey: <K extends keyof ConfigState>(k: K, v: ConfigState[K]) => void
  applyPreset: (id: string) => void
  sources: Source[]
  prepareResult: PrepareSourceResponse | null
  pickOutputDir: () => void
  onChangeSource: () => void
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
            <button className="cfg-src-change" onClick={onChangeSource}>{t.cfgChangeSource}</button>
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

        {/* Transcript preview */}
        {prepareResult && <TranscriptPreview sessionId={prepareResult.session_id} t={t} />}

      </div>{/* /cfg-left */}

      {/* ── CENTER ── */}
      <div className="cfg-center">
        <div className="cfg-center-top">
          <span className="pv-chip ac">{ratioInfo.label} · {ratioInfo.sub}</span>
          <span className="pv-chip cy">{styleLabel}</span>
          <span className="pv-chip">{cfg.platform.replace(/_/g, ' ')}</span>
          <div style={{ flex: 1 }} />
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
              <div className="cfg-sec-hd">
                <span>TARGET MARKET</span>
                <span className="cfg-sec-api">ai_target_market</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '6px' }}>
                {([
                  { v: 'us',    l: '🇺🇸 US'     },
                  { v: 'eu',    l: '🇪🇺 EU'     },
                  { v: 'jp',    l: '🇯🇵 JP'     },
                  { v: 'sea',   l: '🌏 SEA'     },
                  { v: 'kr',    l: '🇰🇷 KR'     },
                  { v: 'latam', l: '🌎 LATAM'   },
                  { v: 'in',    l: '🇮🇳 India'  },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.aiMarket === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('aiMarket', v)}>{l}</div>
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
              <div className="tog-row">
                <div>
                  <div className="tog-lbl">{t.cfgCTAEnable}</div>
                  <div className="tog-desc">{t.cfgCTAEnableDesc}</div>
                </div>
                <Tog checked={cfg.ctaEnabled} onChange={(v) => setCfgKey('ctaEnabled', v)} />
              </div>
              {cfg.ctaEnabled && (
                <div style={{ marginTop: '10px' }}>
                  <div className="cfg-sec-hd" style={{ marginBottom: '6px' }}>
                    <span>{t.cfgCTAType}</span>
                    <span className="cfg-sec-api">cta_type</span>
                  </div>
                  <div className="seg">
                    {([
                      { v: 'auto'    as const, l: t.cfgCTAAuto    },
                      { v: 'comment' as const, l: t.cfgCTAComment  },
                      { v: 'part_2'  as const, l: t.cfgCTAPart2   },
                      { v: 'follow'  as const, l: t.cfgCTAFollow   },
                    ]).map(({ v, l }) => (
                      <div key={v} className={`seg-b${cfg.ctaType === v ? ' on' : ''}`}
                        onClick={() => setCfgKey('ctaType', v)}>{l}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <RangeListEditor
              label={t.cfgClipLock} desc={t.cfgClipLockDesc} apiKey="clip_lock"
              ranges={cfg.clipLock}
              onChange={(v) => setCfgKey('clipLock', v)}
              t={t}
            />
            <RangeListEditor
              label={t.cfgClipExclude} desc={t.cfgClipExcludeDesc} apiKey="clip_exclude"
              ranges={cfg.clipExclude}
              onChange={(v) => setCfgKey('clipExclude', v)}
              t={t}
            />
            <div className="cfg-section">
              <div className="tog-row">
                <div>
                  <div className="tog-lbl">{t.cfgHookApply}</div>
                  <div className="tog-desc">{t.cfgHookApplyDesc}</div>
                </div>
                <Tog checked={cfg.hookApplyEnabled} onChange={(v) => setCfgKey('hookApplyEnabled', v)} />
              </div>
              {cfg.hookApplyEnabled && (
                <div className="tog-row" style={{ marginTop: '10px' }}>
                  <div>
                    <div className="tog-lbl">{t.cfgHookOverlay}</div>
                    <div className="tog-desc">{t.cfgHookOverlayDesc}</div>
                  </div>
                  <Tog checked={cfg.hookOverlayEnabled} onChange={(v) => setCfgKey('hookOverlayEnabled', v)} />
                </div>
              )}
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgStructureBias}</span>
                <span className="cfg-sec-api">structure_bias</span>
              </div>
              <div className="seg">
                {([
                  { v: null          , l: t.cfgBiasOff      },
                  { v: 'hook'        , l: t.cfgBiasHook      },
                  { v: 'balanced'    , l: t.cfgBiasBalanced  },
                  { v: 'story'       , l: t.cfgBiasStory     },
                ] as { v: ConfigState['structureBias']; l: string }[]).map(({ v, l }) => (
                  <div key={String(v)} className={`seg-b${cfg.structureBias === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('structureBias', v)}>{l}</div>
                ))}
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgPartOrder}</span>
                <span className="cfg-sec-api">part_order</span>
              </div>
              <div className="seg">
                <div className={`seg-b${cfg.partOrder === 'viral' ? ' on' : ''}`}
                  onClick={() => setCfgKey('partOrder', 'viral')}>⚡ {t.cfgOrderViral}</div>
                <div className={`seg-b${cfg.partOrder === 'sequential' ? ' on' : ''}`}
                  onClick={() => setCfgKey('partOrder', 'sequential')}>123 {t.cfgOrderSeq}</div>
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
                <div>
                  <span className="tog-lbl">{t.cfgHighlightWord}</span>
                  <span className="cfg-sec-api" style={{ marginLeft: 6 }}>highlight_per_word</span>
                </div>
                <Tog checked={cfg.subHighlight} onChange={(v) => setCfgKey('subHighlight', v)} />
              </div>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgFontSize}: {cfg.subFontSize}px</span>
                <span className="cfg-sec-api">sub_font_size</span>
              </div>
              <input type="range" className="range-in" min={14} max={52} step={2} value={cfg.subFontSize}
                onChange={(e) => setCfgKey('subFontSize', +e.target.value)} />
              <div className="range-vals">
                <span className="range-v">14px</span>
                <span className="range-v">{cfg.subFontSize}px</span>
                <span className="range-v">52px</span>
              </div>
            </div>
            <div className="cfg-section">
              <div className="tog-row">
                <div>
                  <span className="tog-lbl">{t.cfgAutoTranslate}</span>
                  <span className="cfg-sec-api" style={{ marginLeft: 6 }}>subtitle_translate_enabled</span>
                </div>
                <Tog checked={cfg.subTranslate} onChange={(v) => setCfgKey('subTranslate', v)} />
              </div>
              {cfg.subTranslate && (
                <div style={{ marginTop: '8px' }}>
                  <div className="cfg-sec-hd" style={{ marginBottom: '6px' }}>
                    <span>{t.cfgTargetLang}</span>
                    <span className="cfg-sec-api">subtitle_target_language</span>
                  </div>
                  <div className="seg">
                    {([
                      { v: 'vi' as const, l: '🇻🇳 Việt' },
                      { v: 'en' as const, l: '🇺🇸 English' },
                      { v: 'ja' as const, l: '🇯🇵 日本語' },
                    ]).map(({ v, l }) => (
                      <div key={v} className={`seg-b${cfg.subTranslateLang === v ? ' on' : ''}`}
                        onClick={() => setCfgKey('subTranslateLang', v)}>{l}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgSubEmphasis}</span>
                <span className="cfg-sec-api">subtitle_emphasis</span>
              </div>
              <div className="seg">
                {([
                  { v: null          , l: t.cfgEmphasisOff        },
                  { v: 'subtle'      , l: t.cfgEmphasisSubtle      },
                  { v: 'balanced'    , l: t.cfgEmphasisBalanced    },
                  { v: 'aggressive'  , l: t.cfgEmphasisAggressive  },
                ] as { v: ConfigState['subEmphasis']; l: string }[]).map(({ v, l }) => (
                  <div key={String(v)} className={`seg-b${cfg.subEmphasis === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('subEmphasis', v)}>{l}</div>
                ))}
              </div>
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
                <option value="vi-VN">🇻🇳 Tiếng Việt</option>
                <option value="en-US">🇺🇸 English (US)</option>
                <option value="en-GB">🇬🇧 English (UK)</option>
                <option value="ja-JP">🇯🇵 日本語</option>
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
              <select className="sel" value={cfg.voiceMixMode} onChange={(e) => setCfgKey('voiceMixMode', e.target.value as 'replace_original' | 'keep_original_low')}>
                <option value="replace_original">Replace original audio</option>
                <option value="keep_original_low">Keep original (low)</option>
              </select>
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgWhisperModel}</span>
                <span className="cfg-sec-api">whisper_model</span>
              </div>
              <div className="seg">
                {([
                  { v: 'auto',   l: t.cfgWhisperAuto   },
                  { v: 'tiny',   l: t.cfgWhisperTiny    },
                  { v: 'base',   l: t.cfgWhisperBase    },
                  { v: 'small',  l: t.cfgWhisperSmall   },
                  { v: 'medium', l: t.cfgWhisperMedium  },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.whisperModel === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('whisperModel', v)}>{l}</div>
                ))}
              </div>
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
              <div className="cfg-sec-hd">{t.cfgAssets}</div>
              <AssetPicker
                label={t.cfgAssetLogo} desc={t.cfgAssetLogoDesc}
                accept="image/png,image/jpeg"
                value={cfg.assetLogoPath}
                onChange={(v) => setCfgKey('assetLogoPath', v)}
              />
              <AssetPicker
                label={t.cfgAssetIntro} desc={t.cfgAssetIntroDesc}
                accept="video/mp4,video/quicktime,video/webm"
                value={cfg.assetIntroPath}
                onChange={(v) => setCfgKey('assetIntroPath', v)}
              />
              <AssetPicker
                label={t.cfgAssetOutro} desc={t.cfgAssetOutroDesc}
                accept="video/mp4,video/quicktime,video/webm"
                value={cfg.assetOutroPath}
                onChange={(v) => setCfgKey('assetOutroPath', v)}
              />
            </div>
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgAssetMusicProfile}</span>
                <span className="cfg-sec-api">asset_music_profile</span>
              </div>
              <div className="seg">
                {([
                  { v: null         , l: t.cfgAssetMusicOff       },
                  { v: 'clean'      , l: t.cfgAssetMusicClean      },
                  { v: 'energetic'  , l: t.cfgAssetMusicEnergetic  },
                  { v: 'soft'       , l: t.cfgAssetMusicSoft       },
                ] as { v: ConfigState['assetMusicProfile']; l: string }[]).map(({ v, l }) => (
                  <div key={String(v)} className={`seg-b${cfg.assetMusicProfile === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('assetMusicProfile', v)}>{l}</div>
                ))}
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
  jobId, stage, jobStatus, progress, jobMessage, isTerminal, liveParts, wsError, t,
}: {
  jobId: string | null; stage: string; jobStatus: string
  progress: WsProgressSummary | null; jobMessage: string
  isTerminal: boolean; liveParts: JobPart[]
  wsError: string | null; t: Strings
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

      {/* WS error banner */}
      {wsError && !isTerminal && (
        <div style={{ margin: '8px 16px', padding: '8px 12px', background: 'rgba(234,179,8,.1)', border: '1px solid rgba(234,179,8,.3)', borderRadius: '4px', fontSize: '11px', color: 'var(--warn)' }}>
          ⚠ {t.rndWsError}
        </div>
      )}

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
  jobId, parts, partScores, qualityReports, qualityLoadFailed,
  loading, t, aspectRatio, jobStatus, onRetry, isRetrying,
}: {
  jobId: string | null
  parts: JobPart[]
  partScores: Record<number, number>
  qualityReports: Record<number, QualityReport | null>
  qualityLoadFailed: boolean
  loading: boolean
  t: Strings
  aspectRatio: string
  jobStatus: string
  onRetry: () => void
  isRetrying: boolean
}) {
  const [selectedPart, setSelectedPart] = useState<JobPart | null>(null)
  const [sortMode, setSortMode] = useState<'viral' | 'duration'>('viral')
  const doneParts  = parts.filter((p) => p.status === 'done')
  const failedParts = parts.filter((p) => p.status === 'failed')
  const sortedDone = [...doneParts].sort((a, b) =>
    sortMode === 'duration'
      ? (b.duration ?? 0) - (a.duration ?? 0)
      : (partScores[b.part_no] ?? 0) - (partScores[a.part_no] ?? 0)
  )

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
        {jobStatus === 'completed_with_errors' && failedParts.length > 0 && (
          <div style={{ margin: '0 0 8px', padding: '8px 12px', background: 'rgba(234,179,8,.1)', border: '1px solid rgba(234,179,8,.3)', borderRadius: '4px', fontSize: '11px', color: 'var(--warn)' }}>
            ⚠ {failedParts.length} clip{failedParts.length !== 1 ? 's' : ''} failed — {doneParts.length} clip{doneParts.length !== 1 ? 's' : ''} rendered successfully
          </div>
        )}
        <div className="res-toolbar">
          <div className="res-count">
            {t.resClipsRendered(doneParts.length)}
            {failedParts.length > 0 && (
              <span style={{ color: 'var(--fail)', marginLeft: 8, fontSize: 11 }}>· {failedParts.length} failed</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <div className="res-sort">
              <button className={`sort-btn${sortMode === 'viral' ? ' on' : ''}`} onClick={() => setSortMode('viral')}>{t.resSortViral}</button>
              <button className={`sort-btn${sortMode === 'duration' ? ' on' : ''}`} onClick={() => setSortMode('duration')}>{t.resSortDuration}</button>
            </div>
            {failedParts.length > 0 && (
              <button className="btn-xs" style={{ color: 'var(--fail)', borderColor: 'rgba(232,64,122,.4)' }}
                onClick={onRetry} disabled={isRetrying}>
                {isRetrying ? '…' : t.btnRetry}
              </button>
            )}
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
        {/* Failed clips detail */}
        {failedParts.length > 0 && (
          <div style={{ marginTop: '12px', padding: '10px 12px', background: 'rgba(232,64,122,.07)', border: '1px solid rgba(232,64,122,.2)', borderRadius: '6px' }}>
            <div style={{ fontSize: '10px', fontFamily: 'var(--fh)', letterSpacing: '1px', color: 'var(--fail)', marginBottom: '8px' }}>
              {t.resFailedParts} ({failedParts.length})
            </div>
            {failedParts.map((p) => (
              <div key={p.part_no} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '4px 0', borderTop: '1px solid rgba(232,64,122,.1)', fontSize: '11px' }}>
                <span style={{ color: 'var(--fail)', fontFamily: 'var(--fh)', minWidth: 28 }}>#{String(p.part_no).padStart(2, '0')}</span>
                <span style={{ color: 'var(--text-3)', lineHeight: 1.4 }}>{p.message || t.resNoReason}</span>
              </div>
            ))}
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
                ) : qualityLoadFailed ? (
                  <div className="player-no-data" style={{ color: 'var(--warn)' }}>⚠ {t.qualityLoadFailed}</div>
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
