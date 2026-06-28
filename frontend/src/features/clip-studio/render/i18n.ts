import type { Lang } from '../ClipStudio'
import type { JobErrorKind } from '@/types/api'

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
    // Pha 2 — Render Profiles
    cfgFrame: 'FRAME',
    cfgDuration: 'DURATION',
    // Pha 5.7 — source trim
    cfgTrim: 'TRIM SOURCE',
    cfgTrimIn: 'In', cfgTrimOut: 'Out',
    cfgTrimSelected: (d: string) => `Selected: ${d}`,
    cfgTrimReset: 'Reset',
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
    cfgVoiceSrcRewrite: 'AI rewrite', cfgVoiceSrcRewriteDesc: 'AI rewrites the transcript to fit each clip duration',
    cfgRewriteToneHint: 'Optional tone (e.g. dramatic, playful, informative)',
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
    rndWsReconnecting: 'Reconnecting…',
    rndWsPolling: 'Refreshing every 5s · render is unaffected',
    rndCancelling: 'Cancelling render — finishing current step…',
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
    // Pha 1.2 — rendering-screen advisories (were hardcoded VI)
    rndEtaEstimating: 'ETA estimating…',
    rndWatchdogElapsed: (min: number) => `Render running ${min} min`,
    rndWatchdogWarn: '— nearing the 2h watchdog limit. Grant +1h?',
    rndWatchdogExtending: 'Requesting…',
    rndWatchdogDismiss: 'Let it cancel',
    rndStuckOne: (n: number) => `Clip #${n} looks unusually slow`,
    rndStuckMany: (n: number) => `${n} clips look unusually slow`,
    rndStuckNoUpdate: (s: number) => `(no update for ${s}s)`,
    rndStuckHint: 'Render is still running — wait 1–2 more min before cancelling',
    rndEventNoMatch: 'No events match the filter',
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
    errKindDownload: 'Download failed — check URL or disk space',
    errKindWhisper: 'Transcription failed — try a smaller Whisper model',
    errKindSource: 'Source file not found — it may have been moved or deleted',
    errKindFfmpeg: 'FFmpeg encoding error — check render logs',
    errKindQa: 'Output validation failed — video may be corrupt or empty',
    errKindVoice: 'Voiceover failed — TTS engine error',
    errKindCancelled: 'Render was cancelled',
    errKindAiKey: 'AI provider returned no clips — likely a missing or invalid API key',
    errKindRender: 'Render failed — check logs for details',
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
    // Pha 2 — Render Profiles
    cfgFrame: 'KHUNG HÌNH',
    cfgDuration: 'THỜI LƯỢNG',
    // Pha 5.7 — cắt nguồn
    cfgTrim: 'CẮT NGUỒN',
    cfgTrimIn: 'Đầu', cfgTrimOut: 'Cuối',
    cfgTrimSelected: (d: string) => `Đã chọn: ${d}`,
    cfgTrimReset: 'Đặt lại',
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
    cfgVoiceSrcRewrite: 'AI viết lại nội dung', cfgVoiceSrcRewriteDesc: 'AI viết lại transcript vừa khít timing mỗi clip',
    cfgRewriteToneHint: 'Tone tuỳ chọn (ví dụ: kịch tính, vui nhộn, thông tin)',
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
    rndWsReconnecting: 'Đang kết nối lại…',
    rndWsPolling: 'Đang refresh mỗi 5 giây · render vẫn chạy bình thường',
    rndCancelling: 'Đang hủy render — chờ bước hiện tại kết thúc…',
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
    // Pha 1.2 — advisory phụ đề màn render
    rndEtaEstimating: 'ETA đang ước tính…',
    rndWatchdogElapsed: (min: number) => `Render đã chạy ${min} phút`,
    rndWatchdogWarn: '— sắp đạt giới hạn watchdog 2h. Cấp thêm 1h?',
    rndWatchdogExtending: 'Đang xin…',
    rndWatchdogDismiss: 'Để render bị hủy',
    rndStuckOne: (n: number) => `Clip #${n} có vẻ bị chậm bất thường`,
    rndStuckMany: (n: number) => `${n} clip có vẻ bị chậm bất thường`,
    rndStuckNoUpdate: (s: number) => `(không cập nhật trong ${s}s)`,
    rndStuckHint: 'Render vẫn đang chạy — chờ thêm 1-2 phút trước khi cancel',
    rndEventNoMatch: 'Không có event nào khớp filter',
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
    errKindDownload: 'Tải về thất bại — kiểm tra URL hoặc dung lượng ổ đĩa',
    errKindWhisper: 'Phiên âm thất bại — thử model Whisper nhỏ hơn',
    errKindSource: 'Không tìm thấy file nguồn — có thể đã bị di chuyển hoặc xóa',
    errKindFfmpeg: 'Lỗi mã hóa FFmpeg — xem nhật ký render',
    errKindQa: 'Kiểm tra output thất bại — video bị hỏng hoặc trống',
    errKindVoice: 'Thuyết minh thất bại — lỗi TTS engine',
    errKindCancelled: 'Render đã bị hủy',
    errKindAiKey: 'AI không trả về clip nào — có thể thiếu hoặc sai API key',
    errKindRender: 'Render thất bại — xem nhật ký để biết chi tiết',
  },
} as const

