const RENDER_FLOW_ORDER = ['source', 'configure', 'rendering', 'complete'];
let _renderFlowStepRank = 0;
let _renderMonitorLastUpdateAt = 0;
let _renderMonitorLastProgressAt = 0;
let _renderMonitorLastSignature = '';
let _renderMonitorLastJob = null;
let _renderMonitorLastSummary = null;
let _renderMonitorLastParts = [];
let _renderMonitorHeartbeatTimer = null;
let _renderLogsUserToggled = false;
let _selectedClipPaths = new Set();
let _clipsSortOrder        = 'score';
let _uxr3AutoSelectedBest  = false;   // UX-R3-F: auto-preview best clip once per session
let _logAutoScroll = true;
let _rcLastActivePartNo = -1;
let _rcScrollDebounceId = null;
let _rcUserIsScrolling = false;
let _rcUserScrollTimerId = null;
let _rcPreviewJobId = '';
let _rcPreviewPartNo = 0;
let _rcCompareSelA = '';
let _rcCompareSelB = '';
// R8.2.1: in-panel clip compare state
let _r821CompareRefPartNo  = null;
let _r821CompareChalPartNo = null;
let _rcBenchmark = { jobId: '', logsLoaded: false, totalElapsedMs: 0, sceneDetectionMs: null, sceneCount: null, transcriptionMs: null, transcriptionModel: null, transcriptionLiveSec: null, totalParts: 0, completedParts: 0, failedParts: 0, failedStage: '', outputSizes: [] };
const RENDER_MONITOR_STALL_MS = 45000;
let _queueStatusTimer = null;

function mountRenderRuntimePanel() {
  const runtimeMount = qs('render_runtime_mount');
  const activePanel = qs('render_active_panel');
  const bottomPanel = qs('appBottomPanel');
  if (!runtimeMount || !activePanel || !bottomPanel) return;
  if (bottomPanel.dataset.runtimeMounted === '1') return;
  bottomPanel.dataset.runtimeMounted = '1';
  bottomPanel.classList.add('renderCompatWrapper');
  bottomPanel.setAttribute('aria-hidden', 'true');

  const toolbar = bottomPanel.querySelector('.abpToolbar');
  const runtimeBody = qs('rc_bottom');
  if (toolbar && toolbar.parentElement !== runtimeMount) runtimeMount.appendChild(toolbar);
  if (runtimeBody && runtimeBody.parentElement !== runtimeMount) runtimeMount.appendChild(runtimeBody);

  const queuePanel = runtimeMount.querySelector('.rcQueuePanel');
  const partCards = qs('rc_part_cards');
  const errorBlock = qs('abp_error_block');
  const retryBtn = qs('abp_retry_btn');
  if (queuePanel && errorBlock && errorBlock.parentElement !== queuePanel) {
    errorBlock.classList.add('renderRuntimeErrorBlock', 'hiddenView');
    if (retryBtn && retryBtn.parentElement !== errorBlock) errorBlock.appendChild(retryBtn);
    queuePanel.insertBefore(errorBlock, partCards || null);
  }
  RenderAiRuntime.mountPanels();
}

