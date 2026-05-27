import React, { useState, useRef, useEffect } from 'react'
import './RenderWorkflow.css'
import type { Lang } from '../ClipStudio'
import { useRenderStore } from '../../../stores/renderStore'
import { useRenderSocket } from '../../../hooks/useRenderSocket'
import { prepareSource, getPreviewVideoUrl, cancelRender, cancelPrepareSource, retryRender, resumeRender, getPreviewTranscript } from '../../../api/render'
import type { TranscriptSegment } from '../../../api/render'
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
    srcDesc: 'Select a local video file to get started. Use the Download tab for YouTube / TikTok.',
    srcLocalTitle: 'Local File',
    srcLocalDesc: 'Import MP4, MOV, MKV or WEBM from your computer. No internet required.',
    srcAdded: 'SOURCE ADDED',
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
    srcDesc: 'Chọn file video trên máy. Dùng tab Download để tải YouTube / TikTok.',
    srcLocalTitle: 'File trên máy',
    srcLocalDesc: 'Import MP4, MOV, MKV hoặc WEBM từ máy tính. Không cần internet.',
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
type Ratio = 'r916' | 'r34' | 'r45' | 'r11' | 'r169'
type CfgTab = 'ai' | 'sub' | 'narr' | 'output'

interface Source { value: string }

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
  renderProfile: 'fast' | 'balanced' | 'quality' | 'best'
  // v2 goal fields
  targetDuration:  number
  outputCount:     number
  videoType:       'auto' | 'viral' | 'storytelling' | 'educational' | 'emotional' | 'high_retention'
  energyStyle:     'auto' | 'fast' | 'balanced' | 'slow'
  hookStrength:    'aggressive' | 'balanced' | 'soft'
  focusMode:       'auto' | 'face' | 'object' | 'center'
  outputLanguage:  string
  narrationStyle:  'auto' | 'energetic' | 'calm' | 'emotional'
  subDensity:      'auto' | 'low' | 'medium' | 'high'
  subLanguage:     string
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


const RATIO_INFO: Record<Ratio, { label: string; sub: string; api: string }> = {
  r916: { label: '9:16', sub: '1080×1920', api: '9:16' },
  r34:  { label: '3:4',  sub: '1080×1440', api: '3:4'  },
  r45:  { label: '4:5',  sub: '1080×1350', api: '4:5'  },
  r11:  { label: '1:1',  sub: '1080×1080', api: '1:1'  },
  r169: { label: '16:9', sub: '1920×1080', api: '16:9' },
}

const SUB_STYLE_GROUPS = [
  { label: 'Minimal', set: 'clean_pro',        ids: ['clean_pro', 'story_clean_01'] },
  { label: 'Karaoke', set: 'tiktok_bounce_v1', ids: ['tiktok_bounce_v1', 'viral_bold'] },
  { label: 'Emphasis', set: 'bold_cap',         ids: ['bold_cap', 'boxed_caption', 'gaming'] },
]

const QUALITY_MAP = [
  { v: 'fast'    as const, l: '720p'  },
  { v: 'quality' as const, l: '1080p' },
  { v: 'best'    as const, l: '2K'    },
]

