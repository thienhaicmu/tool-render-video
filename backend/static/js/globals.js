let currentJobId = null;
let pollTimer = null;
let pollIntervalMs = 2500;
let activeJobStartedAt = null;
let jobWs = null;          // WebSocket for render job progress
let uploadWs = null;       // WebSocket for upload run progress
let lastStage = '';
let lastMessage = '';
let lastStatus = '';
let lastFailLogJobId = '';
let currentView = 'render';
const stageOrder = ['queued','starting','downloading','scene_detection','segment_building','transcribing_full','rendering','rendering_parallel','writing_report','done'];
const LOG_DEDUPE_WINDOW_MS = 12000;
const logStateByScope = {
  render: { lastText: '', lastAt: 0, lastNode: null, lastCount: 1 },
  upload: { lastText: '', lastAt: 0, lastNode: null, lastCount: 1 },
  channels: { lastText: '', lastAt: 0, lastNode: null, lastCount: 1 },
};
let lastProgressBucket = -1;

// ── Smooth progress animation state ────────────────────────────────────────
// _partTarget[partNo]   = last known backend progress %  (source of truth)
// _partDisplay[partNo]  = visually displayed progress %  (animated toward target)
// _jobTargetPct         = last known job-level overall %
// _jobDisplayPct        = visually displayed job %
const _partTarget  = {};
const _partDisplay = {};
let _jobTargetPct  = 0;
let _jobDisplayPct = 0;
let _smoothRafId   = null;


let currentUploadRunId = null;
let uploadPollTimer = null;
let uploadLoginValid = false;
let selectedUploadVideos = [];
let selectedLocalVideoPath = '';
let selectedRenderOutputDir = '';
let batchYoutubeUrls = [];
// Local video editor state (set when user picks local file)
let _localEditorVideoSrc  = null;
let _localEditorDuration  = 0;
let _localEditorSessionId = null;
let renderChannelsRootPath = '';
let uploadChannelsRootPath = '';
let createChannelsRootPath = '';
let defaultChannelsRootPath = '';
const REQUIRED_UPLOAD_CHANNEL_PREFIX = 'T';
let uploadConfigEditMode = false;
const RENDER_SESSION_ONLY = true;
const uploadConfigEditableIds = [
  'upload_account_key',
  'upload_credential_line',
  'upload_tiktok_username',
  'upload_tiktok_password',
  'upload_mail_username',
  'upload_mail_password',
  'upload_browser_preference',
  'upload_browser_executable',
  'upload_network_mode',
  'upload_proxy_server',
  'upload_proxy_username',
  'upload_proxy_password',
  'upload_schedule_slots',
];

const steps = [
  { key: 'download', label: 'Download Video' },
  { key: 'scenes', label: 'Detect Scenes' },
  { key: 'subtitle', label: 'Generate Subtitles' },
  { key: 'render', label: 'Render Parts' },
  { key: 'score', label: 'Scoring + Report' },
];
const pipeline = [
  { key: 'queued', label: 'Queued', stages: ['queued', 'starting'] },
  { key: 'downloading', label: 'Download', stages: ['downloading'] },
  { key: 'scene', label: 'Scene Detect', stages: ['scene_detection'] },
  { key: 'segment', label: 'Segment Build', stages: ['segment_building'] },
  { key: 'subtitle', label: 'Subtitle', stages: ['transcribing_full'] },
  { key: 'render', label: 'Render', stages: ['rendering', 'rendering_parallel'] },
  { key: 'report', label: 'Report', stages: ['writing_report', 'done'] },
];
const uploadPipeline = [
  { key: 'channel', label: 'Channel' },
  { key: 'profile', label: 'Profile' },
  { key: 'login_check', label: 'Login Check' },
  { key: 'login', label: 'Login' },
  { key: 'queue', label: 'Queue' },
  { key: 'uploading', label: 'Uploading' },
  { key: 'done', label: 'Done' },
];
let uploadActionStage = 'idle';
let uploadWizardStep = 1;
let _ytDownloadAbortCtrl = null;