function setHeaderJob(text){ qs('job_chip').textContent = text; }
function resetRenderSessionUi(){
  initRenderLogScrollBehavior();
  _localEditorVideoSrc  = null;
  _localEditorDuration  = 0;
  _localEditorSessionId = null;
  currentJobId = null;
  lastFailLogJobId = '';
  activeJobStartedAt = null;
  lastStage = '';
  lastMessage = '';
  lastStatus = '';
  lastProgressBucket = -1;
  _stopJobWs();
  if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
  if(qs('event_log_render')) qs('event_log_render').innerHTML = '<div class="rcLogEmpty">No logs yet</div>';
  _logAutoScroll = true;
  const _asbtn = qs('rc_log_autoscroll_btn');
  if (_asbtn) { _asbtn.classList.add('isActive'); _asbtn.title = 'Auto-scroll: On'; }
  setHeaderJob('No active job');
  qs('job_stage_pill').textContent = 'Idle';
  if (qs('job_stage_pill')) qs('job_stage_pill').dataset.stage = '';
  qs('job_title').textContent = 'No active job';
  qs('job_meta_1').textContent = 'Channel - | Source -';
  qs('job_meta_2').textContent = '0/0 clips done';
  qs('job_percent').textContent = '0%';
  qs('job_message').textContent = 'Initializing';
  qs('job_bar').style.width = '0%';
  qs('job_bar').classList.remove('isWaitingActive');
  if (qs('render_active_bar')) qs('render_active_bar').classList.remove('isWaitingActive');
  if (qs('action_title'))   qs('action_title').textContent = 'Waiting for job';
  if (qs('action_state'))   { qs('action_state').textContent = 'idle'; qs('action_state').dataset.status = 'idle'; }
  if (qs('action_message')) qs('action_message').textContent = 'No active processing task.';
  if (qs('action_meta'))    qs('action_meta').textContent = 'Elapsed 00:00 | Updated -';
  if (qs('abp_summary_primary')) qs('abp_summary_primary').textContent = 'Ready';
  if (qs('abp_summary_progress')) qs('abp_summary_progress').textContent = '0%';
  if (qs('abp_summary_meta')) qs('abp_summary_meta').textContent = 'No active render job.';
  if (qs('abp_summary_stage')) qs('abp_summary_stage').textContent = 'Idle';
  if (qs('abp_summary_parts')) qs('abp_summary_parts').textContent = '0 / 0 completed';
  if (qs('abp_summary_active')) qs('abp_summary_active').textContent = 'No active clip';
  if (qs('abp_summary_latest')) qs('abp_summary_latest').textContent = 'Waiting for a render job.';
  if (qs('rc_status')) qs('rc_status').textContent = 'Ready';
  if (qs('rc_status')) qs('rc_status').dataset.state = 'ready';
  if (qs('rc_progress')) qs('rc_progress').textContent = '';
  if (qs('rc_stage')) qs('rc_stage').textContent = '';
  if (qs('rc_parts')) qs('rc_parts').textContent = '';
  if (qs('rc_active')) qs('rc_active').textContent = '';
  if (qs('rc_latest')) qs('rc_latest').textContent = '';
  if (qs('abp_output_text')) qs('abp_output_text').textContent = 'Output folder not set.';
  if (qs('abp_output_meta')) qs('abp_output_meta').textContent = 'Latest file will appear here.';
  if (qs('abp_error_text')) qs('abp_error_text').textContent = 'No blocking errors.';
  if (qs('abp_error_block')) qs('abp_error_block').classList.add('hiddenView');
  if (qs('abp_retry_btn')) qs('abp_retry_btn').classList.add('hiddenView');
  if (qs('rc_open_output_btn')) qs('rc_open_output_btn').disabled = true;
  renderPipeline('queued', 'queued');
  renderSteps(0);
  renderParts([]);
  renderPartFocus([], null);
  renderActivePartCard([], null);
  if(RENDER_SESSION_ONLY && qs('render_history_list')){
    qs('render_history_list').innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
  }
  hideRenderCompletionBar();
  const _pipelineMain = document.getElementById('mainArea');
  if (_pipelineMain) _pipelineMain.classList.remove('inPipeline');
  resetRenderMonitorHeartbeat();
  _renderLogsUserToggled = false;
  setRenderLogsCollapsed(false);
  if (qs('rc_card_job_title')) qs('rc_card_job_title').textContent = '';
  if (qs('rc_card_status_badge')) { qs('rc_card_status_badge').textContent = 'Idle'; qs('rc_card_status_badge').dataset.state = 'idle'; }
  _updateStageTimeline('', '');
  _rcPreviewJobId = '';
  _rcPreviewPartNo = 0;
  const _pvVid = qs('rc_preview_video');
  if (_pvVid) { _pvVid.src = ''; _pvVid.dataset.previewSrc = ''; }
  if (qs('rc_output_preview')) qs('rc_output_preview').classList.add('hiddenView');
  _resetCsPreview();
  _hideCsPreviewArea();
  _rcBenchmark = { jobId: '', logsLoaded: false, totalElapsedMs: 0, sceneDetectionMs: null, sceneCount: null, transcriptionMs: null, transcriptionModel: null, transcriptionLiveSec: null, totalParts: 0, completedParts: 0, failedParts: 0, failedStage: '', outputSizes: [] };
  if (qs('rc_benchmark_panel')) qs('rc_benchmark_panel').classList.add('hiddenView');
  _rcCompareSelA = '';
  _rcCompareSelB = '';
  renderBottomActiveQueue(null, null, []);
  updateRenderMainState(null, null, []);
  resetAiInsightsPanel();
  RenderAiRuntime.reset();
}
function fmtElapsed(ms){
  const sec = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

// ── Render slot visibility ────────────────────────────────────────────────────

async function _loadQueueStatus() {
  try {
    const r = await fetch('/api/render/queue-status');
    if (!r.ok) return;
    const d = await r.json();
    const pill = qs('rc_slot_pill');
    if (pill) {
      pill.textContent = `Slots: ${d.active_renders} / ${d.max_renders} active`;
      pill.dataset.active = String(d.active_renders > 0 ? 1 : 0);
      pill.hidden = false;
    }
  } catch(_) {}
}

function _startQueueStatusPolling() {
  if (_queueStatusTimer) return;
  _loadQueueStatus();
  _queueStatusTimer = setInterval(_loadQueueStatus, 10000);
}

function _stopQueueStatusPolling() {
  if (_queueStatusTimer) { clearInterval(_queueStatusTimer); _queueStatusTimer = null; }
  const pill = qs('rc_slot_pill');
  if (pill) { pill.hidden = true; }
}

// ── Stall / stuck signal detection ───────────────────────────────────────────

function _detectStallSignal(job) {
  const status = String(job?.status || '').toLowerCase();
  const msg = String(job?.message || '').toLowerCase();
  if (status === 'stalled' || status === 'timeout') {
    return 'Render timed out — check logs for details.';
  }
  if (msg.includes('stall detected') || msg.includes('wall-clock timeout') || msg.includes('stall_detected')) {
    return 'Render timed out — check logs for details.';
  }
  if (msg.includes('stall_suspected') || msg.includes('stall suspected') || msg.includes('unknown duration')) {
    return 'Render may be stuck — still waiting for FFmpeg.';
  }
  if (msg.includes('stall') || msg.includes('stuck')) {
    return 'Render may be stuck — still waiting for FFmpeg.';
  }
  if (msg.includes('timeout')) {
    return 'Render timed out — check logs for details.';
  }
  return '';
}

// ── Quality badge helper (per part) ──────────────────────────────────────────

function _partQualityBadgeHtml(part) {
  const penalty = Number(part?.quality_penalty ?? part?.score_penalty ?? 0);
  const warnings = Array.isArray(part?.quality_warnings) ? part.quality_warnings : [];
  if (penalty <= 0 && warnings.length === 0) return '';
  const tip = warnings.length > 0
    ? esc(warnings.slice(0, 3).join(' | '))
    : `Quality penalty: ${penalty}`;
  return `<span class="rcQualityBadge" title="${tip}">&#9888; Quality issue</span>`;
}
function stageLabel(stage){
  const map = {
    queued: 'Queued',
    starting: 'Preparing',
    downloading: 'Preparing source',
    scene_detection: 'Scene Detection',
    segment_building: 'Segment Selection',
    transcribing_full: 'Subtitles',
    rendering: 'Rendering Clips',
    rendering_parallel: 'Rendering Clips',
    writing_report: 'Finalizing',
    done: 'Completed',
    failed: 'Failed',
  };
  return map[stage] || 'Processing';
}
function stageLabelPlain(stage){
  const map = {
    pending: 'Queued',
    queued: 'Queued',
    preparing: 'Preparing',
    starting: 'Preparing',
    downloading: 'Preparing source',
    scene_detecting: 'Detecting scenes',
    scene_detection: 'Detecting scenes',
    segment_building: 'Segment Selection',
    transcribing_full: 'Generating subtitles',
    rendering: 'Rendering clips',
    rendering_parallel: 'Rendering clips',
    writing_report: 'Validating output',
    finalizing: 'Finalizing',
    done: 'Completed',
    completed: 'Completed',
    completed_with_errors: 'Completed with issues',
    failed: 'Failed',
    working: 'Working...',
  };
  return map[(stage || '').toLowerCase()] || (stage ? 'Working...' : '-');
}

function normalizeRenderStatus(status, stage = ''){
  const st = String(status || '').toLowerCase().trim();
  const sg = String(stage || '').toLowerCase().trim();
  if (st === 'pending' || st === 'queued') return 'pending';
  if (st === 'preparing' || st === 'starting') return 'preparing';
  if (st === 'scene_detecting') return 'scene_detecting';
  if (st === 'rendering') return 'rendering';
  if (st === 'completed' || st === 'done' || st === 'complete') return 'completed';
  if (st === 'completed_with_errors' || st === 'partial_failed') return 'completed_with_errors';
  if (st === 'failed' || st === 'interrupted' || st === 'stalled' || st === 'timeout') return 'failed';
  if (st === 'running') {
    if (sg === 'scene_detection' || sg === 'scene_detecting') return 'scene_detecting';
    if (sg === 'segment_building') return 'preparing';
    if (sg === 'rendering' || sg === 'rendering_parallel') return 'rendering';
    if (sg === 'writing_report' || sg === 'finalizing') return 'preparing';
    if (sg === 'queued') return 'pending';
    if (sg === 'starting' || sg === 'downloading' || sg === 'render.prepare_source') return 'preparing';
  }
  return st || (sg ? 'working' : '');
}

function normalizeRenderStage(stage, status = ''){
  const s = String(stage || '').toLowerCase().trim();
  const st = String(status || '').toLowerCase().trim();
  if (s === 'pending') return 'queued';
  if (s === 'preparing') return 'starting';
  if (s === 'scene_detecting') return 'scene_detection';
  if (s === 'finalizing') return 'writing_report';
  if (!s && st === 'scene_detecting') return 'scene_detection';
  if (!s && st === 'rendering') return 'rendering';
  if (!s && st === 'completed') return 'done';
  if (!s && st === 'completed_with_errors') return 'done';
  if (!s && st && !['pending', 'preparing', 'failed'].includes(st)) return 'working';
  return s;
}

function isTerminalRenderStatus(status){
  const st = normalizeRenderStatus(status);
  return st === 'completed' || st === 'completed_with_errors' || st === 'partial_failed' || st === 'failed' || st === 'interrupted' || st === 'done' || st === 'complete';
}

function isPartialRenderStatus(status){
  const st = normalizeRenderStatus(status);
  return st === 'completed_with_errors';
}

function isCompletedRenderStatus(status){
  const st = normalizeRenderStatus(status);
  return st === 'completed';
}

function clampRenderProgress(value){
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function deriveRenderProgress(job, summary = null, parts = []){
  const items = Array.isArray(parts) ? parts : [];
  const s = summary || computeProgressSummary(items);
  const stage = normalizeRenderStage(job?.stage, job?.status);
  const status = normalizeRenderStatus(job?.status, stage);
  const backendPct = clampRenderProgress(job?.progress_percent);
  const partsPct = clampRenderProgress(s?.overall_progress_percent ?? s?.parts_percent);
  let derived = backendPct;

  if (status === 'completed' || status === 'completed_with_errors') return 100;
  if (status === 'rendering' || stage === 'rendering' || stage === 'rendering_parallel') {
    if (partsPct > 0) derived = Math.max(derived, Math.min(90, Math.round(30 + (partsPct / 100) * 60)));
    else if (Number(s?.total_parts || items.length || 0) > 0) {
      const total = Number(s?.total_parts || items.length || 0);
      const completed = Number(s?.completed_parts || 0);
      const failed = Number(s?.failed_parts || 0);
      derived = Math.max(derived, Math.min(90, Math.round(30 + ((completed + failed) / total) * 60)));
    }
  } else if (status === 'scene_detecting' || stage === 'scene_detection') {
    derived = Math.max(derived, backendPct);
  } else if (stage === 'segment_building') {
    derived = Math.max(derived, backendPct || 25);
  } else if (stage === 'writing_report') {
    derived = Math.max(derived, backendPct || 92);
  } else if ((status === 'preparing' || stage === 'starting' || stage === 'downloading') && !derived) {
    derived = 5;
  }
  return clampRenderProgress(derived);
}

function renderUxStageLabel(job, summary = null, parts = []) {
  const stage = normalizeRenderStage(job?.stage, job?.status);
  const status = normalizeRenderStatus(job?.status, stage);
  if (status === 'completed') return 'Completed';
  if (status === 'completed_with_errors') return 'Completed with issues';
  if (status === 'failed') return 'Failed';
  if (stage === 'scene_detection' || status === 'scene_detecting') return 'Detecting scenes';
  if (stage === 'segment_building') return 'Segment Selection';
  if (stage === 'transcribing_full') return 'Generating subtitles';
  if (stage === 'rendering' || stage === 'rendering_parallel' || status === 'rendering') return 'Rendering clips';
  if (stage === 'writing_report') return 'Validating output';
  if (status === 'pending' || stage === 'queued') return 'Preparing';
  if (status === 'preparing' || stage === 'starting' || stage === 'downloading') return 'Preparing';
  return job ? 'Working...' : 'Idle';
}

function renderJobShortId(job) {
  const id = String(job?.id || job?.job_id || currentJobId || '').trim();
  if (!id) return 'Job -';
  return `Job ${id.length > 10 ? `${id.slice(0, 6)}...${id.slice(-4)}` : id}`;
}

function renderElapsedLabel(job) {
  const started = activeJobStartedAt || Date.parse(job?.created_at || job?.started_at || '');
  if (!started || Number.isNaN(started)) return '';
  return `Elapsed ${fmtElapsed(Date.now() - started)}`;
}

function renderMonitorStageLabel(stage, status, summary = null){
  const st = normalizeRenderStatus(status, stage);
  if (isPartialRenderStatus(st)) return 'Completed with errors';
  if (isCompletedRenderStatus(st)) return 'Render complete';
  if (st === 'failed') return 'Render failed';
  const s = normalizeRenderStage(stage, status);
  if ((s === 'rendering' || s === 'rendering_parallel') && summary) {
    const active = Number(summary.processing_parts || 0);
    if (active > 1) return `Rendering ${active} clips in parallel`;
    if (active === 1) return 'Rendering 1 clip';
  }
  return stageLabel(stage);
}

function renderMonitorClipSummary(summary, parts = []){
  const s = summary || computeProgressSummary(parts || []);
  const total = Number(s.total_parts || parts.length || 0);
  const done = Number(s.completed_parts || 0);
  const active = Number(s.processing_parts || 0);
  const failed = Number(s.failed_parts || 0);
  if (!total) return 'No clips created yet';
  const bits = [`${total} clips`];
  if (done > 0) bits.push(`${done} done`);
  if (active > 1) bits.push(`${active} in parallel`);
  else if (active === 1) bits.push('1 rendering');
  if (failed > 0) bits.push(`${failed} failed`);
  return bits.join(' · ');
}

function renderMonitorRelative(ms){
  if (!ms) return 'No backend update yet';
  const sec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (sec < 2) return 'Last update just now';
  if (sec < 60) return `Last update ${sec}s ago`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return rem ? `Last update ${min}m ${rem}s ago` : `Last update ${min}m ago`;
}

function resetRenderMonitorHeartbeat(){
  _renderMonitorLastUpdateAt = 0;
  _renderMonitorLastProgressAt = 0;
  _renderMonitorLastSignature = '';
  _renderMonitorLastJob = null;
  _renderMonitorLastSummary = null;
  _renderMonitorLastParts = [];
  updateRenderMonitorHeartbeat(null, null, []);
}

function ensureRenderMonitorHeartbeatTimer(){
  if (_renderMonitorHeartbeatTimer) return;
  _renderMonitorHeartbeatTimer = setInterval(() => {
    updateRenderMonitorHeartbeat();
  }, 1000);
}

function markRenderMonitorUpdate(job, summary, parts = [], targetPercent = null){
  const now = Date.now();
  _renderMonitorLastUpdateAt = now;
  const s = summary || computeProgressSummary(parts || []);
  _renderMonitorLastJob = job || null;
  _renderMonitorLastSummary = s;
  _renderMonitorLastParts = Array.isArray(parts) ? parts : [];
  const signature = [
    String(job?.status || ''),
    String(job?.stage || ''),
    Math.round(Number(targetPercent ?? job?.progress_percent ?? 0)),
    Number(s.completed_parts || 0),
    Number(s.processing_parts || 0),
    Number(s.failed_parts || 0),
    Number(s.total_parts || parts.length || 0)
  ].join('|');
  if (signature !== _renderMonitorLastSignature) {
    _renderMonitorLastSignature = signature;
    _renderMonitorLastProgressAt = now;
  }
  ensureRenderMonitorHeartbeatTimer();
}

function updateRenderMonitorHeartbeat(job, summary, parts = []){
  const header = qs('render_monitor_header');
  if (!header) return;
  job = job || _renderMonitorLastJob;
  summary = summary || _renderMonitorLastSummary;
  parts = parts && parts.length ? parts : (_renderMonitorLastParts || []);
  const status = String(job?.status || lastStatus || '').toLowerCase();
  const running = currentJobId && !isTerminalRenderStatus(status);
  const partial = isPartialRenderStatus(status);
  const completed = isCompletedRenderStatus(status) || partial;
  const failed = status === 'failed' || status === 'interrupted';
  const now = Date.now();
  const noProgressMs = _renderMonitorLastProgressAt ? now - _renderMonitorLastProgressAt : 0;
  const stalled = running && _renderMonitorLastProgressAt && noProgressMs > RENDER_MONITOR_STALL_MS;

  let monitorState = 'idle';
  if (running) monitorState = stalled ? 'stalled' : 'running';
  if (completed) monitorState = partial ? 'failed' : 'complete';
  if (failed) monitorState = 'failed';
  header.dataset.monitorState = monitorState;

  const pctText = qs('job_percent')?.textContent || '0%';
  const stageText = job ? renderMonitorStageLabel(job.stage, job.status, summary) : (running ? stageLabelPlain(lastStage) : 'Ready to render');
  const primary = qs('render_monitor_primary');
  const secondary = qs('render_monitor_secondary');
  const heartbeat = qs('render_monitor_heartbeat');
  const latestDetail = String(job?.message || '').trim();
  const latestShort = latestDetail.length > 96 ? `${latestDetail.slice(0, 93)}...` : latestDetail;
  if (primary) {
    if (partial) {
      primary.textContent = `Completed with errors · ${pctText}`;
    } else
    if (failed) primary.textContent = `Render failed · ${pctText}`;
    else if (completed) primary.textContent = `Render complete · ${pctText}`;
    else if (running) primary.textContent = `${stageText} · ${pctText}`;
    else primary.textContent = 'Ready to render';
  }
  if (secondary) {
    const clipLine = renderMonitorClipSummary(summary, parts);
    if (partial) secondary.textContent = `${clipLine} · Review failed clips`;
    else if (stalled) secondary.textContent = clipLine;
    else if (completed) secondary.textContent = `${clipLine} · Final clips saved below`;
    else if (failed) secondary.textContent = `${clipLine} · Check diagnostics`;
    else secondary.textContent = running ? clipLine : 'No active render job.';
  }
  if (secondary) {
    const clipLine = renderMonitorClipSummary(summary, parts);
    if (failed) secondary.textContent = `${clipLine} · ${latestShort || 'Check diagnostics'}`;
    else if (running && latestShort) secondary.textContent = `${clipLine} · ${latestShort}`;
  }
  if (heartbeat) {
    heartbeat.textContent = !currentJobId
      ? 'Idle'
      : stalled
      ? `No progress update for ${Math.floor(noProgressMs / 1000)}s — render may be stalled`
      : completed
      ? 'Render complete'
      : failed
      ? 'Render failed'
      : renderMonitorRelative(_renderMonitorLastUpdateAt);
  }
  const pill = qs('job_stage_pill');
  if (pill) pill.dataset.state = monitorState;

  // P0-A: alive signal — set data-alive-state only; renderBottomActiveQueue owns text/hidden
  const etaAliveEl = qs('rc_eta');
  if (etaAliveEl) {
    if (running) {
      const secsSince = _renderMonitorLastProgressAt ? Math.floor((now - _renderMonitorLastProgressAt) / 1000) : 0;
      etaAliveEl.dataset.aliveState = stalled ? 'stalled' : secsSince >= 10 ? 'slow' : 'ok';
    } else {
      delete etaAliveEl.dataset.aliveState;
    }
  }
}
function friendlyJobMessage(job){
  const stage = normalizeRenderStage(job?.stage, job?.status);
  const status = normalizeRenderStatus(job?.status, stage);
  if (isPartialRenderStatus(status)) return 'Completed with errors.';
  if (status === 'completed' || status === 'done' || status === 'complete') return 'Render complete.';
  if (status === 'failed') return friendlyRenderError(job?.message || '', 'Something went wrong during rendering');
  if (status === 'pending') return 'Waiting to start.';
  return stageLabel(stage);
}

function friendlyRenderError(detail, fallback = 'Render could not start') {
  const raw = String(detail || '').trim();
  const low = raw.toLowerCase();
  if (!raw) return fallback;
  if (low.includes('session') && (low.includes('expired') || low.includes('not found') || low.includes('re-open'))) {
    return 'Render could not start';
  }
  if (low.includes('youtube') || low.includes('download') || low.includes('source') || low.includes('video')) {
    return 'Video could not be processed';
  }
  if (low.includes('render') || low.includes('ffmpeg') || low.includes('subtitle') || low.includes('scene')) {
    return 'Something went wrong during rendering';
  }
  return fallback;
}

function getRenderMonitorSourceText(job) {
  const sourceText = getRenderWorkspaceSourceText(job);
  return sourceText && sourceText !== 'No source selected' ? sourceText : 'Source unavailable';
}
function renderPendingClipsMessage(job) {
  const stage = normalizeRenderStage(job?.stage, job?.status);
  const status = normalizeRenderStatus(job?.status, stage);
  if (!isTerminalRenderStatus(status)) {
    if (stage === 'scene_detection') return 'Analyzing video and selecting clips...';
    if (stage === 'segment_building') return 'Preparing clips for rendering...';
    if (stage === 'transcribing_full') return 'Generating subtitles...';
    return 'Clips will appear here when rendering starts';
  }
  return 'Clips will appear here when rendering starts';
}
function updateRenderProgressVisual(job) {
  const stage = normalizeRenderStage(job?.stage, job?.status);
  const status = normalizeRenderStatus(job?.status, stage);
  const staticMs = _renderMonitorLastProgressAt ? (Date.now() - _renderMonitorLastProgressAt) : 0;
  const earlyStage = !['rendering', 'rendering_parallel'].includes(stage);
  const isWaitingActive = !!currentJobId && !isTerminalRenderStatus(status) && earlyStage && staticMs > 8000;
  ['job_bar', 'render_active_bar'].forEach((id) => {
    const el = qs(id);
    if (el) el.classList.toggle('isWaitingActive', isWaitingActive);
  });
}
function getCompletedClipCount(summary, parts){
  const items = Array.isArray(parts) ? parts : [];
  const completedFromSummary = Number(summary?.completed_parts);
  const totalFromSummary = Number(summary?.total_parts);
  if (Number.isFinite(completedFromSummary) && completedFromSummary > 0) return completedFromSummary;
  const doneParts = items.filter((p) => String(p?.status || '').toLowerCase() === 'done').length;
  if (doneParts > 0) return doneParts;
  if (Number.isFinite(totalFromSummary) && totalFromSummary > 0) return totalFromSummary;
  return items.length || 0;
}
function partStatusLabel(status){
  const s = (status || '').toLowerCase();
  const map = {
    queued: 'Waiting',
    waiting: 'Waiting',
    cutting: 'Cutting clip',
    transcribing: 'Generating subtitles',
    rendering: 'Rendering video',
    completed: 'Completed',
    done: 'Completed',
    error: 'Failed',
    failed: 'Failed'
  };
  return map[s] || s;
}
function setActionState(job){
  const stage = normalizeRenderStage(job.stage, job.status);
  const status = normalizeRenderStatus(job.status, stage);
  const running = !isTerminalRenderStatus(status);
  if (running && !activeJobStartedAt) activeJobStartedAt = Date.now();
  if (!running && !activeJobStartedAt) activeJobStartedAt = Date.now();
  const elapsed = fmtElapsed(Date.now() - (activeJobStartedAt || Date.now()));
  const friendly = friendlyJobMessage(job);
  const backendDetail = String(job.message || '').trim();
  if (qs('action_title'))   qs('action_title').textContent = stageLabel(stage);
  if (qs('action_message')) qs('action_message').textContent = friendly;
  if (qs('action_meta'))    qs('action_meta').textContent = `Running for ${elapsed} | Updated ${new Date().toLocaleTimeString()}${backendDetail ? ` | Detail: ${backendDetail}` : ''}`;
  // propagate status/stage as data attributes for CSS visual state
  const _stEl = qs('action_state');
  if (_stEl) { _stEl.textContent = status || 'running'; _stEl.dataset.status = status || 'running'; }
  const _pill = qs('job_stage_pill');
  if (_pill) {
    if (_pill.dataset.stage && _pill.dataset.stage !== stage) {
      _pill.classList.remove('stageChanged');
      void _pill.offsetWidth;
      _pill.classList.add('stageChanged');
    }
    _pill.dataset.stage = stage;
  }
}

function setRenderFlowState(activeStep, subtitle, overrides = {}) {
  // flow bar removed — no-op kept for call-site compatibility
}

function updateRenderFlowByJob(job, summary, parts = []) {
  // flow bar removed — no-op kept for call-site compatibility
}

function buildCompletionHandoff(summary, parts, job) {
  const _lang = (typeof getRenderUiLanguage === 'function') ? getRenderUiLanguage() : 'en';
  const _dict = (window.RENDER_I18N && window.RENDER_I18N[_lang]) || (window.RENDER_I18N && window.RENDER_I18N.en) || {};
  const _t = (key, fallback) => _dict[key] || fallback;
  const items = Array.isArray(parts) ? parts : [];
  const failed = Number(summary?.failed_parts ?? items.filter((p) => String(p?.status || '').toLowerCase() === 'failed').length) || 0;
  const total = Number(summary?.total_parts ?? items.length) || 0;
  const summaryCompleted = Number(summary?.completed_parts);
  const doneParts = items.filter((p) => String(p?.status || '').toLowerCase() === 'done').length;
  const completed = Number.isFinite(summaryCompleted)
    ? summaryCompleted
    : (doneParts || Math.max(0, total - failed));
  const totalLabel = total || (completed + failed);
  const outputLabel = getRenderWorkspaceOutputLabel(job);
  const status = normalizeRenderStatus(job?.status, job?.stage);
  const hasFailure = status === 'failed' || status === 'interrupted';
  const main = failed > 0
    ? `${_t('render_complete', 'Render complete')} - ${completed} clips completed, ${failed} ${_t('failed', 'failed')}`
    : `✓ ${_t('render_complete', 'Render complete')} - ${completed} clips ready`;
  let voiceSummary = '';
  try {
    const raw = job?.result_json;
    const result = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
    const vs = String(result?.voice_summary || '').trim();
    if (vs) voiceSummary = `${_t('voice', 'Voice')}: ${_t(vs, vs)}`;
    const sts = String(result?.subtitle_translate_summary || '').trim();
    if (sts && sts !== 'not used') voiceSummary += (voiceSummary ? ' · ' : '') + `${_t('subtitle_translation', 'Subtitle translation')}: ${_t(sts, sts)}`;
  } catch (_) {}
  const detailParts = [];
  if (totalLabel > 0) detailParts.push(`${totalLabel} total clips`);
  detailParts.push(failed > 0 ? 'Review clips below' : 'Check output folder or review clips below');
  detailParts.push(outputLabel);
  if (voiceSummary) detailParts.push(voiceSummary);
  return { main, detail: detailParts.join(' · ') };
}

function showRenderCompletionBar(text, detail) {
  const bar = qs('render_completion_bar');
  if (!bar) return;
  const msg = qs('render_completion_msg');
  if (msg && text) msg.textContent = text;
  const summary = qs('render_completion_summary');
  if (summary) summary.textContent = detail || '';

  const status = String(_renderMonitorLastJob?.status || '').toLowerCase();
  const isPartial = status === 'completed_with_errors';
  bar.dataset.state = isPartial ? 'warning' : 'success';

  const iconEl = qs('rcb_icon');
  if (iconEl) iconEl.textContent = isPartial ? '⚠' : '✓';

  bar.classList.remove('hiddenView');
  if (typeof updateWfStrip === 'function') updateWfStrip();
}

function hideRenderCompletionBar() {
  const bar = qs('render_completion_bar');
  if (!bar) return;
  bar.classList.add('hiddenView');
  delete bar.dataset.state;
  const summary = qs('render_completion_summary');
  if (summary) summary.textContent = '';
  if (typeof updateWfStrip === 'function') updateWfStrip();
}

function reviewClipsFromBanner() {
  const panel = qs('render_output_panel');
  if (!panel || panel.classList.contains('hiddenView')) {
    if (typeof showToast === 'function') showToast('Clips are not ready yet.', 'info');
    return;
  }
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function deactivateRenderUiForEditorOpen() {
  // Prevent stale "Render complete" handoff UI from leaking into a new editor session.
  hideRenderCompletionBar();

  // Stop any in-flight render progress channels.
  if (typeof _stopJobWs === 'function') _stopJobWs();
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

  // Mark old terminal render jobs inactive for UI purposes while editor is open.
  const monitorStatus = String(_renderMonitorLastJob?.status || lastStatus || '').toLowerCase();
  if (!currentJobId || !monitorStatus || isTerminalRenderStatus(monitorStatus)) {
    currentJobId = null;
  }

  // Clear stale monitor/stall hint state.
  resetRenderMonitorHeartbeat();
  updateRenderMonitorHeartbeat(null, null, []);
  updateRenderMainState(null, null, []);
  renderParts([]);

  // Ensure the main action button returns to editor-open state.
  setRenderActionBusy(false);
}

function backToEditorFromCompletion() {
  const sessionId = (_ev && _ev.sessionId) || null;
  if (!sessionId) {
    addEvent('Editor session is no longer available. Please load the source again.', 'render');
    if (typeof showToast === 'function') showToast('Editor session is no longer available. Please load the source again.', 'error');
    return;
  }
  const pd = {
    session_id: sessionId,
    duration: (_ev && _ev.duration) || 0,
    title: String(qs('evSourceName')?.textContent || (_ev && _ev.sourceUrl) || ''),
    export_dir: (_ev && _ev.exportDir) || null,
  };
  const urlOrPath = (_ev && _ev.sourceUrl) || '';
  const pendingPayload = (_ev && _ev.pendingPayload) || null;
  hideRenderCompletionBar();
  // Restore editor with the existing session — no re-download needed.
  // currentJobId is intentionally left as-is (completed job, no active polling).
  openEditorView_withSession(pd, urlOrPath, pendingPayload);
}

function getCurrentJobPayload(job) {
  try {
    const raw = job?.payload_json;
    if (!raw) return {};
    return typeof raw === 'string' ? JSON.parse(raw) : raw;
  } catch (_) {
    return {};
  }
}

function getRenderWorkspaceSourceText(job) {
  const payload = getCurrentJobPayload(job);
  const evSource = typeof _ev !== 'undefined' ? String(_ev.sourceUrl || '').trim() : '';
  const rawSource = String(
    payload.source_video_path ||
    payload.youtube_url ||
    evSource ||
    ''
  ).trim();
  if (!rawSource) return 'No source selected';
  const sourceMode = String(payload.source_mode || (payload.youtube_url ? 'youtube' : (rawSource.startsWith('http') ? 'youtube' : 'local'))).toLowerCase();
  if (sourceMode === 'local') {
    return rawSource.replace(/\\/g, '/').split('/').filter(Boolean).pop() || rawSource;
  }
  if (typeof _ev !== 'undefined' && String(_ev.sourceUrl || '').trim() && String(_ev.sourceUrl).trim() !== rawSource) {
    return `${String(_ev.sourceUrl).trim()} · ${rawSource}`;
  }
  return rawSource;
}

function getRenderWorkspaceOutputText(job) {
  const payload = getCurrentJobPayload(job);
  const outputDir = getCurrentJobOutputDir(job);
  if (!outputDir) return 'Output folder not set';
  const outputMode = String(payload.output_mode || '').toLowerCase();
  if (outputMode === 'manual') return `Manual output folder · ${outputDir}`;
  if (outputMode === 'channel') {
    const channel = String(payload.channel_code || '').trim();
    return channel ? `Channel ${channel} output folder · ${outputDir}` : `Channel output folder · ${outputDir}`;
  }
  return `Output folder · ${outputDir}`;
}

function getRenderWorkspaceOutputLabel(job) {
  const payload = getCurrentJobPayload(job);
  const outputDir = getCurrentJobOutputDir(job);
  if (!outputDir) return 'Output folder path unavailable';
  const outputMode = String(payload.output_mode || '').toLowerCase();
  if (outputMode === 'manual') return 'Saved to manual output folder';
  if (outputMode === 'channel') return 'Saved to channel output folder';
  return 'Saved to output folder';
}

function rcPartVisualState(status) {
  const st = String(status || '').toLowerCase();
  if (['failed', 'error', 'interrupted'].includes(st)) return 'isFailed';
  if (['completed', 'done'].includes(st)) return 'isCompleted';
  if (['processing', 'running', 'rendering', 'transcribing', 'cutting', 'in_progress'].includes(st)) return 'isRendering';
  return 'isWaiting';
}

function renderBottomControlCenter(job, summary, parts = []) {
  const items = Array.isArray(parts) ? parts : [];
  const s = summary || computeProgressSummary(items || []);
  const status = normalizeRenderStatus(job?.status, job?.stage);
  const terminal = isTerminalRenderStatus(status);
  const done = getCompletedClipCount(s, items);
  const total = Number(s?.total_parts || items.length || 0);
  const active = Number(s?.processing_parts || 0);
  const failed = Number(s?.failed_parts || 0);
  const pct = deriveRenderProgress(job, s, items);
  const activeParts = Array.isArray(s?.active_parts) ? s.active_parts : [];
  const activeText = activeParts.length === 1
    ? `Clip ${Number(activeParts[0]?.part_no || 0)}`
    : activeParts.length > 1
    ? `${activeParts.length} clips active`
    : 'No active clip';
  const latest = String(job?.message || qs('rc_latest')?.textContent || qs('abp_summary_latest')?.textContent || 'Waiting for render...').trim();
  const statusText = !job ? 'Ready' : status === 'failed' ? 'Failed' : terminal ? 'Completed' : 'Rendering';
  const stageText = job ? renderUxStageLabel(job, s, items) : 'Idle';
  const waitingCount = Math.max(0, total - done - active - failed);
  const queueSummary = total > 0
    ? `${done} of ${total} done${active > 0 ? ` · ${active} active` : ''}${waitingCount > 0 ? ` · ${waitingCount} waiting` : ''}${failed > 0 ? ` · ${failed} failed` : ''}`
    : 'Waiting for render...';

  if (qs('rc_status')) {
    qs('rc_status').textContent = statusText;
    qs('rc_status').dataset.state = !job ? 'ready' : (status === 'failed' ? 'failed' : terminal ? 'completed' : 'running');
  }
  if (qs('rc_progress')) qs('rc_progress').textContent = `${pct}%`;
  if (qs('rc_stage')) qs('rc_stage').textContent = `Stage: ${stageText}`;
  if (qs('rc_parts')) qs('rc_parts').textContent = `Clips: ${done}/${total || 0}${failed > 0 ? ` · ${failed} failed` : ''}`;
  if (qs('rc_active')) qs('rc_active').textContent = activeText;
  if (qs('rc_latest')) qs('rc_latest').textContent = latest || 'Waiting for render...';
  if (qs('rc_queue_summary')) qs('rc_queue_summary').textContent = queueSummary;
  if (qs('rc_retry_btn')) qs('rc_retry_btn').classList.toggle('hiddenView', !(status === 'failed' || status === 'interrupted') || !currentJobId);
  if (qs('rc_open_output_btn')) qs('rc_open_output_btn').disabled = !String(qs('abp_output_text')?.textContent || '').trim() || /not set|no output/i.test(String(qs('abp_output_text')?.textContent || ''));

  const cardWrap = qs('rc_part_cards');
  if (!cardWrap) return;
  if (!items.length) {
    cardWrap.innerHTML = `<div class="emptyState">${esc(renderPendingClipsMessage(job || _renderMonitorLastJob))}</div>`;
    return;
  }
  const ordered = [...items].sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0));
  cardWrap.innerHTML = ordered.map((p, idx) => {
    const st = String(p?.status || '').toLowerCase();
    const cls = rcPartVisualState(st);
    const progress = Math.max(0, Math.min(100, Math.round(Number(p?.progress_percent || 0))));
    const partNo = Number(p.part_no || idx + 1);
    const partTitle = p.part_name ? esc(p.part_name) : `Clip ${partNo}`;
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const duration = Math.max(0, endSec - startSec);
    const meta = p.output_file
      ? `Output ready · ${esc(String(p.output_file).split(/[\\\\/]/).pop())}`
      : duration > 0
      ? `${duration.toFixed(1)}s · ${startSec.toFixed(1)}s–${endSec.toFixed(1)}s`
      : '';
    const rawMsg = String(p?.message || '').trim();
    const isDebugMsg = !rawMsg || /_ms=|\bpart_render\b|\w+=\w+/.test(rawMsg);
    const message = isDebugMsg
      ? (cls === 'isWaiting' ? 'Waiting in queue' : cls === 'isCompleted' ? 'Ready in output folder' : cls === 'isFailed' ? 'Needs review' : 'Rendering…')
      : rawMsg;
    return `<article class="rcPartCard ${cls}" data-part-status="${esc(st || 'queued')}">
      <div class="rcPartTop">
        <div class="rcPartTitle">Clip ${partNo} · ${partTitle}</div>
        <div class="rcPartStatus">${esc(partStatusLabel(st))}</div>
      </div>
      <div class="rcPartMessage">${esc(message)}</div>
      <div class="rcMiniProgress" style="--progress:${progress}%"><span></span></div>
      <div class="rcPartMeta">${progress}%${meta ? ` · ${meta}` : ''}</div>
    </article>`;
  }).join('');
}

function clampRcProgress(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function normalizeRcPartState(part) {
  const raw = String(part?.status || '').toLowerCase();
  const stage = String(part?.stage || '').toLowerCase();
  if (['completed', 'done', 'success', 'complete'].includes(raw)) return 'completed';
  if (['failed', 'error', 'interrupted'].includes(raw)) return 'failed';
  if (
    ['processing', 'running', 'rendering', 'transcribing', 'cutting', 'in_progress'].includes(raw) ||
    ['processing', 'running', 'rendering', 'transcribing', 'cutting', 'in_progress'].includes(stage)
  ) return 'rendering';
  return 'waiting';
}

function rcStateLabel(state) {
  if (state === 'completed') return 'Done';
  if (state === 'failed') return 'Failed';
  if (state === 'rendering') return 'Rendering';
  return 'Queued';
}

function rcStateIcon(state) {
  if (state === 'completed') return '✓';
  if (state === 'failed') return '✕';
  if (state === 'rendering') return '▶';
  return '○';
}

function rcCap(s) {
  const text = String(s || '');
  return text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}` : '';
}

function rcPartStageText(part) {
  const stage = String(part?.stage || part?.status || '').toLowerCase();
  return stage ? stageLabelPlain(stage) : 'Waiting';
}

function rcPartMessage(part, fallback = '') {
  return String(part?.message || part?.detail || part?.last_message || part?.note || fallback || '').trim();
}

function _rcInitScrollGuard(container) {
  if (container._sgInit) return;
  container._sgInit = true;
  container.addEventListener('scroll', () => {
    _rcUserIsScrolling = true;
    clearTimeout(_rcUserScrollTimerId);
    _rcUserScrollTimerId = setTimeout(() => { _rcUserIsScrolling = false; }, 1500);
  }, { passive: true });
}

function _rcAutoScrollActive(container, activePartNo) {
  _rcInitScrollGuard(container);
  if (activePartNo === _rcLastActivePartNo) return;
  _rcLastActivePartNo = activePartNo;
  if (activePartNo === -1) return;
  if (_rcUserIsScrolling) return;
  clearTimeout(_rcScrollDebounceId);
  _rcScrollDebounceId = setTimeout(() => {
    if (_rcUserIsScrolling) return;
    const el = container.querySelector('[data-active="1"]');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 120);
}

// ── Output Ranking helpers ────────────────────────────────────────────────────
function _rankMap(job) {
  const map = new Map();
  try {
    const result = parseRenderResult(job);
    const ranking = result?.output_ranking;
    if (!Array.isArray(ranking)) return map;
    ranking.forEach(r => {
      if (r?.part_no != null) {
        map.set(Number(r.part_no), {
          rank:           Number(r.output_rank || 0),
          score:          Number(r.output_score ?? r.output_rank_score ?? 0),
          isBest:         !!(r.is_best_clip ?? r.is_best_output),
          reason:         String(r.ranking_reason || r.reasons || '').trim(),
          confidenceTier: String(r.confidence_tier || '').trim(),
          dominantSignal: String(r.dominant_signal || '').trim(),
          variantType:    String(r.variant_type || '').trim(),
          targetPlatform: String(r.target_platform || '').trim(),
          coverOffset:    Number(r.cover_frame_offset || 0),
          coverFile:      String(r.cover_file || '').trim(),
        });
      }
    });
  } catch (_) {}
  return map;
}

function parseRenderResult(job) {
  try {
    const raw = job?.result_json;
    return raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
  } catch (_) {
    return {};
  }
}

function renderFailureDetails(job, summary = null) {
  const result = parseRenderResult(job);
  const details = result.failed_parts_detail || result.failed_part_details || job?.failed_parts_detail || [];
  const warning = result.ranking_warning || job?.ranking_warning || '';
  const count = Number(result.failed_parts ?? job?.failed_parts ?? summary?.failed_parts ?? 0);
  return {
    count,
    details: Array.isArray(details) ? details : (details ? [details] : []),
    warning: String(warning || '').trim(),
  };
}

function normalizeOutputPart(raw, idx = 0) {
  const p = raw || {};
  const outputFile = p.output_file || p.output_path || p.file_path || p.path || '';
  const status = String(p.status || (outputFile ? 'done' : 'skipped')).toLowerCase();
  return {
    ...p,
    part_no: Number(p.part_no || p.part || p.clip_no || idx + 1),
    part_name: p.part_name || p.name || p.title || '',
    status: status === 'completed' || status === 'complete' ? 'done' : status,
    output_file: outputFile,
    start_sec: Number(p.start_sec || p.start || 0),
    end_sec: Number(p.end_sec || p.end || 0),
  };
}

function collectRenderOutputItems(job, parts = []) {
  const fromParts = Array.isArray(parts) ? parts : [];
  const result = parseRenderResult(job);
  const outputs = Array.isArray(result.outputs) ? result.outputs : [];
  const merged = new Map();
  fromParts.forEach((p, idx) => merged.set(Number(p?.part_no || idx + 1), normalizeOutputPart(p, idx)));
  outputs.forEach((p, idx) => {
    const item = normalizeOutputPart(p, idx);
    merged.set(Number(item.part_no || idx + 1), { ...(merged.get(Number(item.part_no)) || {}), ...item });
  });
  return [...merged.values()];
}

// ── Market Viral score helpers ────────────────────────────────────────────────
function _mvSegmentMap(job) {
  const map = new Map();
  try {
    const raw = job?.result_json;
    const result = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
    const segs = result?.segments;
    if (!Array.isArray(segs)) return map;
    segs.forEach((seg, i) => {
      const score = seg?.mv_viral_score;
      if (score == null) return;
      map.set(i + 1, {
        score:    Number(score),
        tier:     String(seg.mv_viral_tier   || 'weak'),
        market:   String(seg.mv_viral_market || 'US'),
        reasons:  Array.isArray(seg.mv_viral_reasons) ? seg.mv_viral_reasons : [],
        combined: seg?.combined_score  != null ? Number(seg.combined_score)  : null,
        weights:  seg?.combined_weights ?? null,
      });
    });
  } catch (_) {}
  return map;
}

function _mvTop3Set(mvMap) {
  if (!mvMap.size) return new Set();
  const sorted = [...mvMap.entries()].sort((a, b) => b[1].score - a[1].score);
  return new Set(sorted.slice(0, 3).map(([k]) => k));
}

function _renderMvSummary(job, mvMap) {
  const el = qs('mvRenderSummary');
  if (!el) return;
  if (!mvMap || !mvMap.size) {
    el.innerHTML = '';
    el.hidden = true;
    return;
  }
  const sorted = [...mvMap.entries()].sort((a, b) => b[1].score - a[1].score);
  const best   = sorted[0][1];
  const top3   = sorted.slice(0, 3);
  const market = best.market || 'US';

  // Deduplicate reasons across top-3 clips, ordered by frequency
  const freq = new Map();
  top3.forEach(([, v]) => {
    (v.reasons || []).forEach(r => { if (r) freq.set(r, (freq.get(r) || 0) + 1); });
  });
  const reasons = [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([r]) => r);

  const TIER_LABEL = { hot: 'Hot', warm: 'Warm', normal: 'Normal', weak: 'Weak' };
  const tier = best.tier || 'weak';
  const reasonsHtml = reasons.length
    ? `<div class="mvSumReasons">${reasons.map(r => `<span class="mvSumReason">${esc(r)}</span>`).join('')}</div>`
    : '';

  el.hidden = false;
  el.innerHTML =
    `<div class="mvSumTitle">&#127758; Market Viral Summary</div>` +
    `<div class="mvSumRow">` +
      `<div class="mvSumCell"><div class="mvSumLabel">Market</div><div class="mvSumValue">${esc(market)}</div></div>` +
      `<div class="mvSumCell"><div class="mvSumLabel">Best Score</div><div class="mvSumValue">${best.score} <span class="mvSumTierBadge" data-tier="${esc(tier)}">${esc(TIER_LABEL[tier] || tier)}</span></div></div>` +
      `<div class="mvSumCell"><div class="mvSumLabel">Top Clips</div><div class="mvSumValue">${top3.length} selected</div></div>` +
    `</div>` +
    reasonsHtml;
}

function rcToggleClip(el) {
  const path = el.dataset.path;
  if (!path) return;
  if (el.checked) _selectedClipPaths.add(path);
  else _selectedClipPaths.delete(path);
  el.closest('.renderClipItem, .rcQueueRow, .clipCard')?.classList.toggle('isSelected', el.checked);
}

function useTopClips() {
  const paths = [..._selectedClipPaths];
  if (!paths.length) {
    if (typeof showToast === 'function') showToast('Select at least one clip', 'info');
    return;
  }
  window.topClipPaths = paths;
  console.log('[Market Viral] Selected clip paths:', paths);
  if (typeof showToast === 'function') {
    showToast(`${paths.length} clip${paths.length === 1 ? '' : 's'} selected`, 'success');
  }
}

// ── Benchmark helpers ────────────────────────────────────────────────────────

function _parseSqliteUtc(str) {
  if (!str) return 0;
  const s = String(str).trim();
  const cleaned = s.replace(' ', 'T') + (s.includes('+') || s.includes('Z') ? '' : 'Z');
  const ms = Date.parse(cleaned);
  return isNaN(ms) ? 0 : ms;
}

function formatBenchDuration(ms) {
  if (ms == null || isNaN(ms) || ms < 0) return '—';
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${(ms / 1000).toFixed(1)}s`;
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s}s`;
}

function formatBenchBytes(bytes) {
  if (bytes == null || isNaN(bytes) || bytes <= 0) return '—';
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)} GB`;
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function _parseBenchmarkLogs(lines) {
  const result = { sceneDetectionMs: null, sceneCount: null, transcriptionMs: null, transcriptionModel: null, outputSizes: [] };
  for (const line of lines) {
    if (!line) continue;
    try {
      const entry = JSON.parse(line);
      const event = entry?.event || '';
      const ctx = entry?.context || {};
      if (event === 'render.scene.detect.success') {
        if (ctx.duration_ms != null) result.sceneDetectionMs = Number(ctx.duration_ms);
        if (ctx.scene_count != null) result.sceneCount = Number(ctx.scene_count);
      } else if (event === 'subtitle_transcription_completed') {
        if (ctx.elapsed_ms != null) result.transcriptionMs = Number(ctx.elapsed_ms);
        if (ctx.whisper_model) result.transcriptionModel = String(ctx.whisper_model);
      } else if (event === 'output_validation_passed') {
        if (ctx.size_bytes != null && Number(ctx.size_bytes) > 0) result.outputSizes.push(Number(ctx.size_bytes));
      }
      continue;
    } catch (_) {}
    const m1 = line.match(/scene detection done:\s*(\d+)\s*scenes?\s+in\s+(\d+)ms/i);
    if (m1) { result.sceneCount = Number(m1[1]); result.sceneDetectionMs = Number(m1[2]); }
    const m2 = line.match(/subtitle_transcription_completed\s+model=(\S+)\s+elapsed_ms=(\d+)/i);
    if (m2) { result.transcriptionModel = m2[1]; result.transcriptionMs = Number(m2[2]); }
  }
  return result;
}

function _updateBenchmark(job, parts) {
  const jobId = String(job?.id || job?.job_id || currentJobId || '');
  const ranking = _rankMap(job);
  if (!jobId) return;
  if (jobId !== _rcBenchmark.jobId) {
    _rcBenchmark = { jobId, logsLoaded: false, totalElapsedMs: 0, sceneDetectionMs: null, sceneCount: null, transcriptionMs: null, transcriptionModel: null, transcriptionLiveSec: null, totalParts: 0, completedParts: 0, failedParts: 0, failedStage: '', outputSizes: [] };
  }
  const items = Array.isArray(parts) ? parts : [];
  const status = String(job?.status || '').toLowerCase();
  const isTerminal = isTerminalRenderStatus(status);
  const isFailed = status === 'failed' || status === 'interrupted';

  const startMs = _parseSqliteUtc(job?.created_at);
  const endMs = isTerminal ? _parseSqliteUtc(job?.updated_at) : Date.now();
  _rcBenchmark.totalElapsedMs = (startMs > 0 && endMs > startMs) ? (endMs - startMs) : 0;
  _rcBenchmark.totalParts = items.length || 0;
  _rcBenchmark.completedParts = items.filter((p) => String(p?.status || '').toLowerCase() === 'done').length;
  _rcBenchmark.failedParts = items.filter((p) => String(p?.status || '').toLowerCase() === 'failed').length;
  if (isFailed && job?.stage) _rcBenchmark.failedStage = String(job.stage);

  if (job?.message) {
    const msg = String(job.message);
    const m = msg.match(/transcribing[….\s]*\((\d+)s\)/i) || msg.match(/elapsed=(\d+)s/i);
    if (m) _rcBenchmark.transcriptionLiveSec = Number(m[1]);
  }

  if (isTerminal && !_rcBenchmark.logsLoaded) {
    _rcBenchmark.logsLoaded = true;
    fetch(`/api/jobs/${jobId}/logs?lines=400`)
      .then((r) => r.json())
      .then((data) => {
        const lines = Array.isArray(data?.items) ? data.items : [];
        const parsed = _parseBenchmarkLogs(lines);
        if (parsed.sceneDetectionMs != null) _rcBenchmark.sceneDetectionMs = parsed.sceneDetectionMs;
        if (parsed.sceneCount != null) _rcBenchmark.sceneCount = parsed.sceneCount;
        if (parsed.transcriptionMs != null) _rcBenchmark.transcriptionMs = parsed.transcriptionMs;
        if (parsed.transcriptionModel) _rcBenchmark.transcriptionModel = parsed.transcriptionModel;
        if (parsed.outputSizes.length) _rcBenchmark.outputSizes = parsed.outputSizes;
        renderBenchmarkPanel(_renderMonitorLastJob, _renderMonitorLastParts);
      })
      .catch(() => {});
  }
}

function _benchBottleneck(b, status) {
  const isFailed = status === 'failed' || status === 'interrupted';
  if (isFailed) {
    const stageName = b.failedStage ? stageLabel(b.failedStage) : '';
    return stageName ? `Render failed at: ${stageName}` : 'Render did not complete';
  }
  if (b.failedParts > 0) return `${b.failedParts} part${b.failedParts > 1 ? 's' : ''} failed validation`;
  const candidates = [
    { name: 'Transcription', ms: b.transcriptionMs },
    { name: 'Scene detection', ms: b.sceneDetectionMs },
  ].filter((c) => c.ms != null && c.ms > 0);
  if (candidates.length && b.totalElapsedMs > 0) {
    candidates.sort((a, c) => c.ms - a.ms);
    const top = candidates[0];
    if (top.ms / b.totalElapsedMs > 0.25) return `${top.name} dominated this job`;
  }
  if (b.completedParts > 0 && b.failedParts === 0 && b.completedParts === b.totalParts) {
    return `All ${b.completedParts} part${b.completedParts > 1 ? 's' : ''} validated successfully`;
  }
  return '';
}

function renderBenchmarkPanel(job, parts) {
  const panel = qs('rc_benchmark_panel');
  if (!panel) return;
  if (!job) { panel.classList.add('hiddenView'); return; }

  const status = String(job?.status || '').toLowerCase();
  const isTerminal = isTerminalRenderStatus(status);

  _updateBenchmark(job, parts);
  const b = _rcBenchmark;
  const grid = qs('rc_benchmark_grid');
  const insightEl = qs('rc_benchmark_insight');
  const badge = qs('rc_benchmark_badge');

  if (badge) { badge.textContent = isTerminal ? 'Done' : 'Live'; badge.dataset.state = isTerminal ? 'done' : 'live'; }

  const rows = [];
  if (b.totalElapsedMs > 0) rows.push({ label: 'Total time', value: formatBenchDuration(b.totalElapsedMs) });

  if (b.totalParts > 0) {
    const failBit = b.failedParts > 0 ? ` · ${b.failedParts} failed` : '';
    rows.push({ label: 'Clips', value: `${b.completedParts} / ${b.totalParts}${failBit}` });
  }

  const _bmRkMap = _rankMap(job);
  if (_bmRkMap.size > 0) {
    const _bmBestRk = [..._bmRkMap.values()].find(r => r.isBest);
    if (_bmBestRk) {
      const _bmBestPart = [..._bmRkMap.entries()].find(([, r]) => r.isBest)?.[0];
      rows.push({ label: 'Best Output', value: `part_${String(_bmBestPart).padStart(3, '0')} · ${_bmBestRk.score}` });
    }
  }

  try {
    const _bmRaw = job?.result_json;
    const _bmResult = _bmRaw ? (typeof _bmRaw === 'string' ? JSON.parse(_bmRaw) : _bmRaw) : {};
    const _bmExports = _bmResult?.best_exports;
    if (Array.isArray(_bmExports) && _bmExports.length > 0) {
      const _bmBestDir = String(_bmExports[0]?.best_file || '').replace(/\\/g, '/').split('/').slice(0, -1).join('/');
      const _bmDirShort = _bmBestDir ? _bmBestDir.split('/').slice(-2).join('/') : '';
      rows.push({ label: 'Best Exports', value: `${_bmExports.length} file${_bmExports.length !== 1 ? 's' : ''}${_bmDirShort ? ` · …/${_bmDirShort}` : ''}` });
    }
  } catch (_) {}

  if (grid) {
    const sig = rows.map((r) => r.label + '=' + r.value).join('|');
    if (grid.dataset.sig !== sig) {
      grid.dataset.sig = sig;
      grid.innerHTML = '';
      rows.forEach(({ label, value }) => {
        const lbl = document.createElement('span');
        lbl.className = 'rcBenchmarkLabel';
        lbl.textContent = label;
        const val = document.createElement('span');
        val.className = 'rcBenchmarkValue';
        val.textContent = value;
        grid.appendChild(lbl);
        grid.appendChild(val);
      });
    }
  }

  const insightText = _benchBottleneck(b, status);
  if (insightEl) {
    if (insightEl.textContent !== insightText) insightEl.textContent = insightText;
    insightEl.classList.toggle('hiddenView', !insightText);
  }

  panel.classList.toggle('hiddenView', rows.length === 0);
}

function _rcPreviewHandleSelectChange() {
  const sel = qs('rc_preview_part_select');
  if (sel) _rcPreviewPartNo = Number(sel.value) || 0;
  updateOutputPreview(_renderMonitorLastJob, _renderMonitorLastParts);
}

function updateOutputPreview(job, parts) {
  const panel = qs('rc_output_preview');
  if (!panel) return;

  const status = String(job?.status || '').toLowerCase();
  const isCompleted = isCompletedRenderStatus(status) || isPartialRenderStatus(status);

  if (!isCompleted) {
    panel.classList.add('hiddenView');
    return;
  }

  const jobId = String(job?.id || job?.job_id || currentJobId || '').trim();
  if (!jobId) { panel.classList.add('hiddenView'); return; }

  const items = Array.isArray(parts) ? parts : [];
  const doneParts = items
    .filter((p) => {
      const st = String(p?.status || '').toLowerCase();
      return (st === 'done' || st === 'completed') && p.output_file;
    })
    .sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0));

  const selectEl = qs('rc_preview_part_select');
  if (jobId !== _rcPreviewJobId) {
    _rcPreviewJobId = jobId;
    _rcPreviewPartNo = doneParts.length ? Number(doneParts[0].part_no) : 0;
    if (selectEl) {
      selectEl.innerHTML = '';
      if (doneParts.length > 1) {
        doneParts.forEach((p) => {
          const opt = document.createElement('option');
          opt.value = String(p.part_no);
          const lbl = p.part_name
            ? `Clip ${p.part_no} · ${String(p.part_name).slice(0, 20)}`
            : `Clip ${p.part_no}`;
          opt.textContent = lbl;
          selectEl.appendChild(opt);
        });
        selectEl.value = String(_rcPreviewPartNo);
        selectEl.classList.remove('hiddenView');
      } else {
        selectEl.classList.add('hiddenView');
      }
    }
  }

  const targetPart = doneParts.find((p) => Number(p.part_no) === _rcPreviewPartNo) || doneParts[0] || null;
  const videoEl = qs('rc_preview_video');
  const filenameEl = qs('rc_preview_filename');
  const pathEl = qs('rc_preview_path');
  const partnoEl = qs('rc_preview_partno');
  const unavailEl = qs('rc_preview_unavailable');

  if (!targetPart) {
    if (videoEl) { videoEl.src = ''; videoEl.classList.add('hiddenView'); }
    if (unavailEl) {
      unavailEl.textContent = 'No previewable output file found. Use Open Output Folder.';
      unavailEl.classList.remove('hiddenView');
    }
    panel.classList.remove('hiddenView');
    return;
  }

  const partNo = Number(targetPart.part_no);
  const previewUrl = `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/media`;
  const outputFile = String(targetPart.output_file || '');
  const fileName = outputFile.replace(/\\/g, '/').split('/').pop() || `clip-${partNo}.mp4`;
  const outDir = outputFile.replace(/\\/g, '/').split('/').slice(0, -1).join('/');

  if (videoEl) {
    if (videoEl.dataset.previewSrc !== previewUrl) {
      videoEl.dataset.previewSrc = previewUrl;
      videoEl.src = previewUrl;
      videoEl.load();
    }
    videoEl.classList.remove('hiddenView');
  }
  if (unavailEl) unavailEl.classList.add('hiddenView');
  if (filenameEl) filenameEl.textContent = fileName;
  if (pathEl) {
    const shortDir = outDir.length > 52 ? '…' + outDir.slice(-49) : outDir;
    pathEl.textContent = shortDir;
    pathEl.title = outputFile;
  }
  if (partnoEl) {
    const startSec = Number(targetPart.start_sec || 0);
    const endSec = Number(targetPart.end_sec || 0);
    const dur = endSec > startSec ? ` · ${(endSec - startSec).toFixed(1)}s` : '';
    partnoEl.textContent = doneParts.length > 1 ? `Part ${partNo}${dur}` : dur.trim();
  }

  panel.classList.remove('hiddenView');
}

const RC_STAGE_STEPS = [
  { key: 'prepare',  label: 'Preparing', stages: ['starting', 'queued', 'downloading'] },
  { key: 'scenes',   label: 'Scenes',    stages: ['scene_detection'] },
  { key: 'segment',  label: 'Segments',  stages: ['segment_building', 'transcribing_full'] },
  { key: 'render',   label: 'Rendering', stages: ['rendering', 'rendering_parallel'] },
  { key: 'finalize', label: 'Finalizing', stages: ['writing_report'] },
  { key: 'done',     label: 'Completed', stages: ['done', 'completed', 'complete'] },
];

function _updateStageTimeline(stage, status) {
  const el = qs('rc_stage_timeline');
  if (!el) return;
  const stageNorm = String(stage || '').toLowerCase().trim();
  const statusNorm = String(status || '').toLowerCase().trim();
  const isDone = isCompletedRenderStatus(statusNorm) || isPartialRenderStatus(statusNorm);
  const isFailed = statusNorm === 'failed' || statusNorm === 'interrupted';

  if (!stage && !isDone && !isFailed) { el.innerHTML = ''; return; }

  let activeIdx = -1;
  for (let i = 0; i < RC_STAGE_STEPS.length; i++) {
    if (RC_STAGE_STEPS[i].stages.includes(stageNorm)) { activeIdx = i; break; }
  }
  if (isDone) activeIdx = RC_STAGE_STEPS.length - 1;

  el.innerHTML = '';
  RC_STAGE_STEPS.forEach((step, i) => {
    const dotState = i < activeIdx
      ? 'done'
      : i === activeIdx
        ? (isFailed ? 'failed' : 'active')
        : 'pending';

    const item = document.createElement('span');
    item.className = 'rcStageItem';

    const dot = document.createElement('span');
    dot.className = 'rcStageDot';
    dot.dataset.state = dotState;
    dot.title = step.label;

    const label = document.createElement('span');
    label.className = 'rcStageLabel';
    label.textContent = step.label;

    item.appendChild(dot);
    item.appendChild(label);
    el.appendChild(item);

    if (i < RC_STAGE_STEPS.length - 1) {
      const arrow = document.createElement('span');
      arrow.className = 'rcStageArrow';
      el.appendChild(arrow);
    }
  });
}

function renderBottomActiveQueue(job, summary, parts = []) {
  const items = Array.isArray(parts) ? parts : [];
  const s = summary || computeProgressSummary(items || []);
  const status = normalizeRenderStatus(job?.status, job?.stage);
  const terminal = isTerminalRenderStatus(status);
  const overallState = !job
    ? 'ready'
    : (status === 'failed' || status === 'interrupted')
    ? 'failed'
    : terminal
    ? 'completed'
    : 'running';
  const total = Number(s?.total_parts || items.length || 0);
  const completed = getCompletedClipCount(s, items);
  const renderingParts = items.filter((part) => normalizeRcPartState(part) === 'rendering');
  const failed = Number(s?.failed_parts || items.filter((part) => normalizeRcPartState(part) === 'failed').length || 0);
  const waiting = Math.max(0, total - completed - renderingParts.length - failed);
  const pct = clampRcProgress(deriveRenderProgress(job, s, items));
  const stageText = job ? stageLabel(job?.stage || 'queued') : 'Idle';
  const latest = String(job?.message || qs('rc_latest')?.textContent || qs('abp_summary_latest')?.textContent || 'Waiting for render...').trim() || 'Waiting for render...';
  const activePart = renderingParts.find((part) => normalizeRcPartState(part) === 'rendering') || null;
  const activePartNo = Number(activePart?.part_no || 0);
  const activeText = activePart
    ? `Active: Clip ${activePartNo || '?'}`
    : overallState === 'completed'
    ? 'Active: None'
    : overallState === 'failed'
    ? 'Active: Failed'
    : 'Active: Waiting';
  const queueSummary = parts.length > 0
    ? `${completed} of ${parts.length} done${renderingParts.length > 0 ? ` · ${renderingParts.length} active` : ''}${waiting > 0 ? ` · ${waiting} waiting` : ''}${failed > 0 ? ` · ${failed} failed` : ''}`
    : (job ? stageText : '');
  const statusLabel = overallState === 'failed'
    ? 'Failed'
    : overallState === 'completed'
    ? (status === 'completed_with_errors' ? 'Completed with Errors' : 'Completed')
    : overallState === 'running'
    ? stageText
    : 'Ready';

  // Header primary: "Ready" | "Rendering · 15%" | "Completed" | "Failed · 15%"
  const headerPrimary = overallState === 'ready' ? 'Ready'
    : overallState === 'completed' ? (status === 'completed_with_errors' ? `Completed with Errors · ${pct}%` : 'Completed')
    : overallState === 'failed' ? `Failed · ${pct}%`
    : `${stageText} · ${pct}%`;
  // Header secondary: clip summary when parts exist, else stage name
  const headerSecondary = overallState === 'ready' ? ''
    : total > 0 ? renderMonitorClipSummary(s, items)
    : stageText !== 'Idle' ? stageText : '';

  if (qs('rc_status')) {
    qs('rc_status').textContent = headerPrimary;
    qs('rc_status').dataset.state = overallState;
  }
  if (qs('rc_progress')) qs('rc_progress').textContent = '';
  if (qs('rc_stage')) qs('rc_stage').textContent = headerSecondary;
  if (qs('rc_parts')) qs('rc_parts').textContent = '';
  if (qs('rc_active')) qs('rc_active').textContent = '';
  if (qs('rc_queue_summary')) qs('rc_queue_summary').textContent = queueSummary;

  const badge = qs('rc_active_badge');
  const activeCard = qs('rc_active_card');
  const activeTitle = qs('rc_active_title');
  const activeSubtitle = qs('rc_active_subtitle');
  const activePercent = qs('rc_active_percent');
  const activeBar = qs('rc_active_bar');
  const activeStage = qs('rc_active_stage');
  const activeMessage = qs('rc_active_message');
  if (badge) {
    badge.textContent = activePart ? 'Rendering Clips' : statusLabel;
    badge.dataset.state = activePart ? 'rendering' : status === 'completed_with_errors' ? 'warning' : overallState === 'completed' ? 'completed' : overallState === 'failed' ? 'failed' : 'idle';
  }
  if (activeCard) {
    activeCard.classList.remove('isIdle', 'isRendering', 'isCompleted', 'isFailed');
    let activeCardState = 'isIdle';
    let activeCardPct = pct;
    let title, subtitle, stageLine, message;
    message = latest || '';

    if (activePart) {
      activeCardState = 'isRendering';
      activeCardPct = clampRcProgress(activePart?.progress_percent ?? activePart?.progress ?? pct);
      title = `Clip ${activePartNo || '?'}`;
      subtitle = `${rcStateLabel('rendering')} · ${rcPartStageText(activePart)}`;
      stageLine = rcPartStageText(activePart);
      message = rcPartMessage(activePart, latest || 'Clip is currently rendering.');
    } else if (overallState === 'completed') {
      activeCardState = 'isCompleted';
      activeCardPct = 100;
      const partial = status === 'completed_with_errors';
      title = partial ? 'Completed with errors' : 'All clips completed';
      subtitle = `${completed}/${total || 0} clips finished${failed > 0 ? ` · ${failed} failed` : ''}`;
      stageLine = partial ? 'Completed with Errors' : 'Completed';
      message = latest || (partial ? 'Some clips need review. Successful outputs remain available.' : 'All clips finished successfully.');
    } else if (overallState === 'failed') {
      activeCardState = 'isFailed';
      title = 'Render failed';
      subtitle = `${completed}/${total || 0} completed${failed > 0 ? ` · ${failed} failed` : ''}`;
      stageLine = stageText;
      message = latest || 'The render stopped before completion.';
    } else if (!job) {
      // No active job — idle/ready state
      title = 'Ready to render';
      subtitle = 'Configure your video, then click Start Render.';
      stageLine = '';
    } else {
      // Job running but no active clip yet (scene detection, segment building, etc.)
      const jobStage = normalizeRenderStage(job?.stage, job?.status);
      if (jobStage === 'scene_detection') {
        title = 'Analyzing video';
        subtitle = 'Clip cards will appear once scene detection finishes.';
      } else if (jobStage === 'segment_building') {
        title = 'Building clips';
        subtitle = total > 0 ? `${total} segments found · preparing…` : 'Selecting best segments…';
      } else if (jobStage === 'transcribing_full') {
        title = 'Generating subtitles';
        subtitle = 'Subtitle generation in progress.';
      } else if (total > 0) {
        title = stageText;
        subtitle = `${completed}/${total} clips done`;
      } else {
        title = stageText;
        subtitle = latest || 'Preparing...';
      }
      stageLine = stageText;
    }

    activeCard.classList.add(activeCardState);
    activeCard.classList.toggle('isNoJob', !job);
    if (activeTitle) activeTitle.textContent = title;
    if (activeSubtitle) activeSubtitle.textContent = subtitle;
    if (activePercent) activePercent.textContent = `${activeCardPct}%`;
    if (activeBar) activeBar.style.setProperty('--progress', `${activeCardPct}%`);
    if (activeStage) activeStage.textContent = stageLine;
    if (activeMessage) {
      activeMessage.textContent = message;
      delete activeMessage.dataset.aliveState;
    }

    // Stall warning banner — shown inside active card when stall is detected
    const _stallMsg = (!terminal && job) ? _detectStallSignal(job) : '';
    let _stallBanner = activeCard.querySelector('.rcStallBanner');
    if (_stallMsg) {
      if (!_stallBanner) {
        _stallBanner = document.createElement('div');
        _stallBanner.className = 'rcStallBanner';
        activeCard.insertBefore(_stallBanner, activeCard.firstChild);
      }
      _stallBanner.textContent = _stallMsg;
    } else if (_stallBanner) {
      _stallBanner.remove();
    }

    const cardJobTitle = qs('rc_card_job_title');
    const cardStatusBadge = qs('rc_card_status_badge');
    if (cardJobTitle) {
      const src = job ? getRenderWorkspaceSourceText(job) : '';
      const srcText = (src && src !== 'No source selected') ? src : '';
      const jobBits = job ? [renderJobShortId(job), renderElapsedLabel(job), total ? `${completed}/${total} clips` : ''].filter(Boolean) : [];
      cardJobTitle.textContent = jobBits.length ? jobBits.join(' · ') : srcText;
      cardJobTitle.title = srcText;
    }
    if (cardStatusBadge) {
      cardStatusBadge.textContent = statusLabel;
      cardStatusBadge.dataset.state = status === 'completed_with_errors' ? 'warning' : overallState;
    }
    _updateStageTimeline(job?.stage || '', status);
  }

  // ETA: show after ≥2 clips done, hide on terminal/failed
  const etaEl = qs('rc_eta');
  if (etaEl) {
    let etaText = '';
    if (!terminal && overallState === 'running') {
      const startedAt = activeJobStartedAt || 0;
      if (completed >= 2 && waiting > 0 && startedAt > 0) {
        const elapsedMs = Date.now() - startedAt;
        if (elapsedMs > 0) {
          const secPerClip = (elapsedMs / 1000) / completed;
          const etaSec = secPerClip * waiting;
          etaText = etaSec < 60 ? '< 1 min left' : `~${Math.round(etaSec / 60)} min left`;
        }
      } else if (total > 0 && waiting > 0) {
        etaText = 'estimating…';
      } else if (overallState === 'running') {
        etaText = 'Rendering…';
      }
    }
    etaEl.textContent = etaText;
    etaEl.hidden = !etaText;
    if (etaText) etaEl.dataset.aliveState = etaEl.dataset.aliveState || 'ok';
    else delete etaEl.dataset.aliveState;
  }

  updateOutputPreview(job, items);
  renderBenchmarkPanel(job, items);

  const cardWrap = qs('rc_part_cards');
  if (!cardWrap) return;
  cardWrap.textContent = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'emptyState';
    empty.textContent = renderPendingClipsMessage(job || _renderMonitorLastJob);
    cardWrap.appendChild(empty);
    return;
  }

  const ordered = [...items].sort((a, b) => Number(a?.part_no || 0) - Number(b?.part_no || 0));

  const _mvMap = _mvSegmentMap(job);
  const _mvTop3 = terminal ? _mvTop3Set(_mvMap) : new Set();
  const _rkMap = _rankMap(job);
  const _hasRanking = _rkMap.size > 0;

  const _maxScore = items.reduce((max, p) => {
    const s = p?.viral_score ?? p?.score ?? p?.viralScore;
    if (s == null || s === '' || isNaN(Number(s))) return max;
    return Math.max(max, parseFloat(s));
  }, -Infinity);
  const _bestIdx = _maxScore > -Infinity
    ? ordered.findIndex(p => {
        const s = p?.viral_score ?? p?.score ?? p?.viralScore;
        return s != null && s !== '' && !isNaN(Number(s)) && parseFloat(s) === _maxScore;
      })
    : -1;

  let _newActivePartNo = -1;
  ordered.forEach((part, idx) => {
    const state = normalizeRcPartState(part);
    const progress = clampRcProgress(part?.progress_percent ?? part?.progress ?? part?.percent ?? 0);
    const partNo = Number(part?.part_no || idx + 1);
    const partName = String(part?.part_name || '').trim();
    const msgText = rcPartMessage(
      part,
      state === 'completed' ? 'Clip finished successfully.'
        : state === 'failed'  ? 'Clip failed during processing.'
        : state === 'rendering' ? 'Clip is currently rendering.'
        : 'Waiting in queue.'
    );
    const msgLow = msgText.toLowerCase();
    const isWarn = state === 'completed' && (msgLow.includes('warn') || msgLow.includes('narration'));
    const rkData = _rkMap.get(partNo);
    const isBest = _hasRanking ? (rkData?.isBest === true) : (idx === _bestIdx);
    const isMvTop = _mvTop3.has(partNo);
    const visualClass = isWarn ? 'isWarning' : `is${rcCap(state)}`;

    const row = document.createElement('article');
    row.className = `rcQueueRow ${visualClass}${isBest ? ' rcBestPart' : ''}${isMvTop ? ' rcMvTop3' : ''}`;
    if (state === 'rendering') { row.dataset.active = '1'; _newActivePartNo = partNo; }

    const topRow = document.createElement('div');
    topRow.className = 'rcQueueTop';

    const leftCol = document.createElement('div');
    leftCol.className = 'rcQueueLeft';

    if (terminal && state === 'completed' && part.output_file) {
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.className = 'rcClipCheck';
      chk.dataset.path = part.output_file;
      chk.checked = _selectedClipPaths.has(part.output_file);
      chk.addEventListener('change', () => rcToggleClip(chk));
      row.classList.toggle('isSelected', chk.checked);
      leftCol.appendChild(chk);
    }

    const clipLabel = document.createElement('span');
    clipLabel.className = 'rcClipLabel';
    clipLabel.textContent = partName ? `Clip ${partNo} · ${partName}` : `Clip ${partNo}`;
    leftCol.appendChild(clipLabel);

    if (_hasRanking && rkData && state === 'completed') {
      const rkChip = document.createElement('span');
      rkChip.className = `rcRankChip${rkData.isBest ? ' rcRankBest' : ''}`;
      rkChip.textContent = rkData.isBest ? '★ Best Output' : `#${rkData.rank}`;
      leftCol.appendChild(rkChip);
    }

    const rightCol = document.createElement('div');
    rightCol.className = 'rcQueueRight';

    const mvData = _mvMap.get(partNo);
    const rawScore = !mvData ? (part?.viral_score ?? part?.score ?? part?.viralScore) : null;
    const hasBadge = mvData || (rawScore != null && rawScore !== '' && !isNaN(Number(rawScore)));
    if (hasBadge) {
      const badge = document.createElement('div');
      badge.className = 'rcScoreBadge';
      if (mvData) {
        const tierIcon = mvData.tier === 'hot' ? '🔥' : mvData.tier === 'warm' ? '🌡' : '🌍';
        badge.textContent = `${tierIcon} ${mvData.score} ${mvData.market}`;
        badge.dataset.tier = mvData.tier;
        if (mvData.reasons.length) {
          badge.title = mvData.reasons.slice(0, 2).join('\n');
        }
      } else {
        const val = parseFloat(rawScore);
        badge.textContent = `🔥 ${val.toFixed(1)}`;
        badge.dataset.tier = val >= 8 ? 'hot' : val >= 6 ? 'warm' : 'low';
      }
      rightCol.appendChild(badge);
      if (mvData?.combined != null) {
        const cs = document.createElement('div');
        cs.style.cssText = 'font-size:10px;color:rgba(148,163,184,.45);margin-top:2px;text-align:right;';
        cs.textContent = `Combined: ${mvData.combined}`;
        rightCol.appendChild(cs);
        if (mvData.weights) {
          const wl = document.createElement('div');
          wl.style.cssText = 'font-size:9px;color:rgba(148,163,184,.3);text-align:right;';
          const w = mvData.weights;
          const isAdaptive = w.reason && w.reason !== 'fixed';
          wl.textContent = isAdaptive
            ? `Adaptive: ${w.reason.split(';')[0]}`
            : `M${Math.round((w.market_weight || 0) * 100)} V${Math.round((w.viral_weight || 0) * 100)} H${Math.round((w.hook_weight || 0) * 100)}`;
          rightCol.appendChild(wl);
        }
      }
    }

    if (_hasRanking && rkData && state === 'completed') {
      const rkScore = document.createElement('div');
      rkScore.style.cssText = 'font-size:10px;color:rgba(148,163,184,.4);margin-top:3px;text-align:right;';
      rkScore.textContent = `Rank Score: ${rkData.score}`;
      rightCol.appendChild(rkScore);
    }

    topRow.appendChild(leftCol);
    topRow.appendChild(rightCol);

    const bar = document.createElement('div');
    bar.className = 'rcQueueBar';
    const barFill = document.createElement('span');
    barFill.style.setProperty('--progress', `${progress}%`);
    bar.appendChild(barFill);

    const bottom = document.createElement('div');
    bottom.className = 'rcQueueBottom';
    if (state === 'completed') {
      bottom.textContent = isWarn ? '⚠ Completed with warnings' : '✓ Completed';
    } else if (state === 'failed') {
      bottom.textContent = '✕ Failed';
    } else if (state === 'rendering') {
      bottom.textContent = `${progress}%`;
    } else {
      bottom.textContent = 'Waiting…';
    }

    row.appendChild(topRow);
    row.appendChild(bar);
    row.appendChild(bottom);

    cardWrap.appendChild(row);
  });
  _rcAutoScrollActive(cardWrap, _newActivePartNo);
}