// ── Helpers ───────────────────────────────────────────────────────────────────
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

  const [prepareResult, setPrepareResult] = useState<PrepareSourceResponse | null>(null)
  const [isPreparing, setIsPreparing]     = useState(false)
  const [prepareError, setPrepareError]   = useState<string | null>(null)
  const prepareCancelledRef               = useRef(false)
  const prepareAbortRef                   = useRef<AbortController | null>(null)

  const [cfgTab, setCfgTab] = useState<CfgTab>('ai')
  const [cfg, setCfg] = useState<ConfigState>({
    preset: 'viral', ratio: 'r916', minSec: 30, maxSec: 60, clipCount: 5,
    style: 'slay_soft_01', platform: 'tiktok', aiMarket: 'us',
    aiEnabled: true, multiVariant: false, ctaEnabled: false, ctaType: 'auto',
    hookApplyEnabled: false, hookOverlayEnabled: false, structureBias: null,
    clipLock: [], clipExclude: [],
    motionCrop: false,
    subEnabled: true, subStyle: 'tiktok_bounce_v1',
    subHighlight: true, subFontSize: 28, subTranslate: false, subTranslateLang: 'en',
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
          if (f) setSources([{ value: (f as File & { path?: string }).path || f.name }])
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

// ── TranscriptOverlay — subtitle preview overlaid on video, cycles through segs ──
function TranscriptOverlay({ sessionId, subStyle, subEnabled }: { sessionId: string; subStyle: string; subEnabled: boolean }) {
  const [segs, setSegs] = useState<TranscriptSegment[] | null>(null)
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    let cancelled = false
    getPreviewTranscript(sessionId).then(res => {
      if (!cancelled) setSegs(res.segments?.slice(0, 30) ?? [])
    }).catch(() => {
      if (!cancelled) setSegs([])
    })
    return () => { cancelled = true }
  }, [sessionId])

  useEffect(() => {
    if (!segs?.length) return
    const id = setInterval(() => setIdx(i => (i + 1) % segs.length), 2500)
    return () => clearInterval(id)
  }, [segs])

  if (!segs?.length) return null

  const text = segs[idx]?.text ?? ''
  const words = text.trim().split(/\s+/)
  const hlIdx = Math.floor(words.length / 2)

  // Style variants matching SubtitleDemo
  const variants: Record<string, React.CSSProperties> = {
    pro_karaoke:      { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 800, color: '#fff', textShadow: '-1px -1px 0 #000, 1px 1px 0 #000' },
    tiktok_bounce_v1: { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '0 2px 8px rgba(0,0,0,.9)' },
    viral_bold:       { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', letterSpacing: '1px', textShadow: '0 2px 10px rgba(0,0,0,.9)' },
    bold_cap:         { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 900, color: '#fff', textTransform: 'uppercase' as const, textShadow: '0 2px 8px rgba(0,0,0,.9)' },
    boxed_caption:    { fontFamily: 'var(--fb)', fontSize: '12px', fontWeight: 700, color: '#fff', background: 'rgba(0,0,0,.75)', padding: '3px 8px', borderRadius: '4px' },
    story_clean_01:   { fontFamily: 'var(--fb)', fontSize: '12px', fontWeight: 400, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
    clean_pro:        { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 400, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
    gaming:           { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 700, color: '#00E5C8', letterSpacing: '1px', textShadow: '0 0 12px rgba(0,229,200,.8)' },
  }
  const hlColor: Record<string, string> = {
    pro_karaoke: '#FFD700', tiktok_bounce_v1: '#00E5C8', viral_bold: '#fff',
    bold_cap: '#00E5C8', gaming: '#fff',
  }
  const style = variants[subStyle] ?? variants['clean_pro']
  const hlC = hlColor[subStyle] ?? 'var(--cyan)'

  // Position badge bottom-center inside the frame
  const showSub = subEnabled

  return (
    <div style={{
      position: 'absolute', bottom: '18%', left: 0, right: 0,
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      gap: '2px', padding: '0 8px', pointerEvents: 'none',
    }}>
      {/* transcript ticker — always visible */}
      <div style={{
        background: 'rgba(0,0,0,.55)', borderRadius: '4px', padding: '3px 8px',
        fontSize: '9px', color: 'rgba(255,255,255,.7)', fontFamily: 'var(--fb)',
        maxWidth: '90%', textAlign: 'center', lineHeight: 1.4,
        display: showSub ? 'none' : 'block',
      }}>
        {text}
      </div>

      {/* subtitle style preview */}
      {showSub && (
        <div style={{ ...style, maxWidth: '90%', textAlign: 'center', lineHeight: 1.5 }}>
          {words.map((w, i) => (
            <span key={i}>
              {i === hlIdx
                ? <span style={{ color: hlC, WebkitTextFillColor: hlC }}>{w}</span>
                : w}
              {i < words.length - 1 ? ' ' : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}


// ── Step 2 — Configure ────────────────────────────────────────────────────────
function StepConfigure({
  cfg, cfgTab, setCfgTab, setCfgKey, applyPreset,
  sources, prepareResult, pickOutputDir, onChangeSource, t,
}: {
  cfg: ConfigState
  cfgTab: CfgTab
  setCfgTab: (tab: CfgTab) => void
  setCfgKey: <K extends keyof ConfigState>(k: K, v: ConfigState[K]) => void
  applyPreset: (id: string) => void
  sources: Source[]
  prepareResult: PrepareSourceResponse | null
  pickOutputDir: () => void
  onChangeSource: () => void
  t: Strings
}) {
  void applyPreset
  const src          = sources[0]
  const ratioInfo    = RATIO_INFO[cfg.ratio]
  const previewVideoUrl = prepareResult ? getPreviewVideoUrl(prepareResult.session_id) : null
  const styleLabel   = STYLES.find(s => s.id === cfg.style)?.label ?? cfg.style
  const activeSubGroup = SUB_STYLE_GROUPS.find(g => g.ids.includes(cfg.subStyle))?.set ?? 'clean_pro'
  const qualityLabel   = QUALITY_MAP.find(q => q.v === cfg.renderProfile)?.l ?? '1080p'

  return (
    <div className="cfg-screen">

      {/* ── LEFT ──────────────────────────────────────────────────────────── */}
      <div className="cfg-left">

        {/* Source card */}
        <div className="cfg-src-card">
          <div className="cfg-src-thumb">📁</div>
          <div className="cfg-src-info">
            <div className="cfg-src-name">
              {prepareResult?.title || (src?.value ? src.value.slice(0, 28) + '…' : 'No source')}
            </div>
            <div className="cfg-src-meta">
              {prepareResult ? fmtDuration(prepareResult.duration) : 'Local File'}
            </div>
            <button className="cfg-src-change" onClick={onChangeSource}>{t.cfgChangeSource}</button>
          </div>
        </div>

        {/* C. Duration — min / max clip length */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>CLIP DURATION</span>
            <span className="cfg-sec-api">min_part_sec · max_part_sec</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
            {[
              { min: 30,  max: 60  },
              { min: 45,  max: 90  },
              { min: 60,  max: 120 },
              { min: 90,  max: 180 },
            ].map(({ min, max }) => (
              <div key={`${min}-${max}`}
                className={`seg-b${cfg.minSec === min && cfg.maxSec === max ? ' on' : ''}`}
                onClick={() => { setCfgKey('minSec', min); setCfgKey('maxSec', max) }}>
                {min}–{max}s
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-3)', width: '28px' }}>MIN</span>
            <input
              type="number" min={15} max={300} value={cfg.minSec}
              onChange={e => { const v = parseInt(e.target.value, 10); if (!isNaN(v)) setCfgKey('minSec', Math.max(15, Math.min(300, v))) }}
              style={{ width: '56px', padding: '3px 5px', borderRadius: '5px', fontSize: '11px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-1)', textAlign: 'right', outline: 'none' }}
            />
            <span style={{ fontSize: '10px', color: 'var(--text-3)' }}>s</span>
            <span style={{ fontSize: '10px', color: 'var(--text-3)', width: '28px', marginLeft: '6px' }}>MAX</span>
            <input
              type="number" min={15} max={600} value={cfg.maxSec}
              onChange={e => { const v = parseInt(e.target.value, 10); if (!isNaN(v)) setCfgKey('maxSec', Math.max(15, Math.min(600, v))) }}
              style={{ width: '56px', padding: '3px 5px', borderRadius: '5px', fontSize: '11px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-1)', textAlign: 'right', outline: 'none' }}
            />
            <span style={{ fontSize: '10px', color: 'var(--text-3)' }}>s</span>
          </div>
        </div>

        {/* D. Output count */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>OUTPUT VIDEOS</span>
            <span className="cfg-sec-api">output_count</span>
          </div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
            {[1, 3, 5, 10].map(v => (
              <div key={v} className={`seg-b${cfg.outputCount === v ? ' on' : ''}`}
                onClick={() => setCfgKey('outputCount', v)}>{v}</div>
            ))}
            <div className="clip-count-row">
              <button className="cnt-btn" onClick={() => setCfgKey('outputCount', Math.max(1, cfg.outputCount - 1))}>−</button>
              <span className="cnt-val">{cfg.outputCount}</span>
              <button className="cnt-btn" onClick={() => setCfgKey('outputCount', Math.min(20, cfg.outputCount + 1))}>+</button>
            </div>
          </div>
        </div>

        {/* A. Platform */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>{t.cfgPlatform}</span>
            <span className="cfg-sec-api">target_platform</span>
          </div>
          <div className="seg">
            {([
              { v: 'tiktok'          as const, l: 'TikTok'   },
              { v: 'youtube_shorts'  as const, l: 'YT Short' },
              { v: 'instagram_reels' as const, l: 'Reels'    },
            ]).map(({ v, l }) => (
              <div key={v} className={`seg-b${cfg.platform === v ? ' on' : ''}`}
                onClick={() => setCfgKey('platform', v)}>{l}</div>
            ))}
          </div>
        </div>

        {/* A. Frame */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>FRAME</span>
            <span className="cfg-sec-api">aspect_ratio</span>
          </div>
          <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
            {(['r916', 'r34', 'r45', 'r11', 'r169'] as Ratio[]).map(r => (
              <div key={r} className={`seg-b${cfg.ratio === r ? ' on' : ''}`}
                onClick={() => setCfgKey('ratio', r)}>{RATIO_INFO[r].label}</div>
            ))}
          </div>
        </div>

        {/* A. Quality */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>QUALITY</span>
            <span className="cfg-sec-api">render_profile</span>
          </div>
          <div className="seg">
            {QUALITY_MAP.map(({ v, l }) => (
              <div key={v} className={`seg-b${cfg.renderProfile === v ? ' on' : ''}`}
                onClick={() => setCfgKey('renderProfile', v)}>{l}</div>
            ))}
          </div>
        </div>

        {/* M. Output folder */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>{t.cfgSaveFolder}</span>
            <span className="cfg-sec-api">output_dir</span>
          </div>
          <div className="dir-row">
            <input className="dir-in" type="text" placeholder="D:\Videos\Output" value={cfg.outputDir}
              onChange={(e) => setCfgKey('outputDir', e.target.value)} />
            <button className="btn-xs" onClick={pickOutputDir}>Browse</button>
          </div>
          {prepareResult?.export_dir && (
            <div style={{ fontSize: '10px', color: 'var(--text-3)', marginTop: '6px', wordBreak: 'break-all', lineHeight: 1.5 }}>
              Default: {prepareResult.export_dir}
            </div>
          )}
        </div>

      </div>{/* /cfg-left */}

      {/* ── CENTER ────────────────────────────────────────────────────────── */}
      <div className="cfg-center">
        <div className="cfg-center-top">
          <span className="pv-chip ac">{ratioInfo.label} · {ratioInfo.sub}</span>
          <span className="pv-chip cy">{styleLabel}</span>
          <span className="pv-chip">{cfg.platform.replace(/_/g, ' ')}</span>
          <div style={{ flex: 1 }} />
          <span className="pv-chip">{cfg.targetDuration}s</span>
          <span className="pv-chip">×{cfg.outputCount}</span>
          <span className="pv-chip">{qualityLabel}</span>
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
            ) : (
              <div className="pv-placeholder">
                <span className="pv-play">▶</span>
                <span className="pv-hint">Preview updates as you configure</span>
              </div>
            )}
            {cfg.subEnabled && <SubtitleDemo style={cfg.subStyle} />}
            {prepareResult && (
              <TranscriptOverlay sessionId={prepareResult.session_id} subStyle={cfg.subStyle} subEnabled={cfg.subEnabled} />
            )}
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

      {/* ── RIGHT ─────────────────────────────────────────────────────────── */}
      <div className="cfg-right">
        <div className="cfg-tabs">
          {([
            { id: 'ai'     as CfgTab, label: t.cfgTabAI     },
            { id: 'sub'    as CfgTab, label: t.cfgTabSub    },
            { id: 'narr'   as CfgTab, label: t.cfgTabNarr   },
          ]).map((tab) => (
            <button key={tab.id} className={`cfg-tab${cfgTab === tab.id ? ' on' : ''}`} onClick={() => setCfgTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="cfg-tab-body">

          {/* ── AI tab ── */}
          <div className={`cfg-tab-pane${cfgTab === 'ai' ? ' active' : ''}`}>

            {/* E. Video type */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>VIDEO TYPE</span>
                <span className="cfg-sec-api">video_type</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'auto'          as ConfigState['videoType'], l: 'Auto'      },
                  { v: 'viral'         as ConfigState['videoType'], l: 'Viral'     },
                  { v: 'storytelling'  as ConfigState['videoType'], l: 'Story'     },
                  { v: 'educational'   as ConfigState['videoType'], l: 'Edu'       },
                  { v: 'emotional'     as ConfigState['videoType'], l: 'Emotional' },
                  { v: 'high_retention'as ConfigState['videoType'], l: 'Retention' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.videoType === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('videoType', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* I. Market */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>MARKET</span>
                <span className="cfg-sec-api">ai_target_market</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'us',  l: '🇺🇸 US'  },
                  { v: 'vn',  l: '🇻🇳 VN'  },
                  { v: 'jp',  l: '🇯🇵 JP'  },
                  { v: 'kr',  l: '🇰🇷 KR'  },
                  { v: 'eu',  l: '🇪🇺 EU'  },
                  { v: 'sea', l: '🌏 SEA' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.aiMarket === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('aiMarket', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* K. Energy */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>ENERGY</span>
                <span className="cfg-sec-api">energy_style</span>
              </div>
              <div className="seg">
                {([
                  { v: 'auto'     as ConfigState['energyStyle'], l: 'Auto'     },
                  { v: 'fast'     as ConfigState['energyStyle'], l: 'Fast'     },
                  { v: 'balanced' as ConfigState['energyStyle'], l: 'Balanced' },
                  { v: 'slow'     as ConfigState['energyStyle'], l: 'Slow'     },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.energyStyle === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('energyStyle', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* L. Hook strength */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>HOOK</span>
                <span className="cfg-sec-api">hook_strength</span>
              </div>
              <div className="seg">
                {([
                  { v: 'aggressive' as ConfigState['hookStrength'], l: 'Aggressive' },
                  { v: 'balanced'   as ConfigState['hookStrength'], l: 'Balanced'   },
                  { v: 'soft'       as ConfigState['hookStrength'], l: 'Soft'       },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.hookStrength === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('hookStrength', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* J. Focus mode */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>FOCUS</span>
                <span className="cfg-sec-api">reframe_mode</span>
              </div>
              <div className="seg">
                {([
                  { v: 'auto'   as ConfigState['focusMode'], l: 'Auto'   },
                  { v: 'face'   as ConfigState['focusMode'], l: 'Face'   },
                  { v: 'object' as ConfigState['focusMode'], l: 'Object' },
                  { v: 'center' as ConfigState['focusMode'], l: 'Center' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.focusMode === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('focusMode', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* H. Output language */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>OUTPUT LANGUAGE</span>
                <span className="cfg-sec-api">output_language</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'auto', l: 'Keep original' },
                  { v: 'vi',   l: '🇻🇳 VI'        },
                  { v: 'en',   l: '🇺🇸 EN'        },
                  { v: 'ja',   l: '🇯🇵 JA'        },
                  { v: 'ko',   l: '🇰🇷 KO'        },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.outputLanguage === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('outputLanguage', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* AI Director */}
            <div className="cfg-section">
              <div className="tog-row">
                <div>
                  <div className="tog-lbl">{t.cfgAIDirector}</div>
                  <div className="tog-desc">{t.cfgAIDirectorDesc}</div>
                </div>
                <Tog checked={cfg.aiEnabled} onChange={(v) => setCfgKey('aiEnabled', v)} />
              </div>
            </div>

          </div>

          {/* ── SUB tab ── */}
          <div className={`cfg-tab-pane${cfgTab === 'sub' ? ' active' : ''}`}>

            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgEnableSub}</span>
                <Tog checked={cfg.subEnabled} onChange={(v) => setCfgKey('subEnabled', v)} />
              </div>
            </div>

            {/* F. Style — 3 simplified groups */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>STYLE</span>
                <span className="cfg-sec-api">subtitle_style</span>
              </div>
              <div className="seg">
                {SUB_STYLE_GROUPS.map(g => (
                  <div key={g.set} className={`seg-b${activeSubGroup === g.set ? ' on' : ''}`}
                    onClick={() => setCfgKey('subStyle', g.set)}>{g.label}</div>
                ))}
              </div>
            </div>

            {/* F. Language */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>LANGUAGE</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {(['auto', 'vi', 'en', 'ja', 'ko'] as string[]).map(v => (
                  <div key={v} className={`seg-b${cfg.subLanguage === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('subLanguage', v)}>{v === 'auto' ? 'Auto' : v.toUpperCase()}</div>
                ))}
              </div>
            </div>

            {/* F. Amount */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>AMOUNT</span>
                <span className="cfg-sec-api">subtitle_density</span>
              </div>
              <div className="seg">
                {([
                  { v: 'low'    as ConfigState['subDensity'], l: 'Low'    },
                  { v: 'medium' as ConfigState['subDensity'], l: 'Medium' },
                  { v: 'high'   as ConfigState['subDensity'], l: 'High'   },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.subDensity === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('subDensity', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* Auto-translate */}
            <div className="cfg-section">
              <div className="tog-row">
                <div>
                  <span className="tog-lbl">{t.cfgAutoTranslate}</span>
                </div>
                <Tog checked={cfg.subTranslate} onChange={(v) => setCfgKey('subTranslate', v)} />
              </div>
              {cfg.subTranslate && (
                <div style={{ marginTop: '8px' }}>
                  <div className="seg">
                    {([
                      { v: 'vi' as const, l: '🇻🇳 Việt'   },
                      { v: 'en' as const, l: '🇺🇸 English' },
                      { v: 'ja' as const, l: '🇯🇵 日本語'   },
                    ]).map(({ v, l }) => (
                      <div key={v} className={`seg-b${cfg.subTranslateLang === v ? ' on' : ''}`}
                        onClick={() => setCfgKey('subTranslateLang', v)}>{l}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>

          </div>

          {/* ── NARR tab ── */}
          <div className={`cfg-tab-pane${cfgTab === 'narr' ? ' active' : ''}`}>

            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgEnableVoice}</span>
                <Tog checked={cfg.narrEnabled} onChange={(v) => setCfgKey('narrEnabled', v)} />
              </div>
            </div>

            {/* G. Language */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>LANGUAGE</span>
                <span className="cfg-sec-api">voice_language</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'vi-VN' as const, l: '🇻🇳 VI'    },
                  { v: 'en-US' as const, l: '🇺🇸 EN'    },
                  { v: 'en-GB' as const, l: '🇬🇧 EN-GB' },
                  { v: 'ja-JP' as const, l: '🇯🇵 JA'    },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.voiceLang === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('voiceLang', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* G. Voice gender */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>VOICE</span>
                <span className="cfg-sec-api">voice_gender</span>
              </div>
              <div className="seg">
                <div className={`seg-b${cfg.voiceGender === 'female' ? ' on' : ''}`} onClick={() => setCfgKey('voiceGender', 'female')}>♀ Female</div>
                <div className={`seg-b${cfg.voiceGender === 'male'   ? ' on' : ''}`} onClick={() => setCfgKey('voiceGender', 'male')}>♂ Male</div>
              </div>
            </div>

            {/* G. Style */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>STYLE</span>
                <span className="cfg-sec-api">narration_style</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'auto'      as ConfigState['narrationStyle'], l: 'Auto'      },
                  { v: 'energetic' as ConfigState['narrationStyle'], l: 'Energetic' },
                  { v: 'calm'      as ConfigState['narrationStyle'], l: 'Calm'      },
                  { v: 'emotional' as ConfigState['narrationStyle'], l: 'Emotional' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.narrationStyle === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('narrationStyle', v)}>{l}</div>
                ))}
              </div>
            </div>

            {/* G. Source */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>SOURCE</span>
                <span className="cfg-sec-api">voice_source</span>
              </div>
              <div className="seg" style={{ flexDirection: 'column', gap: '3px' }}>
                {([
                  { v: 'subtitle'            as const, l: t.cfgVoiceSrcAuto,   d: t.cfgVoiceSrcAutoDesc   },
                  { v: 'translated_subtitle' as const, l: t.cfgVoiceSrcTrans,  d: t.cfgVoiceSrcTransDesc  },
                  { v: 'manual'              as const, l: t.cfgVoiceSrcManual, d: t.cfgVoiceSrcManualDesc },
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

function ClipRow({ slot, statusLabel, jobId, thumbRatio }: {
  slot: ClipSlot; statusLabel: string; jobId: string | null; thumbRatio: string
}) {
  const state   = clipStateKey(slot.status)
  const pct     = slot.progress_percent
  const isDone  = state === 'done'
  const isFail  = state === 'failed'
  const isWait  = state === 'waiting'
  const isActive = state === 'active'
  const activity = ACTIVITY_LABELS[slot.status.toLowerCase()] ?? ''
  const activeStepIdx = STEP_NODES.findIndex((n) => n.key === slot.status.toLowerCase())

  const thumbUrl = jobId ? getPartThumbnailUrl(jobId, slot.part_no) : null

  const ACCENT: Record<string, string> = {
    done:    '#34C878',
    failed:  '#ef4444',
    active:  '#a855f7',
    waiting: '#6b7280',
  }
  const accentColor = ACCENT[state] ?? '#6b7280'

  return (
    <div style={{
      display: 'flex',
      borderRadius: 10,
      overflow: 'hidden',
      background: 'var(--bg-card)',
      border: `1px solid ${isActive ? 'rgba(168,85,247,.25)' : 'var(--border)'}`,
      boxShadow: isActive ? '0 0 10px rgba(168,85,247,.08)' : 'none',
      transition: 'border-color .15s',
    }}>
      {/* Left accent bar */}
      <div style={{ width: 3, flexShrink: 0, background: `linear-gradient(180deg,${accentColor},${accentColor}55)` }} />

      {/* Thumbnail */}
      <div style={{
        width: 52, flexShrink: 0,
        aspectRatio: thumbRatio,
        background: 'rgba(255,255,255,.04)',
        overflow: 'hidden', position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {thumbUrl && isDone ? (
          <img
            src={thumbUrl}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <span style={{ fontSize: 16, opacity: .25 }}>
            {isFail ? '✕' : isWait ? '○' : isActive ? '▶' : '✓'}
          </span>
        )}
        {/* Progress overlay for active clips */}
        {isActive && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 3,
            background: 'rgba(255,255,255,.08)',
          }}>
            <div style={{
              height: '100%',
              width: `${pct}%`,
              background: `linear-gradient(90deg,${accentColor},#4d7cff)`,
              transition: 'width .4s ease',
            }} />
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: '8px 12px', minWidth: 0 }}>
        {/* Top line */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: isActive ? 6 : 0 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', fontFamily: 'monospace', flexShrink: 0 }}>
            #{String(slot.part_no).padStart(2, '0')}
          </span>

          <span style={{
            fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20, flexShrink: 0,
            background: `${accentColor}20`, color: accentColor,
            animation: isActive ? 'rndv-badge-pulse 1.4s ease-in-out infinite' : 'none',
          }}>
            {isActive && <span style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: accentColor, marginRight: 4, verticalAlign: 'middle' }} />}
            {statusLabel}
          </span>

          {/* Progress bar */}
          <div style={{ flex: 1, height: 3, borderRadius: 99, background: 'rgba(255,255,255,.07)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 99,
              width: `${isDone ? 100 : isFail || isWait ? 0 : pct}%`,
              background: isDone
                ? 'linear-gradient(90deg,#34C878,#22c55e)'
                : `linear-gradient(90deg,${accentColor},#4d7cff)`,
              transition: 'width .4s ease',
            }} />
          </div>

          <span style={{ fontSize: 10, fontWeight: 700, fontFamily: 'monospace', flexShrink: 0, color: accentColor }}>
            {isDone ? '100%' : isFail ? 'ERR' : isWait ? '—' : `${pct}%`}
          </span>
        </div>

        {/* Active: step nodes + activity */}
        {isActive && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {STEP_NODES.map((n, i) => {
                const st = i < activeStepIdx ? 'done' : i === activeStepIdx ? 'active' : 'pending'
                const col = st === 'done' ? '#34C878' : st === 'active' ? '#a855f7' : '#6b7280'
                return (
                  <React.Fragment key={n.key}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <div style={{
                        width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
                        border: `2px solid ${col}`,
                        background: st === 'done' ? col : 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 7,
                      }}>
                        {st === 'done' && <span style={{ color: '#000' }}>✓</span>}
                        {st === 'active' && <span style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: col, animation: 'rndv-badge-pulse 1.2s ease-in-out infinite' }} />}
                      </div>
                      <span style={{ fontSize: 9, color: col, fontWeight: st === 'active' ? 700 : 500 }}>{n.label}</span>
                    </div>
                    {i < STEP_NODES.length - 1 && (
                      <div style={{ flex: 1, height: 1, background: i < activeStepIdx ? '#34C878' : 'rgba(255,255,255,.1)', maxWidth: 20 }} />
                    )}
                  </React.Fragment>
                )
              })}
            </div>
            {activity && (
              <div style={{ fontSize: 9, color: 'var(--text-3)', paddingLeft: 2 }}>{activity}</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StepRendering({
  jobId, stage, jobStatus, progress, jobMessage, isTerminal, liveParts, wsError, t, aspectRatio,
}: {
  jobId: string | null; stage: string; jobStatus: string
  progress: WsProgressSummary | null; jobMessage: string
  isTerminal: boolean; liveParts: JobPart[]
  wsError: string | null; t: Strings; aspectRatio: string
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
  const thumbRatio     = aspectRatio.replace(':', '/')

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
          <span>
            {t.rndPreparing}
            {jobMessage && (
              <span style={{ display: 'block', fontSize: '10px', opacity: 0.55, marginTop: 2 }}>
                {jobMessage}
              </span>
            )}
          </span>
        </div>
      ) : (
        <div className="rndv-clip-list">
          {clipSlots.map((slot) => (
            <ClipRow key={slot.part_no} slot={slot} statusLabel={getStatusLabel(slot.status)} jobId={jobId} thumbRatio={thumbRatio} />
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
    if (outputDir) await window.electronAPI?.openPath?.(outputDir)
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