export type Strings = { [K in keyof typeof T['EN']]: typeof T['EN'][K] extends string ? string : typeof T['EN'][K] }
export function useT(lang: Lang): Strings { return T[lang] as Strings }

// "AI_KEY_MISSING" is a synthetic kind inferred client-side from the
// pipeline's "ai_emission_empty" / "returned_none" / "API key" phrases.
// Treated as a string literal here so the existing JobErrorKind type
// (declared in types/api.ts) doesn't need to change in lockstep with
// the backend — the FE handles the inference + hint surface itself.
export type FrontendErrorKind = JobErrorKind | 'AI_KEY_MISSING'

export const ERROR_KIND_KEY: Record<FrontendErrorKind, keyof Pick<Strings,
  'errKindDownload' | 'errKindWhisper' | 'errKindSource' | 'errKindFfmpeg' |
  'errKindQa' | 'errKindVoice' | 'errKindCancelled' | 'errKindAiKey' | 'errKindRender'
>> = {
  DOWNLOAD_FAILED: 'errKindDownload',
  WHISPER_FAILED:  'errKindWhisper',
  SOURCE_NOT_FOUND:'errKindSource',
  FFMPEG_FAILED:   'errKindFfmpeg',
  QA_FAILED:       'errKindQa',
  VOICE_FAILED:    'errKindVoice',
  CANCELLED:       'errKindCancelled',
  AI_KEY_MISSING:  'errKindAiKey',
  RENDER_FAILED:   'errKindRender',
}

export const ERROR_FIX_STEPS: Record<FrontendErrorKind, string[]> = {
  DOWNLOAD_FAILED:  ['Check the YouTube URL is valid and not private/region-locked', 'Verify disk space on the output drive', 'Try switching to local file mode if download keeps failing'],
  WHISPER_FAILED:   ['Switch to a smaller Whisper model (e.g. "small" instead of "medium")', 'Check available RAM — Whisper needs ~4 GB for large models', 'Disable transcription and use manual subtitles'],
  SOURCE_NOT_FOUND: ['Verify the source file still exists at the original path', 'Re-add the source in Step 1 and render again'],
  FFMPEG_FAILED:    ['Check the render log in the Output folder for the full FFmpeg error', 'Try switching render quality to "Fast" and retry', 'Ensure the output folder has write permissions'],
  QA_FAILED:        ['The exported video was empty or corrupt — check disk space', 'Retry the render — this can occur if the machine was low on memory', 'Check FFmpeg log in the output folder for codec errors'],
  VOICE_FAILED:     ['Disable voiceover and re-render subtitles only', 'Check that the TTS engine is installed and not rate-limited', 'Switch voice source to "subtitle" instead of "manual"'],
  CANCELLED:        ['You cancelled this render — click Retry to restart from scratch', 'Or click Configure to tweak settings before rendering again'],
  AI_KEY_MISSING:   ['Open backend/.env and set GEMINI_API_KEY=AIza… (or OPENAI_API_KEY / ANTHROPIC_API_KEY)', 'Use Configure → AI panel → Test connection to verify the key works before rendering', 'Switch to a different AI provider in Step 2 if your current one is rate-limited or down'],
  RENDER_FAILED:    ['Open the output folder and check render.log for the root cause', 'Retry once — transient errors (memory spike, process collision) often resolve', 'Reduce concurrent jobs in Settings if rendering multiple videos'],
}

/**
 * S5-hotfix — infer a more specific error kind from the raw exception
 * message when the backend's classification is too coarse. Currently
 * catches two cases the backend lumps under "failed":
 *   1. JobCancelledError — surfaces as message ending with ":" + empty
 *      exception body. We treat as CANCELLED.
 *   2. ai_emission_empty / returned_none / "API keys in server .env" —
 *      we treat as AI_KEY_MISSING so the user gets actionable hints
 *      instead of the generic "retry / reduce concurrency" wall.
 *
 * Backend fix (render_pipeline.py outer except handler) is CRITICAL-tier
 * and tracked as follow-up. Until then this client-side inference is
 * the safe path that doesn't risk regressions on the render path.
 */
export function inferErrorKind(
  jobStatus: string,
  jobMessage: string,
  backendKind: JobErrorKind | null,
): FrontendErrorKind | null {
  const msg = (jobMessage || '').toLowerCase()

  // Cancellation pattern: pipeline emits "Failed at step '...': " with
  // empty exception body when JobCancelledError propagates through the
  // outer except. Match on the empty-suffix to be conservative; a real
  // failure always has at least an exception class name after the
  // colon.
  if (jobStatus === 'failed' && /failed at step '.+':\s*$/i.test(jobMessage || '')) {
    return 'CANCELLED'
  }

  if (backendKind === 'CANCELLED' || jobStatus === 'cancelled') {
    return 'CANCELLED'
  }

  // AI key / provider exhaustion pattern.
  if (
    msg.includes('ai_emission_empty') ||
    msg.includes('returned_none') ||
    msg.includes('verify api keys') ||
    msg.includes('api provider chain')
  ) {
    return 'AI_KEY_MISSING'
  }

  return backendKind
}