function updateRenderMainState(job, summary, parts = []) {
  const activePanel = qs('render_active_panel');
  const homePanel = qs('render_home_panel');
  if (!activePanel || !homePanel) return;

  const status = normalizeRenderStatus(job?.status, job?.stage);
  const hasJob = !!job && !!currentJobId;
  const terminal = isTerminalRenderStatus(status);
  const partialStatus = isPartialRenderStatus(status);
  const completedStatus = isCompletedRenderStatus(status) || partialStatus;
  const showActivePanel = hasJob && currentView === 'render';

  homePanel.classList.toggle('hiddenView', !((currentView === 'render') && !showActivePanel));
  activePanel.classList.toggle('hiddenView', !showActivePanel);
  if (!showActivePanel) return;

  const s = summary || computeProgressSummary(parts || []);
  renderBottomActiveQueue(job, s, parts || []);
  const pct = deriveRenderProgress(job, s, parts || []);
  const title = terminal
    ? (partialStatus ? 'Completed with errors' : (completedStatus ? 'Render complete' : 'Render failed'))
    : stageLabel(job?.stage || 'queued');
  const done = getCompletedClipCount(s, parts);
  const total = Number(s?.total_parts || parts.length || 0);
  const active = Number(s?.processing_parts || 0);
  const failed = Number(s?.failed_parts || 0);
  const activeParts = Array.isArray(s?.active_parts) ? s.active_parts : [];
  const activePartText = activeParts.length === 1
    ? `Active clip ${Number(activeParts[0]?.part_no || 0)}`
    : activeParts.length > 1
    ? `${activeParts.length} clips active`
    : '';
  const latestDetail = String(job?.message || '').trim();
  const latestShort = latestDetail.length > 120 ? `${latestDetail.slice(0, 117)}...` : latestDetail;
  const failureInfo = renderFailureDetails(job, s);
  const failureSummary = (typeof friendlyRenderError === 'function')
    ? friendlyRenderError(job?.message || '', 'Render failed')
    : 'Render failed';
  const hasFailure = status === 'failed' || failed > 0 || status === 'completed_with_errors' || failureInfo.count > 0;
  const statusLabel = terminal
    ? (partialStatus ? 'Completed with errors' : (completedStatus ? 'Completed' : 'Failed'))
    : 'Rendering';
  const sourceText = getRenderWorkspaceSourceText(job);
  const outputText = getRenderWorkspaceOutputText(job);
  const outputLabel = getRenderWorkspaceOutputLabel(job);
  const workspaceStage = terminal
    ? (completedStatus
      ? (failed > 0 ? 'Render finished with some clip failures' : 'Render completed successfully')
      : 'Render failed before all clips finished')
    : `${stageLabel(job?.stage || 'queued')}. This render is using the same source workspace you just configured.`;
  const clipBits = [];
  if (total > 0) clipBits.push(`${done}/${total} clips done`);
  if (active > 0) clipBits.push(`${active} rendering`);
  if (failed > 0) clipBits.push(`${failed} failed`);

  if (qs('render_active_state')) qs('render_active_state').textContent = terminal ? (partialStatus ? 'Completed With Errors' : (status === 'failed' ? 'Render Failed' : 'Render Complete')) : 'Current Render';
  if (qs('render_active_title')) qs('render_active_title').textContent = title;
  if (qs('render_active_pct')) qs('render_active_pct').textContent = `${pct}%`;
  if (qs('render_active_bar')) qs('render_active_bar').style.width = `${pct}%`;
  if (qs('render_active_panel')) qs('render_active_panel').dataset.renderState = status === 'failed' ? 'failed' : terminal ? 'complete' : 'running';
  if (qs('render_active_meta')) {
    if (completedStatus) {
      qs('render_active_meta').textContent = failed > 0
        ? `${outputLabel}. ${done} clips are ready and ${failed} need review. View clips below.`
        : `${outputLabel}. All completed clips are listed below.`;
    } else if (status === 'failed' || status === 'interrupted') {
      qs('render_active_meta').textContent = clipBits.length ? `${clipBits.join(' | ')} | Review clips and diagnostics below.` : 'Review diagnostics below.';
    } else {
      qs('render_active_meta').textContent = clipBits.length ? `${clipBits.join(' | ')} | Clips will appear below as they finish.` : 'Clips will appear below as rendering progresses.';
    }
  }
  if (qs('render_workspace_source')) qs('render_workspace_source').textContent = sourceText;
  if (qs('render_workspace_output')) qs('render_workspace_output').textContent = outputText;
  if (qs('render_workspace_stage')) qs('render_workspace_stage').textContent = workspaceStage;
  const previewState = status === 'failed' ? 'failed' : completedStatus ? 'complete' : 'active';
  if (qs('render_workspace_preview')) qs('render_workspace_preview').dataset.previewState = previewState;
  if (qs('render_workspace_preview_badge')) qs('render_workspace_preview_badge').textContent = completedStatus ? (partialStatus ? 'Attention' : 'Results') : status === 'failed' ? 'Attention' : 'Rendering';
  if (qs('render_workspace_preview_title')) {
    qs('render_workspace_preview_title').textContent = completedStatus
      ? (failed > 0 ? 'Render finished with review items' : 'Results are ready')
      : (status === 'failed' || status === 'interrupted')
      ? 'Render stopped before completion'
      : 'Rendering in progress';
  }
  if (qs('render_workspace_preview_text')) {
    qs('render_workspace_preview_text').textContent = completedStatus
      ? 'This workspace stays tied to the same source and destination so you can confirm where outputs were saved.'
      : (status === 'failed' || status === 'interrupted')
      ? 'Preview is unavailable here, but the same source and destination context is preserved while you review progress below.'
      : 'Preview unavailable during render. This workspace remains tied to the same source and output destination you selected in the editor.';
  }
  if (!terminal) {
    const liveBits = [...clipBits];
    if (activePartText) liveBits.push(activePartText);
    if (latestShort) liveBits.push(latestShort);
    if (qs('render_active_meta') && liveBits.length) {
      qs('render_active_meta').textContent = `${liveBits.join(' | ')} | Clips will appear below as rendering progresses.`;
    }
    if (qs('render_workspace_stage')) {
      qs('render_workspace_stage').textContent = [stageLabel(job?.stage || 'queued'), activePartText, latestShort].filter(Boolean).join(' · ');
    }
    if (qs('render_workspace_preview_text') && latestShort) {
      qs('render_workspace_preview_text').textContent = `Latest update: ${latestShort}`;
    }
  } else if (status === 'failed' || status === 'interrupted') {
    if (qs('render_active_meta')) {
      qs('render_active_meta').textContent = clipBits.length
        ? `${clipBits.join(' | ')} | ${failureSummary}. Review clips and diagnostics below.`
        : `${failureSummary}. Review diagnostics below.`;
    }
    if (qs('render_workspace_preview_title')) qs('render_workspace_preview_title').textContent = 'Render failed';
    if (qs('render_workspace_preview_text')) {
      qs('render_workspace_preview_text').textContent = `Render failed: ${latestShort || failureSummary}`;
    }
  } else if (latestShort && qs('render_workspace_preview_text')) {
    qs('render_workspace_preview_text').textContent = `Latest update: ${latestShort}`;
  }
  if (qs('abp_summary_primary')) qs('abp_summary_primary').textContent = statusLabel;
  if (qs('abp_summary_progress')) qs('abp_summary_progress').textContent = `${pct}%`;
  if (qs('abp_summary_meta')) qs('abp_summary_meta').textContent = terminal
    ? (partialStatus ? 'Completed with errors.' : (completedStatus ? 'Render complete.' : `${failureSummary}.`))
    : (latestShort || 'Rendering in progress.');
  if (qs('abp_summary_stage')) {
    qs('abp_summary_stage').textContent = stageLabel(job?.stage || 'queued');
  }
  if (qs('abp_summary_parts')) {
    const partBits = [`${done} / ${total || 0} completed`];
    if (failed > 0) partBits.push(`${failed} failed`);
    qs('abp_summary_parts').textContent = partBits.join(' · ');
  }
  if (qs('abp_summary_active')) {
    qs('abp_summary_active').textContent = activePartText || (active > 0 ? `${active} clips active` : 'No active clip');
  }
  if (qs('abp_summary_latest')) {
    qs('abp_summary_latest').textContent = latestShort || (terminal ? failureSummary : 'Waiting for the next render update.');
  }
  if (qs('abp_output_text')) qs('abp_output_text').textContent = outputText;
  if (qs('abp_output_meta')) qs('abp_output_meta').textContent = outputLabel;
  const _rcPrimary = partialStatus ? `Completed with errors · ${pct}%` : hasFailure ? `Failed · ${pct}%` : terminal ? 'Completed' : `Rendering · ${pct}%`;
  const _rcSecondary = total > 0 ? renderMonitorClipSummary(s, parts) : stageLabel(job?.stage || 'queued');
  if (qs('rc_status')) { qs('rc_status').textContent = _rcPrimary; qs('rc_status').dataset.state = status === 'failed' ? 'failed' : partialStatus ? 'warning' : terminal ? 'completed' : 'running'; }
  if (qs('rc_progress')) qs('rc_progress').textContent = '';
  if (qs('rc_stage')) qs('rc_stage').textContent = _rcSecondary;
  if (qs('rc_parts')) qs('rc_parts').textContent = '';
  if (qs('rc_active')) qs('rc_active').textContent = '';
  if (qs('abp_error_text')) {
    const detailText = [
      failureInfo.count > 0 ? `${failureInfo.count} failed part${failureInfo.count === 1 ? '' : 's'}` : '',
      failureInfo.warning,
      ...failureInfo.details.slice(0, 3).map((d) => typeof d === 'string' ? d : JSON.stringify(d)),
      latestShort,
    ].filter(Boolean).join(' | ');
    qs('abp_error_text').textContent = hasFailure
      ? (status === 'completed_with_errors' ? `Warning: ${detailText || 'Completed with errors.'}` : `Error: ${detailText || failureSummary}`)
      : 'No blocking errors.';
  }
  if (qs('abp_error_block')) qs('abp_error_block').classList.toggle('hiddenView', !hasFailure);
  if (qs('abp_retry_btn')) qs('abp_retry_btn').classList.toggle('hiddenView', !(hasFailure && currentJobId));
  if (qs('rc_open_output_btn')) qs('rc_open_output_btn').disabled = !(completedStatus || String(outputText || '').trim());
  if (qs('render_active_actions')) qs('render_active_actions').classList.toggle('hiddenView', !completedStatus);
  renderAiInsights(job);
  RenderAiRuntime.update(job?.stage || 'queued', status, parts || [], s);
  if (terminal && completedStatus) RenderAiRuntime.showCompletionIntelligence(job, s, parts || []);
  updateRdCard(job, s, parts || []);
  if (typeof updateWfStrip === 'function') updateWfStrip();
}

// ── RD — Dominant Active Render Card helpers ──────────────────────────────────

function _rdBadgeConfig(job, terminal, status, failed, total) {
  if (!job) return { text: 'Idle', state: 'idle' };
  if (status === 'queued' || status === 'pending') return { text: 'Queued', state: 'queued' };
  if (terminal) {
    if (isPartialRenderStatus(status)) {
      return { text: 'Completed with errors', state: 'partial' };
    }
    if (status === 'completed' || status === 'done' || status === 'complete') {
      return failed > 0 && total > 0
        ? { text: '⚠ Partial', state: 'partial' }
        : { text: '✓ Done', state: 'completed' };
    }
    return { text: '✕ Failed', state: 'failed' };
  }
  return { text: 'Running', state: 'running' };
}

function renderSegmentedBar(container, parts) {
  if (!container) return;
  const items = Array.isArray(parts) ? parts : [];
  if (items.length === 0) {
    container.innerHTML = '<div class="rdSegItem rdSegItem--waiting" style="flex:1"></div>';
    return;
  }
  const frag = document.createDocumentFragment();
  items.forEach((part, i) => {
    const state = normalizeRcPartState(part);
    const seg = document.createElement('div');
    seg.className = `rdSegItem rdSegItem--${state}`;
    seg.title = String(part.part_name || `Clip ${part.part_no || i + 1}`);
    frag.appendChild(seg);
  });
  container.replaceChildren(frag);
}

function renderRdClipQueue(container, parts, job) {
  if (!container) return;
  const items = Array.isArray(parts) ? parts : [];
  if (items.length === 0) { container.innerHTML = ''; return; }
  const frag = document.createDocumentFragment();
  items.forEach((part, i) => {
    const state = normalizeRcPartState(part);
    const name = String(part.part_name || `Clip ${part.part_no || i + 1}`);
    const row = document.createElement('div');
    row.className = `rdQueueRow rdQueueRow--${state}`;

    const head = document.createElement('div');
    head.className = 'rdQueueRowHead';
    const nameEl = document.createElement('div');
    nameEl.className = 'rdQueueRowName';
    nameEl.textContent = name;
    const badge = document.createElement('div');
    badge.className = 'rdQueueRowBadge';
    if (state === 'completed') { badge.textContent = '✓ Done'; badge.dataset.state = 'completed'; }
    else if (state === 'failed') { badge.textContent = '✕ Failed'; badge.dataset.state = 'failed'; }
    else if (state === 'rendering') { badge.textContent = '● Rendering'; badge.dataset.state = 'rendering'; }
    else { badge.textContent = '○ Queued'; badge.dataset.state = 'waiting'; }
    head.appendChild(nameEl);
    head.appendChild(badge);
    row.appendChild(head);

    if (state === 'completed' && part.output_file) {
      const pathParts = String(part.output_file).replace(/\\/g, '/').split('/');
      const pathEl = document.createElement('div');
      pathEl.className = 'rdQueueRowPath';
      pathEl.textContent = pathParts.slice(-2).join('/');
      pathEl.title = part.output_file;
      row.appendChild(pathEl);
      const acts = document.createElement('div');
      acts.className = 'rdQueueRowActions';
      const outDir = pathParts.slice(0, -1).join('/') || part.output_file;
      const openBtn = document.createElement('button');
      openBtn.className = 'rdQueueBtn';
      openBtn.textContent = 'Open Folder';
      openBtn.onclick = () => openStoredOutputPath(outDir);
      acts.appendChild(openBtn);
      row.appendChild(acts);
    } else if (state === 'failed') {
      const errEl = document.createElement('div');
      errEl.className = 'rdQueueRowError';
      errEl.textContent = friendlyRenderError(rcPartMessage(part), `Clip ${part.part_no || i + 1} failed`);
      row.appendChild(errEl);
    } else if (state === 'rendering') {
      const pct = clampRcProgress(part.progress_percent);
      if (pct > 0) {
        const progEl = document.createElement('div');
        progEl.className = 'rdQueueRowProg';
        progEl.textContent = `${pct}%`;
        row.appendChild(progEl);
      }
    }
    frag.appendChild(row);
  });
  container.replaceChildren(frag);
}

function updateRdCard(job, summary, parts) {
  const s = summary || computeProgressSummary(Array.isArray(parts) ? parts : []);
  const status = String(job?.status || '').toLowerCase();
  const terminal = isTerminalRenderStatus(status);
  const failed = Number(s?.failed_parts || 0);
  const total = Number(s?.total_parts || (Array.isArray(parts) ? parts.length : 0));

  const badgeEl = qs('rd_badge');
  if (badgeEl) {
    const { text, state } = _rdBadgeConfig(job, terminal, status, failed, total);
    badgeEl.textContent = text;
    badgeEl.dataset.state = state;
  }

  const cardEl = qs('rd_card');
  if (cardEl) {
    cardEl.dataset.state = !job ? 'idle'
      : terminal ? ((status === 'failed' || status === 'interrupted') ? 'failed' : (failed > 0 ? 'partial' : 'completed'))
      : 'running';
  }

  const titleEl = qs('rd_title');
  if (titleEl) {
    const src = getRenderWorkspaceSourceText(job);
    titleEl.textContent = src && src !== 'No source selected' ? src : (job ? 'Render in progress' : 'No active render');
  }

  renderSegmentedBar(qs('rd_seg_bar'), Array.isArray(parts) ? parts : []);
}

function getCurrentJobOutputDir(job) {
  const payload = getCurrentJobPayload(job);
  return String(payload.output_dir || '').trim();
}

function openRenderOutputFolder() {
  if (!currentJobId) return;
  fetch(`/api/jobs/${currentJobId}`)
    .then((r) => r.json())
    .then((job) => {
      const out = getCurrentJobOutputDir(job);
      if (!out) {
        showToast('Output folder is unavailable for this job', 'info');
        return;
      }
      openStoredOutputPath(out);
    })
    .catch(() => showToast('Unable to load output folder path', 'error'));
}

function copyOutputPathToClipboard(out) {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(out)
      .then(() => showToast('Output folder path copied to clipboard', 'info'))
      .catch(() => showToast(`Output folder: ${out}`, 'info'));
  } else {
    showToast(`Output folder: ${out}`, 'info');
  }
}

function openStoredOutputPath(out) {
  const target = String(out || '').trim();
  if (!target) {
    showToast('Output folder is unavailable for this job', 'info');
    return;
  }
  if (window.electronAPI?.openPath) {
    Promise.resolve(window.electronAPI.openPath(target))
      .then((result) => {
        if (result) {
          copyOutputPathToClipboard(target);
          return;
        }
        showToast('Opening output folder', 'success');
      })
      .catch(() => copyOutputPathToClipboard(target));
  } else {
    copyOutputPathToClipboard(target);
  }
  addEvent(`Output folder: ${target}`, 'render');
}

const RENDER_HISTORY_KEY = 'toolRenderVideo.recentRenders.v1';
const RENDER_HISTORY_LIMIT = 15;

function _renderHistoryRead() {
  try {
    const raw = localStorage.getItem(RENDER_HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function _renderHistoryWrite(items) {
  try {
    localStorage.setItem(RENDER_HISTORY_KEY, JSON.stringify(items.slice(0, RENDER_HISTORY_LIMIT)));
  } catch (_) {}
}

function _renderHistoryPayload(job) {
  try {
    const raw = job?.payload_json;
    if (!raw) return {};
    return typeof raw === 'string' ? JSON.parse(raw) : raw;
  } catch (_) {
    return {};
  }
}

function _renderHistoryFileName(value) {
  const clean = String(value || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() || '';
  return clean || String(value || '').trim();
}

function _renderHistoryTitle(sourceType, sourceValue) {
  const value = String(sourceValue || '').trim();
  if (!value) return 'Untitled render';
  if (sourceType === 'local') return _renderHistoryFileName(value) || 'Local video';
  try {
    const u = new URL(value);
    return u.searchParams.get('v') ? `YouTube ${u.searchParams.get('v')}` : u.hostname.replace(/^www\./, '');
  } catch (_) {
    return value.length > 54 ? `${value.slice(0, 51)}...` : value;
  }
}

function _renderHistoryStatus(completed, failed) {
  if (failed > 0 && completed > 0) return 'partial';
  if (failed > 0 && completed === 0) return 'failed';
  if (completed > 0 && failed === 0) return 'completed';
  return 'failed';
}

function _renderHistoryStatusText(status) {
  if (status === 'partial') return 'Partial';
  if (status === 'failed') return 'Failed';
  return 'Completed';
}

function _renderHistoryClipSummary(entry) {
  const completed = Number(entry.completedParts || 0);
  const failed = Number(entry.failedParts || 0);
  if (completed > 0 && failed > 0) return `${completed} clips · ${failed} failed`;
  if (failed > 0) return `${failed} failed`;
  return `${completed} clips`;
}

function _renderHistoryRelativeTime(ts) {
  const t = Number(ts || 0);
  if (!t) return 'just now';
  const seconds = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

function _renderHistoryAttr(value) {
  return String(value || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildRenderHistoryEntry(job, summary, parts) {
  const payload = _renderHistoryPayload(job);
  const items = Array.isArray(parts) ? parts : [];
  const completed = Number(summary?.completed_parts ?? items.filter((p) => String(p?.status || '').toLowerCase() === 'done').length) || 0;
  const failed = Number(summary?.failed_parts ?? items.filter((p) => String(p?.status || '').toLowerCase() === 'failed').length) || 0;
  const total = Number(summary?.total_parts ?? items.length) || (completed + failed);
  const sourceType = String(payload.source_mode || (payload.youtube_url ? 'youtube' : 'local')).toLowerCase();
  const rawSource = sourceType === 'youtube' ? payload.youtube_url : payload.source_video_path;
  const sourceValue = sourceType === 'local' ? _renderHistoryFileName(rawSource) : String(rawSource || '').trim();
  const outputDir = String(payload.output_dir || '').trim();
  const stamp = Date.parse(job?.completed_at || job?.updated_at || job?.created_at || '') || Date.now();
  const doneParts = items
    .filter((p) => String(p?.status || '').toLowerCase() === 'done' && p.output_file)
    .sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0));
  const firstPart = doneParts[0] || null;
  return {
    jobId: String(job?.id || job?.job_id || currentJobId || '').trim(),
    sourceType,
    sourceValue,
    outputDir,
    totalParts: total,
    completedParts: completed,
    failedParts: failed,
    timestamp: stamp,
    title: _renderHistoryTitle(sourceType, rawSource),
    status: _renderHistoryStatus(completed, failed),
    profile: String(payload.render_profile || 'quality').trim(),
    sourceQualityMode: String(payload.source_quality_mode || 'standard_1080').trim(),
    reframeMode: payload.motion_aware_crop ? String(payload.reframe_mode || 'center').trim() : 'none',
    subtitleStyle: String(payload.subtitle_style || '').trim(),
    firstPartNo: firstPart ? Number(firstPart.part_no) : null,
    firstPartFile: firstPart ? String(firstPart.output_file || '') : null,
    firstPartDurationSec: firstPart ? Math.max(0, Number(firstPart.end_sec || 0) - Number(firstPart.start_sec || 0)) : null,
  };
}

function saveRenderHistoryEntry(job, summary, parts) {
  const entry = buildRenderHistoryEntry(job, summary, parts);
  if (!entry.jobId) return;
  const existing = _renderHistoryRead().filter((item) => item.jobId !== entry.jobId);
  const next = [entry, ...existing].sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0));
  _renderHistoryWrite(next);
  renderRenderHistory();
}

function renderRenderHistory() {
  const box = qs('render_history_list');
  if (!box) return;
  const items = _renderHistoryRead();
  if (!items.length) {
    // R7.4: Honest empty state — don't claim AI learns until user actually starts
    box.innerHTML =
      '<div class="renderHistoryEmpty">' +
        '<div class="renderHistoryEmptyIcon">&#127916;</div>' +
        '<div class="renderHistoryEmptyTitle">No renders yet</div>' +
        '<div class="renderHistoryEmptySub">Start a render to see your history here. Review clips after each render to help AI learn your preferences.</div>' +
      '</div>';
    _uxr4PopulateMomentumHero();
    return;
  }
  box.innerHTML = items.map((entry, idx) => {
    const icon = entry.status === 'failed' ? '✕' : entry.status === 'partial' ? '⚠' : '✓';
    const openDisabled = entry.outputDir ? '' : ' disabled';
    const elevatedClass = idx === 0 ? ' uxr4TopItem' : '';
    // R8.3.1-D: Status-aware continuity narrative — resume-oriented for partial, gentle for failed
    const histMeta = entry.status === 'partial'
      ? 'Resume · ' + _renderHistoryClipSummary(entry)
      : entry.status === 'failed'
      ? 'Ready to retry'
      : _renderHistoryStatusText(entry.status) + ' · ' + _renderHistoryClipSummary(entry);
    return `<div class="renderHistoryItem ${esc(entry.status || 'completed')}${elevatedClass}">
      <div class="renderHistoryMain">
        <div class="renderHistoryTop">
          <span class="renderHistoryStatusIcon">${icon}</span>
          <span class="renderHistoryTitle" title="${_renderHistoryAttr(entry.sourceValue)}">${esc(entry.title || 'Untitled render')}</span>
          <span class="renderHistoryTime">${_renderHistoryRelativeTime(entry.timestamp)}</span>
        </div>
        <div class="renderHistoryMeta">${esc(histMeta)}</div>
      </div>
      <div class="renderHistoryActions">
        <button class="ghostButton" type="button"${openDisabled} onclick="openRenderHistoryOutput('${encodeURIComponent(entry.jobId)}')">Open Output Folder</button>
        <button class="secondaryButton" type="button" onclick="rerunRenderHistory('${encodeURIComponent(entry.jobId)}')">Rerun</button>
      </div>
    </div>`;
  }).join('');
  updateComparePanel();
  _uxr4PopulateMomentumHero();
}

// UX-R4-A/D / R7.3 / R8.3.1: Populate creator momentum hero.
// Continue zone reads from /api/jobs/history (real can_rerun semantics);
// falls back to localStorage when API is unavailable.
// R8.3.1: Status-aware narrative, purposeful CTAs, momentum strip.
async function _uxr4PopulateMomentumHero() {
  var continueZone = document.getElementById('uxr4_continue_zone');
  var intelMsg     = document.getElementById('uxr4_intel_msg');
  if (!continueZone && !intelMsg) return;

  // ── Left: creative momentum continue zone ─────────────────────
  if (continueZone) {
    var _apiFailed = false;
    var apiLast = null;
    try {
      var res = await fetch('/api/jobs/history?limit=3&kind=render');
      var data = await res.json();
      var apiItems = res.ok && Array.isArray(data.items) ? data.items : [];
      apiLast = apiItems[0] || null;
    } catch (_) {
      _apiFailed = true;
    }

    if (apiLast && !_apiFailed) {
      var ts = Date.parse(String(apiLast.timestamp || apiLast.updated_at || apiLast.created_at || ''));
      var timeAgo = _renderHistoryRelativeTime(ts || 0);
      var summaryText = String(apiLast.summary_text || '').trim();
      var canRerun = !!apiLast.can_rerun;
      var canRetry = !!apiLast.can_retry;

      // R8.3.1-A: Status-aware creative narrative — what happened, not just a label
      var narrative = '';
      if (canRetry) {
        narrative = 'Render paused mid-way. Resume where you left off.';
      } else if (summaryText) {
        narrative = esc(summaryText);
      } else if (timeAgo) {
        narrative = 'Finished ' + esc(timeAgo) + '.';
      }

      // R8.3.1-B: Single purposeful CTA
      var ctaHtml = canRerun
        ? '<button class="uxr4ContinueBtn" type="button"' +
          ' onclick="rerunRenderHistory(\'' + encodeURIComponent(apiLast.job_id) + '\')">' +
          'Try another render pass</button>'
        : canRetry
        ? '<button class="uxr4ContinueBtn" type="button"' +
          ' onclick="(typeof retryHistoryDownload===\'function\')&&retryHistoryDownload(\'' + encodeURIComponent(apiLast.job_id) + '\')">' +
          'Retry interrupted render</button>'
        : '';

      continueZone.innerHTML =
        '<div class="uxr4ContinueTitle">' + esc(apiLast.title || 'Last project') + '</div>' +
        (narrative ? '<div class="uxr4ContinueNarrative">' + narrative + '</div>' : '') +
        ctaHtml;
    } else {
      // Fallback: localStorage shape
      var lsItems = _renderHistoryRead();
      if (!lsItems.length) {
        continueZone.innerHTML =
          '<div class="uxr4ContinueLabel">Set up your workspace</div>' +
          '<div class="uxr4ContinueSub">Start a render to see your projects here.</div>';
      } else {
        var last = lsItems[0];
        var clips  = Number(last.completedParts || 0);
        var failed = Number(last.failedParts || 0);
        var lsTimeAgo = _renderHistoryRelativeTime(last.timestamp);
        var metaParts = [];
        if (clips > 0) metaParts.push(clips + ' clip' + (clips !== 1 ? 's' : '') + ' reviewed');
        if (failed > 0) metaParts.push(failed + ' failed');
        continueZone.innerHTML =
          '<div class="uxr4ContinueTitle">' + esc(last.title || 'Last project') + '</div>' +
          (metaParts.length
            ? '<div class="uxr4ContinueNarrative">' + esc(metaParts.join(' · ')) +
              ' <span class="uxr4ContinueTime">' + esc(lsTimeAgo) + '</span></div>'
            : '') +
          '<button class="uxr4ContinueBtn" type="button"' +
          ' onclick="rerunRenderHistory(\'' + encodeURIComponent(last.jobId) + '\')">' +
          'Try another render pass</button>';
      }
    }
  }

  // ── Right: creative momentum strip ────────────────────────────
  if (intelMsg) {
    // R8.3.1-C: Momentum tendency sentence from CreatorMemory taste model
    var html = 'Your creative workspace. Start a render to see intelligence here.';
    if (typeof CreatorMemory !== 'undefined') {
      try {
        var taste = CreatorMemory.getTasteModel();
        if (taste && taste.confident) {
          var tendencies = [];
          if (taste.hook === 'aggressive' && taste.hookConf > 0.4) tendencies.push('stronger openings');
          if (taste.pace === 'fast'       && taste.paceConf > 0.4) tendencies.push('faster pacing');
          if (taste.editStyle === 'viral')      tendencies.push('high-energy edits');
          else if (taste.editStyle === 'cinematic') tendencies.push('cinematic storytelling');
          if (tendencies.length) {
            html = '<div class="uxr4MomentumStrip">' +
                   '<div class="uxr4MomentumLabel">Recent tendency</div>' +
                   '<div class="uxr4MomentumTendency">' + esc(tendencies.slice(0, 2).join(' · ')) + '</div>' +
                   '</div>';
          } else {
            var STYLE_LABELS = {
              viral: 'Viral / High-energy', cinematic: 'Cinematic / Story',
              educational: 'Educational / Clarity', balanced: 'Balanced'
            };
            var stRows = '';
            if (taste.editStyle && taste.editStyle !== 'balanced') {
              stRows += '<div class="uxr4IntelTasteRow"><span class="uxr4IntelTasteKey">Edit style</span>' +
                        '<span class="uxr4IntelTasteVal">' + esc(STYLE_LABELS[taste.editStyle] || taste.editStyle) + '</span></div>';
            }
            if (stRows) html = '<div class="uxr4IntelTaste">' + stRows + '</div>';
          }
        } else if (taste && !taste.confident) {
          var prefs = (typeof CreatorMemory.getDerivedPreferences === 'function')
            ? CreatorMemory.getDerivedPreferences() : null;
          var total = prefs ? (prefs.totalSignals || 0) : 0;
          if (total > 0) {
            html = '<div class="uxr4MomentumStrip">' +
                   '<div class="uxr4MomentumLearning">Still learning your preferences — ' + total +
                   ' signal' + (total !== 1 ? 's' : '') + ' so far</div>' +
                   '</div>';
          }
        }
      } catch (_) {}
    }
    intelMsg.innerHTML = html;
  }
}

// ── Compare Outputs (P2-4) ───────────────────────────────────────────────────

function getCompareOutputCandidates() {
  const history = _renderHistoryRead();
  return history
    .filter((e) => e.status !== 'failed' && e.jobId)
    .map((e) => {
      const partNo = e.firstPartNo ?? null;
      const canPreview = partNo != null;
      const previewUrl = canPreview ? `/api/render/jobs/${encodeURIComponent(e.jobId)}/parts/${partNo}/media` : null;
      const label = (e.totalParts > 1 && partNo != null)
        ? `${e.title} · Part ${partNo}`
        : e.title || 'Render';
      return {
        id: `${e.jobId}-${partNo ?? 'dir'}`,
        label,
        fileName: e.firstPartFile ? e.firstPartFile.replace(/\\/g, '/').split('/').pop() : '',
        path: e.firstPartFile || e.outputDir || '',
        previewUrl,
        canPreview,
        duration: e.firstPartDurationSec ?? null,
        sizeBytes: null,
        jobId: e.jobId,
        partNo,
        profile: e.profile || '',
        sourceQualityMode: e.sourceQualityMode || '',
        reframeMode: e.reframeMode || '',
        status: e.status,
        outputDir: e.outputDir || '',
        timestamp: e.timestamp || 0,
      };
    })
    .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0));
}

function _rcCompareSelectA(id) { _rcCompareSelA = String(id || ''); updateComparePanel(); }
function _rcCompareSelectB(id) { _rcCompareSelB = String(id || ''); updateComparePanel(); }

function _buildCompareMeta(c) {
  const el = document.createElement('div');
  el.className = 'rcCompareMeta';
  const dash = '—';
  const rows = [
    { label: 'File',     value: c.fileName || dash },
    { label: 'Duration', value: c.duration != null ? formatBenchDuration(c.duration * 1000) : dash },
    { label: 'Size',     value: c.sizeBytes != null ? formatBenchBytes(c.sizeBytes) : dash },
    { label: 'Profile',  value: c.profile || dash },
    { label: 'Source',   value: c.sourceQualityMode || dash },
    { label: 'Reframe',  value: c.reframeMode || dash },
  ];
  if (c.partNo != null) rows.push({ label: 'Part', value: `Part ${c.partNo}` });
  rows.forEach(({ label, value }) => {
    const lbl = document.createElement('span');
    lbl.className = 'rcCompareLabel';
    lbl.textContent = label;
    const val = document.createElement('span');
    val.className = 'rcCompareValue';
    val.textContent = value;
    el.appendChild(lbl);
    el.appendChild(val);
  });
  return el;
}

function _renderCompareColumn(container, side, candidates, selectedId) {
  if (!container) return;
  if (container.dataset.candidateId === selectedId && container.dataset.candidateCount === String(candidates.length)) return;
  container.dataset.candidateId = selectedId;
  container.dataset.candidateCount = String(candidates.length);

  const cand = candidates.find((c) => c.id === selectedId) || candidates[0];

  const selectEl = document.createElement('select');
  selectEl.className = 'rcCompareSelect';
  selectEl.onchange = () => (side === 'a' ? _rcCompareSelectA : _rcCompareSelectB)(selectEl.value);
  candidates.forEach((c) => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.label.length > 42 ? c.label.slice(0, 40) + '…' : c.label;
    opt.selected = c.id === selectedId;
    selectEl.appendChild(opt);
  });

  let mediaEl;
  if (cand && cand.canPreview && cand.previewUrl) {
    mediaEl = document.createElement('video');
    mediaEl.className = 'rcCompareVideo';
    mediaEl.controls = true;
    mediaEl.preload = 'metadata';
    mediaEl.src = cand.previewUrl;
  } else {
    mediaEl = document.createElement('div');
    mediaEl.className = 'rcCompareVideoFallback';
    const msg = document.createElement('span');
    msg.textContent = 'Preview unavailable.';
    mediaEl.appendChild(msg);
    if (cand?.outputDir) {
      const btn = document.createElement('button');
      btn.className = 'rcPreviewOpenBtn';
      btn.type = 'button';
      btn.textContent = 'Open Folder';
      btn.onclick = () => openStoredOutputPath(cand.outputDir);
      mediaEl.appendChild(btn);
    }
  }

  container.innerHTML = '';
  container.appendChild(selectEl);
  container.appendChild(mediaEl);
  if (cand) container.appendChild(_buildCompareMeta(cand));
}

function _renderCompareDiff(container, a, b) {
  if (!container) return;
  if (!a || !b || a.id === b.id) { container.classList.add('hiddenView'); return; }
  const diffs = [];
  if (a.sizeBytes > 0 && b.sizeBytes > 0) {
    const diff = b.sizeBytes - a.sizeBytes;
    if (Math.abs(diff) > 1048576) diffs.push(`${diff > 0 ? 'B' : 'A'} is larger by ${formatBenchBytes(Math.abs(diff))}`);
  }
  if (a.duration != null && b.duration != null) {
    const diff = b.duration - a.duration;
    if (Math.abs(diff) > 0.5) diffs.push(`${diff > 0 ? 'B' : 'A'} is longer by ${Math.abs(diff).toFixed(1)}s`);
  }
  if (a.profile && b.profile && a.profile !== b.profile) diffs.push(`Profiles differ: ${a.profile} vs ${b.profile}`);
  if (a.reframeMode && b.reframeMode && a.reframeMode !== b.reframeMode) diffs.push(`Reframe differs: ${a.reframeMode} vs ${b.reframeMode}`);
  if (a.sourceQualityMode && b.sourceQualityMode && a.sourceQualityMode !== b.sourceQualityMode) diffs.push(`Source quality differs: ${a.sourceQualityMode} vs ${b.sourceQualityMode}`);
  if (!diffs.length) { container.classList.add('hiddenView'); return; }
  container.classList.remove('hiddenView');
  container.textContent = diffs.join(' · ');
}

function updateComparePanel() {
  const panel = qs('rc_compare_panel');
  if (!panel) return;
  const candidates = getCompareOutputCandidates();
  const emptyEl = qs('rc_compare_empty');
  const gridEl = qs('rc_compare_grid');
  const diffEl = qs('rc_compare_diff');

  if (candidates.length === 0) { panel.classList.add('hiddenView'); return; }
  panel.classList.remove('hiddenView');

  if (candidates.length < 2) {
    if (emptyEl) emptyEl.classList.remove('hiddenView');
    if (gridEl) gridEl.classList.add('hiddenView');
    if (diffEl) diffEl.classList.add('hiddenView');
    return;
  }
  if (emptyEl) emptyEl.classList.add('hiddenView');
  if (gridEl) gridEl.classList.remove('hiddenView');

  // Default: A = oldest available, B = newest
  if (!_rcCompareSelA || !candidates.find((c) => c.id === _rcCompareSelA)) {
    _rcCompareSelA = candidates[candidates.length - 1].id;
  }
  if (!_rcCompareSelB || !candidates.find((c) => c.id === _rcCompareSelB)) {
    _rcCompareSelB = candidates[0].id;
  }
  if (_rcCompareSelA === _rcCompareSelB && candidates.length >= 2) {
    _rcCompareSelA = candidates[candidates.length - 1].id;
    _rcCompareSelB = candidates[0].id;
  }

  _renderCompareColumn(qs('rc_compare_col_a'), 'a', candidates, _rcCompareSelA);
  _renderCompareColumn(qs('rc_compare_col_b'), 'b', candidates, _rcCompareSelB);

  const candA = candidates.find((c) => c.id === _rcCompareSelA);
  const candB = candidates.find((c) => c.id === _rcCompareSelB);
  _renderCompareDiff(diffEl, candA, candB);
}

function openRenderHistoryOutput(jobId) {
  jobId = decodeURIComponent(String(jobId || ''));
  const entry = _renderHistoryRead().find((item) => item.jobId === jobId);
  if (!entry) {
    showToast('Render history item not found', 'error');
    renderRenderHistory();
    return;
  }
  openStoredOutputPath(entry.outputDir);
}

function rerunRenderHistory(jobId) {
  jobId = decodeURIComponent(String(jobId || ''));
  const entry = _renderHistoryRead().find((item) => item.jobId === jobId);
  if (!entry) {
    showToast('Render history item not found', 'error');
    renderRenderHistory();
    return;
  }
  setView('render');
  hideRenderCompletionBar();
  setRenderFlowState('source', 'Source ready', { force: true });
  if (qs('output_mode') && entry.outputDir) {
    qs('output_mode').value = 'manual';
    syncOutputModeUI();
    if (qs('manual_output_dir')) qs('manual_output_dir').value = entry.outputDir;
  }
  if (qs('source_mode')) qs('source_mode').value = entry.sourceType === 'local' ? 'local' : 'youtube';
  syncSourceModeUI();
  if (entry.sourceType === 'youtube') {
    if (qs('youtube_url')) qs('youtube_url').value = entry.sourceValue || '';
    setRenderFlowState('source', 'YouTube URL restored', { force: true });
    showToast('YouTube source restored. Open editor to rerun.', 'success');
  } else {
    selectedLocalVideoPath = '';
    _pendingLocalFile = null;
    if (qs('source_video_path')) qs('source_video_path').value = '';
    if (qs('source_video_name')) qs('source_video_name').textContent = 'Please reselect the local file.';
    setRenderFlowState('source', 'Reselect local file', { force: true });
    showToast('Please reselect the local file', 'info');
  }
}

function applyRenderJobPrefill(job) {
  const payload = _renderHistoryPayload(job);
  const sourceMode = String(payload.source_mode || (payload.youtube_url ? 'youtube' : 'local')).toLowerCase();
  const outputDir = String(payload.output_dir || '').trim();
  setView('render');
  hideRenderCompletionBar();
  setRenderFlowState('source', 'Source ready', { force: true });
  if (qs('output_mode') && outputDir) {
    qs('output_mode').value = 'manual';
    syncOutputModeUI();
    if (qs('manual_output_dir')) qs('manual_output_dir').value = outputDir;
  }
  if (qs('source_mode')) qs('source_mode').value = sourceMode === 'local' ? 'local' : 'youtube';
  syncSourceModeUI();
  if (sourceMode === 'youtube') {
    if (qs('youtube_url')) qs('youtube_url').value = String(payload.youtube_url || '').trim();
    setRenderFlowState('source', 'YouTube URL restored', { force: true });
    showToast('YouTube source restored. Open editor to rerun.', 'success');
  } else {
    selectedLocalVideoPath = '';
    _pendingLocalFile = null;
    if (qs('source_video_path')) qs('source_video_path').value = '';
    if (qs('source_video_name')) qs('source_video_name').textContent = 'Please reselect the local file.';
    setRenderFlowState('source', 'Reselect local file', { force: true });
    showToast('Please reselect the local file', 'info');
  }
}

async function rerunRenderJob(jobId) {
  const res = await fetch(`/api/jobs/${encodeURIComponent(String(jobId || '').trim())}`);
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || 'Render job could not be loaded', 'error');
    return;
  }
  applyRenderJobPrefill(data);
}

function focusBottomPanel() {
  const panel = qs('render_active_panel') || qs('appBottomPanel');
  if (!panel) return;
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function focusRenderLogPanel() {
  const panel = qs('render_active_panel') || qs('appBottomPanel');
  const logBox = qs('event_log_render');
  if (!panel || !logBox) return;
  setRenderLogsCollapsed(false);
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  logBox.scrollTop = 0;
}

async function copyRenderDiagnostics() {
  const lines = [];
  const pushText = (label, id) => {
    const value = String(qs(id)?.textContent || '').trim();
    if (value) lines.push(`${label}: ${value}`);
  };
  pushText('Status', 'rc_status');
  pushText('Progress', 'rc_progress');
  pushText('Stage', 'rc_stage');
  pushText('Parts', 'rc_parts');
  pushText('Active', 'rc_active');
  pushText('Latest', 'rc_latest');
  pushText('Active card', 'rc_active_title');
  pushText('Active detail', 'rc_active_subtitle');
  pushText('Active stage', 'rc_active_stage');
  pushText('Active message', 'rc_active_message');
  pushText('Summary', 'abp_summary_meta');
  pushText('Parts', 'abp_summary_parts');
  pushText('Output', 'abp_output_text');
  pushText('Output info', 'abp_output_meta');
  pushText('Error', 'abp_error_text');
  const logs = Array.from(qs('event_log_render')?.querySelectorAll('.logLine') || [])
    .slice(0, 30)
    .map((node) => String(node.textContent || '').trim())
    .filter(Boolean);
  if (logs.length) {
    lines.push('');
    lines.push('Logs:');
    lines.push(...logs);
  }
  const payload = lines.join('\n').trim();
  if (!payload) {
    showToast('No diagnostics available yet', 'info');
    return;
  }
  try {
    await navigator.clipboard.writeText(payload);
    showToast('Diagnostics copied', 'success');
  } catch (_) {
    showToast('Could not copy diagnostics', 'error');
  }
}

function setRenderLogsCollapsed(collapsed, options = {}) {
  const panel = qs('render_active_panel') || qs('appBottomPanel');
  if (!panel) return;
  panel.classList.toggle('logsCollapsed', !!collapsed);
  const compatPanel = qs('appBottomPanel');
  if (compatPanel && compatPanel !== panel) compatPanel.classList.toggle('logsCollapsed', !!collapsed);
  const btn = qs('rc_toggle_logs_btn') || document.querySelector('.abpLogToggle');
  if (btn) btn.textContent = collapsed ? 'View logs' : 'Hide logs';
  const toggleBtn = qs('rc_log_panel_btn');
  if (toggleBtn) toggleBtn.textContent = collapsed ? 'Logs ›' : '‹ Logs';
  if (options.fromUser) _renderLogsUserToggled = true;
}

function maybeAutoCollapseRenderLogs() {
  if (_renderLogsUserToggled) return;
  if (window.innerWidth >= 900) return;
  setRenderLogsCollapsed(true);
}

function toggleRenderLogs() {
  const panel = qs('render_active_panel') || qs('appBottomPanel');
  if (!panel) return;
  setRenderLogsCollapsed(!panel.classList.contains('logsCollapsed'), { fromUser: true });
}

function toggleLogAutoScroll() {
  _logAutoScroll = !_logAutoScroll;
  const btn = qs('rc_log_autoscroll_btn');
  if (btn) {
    btn.classList.toggle('isActive', _logAutoScroll);
    btn.title = _logAutoScroll ? 'Auto-scroll: On' : 'Auto-scroll: Off';
  }
}

function copyRenderLogs() {
  const box = qs('event_log_render');
  if (!box) return;
  const lines = [...box.querySelectorAll('.logLine')].map(el => {
    const t = el.querySelector('.logTime')?.textContent || '';
    const m = el.querySelector('.logMessage')?.textContent || '';
    return t ? `[${t}] ${m}` : m;
  }).join('\n');
  if (!lines.trim()) { showToast('No logs to copy', 'info'); return; }
  navigator.clipboard.writeText(lines).then(
    () => showToast('Logs copied', 'success'),
    () => showToast('Copy failed', 'error')
  );
}

async function addRenderClipToUploadQueue(item) {
  const payload = {
    video_path: String(item?.video_path || '').trim(),
    render_job_id: String(item?.render_job_id || currentJobId || '').trim(),
    part_no: Number(item?.part_no || 0),
    channel_code: String(item?.channel_code || '').trim(),
    account_id: String(item?.account_id || '').trim(),
    caption: String(item?.caption || ''),
    hashtags: Array.isArray(item?.hashtags) ? item.hashtags : [],
  };
  if (!payload.video_path) {
    showToast('Clip path is unavailable', 'error');
    return;
  }
  if (!payload.channel_code) {
    showToast('Channel is unavailable for this clip', 'error');
    return;
  }
  try {
    const res = await fetch('/api/upload/queue/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Add to queue failed');
    showToast('Added to upload queue', 'success');
    addEvent(`Added to upload queue: ${payload.video_path}`, 'upload');
    if (typeof loadUploadQueue === 'function') loadUploadQueue();
  } catch (e) {
    showToast(`Add to queue failed: ${e.message || e}`, 'error');
  }
}

async function loadUploadQueueLegacy() {
  const box = qs('upload_queue_items_box');
  if (!box) return;
  box.innerHTML = '<div class="emptyState">Loading upload queue...</div>';
  try {
    const res = await fetch('/api/upload/queue');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Load queue failed');
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      box.innerHTML = '<div class="emptyState">No queued clips yet.</div>';
      return;
    }
    box.innerHTML = items.map((item) => {
      const name = String(item.video_path || '').split(/[\\/]/).pop() || 'Clip';
      const status = String(item.status || 'pending');
      const account = String(item.account_id || '-');
      return `<div class="partItem">
        <div class="partInfo">
          <div class="partTitle">${esc(name)}</div>
          <div class="partMeta">Status: ${esc(status)} · Account: ${esc(account)}</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = `<div class="emptyState">Upload queue unavailable: ${esc(e.message || e)}</div>`;
  }
}

async function loadUploadQueue() {
  const box = qs('upload_queue_items_box');
  if (!box) return;
  box.innerHTML = '<div class="emptyState">Loading upload queue...</div>';
  try {
    const res = await fetch('/api/upload/queue');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Load queue failed');
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      box.innerHTML = '<div class="emptyState">No queued clips yet.</div>';
      return;
    }
    box.innerHTML = items.map((item) => {
      const queueId = String(item.queue_id || '');
      const name = String(item.video_path || '').split(/[\\/]/).pop() || 'Clip';
      const status = String(item.status || 'pending');
      const account = String(item.account_id || '-');
      const err = String(item.last_error || '').trim();
      const canRun = status === 'pending' || status === 'failed';
      const canCancel = status === 'pending';
      const statusText = status === 'uploading'
        ? 'Uploading...'
        : status === 'success'
          ? 'Success'
          : status === 'failed'
            ? 'Failed'
            : status;
      const runLabel = status === 'failed' ? 'Retry' : 'Run';
      const actions = [
        canRun ? `<button type="button" class="ghostButton" onclick="runUploadQueueItem(${JSON.stringify(queueId)})">${runLabel}</button>` : '',
        canCancel ? `<button type="button" class="ghostButton" onclick="cancelUploadQueueItem(${JSON.stringify(queueId)})">Cancel</button>` : '',
      ].filter(Boolean).join('');
      return `<div class="partItem">
        <div class="partInfo">
          <div class="partTitle">${esc(name)}</div>
          <div class="partMeta">Status: ${esc(statusText)} - Account: ${esc(account)}</div>
          ${err && status === 'failed' ? `<div class="partMeta">Error: ${esc(err)}</div>` : ''}
        </div>
        ${actions ? `<div class="partActions">${actions}</div>` : ''}
      </div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = `<div class="emptyState">Upload queue unavailable: ${esc(e.message || e)}</div>`;
  }
}

async function runUploadQueueItem(queueId) {
  const id = String(queueId || '').trim();
  if (!id) return;
  showToast('Starting queued upload', 'info');
  setTimeout(() => loadUploadQueue(), 300);
  try {
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(id)}/run`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || 'Run upload failed');
    if (data.status === 'success') {
      showToast('Upload queue item succeeded', 'success');
    } else {
      showToast(`Upload queue item failed: ${data.error || 'see queue error'}`, 'error');
    }
  } catch (e) {
    showToast(`Run upload failed: ${e.message || e}`, 'error');
  } finally {
    loadUploadQueue();
  }
}

async function cancelUploadQueueItem(queueId) {
  const id = String(queueId || '').trim();
  if (!id) return;
  try {
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Cancel failed');
    showToast('Upload queue item cancelled', 'success');
  } catch (e) {
    showToast(`Cancel failed: ${e.message || e}`, 'error');
  } finally {
    loadUploadQueue();
  }
}

function initRenderLogScrollBehavior() {
  const box = qs('event_log_render');
  if (!box || box.dataset.scrollBehaviorInit === '1') return;
  box.dataset.scrollBehaviorInit = '1';
  box.addEventListener('scroll', () => {
    if (!_logAutoScroll) return;
    if (box.scrollTop > 32) {
      _logAutoScroll = false;
      const btn = qs('rc_log_autoscroll_btn');
      if (btn) {
        btn.classList.remove('isActive');
        btn.title = 'Auto-scroll: Off';
      }
    }
  }, { passive: true });
}

if (typeof window !== 'undefined' && typeof window.addEvent === 'function' && !window.addEvent._renderUxWrapped) {
  const _renderUxOriginalAddEvent = window.addEvent;
  window.addEvent = function renderUxAddEvent(text, scope = 'auto') {
    const resolved = scope === 'render' || (scope === 'auto' && typeof currentView !== 'undefined' && currentView === 'render');
    const box = resolved ? qs('event_log_render') : null;
    const autoWanted = _logAutoScroll;
    const nearLatest = !box || box.scrollTop <= 32;
    if (resolved && autoWanted && !nearLatest) _logAutoScroll = false;
    _renderUxOriginalAddEvent(text, scope);
    if (resolved && autoWanted && !nearLatest) _logAutoScroll = true;
  };
  window.addEvent._renderUxWrapped = true;
}
function pipelineStateByStage(stage, status){
  const s = normalizeRenderStage(stage, status);
  const st = normalizeRenderStatus(status, s);
  const idx = pipeline.findIndex(node => node.stages.includes(s));
  return pipeline.map((n, i) => {
    if (idx < 0) return { ...n, state: 'pending' };
    if (st === 'failed' && i === idx) return { ...n, state: 'failed' };
    if (i < idx) return { ...n, state: 'done' };
    if (i === idx) return { ...n, state: (st === 'completed' || st === 'completed_with_errors') ? 'done' : 'running' };
    return { ...n, state: 'pending' };
  });
}
function renderPipeline(stage, status){
  const stateLabel = { pending: 'Waiting', running: 'Current', done: 'Done', failed: 'Failed' };
  const pipelineLabel = {
    queued: 'Queue',
    downloading: 'Source',
    scene: 'Scenes',
    segment: 'Segments',
    subtitle: 'Subtitles',
    render: 'Clips',
    report: 'Report'
  };
  const nodes = pipelineStateByStage(stage, status);
  qs('pipeline_wrap').innerHTML = nodes.map(n => `
    <div class="pipelineNode ${n.state}">
      <div class="nTitle">${pipelineLabel[n.key] || n.label}</div>
      <div class="nState">${stateLabel[n.state] || n.state}</div>
    </div>
  `).join('');
}
function setRenderActionBusy(isBusy){
  initRenderLogScrollBehavior();
  const btn = qs('start_render_btn');
  if(!btn) return;
  btn.disabled = !!isBusy;
  btn.style.opacity = isBusy ? '0.75' : '1';
  btn.textContent = isBusy ? 'Render Running' : 'Open Editor';

  // Expand bottom panel when job starts so pipeline/log are immediately visible.
  if (isBusy) {
    clearRenderOutputPanel();
    _renderMonitorLastUpdateAt = 0;
    _renderMonitorLastProgressAt = Date.now();
    _renderMonitorLastSignature = '';
    _renderMonitorLastJob = { status: 'running', stage: 'queued', progress_percent: _jobDisplayPct || 0 };
    _renderMonitorLastSummary = computeProgressSummary([]);
    _renderMonitorLastParts = [];
    ensureRenderMonitorHeartbeatTimer();
    updateRenderMonitorHeartbeat(_renderMonitorLastJob, _renderMonitorLastSummary, []);
    updateRenderMainState({ status: 'running', stage: 'queued', progress_percent: _jobDisplayPct || 0 }, computeProgressSummary([]), []);
    focusBottomPanel();
    maybeAutoCollapseRenderLogs();
    const panel = qs('render_active_panel') || qs('appBottomPanel');
    if (panel) {
      panel.classList.remove('renderStartPulse');
      void panel.offsetWidth;
      panel.classList.add('renderStartPulse');
    }
  } else if (!currentJobId) {
    updateRenderMainState(null, null, []);
  }

  // Lock/unlock all form inputs in the render setup card
  const card = document.querySelector('#card_render_setup');
  if(!card) return;
  const inputs = card.querySelectorAll('input, select, textarea, button');
  inputs.forEach(el => {
    if(el.id === 'start_render_btn') return; // already handled
    el.disabled = !!isBusy;
    el.style.opacity = isBusy ? '0.6' : '1';
    el.style.pointerEvents = isBusy ? 'none' : '';
  });

  // Show/hide a visual overlay on the form
  _setCardOverlay(card, 'render_busy_overlay', isBusy, 'Processing... please wait');
}

function setUploadBusy(isBusy){
  const card = document.querySelector('#card_upload');
  if(!card) return;
  const inputs = card.querySelectorAll('input, select, textarea, button');
  inputs.forEach(el => {
    el.disabled = !!isBusy;
    el.style.opacity = isBusy ? '0.6' : '1';
    el.style.pointerEvents = isBusy ? 'none' : '';
  });
  _setCardOverlay(card, 'upload_busy_overlay', isBusy, 'Uploading... please wait');
}

function _setCardOverlay(card, overlayId, show, message){
  let overlay = document.querySelector('#' + overlayId);
  if(show){
    if(!overlay){
      overlay = document.createElement('div');
      overlay.id = overlayId;
      overlay.style.cssText = 'position:absolute;inset:0;background:rgba(15,23,42,0.06);border-radius:16px;z-index:10;display:flex;align-items:center;justify-content:center;pointer-events:all;cursor:not-allowed;';
      overlay.innerHTML = '<div style="background:#0f172a;color:white;padding:10px 24px;border-radius:10px;font-weight:600;font-size:14px;letter-spacing:0.3px;box-shadow:0 4px 16px rgba(0,0,0,0.18);">' + message + '</div>';
      card.style.position = 'relative';
      card.appendChild(overlay);
    }
  } else {
    if(overlay) overlay.remove();
  }
}

function stepStatus(index, progress){
  const marks = [18, 34, 52, 90, 100];
  if (progress >= marks[index]) return 'done';
  if (index === 0 || progress >= (marks[index - 1] || 0)) return 'running';
  return 'pending';
}

function renderSteps(progress){
  const stateLabel = { pending: 'Waiting', running: 'In Progress', done: 'Done' };
  const _sgEl = qs('steps_grid');
  if (!_sgEl) return;
  _sgEl.innerHTML = steps.map((s, i) => {
    const st = stepStatus(i, progress || 0);
    return `<div class="stepCard ${st}"><div class="stepIconWrap">${st === 'done' ? 'OK' : st === 'running' ? 'RUN' : '...'}</div><div><div class="stepTitle">${s.label}</div><div class="stepStatus">${stateLabel[st] || st}</div></div></div>`;
  }).join('');
}

function partTimelineStatus(status) {
  const st = String(status || '').toLowerCase();
  if (st === 'completed' || st === 'done') return 'completed';
  if (st === 'failed' || st === 'error') return 'failed';
  if (['waiting', 'cutting', 'transcribing', 'rendering'].includes(st)) return 'processing';
  return 'pending';
}

function formatPartDuration(part) {
  const startSec = Number(part?.start_sec || 0);
  const endSec = Number(part?.end_sec || 0);
  const duration = Math.max(0, Number(part?.duration_sec || 0) || (endSec - startSec));
  return duration > 0 ? `${duration.toFixed(1)}s` : '';
}

function formatPartShortName(part) {
  const raw = String(part?.part_name || part?.output_file || part?.output_path || part?.file_name || '').trim();
  const leaf = raw ? raw.split(/[\\/]/).filter(Boolean).pop() : '';
  return leaf || `Part ${Number(part?.part_no || 0) || '-'}`;
}

function renderProcessOverview(items, summary) {
  const box = qs('rs_process_overview');
  if (!box) return;

  const parts = items || [];
  if (!parts.length) {
    box.innerHTML = '';
    return;
  }

  const s = summary || computeProgressSummary(parts);
  const total = Number(s.total_parts || parts.length || 0);
  const done = Number(s.completed_parts || 0);
  const processing = Number(s.processing_parts || 0);
  const failed = Number(s.failed_parts || 0);
  const pending = Math.max(0, Number(s.pending_parts ?? (total - done - processing - failed)));
  const pct = Math.round(Number(s.overall_progress_percent ?? s.parts_percent ?? 0));
  const stage = s.current_stage ? partStatusLabel(s.current_stage) : (processing > 0 ? 'Rendering clips' : (done >= total ? 'Complete' : 'Waiting'));

  box.innerHTML = `
    <div class="rsPoStage">
      <span class="rsPoLabel">Stage</span>
      <strong>${esc(stage)}</strong>
    </div>
    <div class="rsPoMetric">
      <span class="rsPoLabel">Overall</span>
      <strong>${pct}%</strong>
    </div>
    <div class="rsPoCounts">
      <span class="rsPoCount done">${done} done</span>
      <span class="rsPoCount active">${processing} active</span>
      <span class="rsPoCount failed">${failed} failed</span>
      <span class="rsPoCount pending">${pending} pending</span>
    </div>
  `;
}

function renderProcessSummaryStrip(items, summary) {
  const box = qs('rs_process_summary_strip');
  if (!box) return;

  const parts = items || [];
  if (!parts.length) {
    box.innerHTML = '';
    return;
  }

  const job = _renderMonitorLastJob || null;
  const s = summary || computeProgressSummary(parts);
  const outputDir = getCurrentJobOutputDir(job);
  const done = Number(s.completed_parts || 0);
  const failed = Number(s.failed_parts || 0);
  const bits = [];

  if (outputDir) {
    const shortOutput = String(outputDir).replace(/\\/g, '/').split('/').filter(Boolean).slice(-2).join('/');
    bits.push(`<span class="rsPssItem wide" title="${_renderHistoryAttr(outputDir)}"><b>Output</b>${esc(shortOutput || outputDir)}</span>`);
  }
  bits.push(`<span class="rsPssItem"><b>Ready</b>${done}</span>`);
  bits.push(`<span class="rsPssItem ${failed > 0 ? 'failed' : ''}"><b>Failed</b>${failed}</span>`);

  try {
    const raw = job?.result_json;
    const result = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
    const voiceSummary = String(result?.voice_summary || '').trim();
    const subtitleSummary = String(result?.subtitle_translate_summary || '').trim();
    if (voiceSummary) bits.push(`<span class="rsPssItem"><b>Voice</b>${esc(voiceSummary)}</span>`);
    if (subtitleSummary && subtitleSummary !== 'not used') bits.push(`<span class="rsPssItem"><b>Subtitles</b>${esc(subtitleSummary)}</span>`);
  } catch (_) {}

  box.innerHTML = bits.join('');
}

function renderPartTimeline(parts) {
  const wrap = qs('rs_part_chips_wrap');
  const row  = qs('abp_part_chip_row');
  if (!wrap) return;

  if (!parts || !parts.length) {
    wrap.innerHTML = '';
    if (row) row.classList.remove('hasChips');
    return;
  }

  const activeStatuses = ['waiting', 'cutting', 'transcribing', 'rendering'];
  const ordered = [...parts].sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0));

  const chips = ordered.map(p => {
    const partNo  = Number(p.part_no || 0);
    const label   = 'P' + String(partNo).padStart(2, '0');
    const st      = String(p.status || '').toLowerCase();
    const duration = formatPartDuration(p);
    const pct = Math.max(0, Math.min(100, Math.round(Number(p.progress_percent || 0))));
    const chipStatus = partTimelineStatus(st);
    const statusText = partStatusLabel(st);
    const chipTitle = `Part ${partNo} - ${statusText}${duration ? ` - ${duration}` : ''}`;
    const progressHtml = chipStatus === 'processing'
      ? `<div class="rsClipFill" style="width:${pct}%"></div>`
      : '';
    return `<div class="rsPartChip rsTimelineBlock" data-chip-status="${chipStatus}" data-part-no="${partNo}" title="${_renderHistoryAttr(chipTitle)}" onclick="console.log('Part chip: Part', ${partNo})">
      ${progressHtml}
      <div class="rsClipTop"><span>${esc(label)}</span>${chipStatus === 'processing' ? `<b>${pct}%</b>` : ''}</div>
      <div class="rsClipStatus">${esc(statusText)}</div>
      ${duration ? `<div class="rsClipDur">${esc(duration)}</div>` : ''}
    </div>`;
  });

  wrap.innerHTML = chips.join('');
  if (row) row.classList.add('hasChips');
}

function renderAbpActiveCard(items, summary) {
  const card = qs('abp_active_card');
  if (!card) return;
  card.innerHTML = '';
}

function renderActivePartCard(items, summary) {
  renderAbpActiveCard(items, summary);
}

function renderParts(items, summary){
  renderProcessOverview(items, summary);
  renderProcessSummaryStrip(items, summary);
  renderPartTimeline(items);
  renderAbpActiveCard(items, summary);
  renderBottomActiveQueue(_renderMonitorLastJob, summary || computeProgressSummary(items || []), items || []);
  const wrap = qs('parts_wrap');
  if(!items || !items.length){
    if (qs('clips_section_label')) qs('clips_section_label').textContent = 'Clips';
    wrap.innerHTML = `<div class="emptyState">${esc(renderPendingClipsMessage(_renderMonitorLastJob))}</div>`;
    return;
  }
  const s = summary || computeProgressSummary(items);
  const activeStatuses = ['waiting', 'cutting', 'transcribing', 'rendering'];
  const statusRank = (p) => {
    const st = String(p.status || '').toLowerCase();
    if (activeStatuses.includes(st)) return 0;
    if (st === 'failed') return 1;
    if (st === 'done') return 2;
    return 3;
  };
  const ordered = [...items].sort((a,b)=>{
    const ar = statusRank(a), br = statusRank(b);
    if (ar !== br) return ar - br;
    return Number(a.part_no||0)-Number(b.part_no||0);
  });
  const stuckMap = _stuckPartsMap(summary, items);
  syncPartProgressTargets(ordered);
  const _ptMvMap  = _mvSegmentMap(_renderMonitorLastJob);
  const _ptStatus = String(_renderMonitorLastJob?.status || '').toLowerCase();
  const _ptTerm   = isTerminalRenderStatus(_ptStatus);
  const _ptTop3   = _ptTerm ? _mvTop3Set(_ptMvMap) : new Set();
  const total = Number(s.total_parts || items.length || 0);
  const done = Number(s.completed_parts || 0);
  const rendering = Number(s.processing_parts || 0);
  const failed = Number(s.failed_parts || 0);
  const pending = Math.max(0, total - done - rendering - failed);
  const pct = Math.round(Number(s.overall_progress_percent ?? s.parts_percent ?? 0));
  if (qs('clips_section_label')) qs('clips_section_label').textContent = `Clips · ${done}/${total || 0} completed`;

  // Parallel worker chips: show per-worker status when > 1 part active simultaneously
  const activeParts = s.active_parts || [];
  let parallelBarHtml = '';
  if (activeParts.length > 1) {
    const chips = activeParts.map(ap => {
      const st = (ap.status || '').toLowerCase();
      const apKey = String(ap.part_no ?? '');
      const isStuck = stuckMap.has(apKey);
      return `<span class="activePartChip${isStuck ? ' stuck' : ''}"><span class="chipDot ${st}"></span>Clip ${Number(ap.part_no||0)} · ${partStatusLabel(st)}${isStuck ? ' ⚠' : ''}</span>`;
    }).join('');
    parallelBarHtml = `<div class="activePartsBar">${chips}<span class="workersBadge">${activeParts.length} parallel</span></div>`;
  }

  const renderingLabel = rendering > 1 ? `${rendering} in parallel` : rendering === 1 ? '1 rendering' : '';
  const summaryHtml = `<div class="clipsSummaryStrip">
    <span class="clipsSummaryTitle">${total} clips</span>
    ${rendering > 0 ? `<span class="psBadge srendering">${renderingLabel}</span>` : ''}
    ${done > 0 ? `<span class="psBadge sdone">${done} done</span>` : ''}
    ${failed > 0 ? `<span class="psBadge sfailed">${failed} failed</span>` : ''}
    ${pending > 0 ? `<span class="psBadge squeued">${pending} waiting</span>` : ''}
    <span class="clipsSummaryPct">${pct}%</span>
  </div>`;
  const rowsHtml = ordered.map((p, idx) => {
    const st     = (p.status || '').toLowerCase();
    const isRun  = activeStatuses.includes(st);
    const key    = String(p.part_no ?? idx + 1);
    const isStuck = isRun && stuckMap.has(key);
    const disp   = Math.round(_partDisplay[key] ?? Number(p.progress_percent || 0));
    const errMsg  = st === 'failed' ? esc(p.message || '') : '';
    const errHtml = errMsg ? `<div class="partError">${errMsg}</div>` : '';
    const stuckHtml = isStuck ? `<div class="partStuckNote">${_stuckLabel(stuckMap.get(key))}</div>` : '';
    const qualityBadgeHtml = st === 'done' ? _partQualityBadgeHtml(p) : '';
    const partNo = Number(p.part_no || idx + 1);
    const isMvTop = _ptTop3.has(partNo);
    const rowClass  = `${st || 'queued'}${isRun ? ' running isActive' : ''}${st === 'done' ? ' isDone' : ''}${st === 'failed' ? ' isFailed' : ''}${isStuck ? ' stuck' : ''}${isMvTop ? ' mvTop3' : ''}`.trim();
    const partName = p.part_name ? esc(p.part_name) : `Clip ${partNo}`;
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const duration = Math.max(0, endSec - startSec);
    const mvRow = _ptMvMap.get(partNo);
    const _mvWtLabel = (() => {
      if (!mvRow?.weights) return '';
      const w = mvRow.weights;
      return w.reason && w.reason !== 'fixed'
        ? `Adaptive`
        : `M${Math.round((w.market_weight || 0) * 100)} V${Math.round((w.viral_weight || 0) * 100)} H${Math.round((w.hook_weight || 0) * 100)}`;
    })();
    const _mvCsPill = mvRow?.combined != null
      ? `<span style="font-size:10px;color:rgba(148,163,184,.4);margin-left:4px;">${_mvWtLabel ? `${_mvWtLabel} · ` : ''}Combined: ${mvRow.combined}</span>`
      : '';
    const mvPillHtml = mvRow
      ? `<span class="mvScorePill" data-mv-tier="${esc(mvRow.tier)}"${mvRow.reasons.length ? ` title="${esc(mvRow.reasons.slice(0,2).join(' | '))}"` : ''}>&#127758; ${mvRow.score} ${esc(mvRow.market)}</span>${_mvCsPill}`
      : '';
    return `
    <div class="partRow ${rowClass}" data-part-status="${esc(st || 'queued')}">
      <div class="partLeft">
        <div class="rankBadge">C${partNo}</div>
        <div>
          <div class="partName">${partName}</div>
          <div class="partMeta"><span class="clipDuration">${duration.toFixed(1)}s</span> | ${startSec.toFixed(1)}s–${endSec.toFixed(1)}s</div>
          ${errHtml}${stuckHtml}${qualityBadgeHtml}
        </div>
      </div>
      <div class="partProgressCell">
        <div class="partProgressTop">
          <span class="partProgressLabel">${partStatusLabel(st)}</span>
          <span class="partProgressPct" id="row_ppct_${key}">${disp}%</span>
        </div>
        <div class="miniProgress"><div class="miniProgressValue ${esc(st)}" id="row_pbar_${key}" style="width:${disp}%"></div></div>
      </div>
      <div class="partRight">
        <div class="statusBadge ${esc((p.status || '').toLowerCase())}">${partStatusLabel(p.status)}</div>
        ${mvPillHtml}
      </div>
    </div>
  `}).join('');
  wrap.innerHTML = parallelBarHtml + summaryHtml + rowsHtml;
}

function syncPartProgressTargets(items) {
  (items || []).forEach((p, idx) => {
    const key = String(p.part_no ?? idx + 1);
    const backendPct = Number(p.progress_percent || 0);
    _partTarget[key] = backendPct;
    if(_partDisplay[key] == null) _partDisplay[key] = backendPct;
    const st = (p.status||'').toLowerCase();
    if(st === 'done' || st === 'failed') _partDisplay[key] = backendPct;
  });
  _scheduleSmooth();
}

// ── Stuck-part helpers ────────────────────────────────────────────────
const _STUCK_THRESHOLD_S = 120;

function _parseUpdatedAt(val) {
  // Parse SQLite UTC string "YYYY-MM-DD HH:MM:SS" to a Unix seconds float.
  if (!val) return 0;
  try { return new Date(String(val).trim().replace(' ', 'T') + 'Z').getTime() / 1000; }
  catch(_) { return 0; }
}

function _stuckLabel(seconds) {
  if (seconds < 60) return `No progress for ${seconds}s`;
  const m = Math.floor(seconds / 60), s = seconds % 60;
  return s > 0 ? `No progress for ${m}m ${s}s` : `No progress for ${m}m`;
}

// Returns a Map<partNoStr, stuckSeconds> for all currently-stuck active parts.
// Prefers server-computed stuck_parts (from WS summary) when available;
// falls back to client-side computation from parts' own updated_at field.
function _stuckPartsMap(summary, parts) {
  const sp = (summary||{}).stuck_parts;
  if (sp && sp.length > 0) {
    const m = new Map();
    sp.forEach(e => m.set(String(e.part_no ?? ''), Number(e.stuck_seconds || 0)));
    return m;
  }
  // HTTP-polling fallback: compute from updated_at on each part
  const _active = ['waiting','cutting','transcribing','rendering'];
  const now = Date.now() / 1000;
  const m = new Map();
  (parts||[]).forEach(p => {
    if (!_active.includes((p.status||'').toLowerCase())) return;
    const ts = _parseUpdatedAt(p.updated_at);
    if (ts > 0 && (now - ts) > _STUCK_THRESHOLD_S)
      m.set(String(p.part_no ?? ''), Math.round(now - ts));
  });
  return m;
}
// ─────────────────────────────────────────────────────────────────────

function computeProgressSummary(parts){
  const total = (parts||[]).length;
  const empty = {
    total_parts:0, completed_parts:0, failed_parts:0, pending_parts:0,
    processing_parts:0, in_progress_count:0, active_parts:[], stuck_parts:[],
    current_part:null, current_stage:null,
    overall_progress_percent:0, parts_percent:0,
  };
  if(!total) return empty;
  const _active = ['waiting','pending','cutting','transcribing','rendering','processing','running','in_progress'];
  const done    = parts.filter(p=>['done','completed','complete'].includes(String(p.status||'').toLowerCase())).length;
  const failed  = parts.filter(p=>['failed','error'].includes(String(p.status||'').toLowerCase())).length;
  const inProg  = parts.filter(p=>_active.includes(String(p.status||'').toLowerCase()));
  const pending = Math.max(0, total - done - failed - inProg.length);
  const pSum    = parts.reduce((s,p)=>s+Number(p.progress_percent||0),0);
  const overall = total>0 ? Math.round(pSum/total*10)/10 : 0;
  const now = Date.now() / 1000;
  const activeParts = [];
  const stuckParts  = [];
  inProg.forEach(p => {
    const partStatus = String(p.status || '').toLowerCase();
    activeParts.push({ part_no: p.part_no, status: partStatus, progress_percent: Number(p.progress_percent||0) });
    const ts = _parseUpdatedAt(p.updated_at);
    if (ts > 0 && (now - ts) > _STUCK_THRESHOLD_S)
      stuckParts.push({ part_no: p.part_no, status: p.status, stuck_seconds: Math.round(now - ts) });
  });
  return {
    total_parts:               total,
    completed_parts:           done,
    failed_parts:              failed,
    pending_parts:             pending,
    processing_parts:          inProg.length,
    in_progress_count:         inProg.length,
    active_parts:              activeParts,
    stuck_parts:               stuckParts,
    current_part:              inProg[0]?.part_no??null,
    current_stage:             inProg[0]?.status??null,
    overall_progress_percent:  overall,
    parts_percent:             overall,
  };
}

function renderPartFocus(items, summary){
  const box = qs('part_focus');
  if(!box) return;

  const ordered = [...(items||[])].sort((a,b)=>Number(a.part_no||0)-Number(b.part_no||0));
  const s = summary || computeProgressSummary(ordered);

  if(!s.total_parts){
    box.innerHTML = '<div class="partFocusTitle">Live Clip Tracking</div><div class="partFocusLine">Clips will appear here once rendering begins.</div>';
    return;
  }

  // ── Sync smooth-animation targets from backend data ─────────────────
  syncPartProgressTargets(ordered);

  const pending = s.pending_parts ?? (s.total_parts - s.completed_parts - s.failed_parts - s.processing_parts);

  const stuckMap = _stuckPartsMap(s, ordered);

  // ── Active parts highlight bar ───────────────────────────────────────
  const activeParts = s.active_parts || [];
  let activeBarHtml = '';
  if(activeParts.length > 0){
    const chips = activeParts.map(ap => {
      const st      = (ap.status||'').toLowerCase();
      const apKey   = String(ap.part_no ?? '');
      const isStuck = stuckMap.has(apKey);
      return `<span class="activePartChip${isStuck ? ' stuck' : ''}"><span class="chipDot ${st}"></span>P${Number(ap.part_no||0)} · ${partStatusLabel(st)}${isStuck ? ' ⚠' : ''}</span>`;
    }).join('');
    const workerLabel = activeParts.length > 1
      ? `<span class="workersBadge">${activeParts.length} parallel</span>`
      : '';
    activeBarHtml = `<div class="activePartsBar">${chips}${workerLabel}</div>`;
  }

  // ── Summary strip ────────────────────────────────────────────────────
  let stripHtml = `<div class="partsSummaryStrip">
    <span class="partsSummaryLabel">Clips</span>
    <span class="psBadge sdone">${s.completed_parts} done</span>`;
  if(s.processing_parts > 0)
    stripHtml += `<span class="psBadge srendering">${s.processing_parts} active</span>`;
  if(s.failed_parts > 0)
    stripHtml += `<span class="psBadge sfailed">${s.failed_parts} failed</span>`;
  if(stuckMap.size > 0)
    stripHtml += `<span class="psBadge" style="background:rgba(245,158,11,.15);color:#fbbf24;">${stuckMap.size} stuck</span>`;
  if(pending > 0)
    stripHtml += `<span class="psBadge squeued">${pending} queued</span>`;
  const overallPct = s.overall_progress_percent ?? s.parts_percent ?? 0;
  stripHtml += `<span class="partsSummaryAvg">${overallPct}% avg</span></div>`;

  // ── Per-part mini cards (IDs for in-place smooth update) ─────────────
  const cardsHtml = ordered.map(p => {
    const st      = (p.status||'queued').toLowerCase();
    const key     = String(p.part_no || 0);
    const disp    = Math.round(_partDisplay[key] ?? Number(p.progress_percent||0));
    const active  = ['waiting','cutting','transcribing','rendering'].includes(st);
    const isStuck = active && stuckMap.has(key);
    const cardClass = `partProgressCard ${st}${isStuck ? ' stuck' : ''}`;
    const barClass  = `pBarFill ${isStuck ? 'stuck' : st}`;
    const stuckNote = isStuck ? `<div class="pStuck">${_stuckLabel(stuckMap.get(key))}</div>` : '';
    return `<div class="${cardClass}">
      <div class="pCardTop">
        <span class="pNo">P${Number(p.part_no||0)}</span>
        <span class="pPct" id="ppct_${key}">${disp}%</span>
      </div>
      <div class="pBar"><div class="${barClass}" id="pbar_${key}" style="width:${disp}%"></div></div>
      <div class="pStage${isStuck ? ' stuck' : ''}">${partStatusLabel(st)}</div>
      ${stuckNote}
    </div>`;
  }).join('');

  box.innerHTML = `<div class="partFocusTitle">Live Clip Tracking</div>${activeBarHtml}${stripHtml}<div class="partsProgressGrid">${cardsHtml}</div>`;
}

function updateStatusBar(job, summary) {
  const dot   = qs('sbDot');
  const label = qs('sbLabel');
  const sumEl = qs('sbSummary');
  const pctEl = qs('sbPct');
  const area  = qs('sbJobArea');
  if (!dot || !label) return;

  const stage     = normalizeRenderStage(job.stage, job.status);
  const status    = normalizeRenderStatus(job.status, stage);
  const pct       = deriveRenderProgress(job, summary, _renderMonitorLastParts || []);
  const isRunning = !isTerminalRenderStatus(status) && !!status;
  const isPartial = isPartialRenderStatus(status);
  const isDone    = isCompletedRenderStatus(status) || isPartial;
  const isFailed  = status === 'failed';

  dot.className = 'statusDot ' + (isFailed ? 'statusDotFailed' : isRunning ? 'statusDotRunning' : 'statusDotReady');
  label.textContent = isPartial ? 'Completed with errors' : isDone ? 'Done' : isFailed ? 'Failed' : isRunning ? stageLabelPlain(stage) : 'Idle';

  if (sumEl) {
    if (summary && summary.total_parts > 0) {
      const d = summary.completed_parts || 0;
      const t = summary.total_parts || 0;
      const a = summary.processing_parts > 0 ? ` · ${summary.processing_parts} active` : '';
      sumEl.textContent = `- ${d}/${t} clips${a}`;
    } else {
      sumEl.textContent = '';
    }
  }

  if (pctEl) pctEl.textContent = (isRunning || isDone) ? pct + '%' : '';
  if (area)  area.style.cursor = currentJobId ? 'pointer' : 'default';
}

// ── Render Output Panel (Phase 3) ────────────────────────────────────────

let _previewCurrentJobId = null;
let _previewCurrentPartNo = null;
let _previewCurrentOutputDir = null;
let _csPreviewJobId = null;
let _csPreviewPartNo = null;
let _csPreviewOutputFile = null;

function showRenderOutputPanel() {
  const p = qs('render_output_panel');
  if (!p) return;
  p.dataset.populated = '1';
  p.classList.remove('hiddenView');
}

function hideRenderOutputPanel() {
  const p = qs('render_output_panel');
  if (!p) return;
  p.dataset.populated = '0';
  p.classList.add('hiddenView');
}

function clearRenderOutputPanel() {
  _selectedClipPaths       = new Set();
  _uxr3AutoSelectedBest    = false;       // UX-R3-F
  resetAiStrategyPanel();
  const _sumEl = qs('mvRenderSummary');
  if (_sumEl) { _sumEl.innerHTML = ''; _sumEl.hidden = true; }
  const list = qs('render_output_list');
  if (list) list.innerHTML = '<div class="renderOutputEmpty">Clips will appear here when rendering starts</div>';
  const badge = qs('render_output_badge');
  if (badge) badge.textContent = '0';
  const path = qs('render_output_path');
  if (path) path.textContent = '';
  _hideCsPreviewArea();
  hideRenderOutputPanel();
}

function _hideCsPreviewArea() {
  const area = qs('cs_preview_area');
  if (area) area.classList.add('hiddenView');
}

function _resetCsPreview() {
  const video = qs('cs_preview_video');
  const bar = qs('cs_preview_bar');
  const empty = qs('cs_preview_empty');
  const loading = qs('cs_preview_loading');
  const error = qs('cs_preview_error');
  if (video) {
    if (video._csOnReady) { video.removeEventListener('canplay', video._csOnReady); video.removeEventListener('loadeddata', video._csOnReady); video._csOnReady = null; }
    if (video._csOnError) { video.removeEventListener('error', video._csOnError); video._csOnError = null; }
    video.pause(); video.src = ''; video.dataset.previewSrc = ''; video.classList.add('hiddenView');
  }
  if (bar) bar.classList.add('hiddenView');
  if (loading) loading.classList.add('hiddenView');
  if (error) { error.textContent = ''; error.classList.add('hiddenView'); }
  if (empty) empty.classList.remove('hiddenView');
  _csPreviewJobId = null;
  _csPreviewPartNo = null;
  _csPreviewOutputFile = null;
  document.querySelectorAll('.clipCard.isPreviewActive').forEach((el) => el.classList.remove('isPreviewActive'));
}

function closeCenterPreview() {
  _resetCsPreview();
  _hideCsPreviewArea();
}

function openCsPreviewFolder() {
  if (!_csPreviewOutputFile) return;
  const dir = String(_csPreviewOutputFile).replace(/\\/g, '/').split('/').slice(0, -1).join('/');
  openStoredOutputPath(dir || _csPreviewOutputFile);
}

function centerPreviewClip(jobId, partNo, outputFile, partName) {
  const st = String(outputFile || '').trim();
  if (!jobId || !partNo || !st) return;
  _csPreviewJobId = String(jobId);
  _csPreviewPartNo = Number(partNo);
  _csPreviewOutputFile = st;

  const area = qs('cs_preview_area');
  const video = qs('cs_preview_video');
  const bar = qs('cs_preview_bar');
  const empty = qs('cs_preview_empty');
  const loading = qs('cs_preview_loading');
  const errorEl = qs('cs_preview_error');
  const nameEl = qs('cs_preview_name');
  const metaEl = qs('cs_preview_meta');
  const dlLink = qs('cs_preview_download');
  if (!area || !video) return;

  const src = `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${Number(partNo)}/media`;
  const srcChanged = video.dataset.previewSrc !== src;

  if (srcChanged) {
    video.pause();
    video.src = '';
    video.dataset.previewSrc = src;
    // Reset to loading state
    if (empty) empty.classList.add('hiddenView');
    if (errorEl) { errorEl.textContent = ''; errorEl.classList.add('hiddenView'); }
    video.classList.add('hiddenView');
    if (loading) loading.classList.remove('hiddenView');

    // Remove stale handlers from any previous load that did not resolve
    if (video._csOnReady) { video.removeEventListener('canplay', video._csOnReady); video.removeEventListener('loadeddata', video._csOnReady); }
    if (video._csOnError) { video.removeEventListener('error', video._csOnError); }

    // Use both canplay and loadeddata: canplay requires HAVE_FUTURE_DATA which Electron
    // may not reach while the element is display:none; loadeddata fires at HAVE_CURRENT_DATA
    // (first frame decoded) and is reliable regardless of visibility state.
    const _onReady = function() {
      video.removeEventListener('canplay', _onReady);
      video.removeEventListener('loadeddata', _onReady);
      video._csOnReady = null;
      if (loading) loading.classList.add('hiddenView');
      video.classList.remove('hiddenView');
      video.muted = true;
      video.play().catch(() => {});
      console.log('[preview] loaded', src);
    };
    const _onError = function() {
      video.removeEventListener('error', _onError);
      video._csOnError = null;
      if (loading) loading.classList.add('hiddenView');
      video.classList.add('hiddenView');
      if (errorEl) {
        errorEl.textContent = 'Preview unavailable. Open the output folder to view this clip.';
        errorEl.classList.remove('hiddenView');
      }
      console.log('[preview] error', video.error && video.error.code, video.error && video.error.message || '');
    };
    video._csOnReady = _onReady;
    video._csOnError = _onError;
    video.addEventListener('canplay', _onReady);
    video.addEventListener('loadeddata', _onReady);
    video.addEventListener('error', _onError);

    console.log('[preview] src', src);
    video.src = src;
    video.load();
  } else {
    // Same source — ensure visible, hide loading/error overlays
    if (empty) empty.classList.add('hiddenView');
    if (loading) loading.classList.add('hiddenView');
    if (errorEl) errorEl.classList.add('hiddenView');
    video.classList.remove('hiddenView');
  }

  // Enrich bar with metadata from part record
  const part = (_renderMonitorLastParts || []).find((p) => Number(p.part_no) === Number(partNo));
  if (nameEl) nameEl.textContent = String(part?.part_name || partName || `Clip ${partNo}`);
  if (metaEl) {
    const chunks = [];
    if (part) {
      const dur = Number(part.end_sec || 0) - Number(part.start_sec || 0);
      if (dur > 0) chunks.push(`${Math.round(dur)}s`);
      const score = Number(part.score ?? part.viral_score ?? part.quality_score ?? NaN);
      if (!isNaN(score) && score > 0) chunks.push(`Score ${score.toFixed(1)}`);
    }
    metaEl.textContent = chunks.join(' · ');
  }
  if (dlLink) { dlLink.href = src; dlLink.setAttribute('download', `clip-${partNo}.mp4`); }

  // Aspect ratio from selected card
  const card = document.querySelector(`.clipCard[data-part-no="${Number(partNo)}"]`);
  const aspect = card?.dataset?.aspect || '16:9';
  area.dataset.aspect = aspect;

  if (bar) bar.classList.remove('hiddenView');
  area.classList.remove('hiddenView');
  area.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  document.querySelectorAll('.clipCard.isPreviewActive').forEach((el) => el.classList.remove('isPreviewActive'));
  if (card) card.classList.add('isPreviewActive');
}

// R7.1: Generate truthful clip reason from AI director output + raw signals + taste model.
// Prefers rk.reason when present; falls back to signal-derived text.
function _r7TruthfulReason(rk, motionScore, hookScore) {
  if (rk.reason) {
    var r = String(rk.reason);
    return r.length > 80 ? r.slice(0, 77) + '…' : r;
  }
  if (motionScore === null && hookScore === null) return null;
  var parts = [];
  if (hookScore !== null) {
    parts.push(hookScore >= 0.7 ? 'Strong opening hook' : hookScore >= 0.5 ? 'Moderate hook' : 'Weak hook');
  }
  if (motionScore !== null) {
    parts.push(motionScore >= 0.7 ? 'high motion energy' : motionScore >= 0.5 ? 'moderate motion' : 'low motion');
  }
  if (typeof CreatorMemory !== 'undefined') {
    try {
      var taste = CreatorMemory.getTasteModel();
      if (taste && taste.confident) {
        if (taste.hook === 'aggressive' && hookScore !== null && hookScore >= 0.65) {
          parts.push('matches your hook preference');
        } else if (taste.editStyle === 'cinematic' && motionScore !== null && motionScore < 0.5) {
          parts.push('fits your cinematic pace');
        }
      }
    } catch (_) {}
  }
  return parts.length ? parts.join(', ') + '.' : null;
}

// R7.1: Build signal chip row HTML for hook + motion scores.
// Tradeoff labels ("Stronger hook", "Better motion") appear when this non-best clip
// beats the best clip's score by a meaningful margin.
function _r7SignalRow(motionScore, hookScore, isBest, bestMotion, bestHook) {
  var chips = [];
  var tradeoffs = [];
  if (hookScore !== null) {
    var hp = Math.round(hookScore * 100);
    var hc = hookScore >= 0.7 ? 'sig-high' : hookScore >= 0.5 ? 'sig-mid' : 'sig-low';
    chips.push('<span class="clipCardSig ' + hc + '" data-sig="hook">Hook ' + hp + '%</span>');
    if (!isBest && bestHook !== null && hookScore > bestHook + 0.08) tradeoffs.push('Stronger hook');
  }
  if (motionScore !== null) {
    var mp = Math.round(motionScore * 100);
    var mc = motionScore >= 0.7 ? 'sig-high' : motionScore >= 0.5 ? 'sig-mid' : 'sig-low';
    chips.push('<span class="clipCardSig ' + mc + '" data-sig="motion">Motion ' + mp + '%</span>');
    if (!isBest && bestMotion !== null && motionScore > bestMotion + 0.08) tradeoffs.push('Better motion');
  }
  if (!chips.length) return '';
  var tradeoffHtml = tradeoffs.length
    ? '<div class="clipCardTradeoff">' + tradeoffs.join(' · ') + '</div>' : '';
  return '<div class="clipCardSignals">' + chips.join('') + tradeoffHtml + '</div>';
}

// R8.2.1: Builds the tradeoff panel HTML for two-clip comparison.
// Uses ONLY real signals: hook_score, motion_score, output_rank_score, AI reason.
// refRk and chalRk are entries from _rankMap(); refPart/chalPart from WS payload.
function _r821BuildTradeoffHtml(refPart, refRk, chalPart, chalRk) {
  // Scores are on 0–10 scale (per _rankMap / card display)
  const refScoreRaw  = Number(refRk.score  || 0);
  const chalScoreRaw = Number(chalRk.score || 0);
  const refScore  = refScoreRaw.toFixed(1);
  const chalScore = chalScoreRaw.toFixed(1);
  const refHook   = refPart.hook_score   != null ? Math.round(Number(refPart.hook_score)   * 100) : null;
  const chalHook  = chalPart.hook_score  != null ? Math.round(Number(chalPart.hook_score)  * 100) : null;
  const refMot    = refPart.motion_score != null ? Math.round(Number(refPart.motion_score) * 100) : null;
  const chalMot   = chalPart.motion_score!= null ? Math.round(Number(chalPart.motion_score)* 100) : null;
  const refName   = refPart.part_name  ? esc(refPart.part_name)  : ('Clip ' + Number(refPart.part_no  || 0));
  const chalName  = chalPart.part_name ? esc(chalPart.part_name) : ('Clip ' + Number(chalPart.part_no || 0));

  // Signal comparison rows — only show signals that exist on both clips
  var rows = '';
  if (refHook !== null && chalHook !== null) {
    const rW = refHook >= chalHook;
    rows += '<div class="r821TradeoffRow">' +
      '<span class="r821TradeoffSig">Hook</span>' +
      '<span class="r821TradeoffA' + (rW ? ' r821Wins' : '') + '">' + refHook  + '%</span>' +
      '<span class="r821TradeoffVs">vs</span>' +
      '<span class="r821TradeoffB' + (!rW ? ' r821Wins' : '') + '">' + chalHook + '%</span>' +
      '</div>';
  }
  if (refMot !== null && chalMot !== null) {
    const rW = refMot >= chalMot;
    rows += '<div class="r821TradeoffRow">' +
      '<span class="r821TradeoffSig">Motion</span>' +
      '<span class="r821TradeoffA' + (rW ? ' r821Wins' : '') + '">' + refMot  + '%</span>' +
      '<span class="r821TradeoffVs">vs</span>' +
      '<span class="r821TradeoffB' + (!rW ? ' r821Wins' : '') + '">' + chalMot + '%</span>' +
      '</div>';
  }
  // Score row always shown — ref is always the higher-scored clip (0–10 scale)
  rows += '<div class="r821TradeoffRow">' +
    '<span class="r821TradeoffSig">Score</span>' +
    '<span class="r821TradeoffA r821Wins">' + refScore  + '/10</span>' +
    '<span class="r821TradeoffVs">vs</span>' +
    '<span class="r821TradeoffB">' + chalScore + '/10</span>' +
    '</div>';

  // Reasoning — prefer AI director reason; synthesize from signals otherwise
  var reasoning = '';
  if (refRk.reason) {
    var _rr = String(refRk.reason);
    reasoning = _rr.length > 140 ? _rr.slice(0, 137) + '…' : _rr;
  } else {
    var _parts = [];
    const _confTier = refRk.confidenceTier || '';
    const _scoreGap = Math.round((refScoreRaw - chalScoreRaw) * 10) / 10;
    if (refHook !== null && chalHook !== null) {
      const hookDelta = refHook - chalHook;
      if (Math.abs(hookDelta) >= 5) {
        _parts.push(hookDelta > 0
          ? 'Hook +' + hookDelta + '% advantage.'
          : 'Challenger leads hook by ' + (-hookDelta) + '%.');
      }
    }
    if (refMot !== null && chalMot !== null) {
      const motDelta = refMot - chalMot;
      if (Math.abs(motDelta) >= 8) {
        _parts.push(motDelta > 0
          ? 'Motion +' + motDelta + '% advantage.'
          : 'Challenger leads motion by ' + (-motDelta) + '%.');
      }
    }
    var confPrefix = '';
    if (_confTier === 'experimental') confPrefix = 'Close call (+' + _scoreGap.toFixed(1) + ' pts). ';
    else if (_confTier === 'worth_testing') confPrefix = 'Slight edge (+' + _scoreGap.toFixed(1) + ' pts). ';
    reasoning = confPrefix + (_parts.join(' ') || 'Score reflects combined hook, motion, and quality signals.');
  }

  // Taste alignment — only when CreatorMemory is confident
  var tasteHtml = '';
  if (typeof CreatorMemory !== 'undefined') {
    try {
      var taste = CreatorMemory.getTasteModel();
      if (taste && taste.confident) {
        if (taste.hook === 'aggressive' && refHook !== null && chalHook !== null) {
          if (refHook > chalHook)
            tasteHtml = '<div class="r821TasteNote">Your profile favors strong openings — aligns with this result.</div>';
          else if (chalHook > refHook)
            tasteHtml = '<div class="r821TasteNote">Your profile favors strong openings — worth a second look at ' + chalName + '.</div>';
        } else if (taste.editStyle === 'cinematic' && refMot !== null && refMot < 40) {
          tasteHtml = '<div class="r821TasteNote">Your cinematic profile may favor lower-motion clips.</div>';
        }
      }
    } catch (_) {}
  }

  return '<div class="r821TradeoffSignals">' + rows + '</div>' +
    '<div class="r821Reasoning">' +
      '<div class="r821ReasoningLabel">Why ' + refName + ' ranked higher</div>' +
      '<div class="r821ReasoningText">' + esc(reasoning) + '</div>' +
    '</div>' +
    tasteHtml;
}

// R8.2.1: Enter in-panel clip compare mode.
// refPartNo = lead (best) clip; chalPartNo = challenger (strong candidate).
// No modal, no route change — injects compare strip above clips grid.
function r821EnterCompare(refPartNo, chalPartNo) {
  const panel = qs('render_output_panel');
  if (!panel) return;

  const job   = _renderMonitorLastJob;
  const parts = _renderMonitorLastParts;
  if (!job || !parts) return;

  const ranking = _rankMap(job);
  const refPart  = parts.find(function (p) { return Number(p.part_no || 0) === refPartNo;  }) || null;
  const chalPart = parts.find(function (p) { return Number(p.part_no || 0) === chalPartNo; }) || null;
  if (!refPart || !chalPart) return;

  const refRk  = ranking.get(refPartNo)  || { score: 0, reason: '' };
  const chalRk = ranking.get(chalPartNo) || { score: 0, reason: '' };

  _r821CompareRefPartNo  = refPartNo;
  _r821CompareChalPartNo = chalPartNo;

  // Remove any previous strip before rebuilding
  const prev = document.getElementById('r821_compare_strip');
  if (prev) prev.remove();

  const jId     = encodeURIComponent(String(job.job_id || ''));
  const refName = refPart.part_name  ? esc(refPart.part_name)  : ('Clip ' + refPartNo);
  const chalName= chalPart.part_name ? esc(chalPart.part_name) : ('Clip ' + chalPartNo);
  const refSrc  = jId && refPart.output_file
    ? '/api/render/jobs/' + jId + '/parts/' + refPartNo  + '/media' : '';
  const chalSrc = jId && chalPart.output_file
    ? '/api/render/jobs/' + jId + '/parts/' + chalPartNo + '/media' : '';

  const refVid  = refSrc
    ? '<video class="r821CompareVid" src="' + refSrc  + '" controls playsinline muted></video>'
    : '<div class="r821CompareVidFallback">No preview available</div>';
  const chalVid = chalSrc
    ? '<video class="r821CompareVid" src="' + chalSrc + '" controls playsinline muted></video>'
    : '<div class="r821CompareVidFallback">No preview available</div>';

  const strip = document.createElement('div');
  strip.id = 'r821_compare_strip';
  strip.className = 'r821CompareStrip';
  strip.innerHTML =
    '<div class="r821CompareHeader">' +
      '<span class="r821CompareTitle">Side-by-side comparison</span>' +
      '<button class="r821ExitBtn" type="button" onclick="r821ExitCompare()">Back to review</button>' +
    '</div>' +
    '<div class="r821CompareBody">' +
      '<div class="r821CompareLeft">' +
        '<div class="r821ClipLabel r821ClipLabelRef">Lead &middot; ' + refName + '</div>' +
        refVid +
      '</div>' +
      '<div class="r821CompareMid">' +
        _r821BuildTradeoffHtml(refPart, refRk, chalPart, chalRk) +
      '</div>' +
      '<div class="r821CompareRight">' +
        '<div class="r821ClipLabel">Candidate &middot; ' + chalName + '</div>' +
        chalVid +
      '</div>' +
    '</div>';

  const list = qs('render_output_list');
  if (list) panel.insertBefore(strip, list);
  else panel.appendChild(strip);

  panel.classList.add('r821Active');
  setTimeout(function () { strip.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 80);
}

// R8.2.1: Exit compare mode — removes strip, restores panel.
function r821ExitCompare() {
  const panel = qs('render_output_panel');
  const strip = document.getElementById('r821_compare_strip');
  if (strip) strip.remove();
  if (panel) panel.classList.remove('r821Active');
  _r821CompareRefPartNo  = null;
  _r821CompareChalPartNo = null;
}

// R8.2: Builds HTML for the editorial notes sidebar.
// Uses only real signals: ranking scores, hook/motion per clip, tier distribution.
// Returns empty string when AI director is off or no ranking data.
function _r8BuildEditorialNotes(job, all, ranking) {
  const aiEnabled = job && job.ai_director_enabled === true;
  const done = all.filter(function (p) {
    return ['done','completed','complete'].includes(String(p.status||'').toLowerCase());
  });
  if (!aiEnabled || ranking.size === 0 || done.length === 0) return '';

  // Locate best clip
  var bestPart = null, bestRk = null;
  ranking.forEach(function (rk, pNo) {
    if (rk.isBest) {
      bestPart = done.find(function (p) { return Number(p.part_no || 0) === pNo; }) || null;
      bestRk = rk;
    }
  });

  // Tier distribution (mirrors _applyUxR3Tiers threshold)
  const bestScore = bestRk ? Number(bestRk.score || 0) : 0;
  const strongThresh = bestScore * 0.85;
  var nBest = 0, nStrong = 0, nOther = 0;
  done.forEach(function (p) {
    const rk = ranking.get(Number(p.part_no || 0));
    if (!rk) { nOther++; return; }
    if (rk.isBest) { nBest++; return; }
    if (Number(rk.score || 0) >= strongThresh) nStrong++;
    else nOther++;
  });

  // Signal counts (real hook/motion scores from WS payload)
  var highHook = 0, highMotion = 0;
  done.forEach(function (p) {
    if (p.hook_score   != null && Number(p.hook_score)   >= 0.7) highHook++;
    if (p.motion_score != null && Number(p.motion_score) >= 0.7) highMotion++;
  });

  var html = '';

  // Lead clip section
  if (bestPart && bestRk) {
    const bName = bestPart.part_name ? esc(bestPart.part_name) : ('Clip ' + Number(bestPart.part_no || 0));
    const bScore  = Number(bestRk.score || 0).toFixed(1);   // 0–10 scale, display as X.X/10
    const bRaw  = String(bestRk.reason || '');
    const bReason = bRaw.length > 70 ? bRaw.slice(0, 67) + '…' : bRaw;
    html += '<div class="r8NotesSection">';
    html += '<div class="r8NotesSectionLabel">Lead Clip</div>';
    html += '<div class="r8NotesBestName">' + bName + '<span class="r8NotesBestScore">' + bScore + '</span></div>';
    if (bReason) html += '<div class="r8NotesBestReason">' + esc(bReason) + '</div>';
    html += '</div>';
  }

  // Tier breakdown + editing direction
  if (done.length > 1) {
    const direction = (nBest + nStrong >= 3)
      ? 'Strong field — lead first, cut from strong.'
      : (nStrong === 0)
        ? 'Single standout — lead clip dominates the cut.'
        : 'Review strong candidates before locking an order.';
    html += '<div class="r8NotesSection">';
    html += '<div class="r8NotesSectionLabel">Tier Breakdown</div>';
    html += '<div class="r8NotesTierRow">';
    html += '<span class="r8NotesTierChip r8NotesTierBest">' + nBest + ' best</span>';
    if (nStrong > 0) html += '<span class="r8NotesTierChip r8NotesTierStrong">' + nStrong + ' strong</span>';
    if (nOther  > 0) html += '<span class="r8NotesTierChip r8NotesTierOther">'  + nOther  + ' other</span>';
    html += '</div>';
    html += '<div class="r8NotesDirection">' + direction + '</div>';
    html += '</div>';
  }

  // Signal summary
  if (highHook > 0 || highMotion > 0) {
    html += '<div class="r8NotesSection">';
    html += '<div class="r8NotesSectionLabel">Signals</div>';
    if (highHook   > 0) html += '<div class="r8NotesSignalLine">' + highHook   + ' clip' + (highHook   !== 1 ? 's' : '') + ' strong hook (≥70%)</div>';
    if (highMotion > 0) html += '<div class="r8NotesSignalLine">' + highMotion + ' clip' + (highMotion !== 1 ? 's' : '') + ' high motion (≥70%)</div>';
    html += '</div>';
  }

  return html;
}

// UX-R3: Tier classification + header injection.
// Runs after list.innerHTML is built; safe to call on every re-render.
// Sets data-uxr3-tier on each card; inserts .uxr3TierHeader divs
// between tier groups (score-sort mode only).
function _applyUxR3Tiers(list, ranking, done, failed, skipped, aiDirectorEnabled) {
  if (!list) return;

  // ── Clean up any previous pass ────────────────────────
  list.querySelectorAll('.uxr3TierHeader').forEach(function (el) { el.remove(); });
  list.querySelectorAll('.uxr7NoRankBanner').forEach(function (el) { el.remove(); });
  list.querySelectorAll('.clipCard[data-uxr3-tier]').forEach(function (c) {
    delete c.dataset.uxr3Tier;
  });

  // R7.1: Honest fallback when AI Director explicitly disabled
  if (aiDirectorEnabled === false) {
    if (_clipsSortOrder === 'score') {
      var noRankBanner = document.createElement('div');
      noRankBanner.className = 'uxr7NoRankBanner';
      noRankBanner.textContent = 'AI ranking unavailable. Showing render order.';
      list.insertBefore(noRankBanner, list.firstChild);
    }
    return;
  }

  // ── Relative strong threshold (UX-R3.1-A) ───────────
  // Strong = within 15% of best clip's score. Fallback: DOM data-tier when ranking unavailable.
  var _bestScore = 0;
  ranking.forEach(function (rk) { if (rk.isBest && rk.score > _bestScore) _bestScore = rk.score; });
  if (!_bestScore) ranking.forEach(function (rk) { if (rk.score > _bestScore) _bestScore = rk.score; });
  var _strongThreshold = _bestScore > 0 ? _bestScore * 0.85 : -1;

  // ── Classify each card by tier ────────────────────────
  var bestCards    = [];
  var strongCards  = [];
  var otherCards   = [];
  var failedCards  = [];
  var skippedCards = [];

  Array.from(list.querySelectorAll('.clipCard')).forEach(function (card) {
    var partNo = Number(card.dataset.partNo || 0);
    var rk     = ranking.get(partNo) || {};
    if (card.classList.contains('isBestClip') || rk.isBest) {
      card.dataset.uxr3Tier = 'best';
      bestCards.push(card);
    } else if (card.classList.contains('isFailed')) {
      card.dataset.uxr3Tier = 'failed';
      failedCards.push(card);
    } else if (card.classList.contains('isSkipped')) {
      card.dataset.uxr3Tier = 'skipped';
      skippedCards.push(card);
    } else if (card.classList.contains('isDone')) {
      var isStrong;
      if (_strongThreshold > 0) {
        isStrong = (rk.score || 0) >= _strongThreshold;
      } else {
        // No ranking data: fall back to DOM data-tier="high"
        var scoreEl = card.querySelector('.clipCardScore');
        isStrong = scoreEl ? scoreEl.dataset.tier === 'high' : false;
      }
      if (isStrong) {
        card.dataset.uxr3Tier = 'strong';
        strongCards.push(card);
      } else {
        card.dataset.uxr3Tier = 'other';
        otherCards.push(card);
      }
    }
  });

  // ── Only insert headers in score-sort mode ───────────
  if (_clipsSortOrder !== 'score') return;

  function _makeHeader(label, count, extraClass) {
    var div = document.createElement('div');
    div.className = 'uxr3TierHeader' + (extraClass ? ' ' + extraClass : '');
    div.innerHTML =
      '<span class="uxr3TierLabel">' + label + '</span>' +
      (count != null ? '<span class="uxr3TierCount">' + count + '</span>' : '');
    return div;
  }

  // Strong Candidates header — only when there are both tiers above and below
  if (strongCards.length && (bestCards.length || otherCards.length || failedCards.length || skippedCards.length)) {
    list.insertBefore(_makeHeader('Strong Candidates', strongCards.length), strongCards[0]);
  }

  // Additional Results header — only when preceded by best or strong
  if (otherCards.length && (bestCards.length || strongCards.length)) {
    list.insertBefore(_makeHeader('Additional Results', otherCards.length), otherCards[0]);
  }

  // Needs Review header (collapsible) — failed + skipped
  var firstProblem = failedCards[0] || skippedCards[0];
  if (firstProblem) {
    var fLen   = failedCards.length;
    var sLen   = skippedCards.length;
    var fPart  = fLen ? (fLen + ' failed')  : '';
    var sPart  = sLen ? (sLen + ' skipped') : '';
    var label  = [fPart, sPart].filter(Boolean).join(' · ') || 'Needs Review';
    var header = _makeHeader(label, null, 'uxr3ProblemHeader');

    var btn = document.createElement('button');
    btn.className = 'uxr3TierToggle';
    btn.type      = 'button';
    btn.setAttribute('aria-label', 'Show or hide problem clips');
    header.appendChild(btn);

    // Start collapsed when there are successful clips
    var startCollapsed = done.length > 0;
    if (startCollapsed) {
      header.classList.add('uxr3Collapsed');
      btn.textContent = '▸';
    } else {
      btn.textContent = '▾';
    }

    btn.addEventListener('click', function () {
      var collapsed = header.classList.toggle('uxr3Collapsed');
      btn.textContent = collapsed ? '▸' : '▾';
    });

    list.insertBefore(header, firstProblem);
  }
}

function populateRenderOutputPanel(job, parts) {
  const list = qs('render_output_list');
  const badge = qs('render_output_badge');
  const pathEl = qs('render_output_path');
  if (!list) return;

  const items = collectRenderOutputItems(job, parts);
  const done = items.filter((p) => ['done', 'completed', 'complete'].includes(String(p?.status || '').toLowerCase()));
  const failed = items.filter((p) => ['failed', 'error'].includes(String(p?.status || '').toLowerCase()));
  const skipped = items.filter((p) => String(p?.status || '').toLowerCase() === 'skipped');
  // Sort done clips: by AI score desc when _clipsSortOrder==='score', else by part_no
  const ranking = _rankMap(job);
  const doneSorted = _clipsSortOrder === 'score'
    ? done.slice().sort((a, b) => {
        const sa = Number(ranking.get(Number(a.part_no || 0))?.score || 0);
        const sb = Number(ranking.get(Number(b.part_no || 0))?.score || 0);
        if (sb !== sa) return sb - sa;
        const ba = !!(ranking.get(Number(a.part_no || 0))?.isBest);
        const bb = !!(ranking.get(Number(b.part_no || 0))?.isBest);
        if (ba !== bb) return ba ? -1 : 1;
        return Number(a.part_no || 0) - Number(b.part_no || 0);
      })
    : done.slice().sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0));
  const all = [
    ...doneSorted,
    ...failed.sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0)),
    ...skipped.sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0)),
  ];

  // Seed selection with top-3 market viral clips
  _selectedClipPaths = new Set();
  const _opMvMap = _mvSegmentMap(job);
  const _opTop3  = _mvTop3Set(_opMvMap);
  done.forEach((p) => {
    if (_opTop3.has(Number(p.part_no)) && p.output_file) {
      _selectedClipPaths.add(p.output_file);
    }
  });
  _renderMvSummary(job, _opMvMap);

  if (badge) badge.textContent = String(done.length);

  const outputDir = getCurrentJobOutputDir(job);
  if (qs('abp_output_text')) qs('abp_output_text').textContent = outputDir ? `Output folder: ${outputDir}` : 'Output folder not set.';
  if (qs('abp_output_meta')) qs('abp_output_meta').textContent = 'Latest file will appear here.';
  if (qs('rc_open_output_btn')) qs('rc_open_output_btn').disabled = !outputDir;
  const failureInfo = renderFailureDetails(job, computeProgressSummary(items));
  if (pathEl) {
    if (failureInfo.count > 0 || failureInfo.warning) {
    const warningText = [
      failureInfo.count > 0 ? `${failureInfo.count} failed part${failureInfo.count === 1 ? '' : 's'}` : '',
      failureInfo.warning,
      ...failureInfo.details.slice(0, 3).map((d) => typeof d === 'string' ? d : JSON.stringify(d)),
    ].filter(Boolean).join(' · ');
      pathEl.textContent = warningText ? `Completed with errors: ${warningText}` : (outputDir ? `Output folder: ${outputDir}` : '');
    } else {
      pathEl.textContent = '';
    }
  }

  if (!all.length) {
    if (qs('abp_output_meta')) qs('abp_output_meta').textContent = 'Latest file will appear here.';
    // R7.4: status-aware empty message — no misleading "will appear" when render already failed
    const _emptyJobStatus = String(job?.status || '').toLowerCase();
    const _emptyIsFailed  = _emptyJobStatus === 'failed' || _emptyJobStatus === 'interrupted';
    const _emptyIsRunning = !_emptyIsFailed && _emptyJobStatus !== 'done' && _emptyJobStatus !== 'completed'
                            && _emptyJobStatus !== 'complete' && _emptyJobStatus !== 'completed_with_errors';
    const _emptyMsg = _emptyIsFailed
      ? 'Render stopped before any clips completed.'
      : _emptyIsRunning
      ? 'Clips will appear here as rendering progresses.'
      : 'Clips will appear here when rendering starts.';
    list.innerHTML = '<div class="renderOutputEmpty">' + _emptyMsg + '</div>';
    showRenderOutputPanel();
    return;
  }

  const jobId = String(job?.id || job?.job_id || currentJobId || '');
  const _jobPayload = getCurrentJobPayload(job);
  const _aspectRaw = String(_jobPayload?.aspect_ratio || '9:16');
  const _dataAspect = ['9:16', '3:4', '4:5', '1:1', '16:9'].includes(_aspectRaw) ? _aspectRaw : '9:16';

  // Phase 49C/49D — Parse best export reasons once, before card loop (hardened)
  const _cardAiUx = _parseAiUx(job);
  const _bestExportWhy = _cardAiUx && _cardAiUx.best_export && _cardAiUx.best_export.enabled
    ? _aiSafeList(_cardAiUx.best_export.why, 100, 3)
    : [];

  // R7.1: Read AI Director flag; precompute best clip signals for tradeoff comparison
  const _aiDirectorEnabled = _jobPayload.ai_director_enabled;
  let _bestMotion = null, _bestHook = null;
  all.forEach(function(bp) {
    const bpRk = ranking.get(Number(bp.part_no || 0)) || {};
    if (bpRk.isBest) {
      _bestMotion = bp.motion_score != null ? Number(bp.motion_score) : null;
      _bestHook   = bp.hook_score   != null ? Number(bp.hook_score)   : null;
    }
  });

  // R8.2.1: Pre-compute compare-eligible tiers (best + strong candidates)
  // Best clip is the reference; strong candidates show Compare vs best.
  var _r821BestPartNo    = null;
  var _r821SecondPartNo  = null;
  var _r821BestScore     = 0;
  var _r821SecondScore   = 0;
  ranking.forEach(function (rk, pNo) {
    if (rk.isBest) { _r821BestPartNo = pNo; _r821BestScore = Number(rk.score || 0); }
  });
  const _r821StrongThresh = _r821BestScore * 0.85;
  ranking.forEach(function (rk, pNo) {
    if (!rk.isBest && Number(rk.score || 0) >= _r821StrongThresh && Number(rk.score || 0) > _r821SecondScore) {
      _r821SecondScore = Number(rk.score || 0);
      _r821SecondPartNo = pNo;
    }
  });
  // Best clip Compare button compares best vs second-ranked strong candidate (if exists)
  // Strong candidate Compare button compares best vs that clip
  const _r821HasRankingData = ranking.size > 0 && _r821BestPartNo !== null;

  // UP18: Read creator's learned variant preference (null when no confident signal yet).
  const _cfVariantPref = (typeof CreatorFeedback !== 'undefined')
    ? ((CreatorFeedback.getVariantPreference() || {}).variant || '') : '';

  // UP14: Platform banner — shows when a non-default platform is selected for the job.
  const _jobTargetPlatform = String(getCurrentJobPayload(job)?.target_platform || '').trim().toLowerCase();
  const _platformBannerLabel = {tiktok:'TikTok',youtube_shorts:'YouTube Shorts',instagram_reels:'Instagram Reels'}[_jobTargetPlatform] || '';
  const _platformBanner = (_platformBannerLabel && _jobTargetPlatform !== 'youtube_shorts')
    ? `<div class="clipsPlatformBanner">Optimized for: ${esc(_platformBannerLabel)}</div>` : '';
  list.innerHTML = _platformBanner + all.map((p) => {
    const partNo = Number(p.part_no || 0);
    const st = String(p?.status || '').toLowerCase();
    const isFailed = st === 'failed' || st === 'error';
    const isSkipped = st === 'skipped';
    const isDone = st === 'done' || st === 'completed' || st === 'complete';
    const hasFile = !!p.output_file;
    const name = p.part_name ? esc(p.part_name) : `Clip ${partNo}`;
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const dur = Math.max(0, endSec - startSec).toFixed(1);
    const rk = ranking.get(partNo) || {};
    const statusText = isFailed ? 'failed' : isSkipped ? 'skipped' : isDone ? 'completed' : (st || 'pending');
    const scoreVal = Number(rk.score || 0);
    const hasScore = !!(rk.rank || rk.score);
    const scoreTier = scoreVal >= 8 ? 'high' : scoreVal >= 6 ? 'mid' : scoreVal >= 4 ? 'low' : 'weak';
    // R7.1: raw signal scores from parts payload
    const motionScore = p.motion_score != null ? Number(p.motion_score) : null;
    const hookScore   = p.hook_score   != null ? Number(p.hook_score)   : null;
    const _clipReason = _r7TruthfulReason(rk, motionScore, hookScore);
    // P1.7-F: static JPEG thumbnail (cached 24h) + lazy video for hover preview
    const _thumbBase = `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}`;
    // UP15: use smart cover offset when available; fall back to t=1 (1 second in).
    const _thumbT = rk.coverOffset > 0 ? rk.coverOffset : 1;
    const thumbHtml = isDone && hasFile && jobId
      ? `<img class="clipCardThumbImg" src="${_thumbBase}/thumbnail?t=${_thumbT}" loading="lazy" alt="" onerror="this.classList.add('is-error')">`
        + `<video class="clipCardThumbVid" data-src="${_thumbBase}/media" preload="none" muted playsinline></video>`
      : `<div class="clipCardThumbPlaceholder">${isFailed ? '✗' : isSkipped ? '—' : '⋯'}</div>`;
    const thumbAttrs = (isDone && hasFile && jobId)
      ? ` data-previewable="true" onclick="centerPreviewClip(${JSON.stringify(jobId)},${partNo},${JSON.stringify(p.output_file || '')},${JSON.stringify(p.part_name || `Clip ${partNo}`)})" style="cursor:pointer"`
      : '';
    const previewBtn = (!isFailed && !isSkipped && hasFile && jobId)
      ? `<button class="clipCardBtn clipCardBtnPreview" type="button" onclick="centerPreviewClip(${JSON.stringify(jobId)},${partNo},${JSON.stringify(p.output_file || '')},${JSON.stringify(p.part_name || `Clip ${partNo}`)})">Preview</button>`
      : '';
    const _dlVariant = JSON.stringify(rk.variantType || '');
    const downloadBtn = (!isFailed && hasFile && jobId)
      ? `<a class="clipCardBtn renderClipActionLink" href="/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/stream" download onclick="if(typeof CreatorTaste!=='undefined'&&${rk.rank||0}>0)CreatorTaste.recordDownload(${rk.rank||0});if(typeof CreatorFeedback!=='undefined'&&${_dlVariant})CreatorFeedback.recordVariantDownload(${_dlVariant})">Download</a>`
      : '';
    const openBtn = hasFile
      ? `<button class="clipCardBtn" type="button" onclick="openClipFile(${JSON.stringify(p.output_file)})">Folder</button>`
      : '';
    // R8.2.1: Compare button — best clip (vs second) or strong candidate (vs best)
    // scoreVal and _r821StrongThresh are both 0–10 scale
    const _r821IsRef    = _r821HasRankingData && rk.isBest;
    const _r821IsStrong = _r821HasRankingData && !rk.isBest && scoreVal >= _r821StrongThresh;
    const _r821RefPNo   = _r821IsRef ? partNo : _r821BestPartNo;
    const _r821ChalPNo  = _r821IsRef ? _r821SecondPartNo : partNo;
    const _r821ShowCmp  = isDone && hasFile && (
      (_r821IsRef && _r821SecondPartNo !== null) ||
      (_r821IsStrong && _r821BestPartNo !== null && partNo !== _r821BestPartNo)
    );
    const compareBtn = _r821ShowCmp
      ? `<button class="clipCardBtn clipCardBtnCompare" type="button" onclick="r821EnterCompare(${_r821RefPNo},${_r821ChalPNo})">Compare</button>`
      : '';
    // UP15: Cover button — opens the auto-exported thumbnail in the output folder.
    const coverBtn = (isDone && rk.coverFile)
      ? `<button class="clipCardBtn clipCardBtnCover" type="button" onclick="openClipFile(${JSON.stringify(rk.coverFile)})">Cover</button>`
      : '';
    if (qs('abp_output_meta') && hasFile) qs('abp_output_meta').textContent = `Latest file: ${String(p.output_file || '').split(/[\\\\/]/).pop()}`;
    const isSelected = isDone && hasFile && _selectedClipPaths.has(p.output_file);
    const cardClass = `clipCard${isFailed ? ' isFailed' : ''}${isSkipped ? ' isSkipped' : ''}${isDone ? ' isDone' : ''}${isSelected ? ' isSelected' : ''}${rk.isBest ? ' isBestClip' : ''}`;
    const failReasonRaw = isFailed ? String(p?.message || '').trim() : '';
    const failReasonClean = (failReasonRaw && !/(_ms=|\bpart_render\b|\w+=\w+)/.test(failReasonRaw)) ? failReasonRaw.slice(0, 80) : '';
    return `<div class="${cardClass}" data-clip-status="${esc(st || 'queued')}" data-part-no="${partNo}" data-aspect="${_dataAspect}">
      <div class="clipCardThumbWrap"${thumbAttrs}>
        ${thumbHtml}
        ${rk.isBest ? '<div class="clipCardBestFlag">Best</div>' : ''}
        <div class="clipCardDurTag">${dur}s</div>
      </div>
      <div class="clipCardBody">
        <div class="clipCardTitle">${name}</div>
        ${rk.variantType ? `<div class="clipCardVariantBadge" data-variant="${esc(rk.variantType)}">${
          rk.variantType === 'aggressive' ? 'Aggressive' :
          rk.variantType === 'balanced'   ? 'Balanced'   :
          rk.variantType === 'story_first'? 'Story-first': esc(rk.variantType)
        }${_cfVariantPref && rk.variantType === _cfVariantPref ? '<span class="cfVariantPref"> · recent</span>' : ''}</div>` : ''}
        <div class="clipCardScoreRow">
          ${hasScore
            ? `<span class="clipCardScore" data-tier="${scoreTier}">${scoreVal.toFixed(1)}<span class="clipCardScoreMax"> /10</span></span><span class="clipCardRankTag">#${rk.rank || '?'}</span>`
            : `<span class="clipCardScore" data-tier="weak">—</span>`}
          <span class="clipCardStatusDot" data-status="${esc(statusText)}" title="${esc(statusText)}"></span>
        </div>
        ${_clipReason ? `<div class="clipCardReason">${esc(_clipReason)}</div>` : ''}
        ${(motionScore !== null || hookScore !== null) && (rk.isBest || scoreVal >= 6) ? _r7SignalRow(motionScore, hookScore, rk.isBest, _bestMotion, _bestHook) : ''}
        ${failReasonClean ? `<div class="clipCardFailReason">${esc(failReasonClean)}</div>` : ''}
        ${_shouldRenderBestExport(_cardAiUx, rk.isBest) ? `<div class="aiux-best-export"><div class="aiux-best-title">Why this output?</div><ul class="aiux-best-reasons">${_bestExportWhy.map(function(w){return`<li class="aiux-best-reason"><span class="aiux-best-check">&#x2713;</span>${esc(w)}</li>`;}).join('')}</ul></div>` : ''}
        <div class="clipCardActions">${previewBtn}${downloadBtn}${openBtn}${coverBtn}${compareBtn}</div>
      </div>
    </div>`;
  }).join('');

  // Only reset preview when job changes; never auto-show the area
  const _prevArea = qs('cs_preview_area');
  if (_prevArea) {
    if (!all.length) {
      _hideCsPreviewArea();
    } else if (_csPreviewJobId !== null && _csPreviewJobId !== jobId) {
      _resetCsPreview();
      _hideCsPreviewArea();
    }
  }

  // P1.6-E: bind hover video previews on freshly rendered cards
  _bindCardHoverPreviews(list);

  // P2-C: inject AI review badges into output cards
  if (typeof EditorReviewIntelligence !== 'undefined') {
    const _rClips = (typeof EditorState !== 'undefined') ? EditorState.getState().clips     : [];
    const _rSubs  = (typeof EditorState !== 'undefined') ? EditorState.getState().subtitles : [];
    const _rDur   = (typeof EditorState !== 'undefined') ? EditorState.getState().duration  : 0;
    EditorReviewIntelligence.analyze(all, _rClips, _rSubs, _rDur);
    EditorReviewIntelligence.annotateCards(list);
  }

  renderAiStrategyPanel(job);
  // P2.9.1-A: Restore transient card classes wiped by full innerHTML replacement above
  if (typeof RenderAiRuntime !== 'undefined') RenderAiRuntime.reapplyTransientState();

  // UX-R3-A/B/C/D/E: Tier classification + headers
  _applyUxR3Tiers(list, ranking, done, failed, skipped, _aiDirectorEnabled);

  // R8.2: Editorial studio notes — real signals sidebar
  const _r8Panel = qs('render_output_panel');
  var _r8NotesEl = _r8Panel ? _r8Panel.querySelector('#r8_editorial_notes') : null;
  const _r8NotesBody = _r8BuildEditorialNotes(job, all, ranking);
  if (_r8NotesBody && _r8Panel) {
    if (!_r8NotesEl) {
      _r8NotesEl = document.createElement('div');
      _r8NotesEl.id = 'r8_editorial_notes';
      _r8NotesEl.className = 'r8EditorialNotes';
      _r8Panel.appendChild(_r8NotesEl);
    }
    _r8NotesEl.innerHTML = '<div class="r8NotesHeader">Editorial</div><div class="r8NotesSections">' + _r8NotesBody + '</div>';
    _r8Panel.classList.add('r8StudioActive');
  } else {
    if (_r8NotesEl) _r8NotesEl.innerHTML = '';
    if (_r8Panel) _r8Panel.classList.remove('r8StudioActive');
  }

  // UX-R3-F: Auto-open best clip in center preview once on completion
  if (!_uxr3AutoSelectedBest) {
    var _r3Status   = String(job && job.status || '').toLowerCase();
    var _r3Terminal = _r3Status === 'done' || _r3Status === 'completed' ||
                      _r3Status === 'complete' || _r3Status === 'completed_with_errors';
    if (_r3Terminal) {
      var _r3BestEntry = null;
      ranking.forEach(function (rk, pNo) { if (rk.isBest) _r3BestEntry = [pNo, rk]; });
      if (_r3BestEntry) {
        var _r3PartNo = _r3BestEntry[0];
        var _r3Part   = done.find(function (p) { return Number(p.part_no || 0) === _r3PartNo; });
        if (_r3Part && _r3Part.output_file && typeof centerPreviewClip === 'function') {
          _uxr3AutoSelectedBest = true;
          setTimeout(function () {
            // UX-R3.1-C: Skip if creator already opened a preview manually
            if (_csPreviewJobId !== null || _cardHoverActiveVid !== null) return;
            centerPreviewClip(currentJobId, _r3PartNo, _r3Part.output_file, _r3Part.part_name || ('Clip ' + _r3PartNo));
          }, 900);
        }
      }
    }
  }

  showRenderOutputPanel();
  renderBottomActiveQueue(job, computeProgressSummary(items), items);
  const panel = qs('render_output_panel');
  if (panel) setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80);
}

// ── P1.6-E: Hover video preview on output cards ──────────────────────────────
// Plays clip thumbnail video silently on hover; pauses and resets on leave.
// IntersectionObserver prevents activation for off-screen cards.
let _cardHoverObserver = null;
let _cardHoverActiveVid = null;

function _stopCardHoverVideo() {
  if (_cardHoverActiveVid) {
    _cardHoverActiveVid.pause();
    _cardHoverActiveVid.currentTime = 1;
    const card = _cardHoverActiveVid.closest?.('.clipCard');
    if (card) card.classList.remove('is-preview-playing');
    _cardHoverActiveVid = null;
  }
}

function _bindCardHoverPreviews(container) {
  if (!container) return;

  // Disconnect stale observer from previous render
  if (_cardHoverObserver) { _cardHoverObserver.disconnect(); _cardHoverObserver = null; }
  _stopCardHoverVideo();

  _cardHoverObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      const vid = entry.target.querySelector('.clipCardThumbVid');
      if (vid) vid._cardInView = entry.isIntersecting;
      // Pause if card scrolls out of view while playing
      if (!entry.isIntersecting && _cardHoverActiveVid === vid) _stopCardHoverVideo();
    });
  }, { threshold: 0.2 });

  container.querySelectorAll('.clipCard').forEach(card => {
    _cardHoverObserver.observe(card);

    const thumbWrap = card.querySelector('.clipCardThumbWrap');
    const vid       = card.querySelector('.clipCardThumbVid');
    if (!thumbWrap || !vid) return;

    // UX-R5: Direct assignment prevents listener accumulation on re-render
    thumbWrap.onmouseenter = () => {
      if (vid._cardInView === false) return;
      if (_cardHoverActiveVid === vid) return;
      _stopCardHoverVideo();
      // Lazy-set src on first hover so browser doesn't download until needed
      if (!vid.getAttribute('src') && vid.dataset.src) vid.src = vid.dataset.src;
      _cardHoverActiveVid = vid;
      vid.currentTime = 0;
      vid.loop = true;
      vid.muted = true;
      vid.play().catch(() => {});
      card.classList.add('is-preview-playing');
    };

    thumbWrap.onmouseleave = () => {
      if (_cardHoverActiveVid === vid) _stopCardHoverVideo();
    };
  });
}

function sortClipsView(val) {
  _clipsSortOrder = val || 'score';
  if (_renderMonitorLastJob) {
    populateRenderOutputPanel(_renderMonitorLastJob, _renderMonitorLastParts);
  } else {
    // UX-R3.1-B: DOM-only fallback when job data unavailable — rebuild tier headers in-place
    var _r31List = document.getElementById('render_output_list');
    if (_r31List) {
      _applyUxR3Tiers(
        _r31List, new Map(),
        Array.from(_r31List.querySelectorAll('.clipCard.isDone')),
        Array.from(_r31List.querySelectorAll('.clipCard.isFailed')),
        Array.from(_r31List.querySelectorAll('.clipCard.isSkipped'))
      );
    }
  }
}

function previewClip(jobId, partNo) {
  // Redirect to center-stage inline preview if we have part data
  const part = (_renderMonitorLastParts || []).find((p) => Number(p.part_no) === Number(partNo));
  if (part && part.output_file) {
    centerPreviewClip(jobId, partNo, part.output_file, part.part_name || '');
    return;
  }
  // Fallback: open modal when part record unavailable
  const modal = qs('clip_preview_modal');
  const video = qs('clip_preview_video');
  const title = qs('clip_preview_title');
  if (!modal || !video) return;
  _previewCurrentJobId = jobId;
  _previewCurrentPartNo = partNo;
  const src = `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/media`;
  if (title) title.textContent = `Clip ${partNo}`;
  video.src = src;
  video.load();
  modal.classList.remove('hiddenView');
}

function closeClipPreview(event) {
  const modal = qs('clip_preview_modal');
  if (!modal) return;
  if (event && event.target !== modal) return;
  const video = qs('clip_preview_video');
  if (video) { video.pause(); video.src = ''; }
  modal.classList.add('hiddenView');
  _previewCurrentJobId = null;
  _previewCurrentPartNo = null;
}

function openCurrentClipFolder() {
  if (_previewCurrentOutputDir) {
    openStoredOutputPath(_previewCurrentOutputDir);
    return;
  }
  if (!currentJobId) return;
  fetch(`/api/jobs/${encodeURIComponent(currentJobId)}`)
    .then((r) => r.json())
    .then((job) => {
      const out = getCurrentJobOutputDir(job);
      if (out) openStoredOutputPath(out);
      else showToast('Output folder is unavailable', 'info');
    })
    .catch(() => showToast('Unable to load output folder path', 'error'));
}

function openClipFile(filePath) {
  const p = String(filePath || '').trim();
  if (!p) { showToast('File path is unavailable', 'info'); return; }
  const dir = p.replace(/\\/g, '/').split('/').slice(0, -1).join('/');
  openStoredOutputPath(dir || p);
}

// ── AI Insights Panel (Phase 7) ───────────────────────────────────────────────

function _aiBarLevel(pct) {
  const n = Number(pct) || 0;
  if (n >= 70) return 'high';
  if (n >= 40) return 'mid';
  return 'low';
}

function _aiBarRowHtml(label, pct) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  const lvl = _aiBarLevel(p);
  return `<div class="aiBarRow"><span class="aiBarLabel">${esc(label)}</span><div class="aiBar"><div class="aiBarFill" data-level="${lvl}" style="--ai-bar-pct:${p}%"></div></div><span class="aiBarPct">${p}%</span></div>`;
}

function _aiEnergyLabel(level) {
  if (level === null || level === undefined) return null;
  const e = Number(level);
  if (isNaN(e)) return null;
  if (e > 0.75) return 'High';
  if (e > 0.4) return 'Moderate';
  return 'Low';
}

function renderAiInsights(job) {
  const panel = qs('ai_insights_panel');
  const body = qs('ai_insights_body');
  const confBadge = qs('ai_conf_badge');
  if (!panel) return;

  let result = {};
  try {
    const raw = job && job.result_json;
    result = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
  } catch (_) {}

  const aiDir = result && result.ai_director;

  if (!aiDir || !aiDir.enabled) {
    panel.classList.add('hiddenView');
    return;
  }

  panel.classList.remove('hiddenView');
  if (typeof _evSetAiPlan === 'function') _evSetAiPlan(aiDir);

  const summary  = aiDir.ai_summary   || {};
  const conf     = aiDir.ai_confidence || {};
  const fullConf = aiDir.confidence    || {};
  const pacing   = aiDir.pacing        || {};
  const camera   = aiDir.camera        || {};
  const subtitle = aiDir.subtitle      || {};
  const memCtx   = aiDir.memory_context || {};

  // Confidence badge
  const overall = conf.overall != null ? Number(conf.overall) : null;
  if (confBadge) {
    confBadge.textContent = overall != null ? `${overall}%` : '–';
    confBadge.dataset.level = overall != null ? _aiBarLevel(overall) : '';
  }

  if (!body) return;

  const parts = [];

  // ── 1. Summary headline + bullets ─────────────────────────────
  const headline = String(summary.headline || '').trim();
  const lines = Array.isArray(summary.summary_lines) ? summary.summary_lines.slice(0, 5) : [];
  if (headline || lines.length) {
    let h = '<div class="aiInSection">';
    if (headline) h += `<div class="aiHeadline">${esc(headline)}</div>`;
    if (lines.length) {
      h += '<ul class="aiSummaryList">';
      lines.forEach(l => { h += `<li class="aiSummaryItem">${esc(String(l))}</li>`; });
      h += '</ul>';
    }
    h += '</div>';
    parts.push(h);
  }

  // ── 2. Confidence bars ─────────────────────────────────────────
  const semConf = conf.semantic != null ? Number(conf.semantic) : null;
  const memConf = conf.memory   != null ? Number(conf.memory)   : null;
  const pacConf = conf.pacing   != null ? Number(conf.pacing)   : null;
  if (semConf !== null || memConf !== null || pacConf !== null) {
    let h = '<div class="aiInSection"><div class="aiInSectionTitle">Confidence</div><div class="aiConfGrid">';
    if (semConf !== null) h += _aiBarRowHtml('Semantic', semConf);
    if (pacConf !== null) h += _aiBarRowHtml('Pacing', pacConf);
    if (memConf !== null) h += _aiBarRowHtml('Memory', memConf);
    h += '</div></div>';
    parts.push(h);
  }

  // ── 3. Pacing + Camera cards (2-col grid) ─────────────────────
  const cutStyle   = String(pacing.suggested_cut_style || '');
  const emotion    = String(pacing.emotion || '');
  const bpm        = pacing.bpm != null ? Number(pacing.bpm) : null;
  const energyLbl  = _aiEnergyLabel(pacing.energy_level);
  const camBhv     = String(camera.behavior || 'none');
  const camZoom    = camera.zoom_strength != null ? Number(camera.zoom_strength) : null;

  let cardH = '<div class="aiInSection"><div class="aiInsightGrid">';

  // Pacing card
  cardH += '<div class="aiInsightCard"><div class="aiInsightCardTitle">Pacing</div><div class="aiInsightCardRow">';
  if (cutStyle && cutStyle !== 'standard') cardH += `<span class="aiInsightCardBadge">${esc(cutStyle.replace(/_/g,' '))}</span>`;
  if (bpm !== null) cardH += `<span class="aiInsightCardBadge">${bpm.toFixed(0)} BPM</span>`;
  if (emotion && emotion !== 'neutral') cardH += `<span class="aiInsightCardBadge">${esc(emotion)}</span>`;
  if (energyLbl) cardH += `<span class="aiInsightCardBadge${energyLbl === 'High' ? ' green' : energyLbl === 'Moderate' ? ' amber' : ''}">${esc(energyLbl)}</span>`;
  if (!cutStyle && bpm === null && !energyLbl) cardH += `<span class="aiInsightMuted">${esc(String(pacing.pacing_style || 'default'))}</span>`;
  cardH += '</div></div>';

  // Camera card
  cardH += '<div class="aiInsightCard"><div class="aiInsightCardTitle">Camera</div><div class="aiInsightCardRow">';
  if (camBhv && camBhv !== 'none') {
    cardH += `<span class="aiInsightCardBadge">${esc(camBhv.replace(/_/g,' '))}</span>`;
    if (camZoom !== null && camZoom > 1.0) cardH += `<span class="aiInsightCardBadge">${camZoom.toFixed(2)}x</span>`;
  } else {
    cardH += `<span class="aiInsightMuted">Disabled</span>`;
  }
  if (camera.subtitle_safe) cardH += `<span class="aiInsightCardBadge green">sub-safe</span>`;
  cardH += '</div></div>';

  cardH += '</div></div>';
  parts.push(cardH);

  // ── 4. Subtitle card ──────────────────────────────────────────
  const subTone    = String(subtitle.tone || 'default');
  const subEmph    = String(subtitle.emphasis_style || 'none');
  const subDensity = String(subtitle.density || 'normal');
  const beatAware  = !!subtitle.beat_aware;
  const emAware    = !!subtitle.emotion_aware;
  if (subTone !== 'default' || subEmph !== 'none' || beatAware || emAware) {
    let h = '<div class="aiInSection"><div class="aiInsightCard aiInsightCardWide"><div class="aiInsightCardTitle">Subtitles</div><div class="aiInsightCardRow">';
    if (subTone !== 'default') h += `<span class="aiInsightCardBadge">${esc(subTone)} tone</span>`;
    if (subEmph !== 'none')    h += `<span class="aiInsightCardBadge">${esc(subEmph)} emphasis</span>`;
    if (subDensity !== 'normal') h += `<span class="aiInsightCardBadge">${esc(subDensity)} density</span>`;
    if (beatAware) h += `<span class="aiInsightCardBadge green">beat-aware</span>`;
    if (emAware)   h += `<span class="aiInsightCardBadge green">emotion-aware</span>`;
    h += '</div></div></div>';
    parts.push(h);
  }

  // ── 5. Memory card (only when results present) ─────────────────
  const memResults = Array.isArray(memCtx.results) ? memCtx.results : [];
  if (memResults.length > 0) {
    const mode = String(aiDir.mode || '');
    let h = '<div class="aiInSection"><div class="aiMemCard">';
    h += '<div class="aiMemCardTitle">Memory</div>';
    h += `<div class="aiMemCardRow">Similar renders found: <strong>${memResults.length}</strong>`;
    if (mode) h += ` · <span style="color:var(--text-dim)">${esc(mode.replace(/_/g,' '))}</span>`;
    h += '</div></div></div>';
    parts.push(h);
  }

  // ── 6. Warnings (compact pills, only non-empty) ─────────────────
  const summaryWarnings = Array.isArray(summary.warnings) ? summary.warnings : [];
  if (summaryWarnings.length) {
    const pills = summaryWarnings
      .map(w => `<span class="aiWarnPill">${esc(String(w))}</span>`)
      .join('');
    parts.push(`<div class="aiInSection"><div class="aiWarnRow">${pills}</div></div>`);
  }

  body.innerHTML = parts.join('');
}

function resetAiInsightsPanel() {
  if (typeof EditorReviewIntelligence !== 'undefined') EditorReviewIntelligence.reset();
  const panel = qs('ai_insights_panel');
  if (panel) panel.classList.add('hiddenView');
  const body = qs('ai_insights_body');
  if (body) body.innerHTML = '';
  const badge = qs('ai_conf_badge');
  if (badge) { badge.textContent = '–'; badge.dataset.level = ''; }
}

// ── Phase 49D — AI UX Hardening Helpers ──────────────────────────────────────

function _aiSafeText(s, maxLen) {
  // Trims, rejects literal "null"/"undefined", truncates if over maxLen.
  try {
    const t = String(s == null ? '' : s).trim();
    if (!t || t === 'null' || t === 'undefined') return '';
    return (maxLen > 0 && t.length > maxLen) ? t.slice(0, maxLen - 1) + '…' : t;
  } catch (_) { return ''; }
}

function _aiSafeList(arr, maxLen, maxItems) {
  // Filters, trims, deduplicates, and bounds an array to safe non-empty strings.
  if (!Array.isArray(arr)) return [];
  const cap = maxItems > 0 ? maxItems : 5;
  const seen = new Set();
  const out = [];
  for (let i = 0; i < arr.length && out.length < cap; i++) {
    const s = _aiSafeText(arr[i], maxLen > 0 ? maxLen : 120);
    if (s && !seen.has(s)) { seen.add(s); out.push(s); }
  }
  return out;
}

function _aiClampConf(v) {
  // Returns confidence clamped [0,1] rounded to 2dp, or null if non-finite.
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.round(Math.min(1, Math.max(0, n)) * 100) / 100;
}

function _parseAiUx(job) {
  // Returns the ai_ux object when available === true, null otherwise. Never throws.
  try {
    const raw = job && job.result_json;
    const obj = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
    const aiUx = obj && obj.ai_ux;
    if (aiUx && aiUx.available === true) return aiUx;
  } catch (_) {}
  return null;
}

function _shouldRenderAiStrategy(aiUx) {
  // Returns true only when there is at least one displayable content section.
  if (!aiUx) return false;
  const s = aiUx.strategy || {};
  return !!(
    _aiSafeList(s.recommendations, 120, 5).length ||
    _aiSafeList(s.why, 120, 4).length ||
    _aiSafeText(s.creator_style, 60) ||
    _aiSafeText(s.target_market, 40) ||
    _aiClampConf(s.confidence) != null
  );
}

function _shouldRenderBestExport(aiUx, isBest) {
  // Returns true only when best card has enabled reasons from ai_ux.
  if (!isBest || !aiUx) return false;
  const be = aiUx.best_export || {};
  return !!(be.enabled && _aiSafeList(be.why, 100, 3).length);
}

// ── Phase 49B — AI Strategy Panel ────────────────────────────────────────────

function renderAiStrategyPanel(job) {
  // Inject a compact AI Strategy panel above the clips list inside render_output_panel.
  // Silently no-ops when ai_ux is missing, unavailable, or has no displayable content.
  try {
    const container = qs('render_output_panel');
    const listEl    = qs('render_output_list');
    if (!container || !listEl) return;

    // Remove any previously injected panel (idempotent on re-render)
    const existing = document.getElementById('aiux_strategy_panel');
    if (existing) existing.remove();

    const aiUx = _parseAiUx(job);
    if (!aiUx || !_shouldRenderAiStrategy(aiUx)) return;

    const strategy      = aiUx.strategy       || {};
    const safeInfluence = aiUx.safe_influence  || {};

    const confRaw  = _aiClampConf(strategy.confidence);
    const confPct  = confRaw != null ? Math.round(confRaw * 100) : null;
    const confLevel = confPct != null ? (confPct >= 80 ? 'high' : confPct >= 60 ? 'mid' : 'low') : '';
    const creatorStyle = _aiSafeText(strategy.creator_style, 60);
    const targetMarket = _aiSafeText(strategy.target_market, 40);
    const recs     = _aiSafeList(strategy.recommendations, 120, 5);
    const why      = _aiSafeList(strategy.why, 120, 4);
    const applied  = !!safeInfluence.applied;
    const infItems = applied ? _aiSafeList(safeInfluence.items, 120, 4) : [];

    let h = '<div id="aiux_strategy_panel" class="aiux-panel" role="region" aria-label="AI Strategy">';

    // ── Header ──────────────────────────────────────────────────────────────
    h += '<div class="aiux-header">';
    h += '<span class="aiux-title">AI Strategy</span>';
    if (confPct != null) {
      h += `<span class="aiux-conf-badge" data-level="${confLevel}">${confPct}% confidence</span>`;
    }
    h += '</div>';

    // ── Body ────────────────────────────────────────────────────────────────
    h += '<div class="aiux-body">';

    if (creatorStyle || targetMarket) {
      h += '<div class="aiux-chips">';
      if (creatorStyle) h += `<span class="aiux-chip aiux-chip--style">${esc(creatorStyle)}</span>`;
      if (targetMarket) h += `<span class="aiux-chip aiux-chip--market">${esc(targetMarket)}</span>`;
      h += '</div>';
    }

    if (recs.length) {
      h += '<div class="aiux-section"><div class="aiux-section-label">Recommended</div><ul class="aiux-list">';
      recs.forEach(function(r) { h += `<li class="aiux-list-item"><span class="aiux-check">&#x2713;</span>${esc(r)}</li>`; });
      h += '</ul></div>';
    }

    if (why.length) {
      h += '<div class="aiux-section"><div class="aiux-section-label">Why</div><ul class="aiux-list aiux-list--why">';
      why.forEach(function(w) { h += `<li class="aiux-list-item"><span class="aiux-bullet">&bull;</span>${esc(w)}</li>`; });
      h += '</ul></div>';
    }

    if (applied && infItems.length) {
      h += '<div class="aiux-section"><div class="aiux-section-label">AI Adjustments</div><ul class="aiux-list">';
      infItems.forEach(function(item) { h += `<li class="aiux-list-item"><span class="aiux-check aiux-check--applied">&#x2736;</span>${esc(item)}</li>`; });
      h += '</ul></div>';
    }

    h += '</div></div>'; // .aiux-body + .aiux-panel

    const wrap = document.createElement('div');
    wrap.innerHTML = h;
    const panelNode = wrap.firstElementChild;
    if (panelNode) container.insertBefore(panelNode, listEl);
  } catch (_) {
    // Silently ignore — never crash the render result
  }
}

function resetAiStrategyPanel() {
  // Remove injected AI Strategy panel when output panel is cleared.
  try {
    const panel = document.getElementById('aiux_strategy_panel');
    if (panel) panel.remove();
  } catch (_) {}
}

/* =======================================================
   P2.6 — Render Intelligence Runtime
   Non-destructive overlay: AI process card, clip evolution
   feed, AI reasoning stream, completion intelligence.
   ======================================================= */
const RenderAiRuntime = (() => {
  'use strict';

  const _STAGES = [
    { key: 'init',     label: 'Reading the Room',      backends: ['queued', 'starting'],               icon: '◉', msg: 'Calibrating your workspace to the source material' },
    { key: 'source',   label: 'Studying the Source',   backends: ['downloading'],                      icon: '⬇', msg: 'Understanding what you gave us — format, quality, and length' },
    { key: 'scene',    label: 'Mapping the Story',     backends: ['scene_detection'],                  icon: '⬜', msg: 'Finding where scenes breathe and cuts want to happen' },
    { key: 'audio',    label: 'Listening for Hooks',   backends: ['transcribing_full'],                icon: '♪', msg: 'Speech becomes a map — every word timed to the frame' },
    { key: 'beat',     label: 'Feeling the Rhythm',    backends: ['transcribing_full'],                icon: '♩', msg: 'Matching cadence to clip scoring — pacing defines the cut' },
    { key: 'segment',  label: 'Spotting the Moments',  backends: ['segment_building'],                 icon: '▦', msg: 'Candidate clips surfaced and ranked by density of strong material' },
    { key: 'scoring',  label: 'Scoring the Clips',     backends: ['segment_building', 'rendering'],    icon: '▤', msg: 'Retention signal measured — which clips earn their place' },
    { key: 'assembly', label: 'Building the Cut',      backends: ['rendering'],                        icon: '◧', msg: 'AI director ordering the sequence for maximum impact' },
    { key: 'encode',   label: 'Rendering',             backends: ['rendering', 'rendering_parallel'],  icon: '▶', msg: 'Your clips are being born — transforms, color, and audio applied' },
    { key: 'validate', label: 'Checking Quality',      backends: ['rendering_parallel'],               icon: '✓', msg: 'Every clip verified against your quality bar before delivery' },
    { key: 'report',   label: 'Writing the Brief',     backends: ['writing_report'],                   icon: '▤', msg: 'Per-clip intelligence compiled — the story of your render' },
    { key: 'export',   label: 'Finishing',             backends: ['done', 'completed'],                icon: '⬆', msg: 'Packaging your clips — ready to review and export' },
  ];

  const _REASONING = {
    init:     'Workspace open. Source parameters locked and ready to begin.',
    source:   'Source ingested — stream quality and duration confirmed.',
    scene:    'Natural cuts mapped — editorial boundaries found in your footage.',
    audio:    'Every word timed to the frame. Speech rhythm captured as a scoring map.',
    beat:     'Audio cadence feeds the scoring model — pacing will match your material.',
    segment:  'Clip windows identified and ranked by concentration of strong material.',
    scoring:  'Retention signal live — AI scoring each candidate against viral thresholds.',
    assembly: 'Sequence decided. AI director assembled the edit order for impact.',
    encode:   'Clips rendering now — your vision is being written to file.',
    validate: 'Quality check running — timing, sync, and bitrate verified per clip.',
    report:   'Intelligence compiled — your per-clip scores and editorial brief are ready.',
    export:   'Delivery complete. Your clips are ready to review and export.',
  };

  let _mounted                = false;
  let _lastStageIdx           = -1;
  let _reasonItems            = [];
  let _lastPartCount          = 0;
  let _completionNarrativeSet = false;
  let _arrivalTriggered       = false;    // P2.9.1-C: idempotent arrival
  let _morphPending           = false;    // P2.9.1-E: no overlapping morphs
  let _maxKnownTotal          = 0;        // P2.9.1-B: stable denominator
  let _lastConfidenceLevel    = '';       // P2.9.1-B: monotonic advance only
  const _transientCards       = new Map(); // P2.9.1-A: partNo → {elevated,causal,expiresAt}
  let _lastConcernHash        = '';       // P3.4: dedup concern renders
  let _lastHeroConcernHash   = '';       // UX-R1: dedup hero concern renders

  function mountPanels() {
    if (_mounted) return;
    _mounted = true;
    const queuePanel = document.querySelector('.rcQueuePanel');
    const partCards  = document.getElementById('rc_part_cards');
    if (queuePanel && !document.getElementById('rc_ai_process_cards')) {
      const el = document.createElement('div');
      el.id = 'rc_ai_process_cards';
      el.className = 'rcAiProcessCards hiddenView';
      if (partCards) queuePanel.insertBefore(el, partCards);
      else queuePanel.appendChild(el);
    }
    if (queuePanel && !document.getElementById('rc_ai_evolution_feed') && partCards) {
      const el = document.createElement('div');
      el.id = 'rc_ai_evolution_feed';
      el.className = 'rcAiEvolutionFeed hiddenView';
      el.innerHTML =
        '<div class="rcAiEvolutionHeader"><span>Clip Intelligence</span></div>' +
        '<div id="rc_ai_evolution_list" class="rcAiEvolutionList"></div>';
      queuePanel.insertBefore(el, partCards);
    }
    const logList = document.getElementById('event_log_render');
    if (logList && !document.getElementById('rc_ai_reason_feed')) {
      const el = document.createElement('div');
      el.id = 'rc_ai_reason_feed';
      el.className = 'rcAiReasonFeed hiddenView';
      el.innerHTML =
        '<div class="rcAiReasonHeader">' +
          '<span class="rcAiReasonLabel">AI Reasoning</span>' +
          '<span class="rcAiReasonBadge">Live</span>' +
        '</div>' +
        '<div id="rc_ai_reason_list" class="rcAiReasonList"></div>';
      logList.parentElement.insertBefore(el, logList);
    }
  }

  function _stageIdx(backendStage) {
    if (!backendStage) return -1;
    const s = String(backendStage).toLowerCase();
    for (let i = 0; i < _STAGES.length; i++) {
      if (_STAGES[i].backends.includes(s)) return i;
    }
    return -1;
  }

  function update(backendStage, status, parts, summary) {
    mountPanels();
    const isComplete = status === 'done' || status === 'completed' || status === 'completed_with_errors';
    const isFailed   = status === 'failed' || status === 'interrupted';
    const rawIdx     = _stageIdx(backendStage);
    const newIdx     = isComplete ? _STAGES.length - 1 : rawIdx;
    if (newIdx >= 0 && newIdx !== _lastStageIdx) {
      _lastStageIdx = newIdx;
      _pushReason(_STAGES[newIdx].key);
      _showReasonFeed();
    }
    _updateProcessCard(newIdx, isFailed);
    _updateEvolutionFeed(parts);
    _renderConcernItems(parts);
    _updateHero(newIdx, isFailed, parts, summary);
  }

  function _updateProcessCard(idx, isFailed) {
    const el = document.getElementById('rc_ai_process_cards');
    if (!el) return;
    if (idx < 0) { el.classList.add('hiddenView'); return; }
    const stg = _STAGES[idx];
    if (!stg) { el.classList.add('hiddenView'); return; }
    el.classList.remove('hiddenView');
    const pct   = Math.round((idx / (_STAGES.length - 1)) * 100);
    const state = isFailed ? 'failed' : idx === _STAGES.length - 1 ? 'done' : 'running';

    // P2.9-C: Continuity — same stage → only update progress bar, no hard replace
    const prevCard = el.querySelector('.rcAiProcCard');
    if (prevCard && prevCard.querySelector('.rcAiProcLabel')?.textContent === stg.label) {
      const fill  = prevCard.querySelector('.rcAiProcFill');
      const pctEl = prevCard.querySelector('.rcAiProcPct');
      if (fill)  fill.style.setProperty('--w', pct + '%');
      if (pctEl) pctEl.textContent = pct + '%';
      return;
    }

    // Stage changed — morph transition: fade out → swap → fade in
    // P2.9.1-E: Skip morph class if one is already pending (rapid WS ticks)
    if (prevCard && !_morphPending) {
      _morphPending = true;
      el.classList.add('p29Morphing');
    }
    requestAnimationFrame(() => {
      el.innerHTML =
        '<div class="rcAiProcCard" data-state="' + state + '">' +
          '<div class="rcAiProcIcon">' + stg.icon + '</div>' +
          '<div class="rcAiProcBody">' +
            '<div class="rcAiProcLabel">' + esc(stg.label) + '</div>' +
            '<div class="rcAiProcMsg">' + esc(stg.msg) + '</div>' +
          '</div>' +
          '<div class="rcAiProcMeta">' +
            '<span class="rcAiProcPct">' + pct + '%</span>' +
            '<div class="rcAiProcBar"><div class="rcAiProcFill" style="--w:' + pct + '%"></div></div>' +
          '</div>' +
        '</div>';
      el.classList.remove('p29Morphing');
      _morphPending = false;
    });
  }

  // R8.1.1: Co-pilot action map — EditorConsensus action → first-person reason + expected impact.
  // All entries derive from real agent signals. No invented copy.
  const _COPILOT_ACTION = {
    strongerHook:            { doing: "I'm tightening the opening",     because: 'opening retention is below your recent edits',      impact: 'stronger opening hold' },
    fasterPacing:            { doing: "I'm reducing slower moments",    because: 'pacing is softer than your recent editing style',    impact: 'steadier viewing rhythm' },
    removeDeadSpace:         { doing: "I'm trimming dead air",          because: 'silences are extending beyond natural beat points',  impact: 'tighter overall cut' },
    viralMode:               { doing: "I'm amplifying signal density",  because: 'overall energy is below your viral threshold',       impact: 'higher retention curve' },
    cinematicMode:           { doing: "I'm preserving narrative beats", because: 'pacing aligns with your cinematic edit profile',     impact: 'stronger story rhythm' },
    subtitleCleanup:         { doing: "I'm clearing subtitle clutter",  because: 'text density is reducing visual clarity',            impact: 'cleaner visual focus' },
    smartClipPrioritization: { doing: "I'm reordering by signal",      because: 'hook scores suggest a stronger opening sequence',    impact: 'better opening impact' },
  };

  // R8.1.1: Build co-pilot narrative from real signals.
  // Returns { line1, line2, impact } — one collaborative voice, no fragments.
  // line1  = what stage / how many clips  (always shown)
  // line2  = WHY the AI is doing what it's doing (co-pilot action or clip signal)
  // impact = expected outcome (shown only when co-pilot action is active)
  function _r8BuildNarrative(stgKey, parts, summary) {
    const safeParts = Array.isArray(parts) ? parts : [];
    const done = safeParts.filter(function (p) {
      const st = String(p.status || '').toLowerCase();
      return st === 'done' || st === 'completed' || st === 'complete';
    });
    const total    = safeParts.length;
    const stuckMap = _stuckPartsMap(summary, safeParts);

    // line1: stage context with live counts
    const stageNarr = {
      init:     'Setting up your creative workspace.',
      source:   'Studying the source — format, quality, and duration.',
      scene:    'Mapping where scenes breathe and cuts want to happen.',
      audio:    'Reading the transcript rhythm to align pacing.',
      beat:     'Matching audio cadence to clip scoring.',
      segment:  'Surfacing your strongest moments from the source.',
      scoring:  (total - done.length) > 0
                  ? 'Scoring ' + (total - done.length) + ' remaining clip' + ((total - done.length) !== 1 ? 's' : '') + '.'
                  : 'Measuring retention signal across clips.',
      assembly: 'Sequencing clips for maximum opening impact.',
      encode:   (done.length > 0 && total > 0)
                  ? done.length + ' of ' + total + ' clip' + (total !== 1 ? 's' : '') + ' rendered.'
                  : 'Encoding your clips.',
      validate: 'Verifying each clip meets your quality bar.',
      report:   'Compiling per-clip intelligence.',
      export:   'Packaging your clips — ready to review.',
    };
    var line1  = stageNarr[stgKey] || 'Processing.';
    var line2  = '';
    var impact = '';

    // Priority 1: stall — calm, collaborative, never alarmist
    if (stuckMap.size > 0) {
      const firstKey  = stuckMap.keys().next().value;
      const stuckSecs = stuckMap.get(firstKey);
      const mins      = Math.floor(stuckSecs / 60);
      const stuckPart = safeParts.find(function (p) { return String(p.part_no ?? '') === String(firstKey); });
      const stuckName = stuckPart ? (stuckPart.part_name || ('Clip ' + firstKey)) : ('Clip ' + firstKey);
      line2 = esc(stuckName) + ' is taking ' + (mins > 1 ? mins + ' min' : 'longer than expected') +
              '. You can continue reviewing completed clips while recovery continues.';
      return { line1, line2, impact };
    }

    // Priority 2: active agent consensus action → co-pilot action reasoning
    // Only fires when confidence >= 0.65 and EditorConsensus is loaded.
    if (typeof EditorConsensus !== 'undefined') {
      try {
        const debate = EditorConsensus.resolveFromLive(safeParts);
        if (debate && debate.action && debate.confidence >= 0.65) {
          const cp = _COPILOT_ACTION[debate.action];
          if (cp) {
            line2  = cp.doing + ' — ' + cp.because + '.';
            impact = cp.impact;
            return { line1, line2, impact };
          }
        }
      } catch (_) {}
    }

    // Priority 3: last completed clip with co-pilot clip-action voice
    if (done.length > 0) {
      const last   = done[done.length - 1];
      const name   = last.part_name ? esc(last.part_name) : ('Clip ' + Number(last.part_no || 0));
      const hook   = last.hook_score   != null ? Number(last.hook_score)   : null;
      const motion = last.motion_score != null ? Number(last.motion_score) : null;
      var clipLine = '';
      try {
        const taste = (typeof CreatorMemory !== 'undefined') ? CreatorMemory.getTasteModel() : null;
        if (hook !== null && motion !== null) {
          if (hook >= 0.7 && motion >= 0.65) {
            clipLine = taste && taste.confident && taste.hook === 'aggressive'
              ? "I'm moving this toward the front — matches your hook profile."
              : "I'm keeping this — strong hook and motion.";
          } else if (hook >= 0.7) {
            clipLine = "I'm keeping this toward the top — opening retention is strong.";
          } else if (motion >= 0.7) {
            clipLine = taste && taste.confident && taste.pace === 'fast'
              ? "I'm preserving this energy — fits your fast-pacing profile."
              : "I'm preserving this — high motion holds attention.";
          } else if (hook < 0.35) {
            clipLine = taste && taste.confident && taste.hook === 'aggressive'
              ? "I'm ranking this lower — hook falls below your usual threshold."
              : "I'm ranking this lower — hook signal is weak.";
          } else {
            clipLine = "I'm scoring this as a solid candidate.";
          }
        } else {
          clipLine = "I'm scoring this for the output.";
        }
      } catch (_) { clipLine = ''; }
      line2 = name + ' completed. ' + clipLine;
      return { line1, line2, impact };
    }

    // Priority 4: taste alignment before any clips arrive
    if (typeof CreatorMemory !== 'undefined') {
      try {
        const taste = CreatorMemory.getTasteModel();
        if (taste && taste.confident && taste.editStyle && taste.editStyle !== 'balanced') {
          const styleMap = {
            viral:       "I'm prioritizing viral energy — based on your recent review patterns.",
            cinematic:   "I'm preserving cinematic pacing — based on your recent review patterns.",
            educational: "I'm prioritizing clarity-first editing — based on your recent review patterns.",
          };
          line2 = styleMap[taste.editStyle] || '';
        }
      } catch (_) {}
    }

    return { line1, line2, impact };
  }

  function _updateHero(idx, isFailed, parts, summary) {
    const heroEl = document.getElementById('uxr1_ai_hero');
    if (!heroEl) return;
    const stgIcon  = document.getElementById('uxr1_stage_icon');
    const stgLabel = document.getElementById('uxr1_stage_label');
    const stgMsg   = document.getElementById('uxr1_stage_msg');
    if (idx >= 0 && _STAGES[idx]) {
      const stg = _STAGES[idx];
      if (stgIcon)  stgIcon.textContent  = stg.icon;
      if (stgLabel) stgLabel.textContent = stg.label;
      // R8.1: stgMsg is suppressed; editorial narrative takes its place
      if (stgMsg) stgMsg.hidden = true;
      heroEl.dataset.stage  = stg.key;
      heroEl.dataset.failed = isFailed ? '1' : '';

      // R8.1: Inject single editorial narrative into .uxr1StageBody
      const narr = _r8BuildNarrative(stg.key, parts, summary);
      var narrEl = heroEl.querySelector('#uxr1_narrative');
      if (!narrEl) {
        narrEl = document.createElement('div');
        narrEl.id = 'uxr1_narrative';
        narrEl.className = 'uxr1Narrative';
        const bodyEl = heroEl.querySelector('.uxr1StageBody');
        if (bodyEl) bodyEl.appendChild(narrEl);
        else heroEl.appendChild(narrEl);
      }
      narrEl.innerHTML =
        '<p class="uxr1NarrL1">' + narr.line1 + '</p>' +
        (narr.line2 ? '<p class="uxr1NarrL2">' + narr.line2 + '</p>' : '') +
        (narr.impact ? '<p class="uxr1NarrImpact">' + esc(narr.impact) + '</p>' : '');
    }

    // R7.2/R8.1: Stall is surfaced in the editorial narrative (line2). Remove any old .uxr1StallWarn.
    const _oldStall = heroEl.querySelector('.uxr1StallWarn');
    if (_oldStall) _oldStall.remove();

    const concernsEl = document.getElementById('uxr1_concerns');
    if (!concernsEl) return;
    const concerns = (typeof RuntimeIntelligence !== 'undefined')
      ? RuntimeIntelligence.getConcerns(Array.isArray(parts) ? parts : [])
      : [];
    const hash = concerns.map(c => c.type + ':' + c.label).join('|');
    if (hash === _lastHeroConcernHash) return;
    _lastHeroConcernHash = hash;
    if (!concerns.length) { concernsEl.innerHTML = ''; return; }
    // R8.1.1-E: Concerns are supporting evidence, not competing cards
    concernsEl.innerHTML =
      '<div class="uxr1ConcernsLabel">Supporting signals</div>' +
      concerns.map(function (c) {
        return '<div class="uxr1ConcernItem" data-concern-type="' + esc(c.type) + '">' +
          '<div class="uxr1ConcernLabel">' + esc(c.label) + '</div>' +
          '<div class="uxr1ConcernMsg">'   + esc(c.msg)   + '</div>' +
          '</div>';
      }).join('');
  }

  function _updateEvolutionFeed(parts) {
    if (!Array.isArray(parts) || !parts.length) return;
    const done = parts.filter(p => {
      const st = String(p.status || '').toLowerCase();
      return st === 'done' || st === 'completed' || st === 'complete';
    });
    if (done.length <= _lastPartCount) return;
    const newOnes = done.slice(_lastPartCount);
    _lastPartCount = done.length;
    const listEl = document.getElementById('rc_ai_evolution_list');
    const feedEl = document.getElementById('rc_ai_evolution_feed');
    if (!listEl || !feedEl) return;
    feedEl.classList.remove('hiddenView');
    newOnes.forEach(p => {
      const pNo    = Number(p.part_no || 0);
      // R8.1: Use part_name when available, not generic "Clip N"
      const pName  = p.part_name ? esc(p.part_name) : ('Clip ' + esc(String(pNo)));
      const rawSc  = p.viral_score != null ? Number(p.viral_score) : null;
      const pct    = rawSc !== null ? Math.round(rawSc * 100) : null;
      const hook   = p.hook_score   != null ? Number(p.hook_score)   : null;
      const motion = p.motion_score != null ? Number(p.motion_score) : null;
      const tier   = pct !== null ? (pct >= 75 ? 'high' : pct >= 50 ? 'mid' : 'low') : 'low';
      // R8.1.1-D: Co-pilot voice — "I'm [action]ing this" from real signals + taste
      var editWhy = '';
      try {
        const _evTaste = (typeof CreatorMemory !== 'undefined') ? CreatorMemory.getTasteModel() : null;
        if (hook !== null && motion !== null) {
          if (hook >= 0.7 && motion >= 0.65) {
            editWhy = _evTaste && _evTaste.confident && _evTaste.hook === 'aggressive'
              ? "I'm moving this toward the front — matches your hook profile."
              : "I'm keeping this — strong hook and motion.";
          } else if (hook >= 0.7) {
            editWhy = "I'm keeping this toward the top — opening retention is strong.";
          } else if (motion >= 0.7) {
            editWhy = _evTaste && _evTaste.confident && _evTaste.pace === 'fast'
              ? "I'm preserving this energy — fits your fast-pacing profile."
              : "I'm preserving this — high motion holds attention.";
          } else if (hook < 0.35 && motion < 0.4) {
            editWhy = _evTaste && _evTaste.confident && _evTaste.hook === 'aggressive'
              ? "I'm ranking this lower — falls below your hook threshold."
              : "I'm ranking this lower — weaker opening signal.";
          } else {
            editWhy = "I'm scoring this as a solid candidate.";
          }
        }
      } catch (_) {}
      const ctx = (typeof RuntimeIntelligence !== 'undefined')
        ? RuntimeIntelligence.getEvolutionContext(pNo, pct, tier)
        : { why: tier === 'high' ? 'Strong hook from the first frame — this one is a keeper.' : tier === 'mid' ? 'Solid clip — good bones, room to sharpen the hook.' : 'Lower signal — may not crack the top picks.', tasteNote: null };
      const why = editWhy || ctx.why;
      const scoreHtml = pct !== null ? '<span class="p28EvolScore">' + pct + '%</span>' : '';
      const tasteHtml = ctx.tasteNote ? '<span class="p34EvolTaste">' + esc(ctx.tasteNote) + '</span>' : '';
      const row = document.createElement('div');
      row.className = 'p28EvolItem tier-' + tier;
      row.innerHTML =
        '<div class="p28EvolSignal"></div>' +
        '<div class="p28EvolContent">' +
          '<div class="p28EvolHead">' +
            '<span class="p28EvolName">' + pName + '</span>' +
            scoreHtml +
          '</div>' +
          '<div class="p28EvolWhy">' + esc(why) + tasteHtml + '</div>' +
        '</div>';
      listEl.insertBefore(row, listEl.firstChild);
      // Keep max 6 clip items; concern items are excluded from count
      const clipItems = listEl.querySelectorAll('.p28EvolItem');
      while (clipItems.length > 6) listEl.removeChild(clipItems[clipItems.length - 1]);
      _syncOutputCard(pNo, tier);
    });
    // P2.9-F: Apply confidence evolution to best card after each batch
    _applyConfidenceEvolution(done.length, parts.length);
  }

  // P3.4: Render editorial concern items inside the evolution list.
  // Concerns are taste-aware and based on real signals only.
  function _renderConcernItems(parts) {
    const listEl = document.getElementById('rc_ai_evolution_list');
    if (!listEl) return;
    const concerns = (typeof RuntimeIntelligence !== 'undefined')
      ? RuntimeIntelligence.getConcerns(parts) : [];
    const hash = concerns.map(c => c.type).join(',');
    if (hash === _lastConcernHash) return;
    _lastConcernHash = hash;
    listEl.querySelectorAll('.p34ConcernItem').forEach(el => el.remove());
    if (!concerns.length) return;
    const feedEl = document.getElementById('rc_ai_evolution_feed');
    if (feedEl) feedEl.classList.remove('hiddenView');
    concerns.forEach(c => {
      const el = document.createElement('div');
      el.className = 'p34ConcernItem';
      el.dataset.concernType = c.type;
      el.innerHTML =
        '<div class="p34ConcernSignal"></div>' +
        '<div class="p34ConcernBody">' +
          '<div class="p34ConcernLabel">' + esc(c.label) + '</div>' +
          '<div class="p34ConcernMsg">' + esc(c.msg) + '</div>' +
        '</div>';
      listEl.appendChild(el);
    });
  }

  function _pushReason(stageKey) {
    const msg = _REASONING[stageKey];
    if (!msg) return;
    _reasonItems.push({ stageKey, msg });
    if (_reasonItems.length > 10) _reasonItems.shift();
    _renderReasonFeed();
  }

  function _renderReasonFeed() {
    const el = document.getElementById('rc_ai_reason_list');
    if (!el) return;
    el.innerHTML = _reasonItems.slice().reverse().map(item =>
      '<div class="rcAiReasonItem" data-stage="' + item.stageKey + '">' +
        '<span class="rcAiReasonDot"></span>' +
        '<span class="rcAiReasonText">' + esc(item.msg) + '</span>' +
      '</div>'
    ).join('');
  }

  function _showReasonFeed() {
    const el = document.getElementById('rc_ai_reason_feed');
    if (el) el.classList.remove('hiddenView');
  }

  function _syncOutputCard(partNo, tier) {
    const card = document.querySelector('.clipCard[data-part-no="' + partNo + '"]');
    if (!card) return;
    // P2.9.1-A: Register transient state so reapplyTransientState() can restore after re-renders
    const expiresAt = Date.now() + 2600;
    _transientCards.set(partNo, { elevated: true, causal: tier === 'high', expiresAt });
    // P2.8-B: pulse
    card.classList.remove('p28ClipMoment');
    void card.offsetWidth;
    card.classList.add('p28ClipMoment');
    // P2.9-A: causal elevation + editorial consequence
    card.classList.add('p29Elevated');
    if (tier === 'high') card.classList.add('p29Causal');
    setTimeout(() => {
      _transientCards.delete(partNo);
      const c = document.querySelector('.clipCard[data-part-no="' + partNo + '"]');
      if (c) c.classList.remove('p28ClipMoment', 'p29Elevated', 'p29Causal');
    }, 2600);
  }

  function reapplyTransientState() {
    // P2.9.1-A: Called by populateRenderOutputPanel after full re-render to restore transient classes
    const now = Date.now();
    _transientCards.forEach((state, partNo) => {
      if (state.expiresAt <= now) { _transientCards.delete(partNo); return; }
      const card = document.querySelector('.clipCard[data-part-no="' + partNo + '"]');
      if (!card) return;
      if (state.elevated) card.classList.add('p29Elevated');
      if (state.causal)   card.classList.add('p29Causal');
    });
    if (_lastConfidenceLevel) {
      const bestCard = document.querySelector('.clipCard.isBestClip');
      if (bestCard) bestCard.dataset.p29Confidence = _lastConfidenceLevel;
    }
  }

  function _applyConfidenceEvolution(doneCount, totalCount) {
    // P2.9.1-B: Stable denominator — never shrink the known total across ticks
    _maxKnownTotal = Math.max(_maxKnownTotal, totalCount);
    const denominator = _maxKnownTotal || 1;
    const ratio    = doneCount / denominator;
    const newLevel = ratio < 0.3 ? 'emerging' : ratio < 0.62 ? 'rising' : ratio < 0.88 ? 'strong' : 'peak';
    // P2.9.1-B: Monotonic advance — never regress (emerging→rising→strong→peak only)
    const ORDER = ['', 'emerging', 'rising', 'strong', 'peak'];
    if (ORDER.indexOf(newLevel) <= ORDER.indexOf(_lastConfidenceLevel)) return;
    _lastConfidenceLevel = newLevel;
    const bestCard = document.querySelector('.clipCard.isBestClip');
    if (bestCard) bestCard.dataset.p29Confidence = newLevel;
  }

  function _triggerCompletionArrival() {
    // P2.9.1-C: Idempotent — once per render session, safe across WS reconnects
    if (_arrivalTriggered) return;
    _arrivalTriggered = true;
    const panel = document.getElementById('render_active_panel');
    if (panel) {
      panel.classList.add('p29Arrival');
      setTimeout(() => { if (panel) panel.classList.remove('p29Arrival'); }, 1500);
    }
    const header = document.querySelector('.rcAiEvolutionHeader span');
    if (header) header.textContent = 'Creative Outcome';
  }

  // UX-R2-A: Morph #uxr1_ai_hero from orchestration to outcome reveal
  function _morphHeroToOutcome(narrative) {
    const heroEl = document.getElementById('uxr1_ai_hero');
    if (!heroEl) return;
    heroEl.classList.add('uxr2OutcomeMode');
    const iconEl  = document.getElementById('uxr1_stage_icon');
    const labelEl = document.getElementById('uxr1_stage_label');
    const msgEl   = document.getElementById('uxr1_stage_msg');
    const concEl  = document.getElementById('uxr1_concerns');
    if (iconEl)  iconEl.textContent  = '✓';
    if (labelEl) labelEl.textContent = 'Creative Outcome';
    if (msgEl)   msgEl.textContent   = narrative.summaryMsg || '';
    if (concEl)  concEl.innerHTML    = '';
  }

  // UX-R2-B/C/D/E/F: Populate and reveal #uxr2_completion_hero
  function _showCompletionHero(job, parts, narrative, completed, topPct) {
    const heroEl = document.getElementById('uxr2_completion_hero');
    if (!heroEl) return;

    const jobId      = String(job?.id || job?.job_id || '');
    const rk         = (typeof _rankMap === 'function') ? _rankMap(job) : new Map();
    const bestEntry  = [...rk.entries()].find(([, r]) => r.isBest);
    const bestPartNo = bestEntry ? bestEntry[0] : null;
    const bestRkData = bestEntry ? bestEntry[1] : null;
    const bestPart   = bestPartNo != null
      ? completed.find(p => Number(p.part_no || 0) === bestPartNo)
      : null;
    const hasBest    = !!(bestPart && jobId && bestPartNo != null);

    // ── Thumb ──────────────────────────────────────────────
    const thumbEl = document.getElementById('uxr2_hero_thumb');
    if (thumbEl) {
      if (hasBest) {
        const thumbBase    = '/api/render/jobs/' + encodeURIComponent(jobId) + '/parts/' + bestPartNo;
        const bestViralPct = Math.round(Number(bestPart.viral_score || 0) * 100) || topPct;
        thumbEl.innerHTML =
          '<img class="uxr2ThumbImg" src="' + thumbBase + '/thumbnail?t=1" alt="" onerror="this.classList.add(\'is-error\')">' +
          '<video class="uxr2ThumbVid" data-src="' + thumbBase + '/media" preload="none" muted playsinline></video>' +
          '<div class="uxr2ThumbScore">' + bestViralPct + '%</div>';
        const vidEl = thumbEl.querySelector('.uxr2ThumbVid');
        if (vidEl) {
          // UX-R5: Direct assignment prevents listener accumulation across completion sessions
          thumbEl.onmouseenter = function () {
            if (!vidEl.src && vidEl.dataset.src) vidEl.src = vidEl.dataset.src;
            vidEl.classList.add('uxr2VidActive');
            vidEl.play().catch(function () {});
          };
          thumbEl.onmouseleave = function () {
            vidEl.classList.remove('uxr2VidActive');
            vidEl.pause();
          };
        }
      } else {
        heroEl.dataset.state = 'no-best';
      }
    }

    // ── Narrative ───────────────────────────────────────────
    const narrativeMsgEl = document.getElementById('uxr2_narrative_msg');
    if (narrativeMsgEl) {
      narrativeMsgEl.textContent = !completed.length
        ? 'AI could not confidently identify a strongest result.'
        : (narrative.summaryMsg || '');
    }
    const narrativeReasonEl = document.getElementById('uxr2_narrative_reason');
    if (narrativeReasonEl && bestRkData && bestRkData.reason) {
      narrativeReasonEl.textContent = bestRkData.reason;
      narrativeReasonEl.hidden      = false;
    }
    const narrativeBitsEl = document.getElementById('uxr2_narrative_bits');
    if (narrativeBitsEl && narrative.bits && narrative.bits.length) {
      narrativeBitsEl.innerHTML = narrative.bits
        .map(function (b) { return '<span class="uxr2Bit">' + esc(b) + '</span>'; })
        .join('');
    }

    // ── CTAs ────────────────────────────────────────────────
    const reviewBtn = document.getElementById('uxr2_cta_review');
    if (reviewBtn) {
      if (hasBest) {
        reviewBtn.onclick = function () {
          if (typeof centerPreviewClip === 'function') {
            centerPreviewClip(jobId, bestPartNo, bestPart.output_file || '', bestPart.part_name || ('Clip ' + bestPartNo));
          }
        };
      } else {
        reviewBtn.textContent = 'Review Clips';
        reviewBtn.onclick = function () {
          const panel = document.getElementById('render_output_panel');
          if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        };
      }
    }
    const exportLink = document.getElementById('uxr2_cta_export');
    if (exportLink && hasBest) {
      exportLink.href = '/api/jobs/' + encodeURIComponent(jobId) + '/parts/' + bestPartNo + '/stream';
      exportLink.removeAttribute('hidden');
    }
    const folderBtn = document.getElementById('uxr2_cta_folder');
    if (folderBtn) {
      folderBtn.onclick = function () {
        if (typeof openRenderOutputFolder === 'function') openRenderOutputFolder();
      };
    }

    // ── Demote completion bar; elevate output list ──────────
    const bar = document.getElementById('render_completion_bar');
    if (bar) bar.classList.add('uxr2BarDemoted');
    const listEl = document.getElementById('render_output_list');
    if (listEl) listEl.classList.add('uxr2Complete');

    // ── Reveal ──────────────────────────────────────────────
    heroEl.classList.remove('hiddenView');
    requestAnimationFrame(function () { heroEl.classList.add('uxr2HeroActive'); });
  }

  function showCompletionIntelligence(job, summary, parts) {
    const insightEl  = document.getElementById('rc_benchmark_insight');
    const benchPanel = document.getElementById('rc_benchmark_panel');
    if (!insightEl || !benchPanel) return;
    const allParts  = Array.isArray(parts) ? parts : [];
    const completed = allParts.filter(p => {
      const st = String(p.status || '').toLowerCase();
      return st === 'done' || st === 'completed' || st === 'complete';
    });
    if (!completed.length) return;
    const scores   = completed.map(p => Number(p.viral_score || 0));
    const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
    const topScore = Math.max(...scores);
    const avgPct   = Math.round(avgScore * 100);
    const topPct   = Math.round(topScore * 100);
    const tier     = avgPct >= 70 ? 'high' : avgPct >= 50 ? 'mid' : 'low';
    const topTier  = topPct >= 70 ? 'high' : topPct >= 50 ? 'mid' : 'low';
    const totalAll = allParts.length || Number(summary?.total_parts || 0);

    // P3.4: Taste-aware completion narrative
    const narrative = (typeof RuntimeIntelligence !== 'undefined')
      ? RuntimeIntelligence.getCompletionNarrative(avgPct, topPct, completed.length)
      : { summaryMsg: avgPct >= 70 ? 'Strong output batch — average viral signal is above retention threshold.' : avgPct >= 50 ? 'Solid batch with room to optimize — hook selection could be refined.' : 'Output complete — consider re-scoring with tighter clip selection.', bits: [], tasteNote: null };

    const tasteNoteHtml = narrative.tasteNote
      ? '<div class="p34TasteNote">' + esc(narrative.tasteNote) + '</div>'
      : '';

    insightEl.classList.remove('hiddenView');
    insightEl.innerHTML =
      '<div class="rcAiCompCard">' +
        '<div class="rcAiCompRow">' +
          '<span class="rcAiCompLabel">Avg Viral Score</span>' +
          '<span class="rcAiCompScore" data-tier="' + tier + '">' + avgPct + '%</span>' +
        '</div>' +
        '<div class="rcAiCompRow">' +
          '<span class="rcAiCompLabel">Top Clip</span>' +
          '<span class="rcAiCompScore" data-tier="' + topTier + '">' + topPct + '%</span>' +
        '</div>' +
        '<div class="rcAiCompRow">' +
          '<span class="rcAiCompLabel">Clips Rendered</span>' +
          '<span class="rcAiCompCount">' + completed.length + ' / ' + totalAll + '</span>' +
        '</div>' +
        '<div class="rcAiCompSummary">' + esc(narrative.summaryMsg) + '</div>' +
        tasteNoteHtml +
      '</div>';

    // P2.9-E: Trigger cinematic completion arrival moment once
    if (!_completionNarrativeSet) {
      _completionNarrativeSet = true;
      _triggerCompletionArrival();

      // Completion bar becomes creative outcome summary
      const msgEl     = document.querySelector('.renderCompletionMsg');
      const summaryEl = document.querySelector('.renderCompletionSummary');
      if (msgEl && avgPct >= 70) {
        msgEl.textContent = 'AI finished shaping your output.';
      }
      if (summaryEl) {
        // P3.4: Use taste-aware bits if available, else build fallback
        const bits = narrative.bits.length ? narrative.bits : (() => {
          const b = [];
          if (topPct >= 75)      b.push('Best clip ' + topPct + '% — strong hook');
          else if (topPct >= 55) b.push('Top clip scored ' + topPct + '%');
          if (completed.length)  b.push(completed.length + ' clips AI-scored');
          b.push('avg ' + avgPct + '%');
          return b;
        })();
        summaryEl.textContent = bits.join(' · ');
      }

      // Lock in peak confidence on the best card
      setTimeout(() => _applyConfidenceEvolution(completed.length, completed.length), 200);

      // UX-R2: Hero morph + completion hero reveal
      _morphHeroToOutcome(narrative);
      _showCompletionHero(job, parts, narrative, completed, topPct);
    }
  }

  function reset() {
    _lastStageIdx           = -1;
    _reasonItems            = [];
    _lastPartCount          = 0;
    _completionNarrativeSet = false;
    _arrivalTriggered       = false;   // P2.9.1-C
    _morphPending           = false;   // P2.9.1-E
    _maxKnownTotal          = 0;       // P2.9.1-B
    _lastConfidenceLevel    = '';      // P2.9.1-B
    _transientCards.clear();           // P2.9.1-A
    _lastConcernHash        = '';      // P3.4
    _lastHeroConcernHash   = '';      // UX-R1
    {
      // UX-R2: reset completion hero
      const h2 = document.getElementById('uxr2_completion_hero');
      if (h2) {
        h2.classList.add('hiddenView');
        h2.classList.remove('uxr2HeroActive');
        h2.dataset.state = '';
        const thumbEl = document.getElementById('uxr2_hero_thumb');
        if (thumbEl) thumbEl.innerHTML = '<div class="uxr2ThumbPlaceholder">◎</div>';
        const msgEl2 = document.getElementById('uxr2_narrative_msg');
        if (msgEl2) msgEl2.textContent = '';
        const reasonEl = document.getElementById('uxr2_narrative_reason');
        if (reasonEl) { reasonEl.textContent = ''; reasonEl.hidden = true; }
        const bitsEl = document.getElementById('uxr2_narrative_bits');
        if (bitsEl) bitsEl.innerHTML = '';
        const exportLink = document.getElementById('uxr2_cta_export');
        if (exportLink) { exportLink.removeAttribute('href'); exportLink.setAttribute('hidden', ''); }
      }
      const uxr1Hero = document.getElementById('uxr1_ai_hero');
      if (uxr1Hero) uxr1Hero.classList.remove('uxr2OutcomeMode');
      const bar2 = document.getElementById('render_completion_bar');
      if (bar2) bar2.classList.remove('uxr2BarDemoted');
      const listEl2 = document.getElementById('render_output_list');
      if (listEl2) listEl2.classList.remove('uxr2Complete');
    }
    {
      const heroEl = document.getElementById('uxr1_ai_hero');
      if (heroEl) {
        heroEl.dataset.stage  = '';
        heroEl.dataset.failed = '';
        const ic = document.getElementById('uxr1_stage_icon');
        const lb = document.getElementById('uxr1_stage_label');
        const mg = document.getElementById('uxr1_stage_msg');
        const cc = document.getElementById('uxr1_concerns');
        if (ic) ic.textContent = _STAGES[0] ? _STAGES[0].icon  : '◉';
        if (lb) lb.textContent = _STAGES[0] ? _STAGES[0].label : 'Reading the Room';
        if (mg) mg.textContent = _STAGES[0] ? _STAGES[0].msg   : '';
        if (cc) cc.innerHTML   = '';
      }
    }
    // Clear P2.9 confidence state from any lingering best card
    const bestCard = document.querySelector('.clipCard.isBestClip');
    if (bestCard) delete bestCard.dataset.p29Confidence;
    // Clear evolution header back to default
    const header = document.querySelector('.rcAiEvolutionHeader span');
    if (header) header.textContent = 'Clip Intelligence';
    ['rc_ai_process_cards', 'rc_ai_evolution_feed', 'rc_ai_reason_feed'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.add('hiddenView');
    });
    ['rc_ai_evolution_list', 'rc_ai_reason_list'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '';
    });
    // P3.4: concern items live inside evolution list (cleared above)
    const insightEl = document.getElementById('rc_benchmark_insight');
    if (insightEl) { insightEl.classList.add('hiddenView'); insightEl.innerHTML = ''; }
  }

  return { mountPanels, update, reset, showCompletionIntelligence, reapplyTransientState };
})();
