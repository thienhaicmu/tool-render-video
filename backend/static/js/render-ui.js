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
const RENDER_MONITOR_STALL_MS = 45000;

function setHeaderJob(text){ qs('job_chip').textContent = text; }
function resetRenderSessionUi(){
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
  if(qs('event_log_render')) qs('event_log_render').innerHTML = '';
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
  qs('action_title').textContent = 'Waiting for job';
  qs('action_state').textContent = 'idle';
  if (qs('action_state')) qs('action_state').dataset.status = 'idle';
  qs('action_message').textContent = 'No active processing task.';
  qs('action_meta').textContent = 'Elapsed 00:00 | Updated -';
  renderPipeline('queued', 'queued');
  renderSteps(0);
  renderParts([]);
  renderPartFocus([], null);
  if(RENDER_SESSION_ONLY && qs('jobs_out')){
    qs('jobs_out').innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
  }
  setRenderFlowState('source', 'Select source', { source: 'active', force: true });
  hideRenderCompletionBar();
  resetRenderMonitorHeartbeat();
  _renderLogsUserToggled = false;
  setRenderLogsCollapsed(false);
  updateRenderMainState(null, null, []);
}
function fmtElapsed(ms){
  const sec = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}
function stageLabel(stage){
  const map = {
    queued: 'Queued',
    starting: 'Preparing render',
    downloading: 'Preparing source',
    scene_detection: 'Detecting scenes',
    segment_building: 'Building smart segments',
    transcribing_full: 'Generating subtitles',
    rendering: 'Rendering clips',
    rendering_parallel: 'Rendering clips',
    writing_report: 'Writing report and outputs',
    done: 'Complete',
    failed: 'Failed',
  };
  return map[stage] || 'Processing';
}
function stageLabelPlain(stage){
  const map = {
    queued: 'Waiting',
    starting: 'Preparing',
    downloading: 'Preparing source',
    scene_detection: 'Detecting scenes',
    segment_building: 'Building segments',
    transcribing_full: 'Generating subtitles',
    rendering: 'Rendering clips',
    rendering_parallel: 'Rendering clips',
    writing_report: 'Writing report',
    done: 'Done',
    failed: 'Failed',
  };
  return map[(stage || '').toLowerCase()] || (stage || '-');
}

function isTerminalRenderStatus(status){
  const st = String(status || '').toLowerCase();
  return st === 'completed' || st === 'failed' || st === 'interrupted' || st === 'done' || st === 'complete';
}

function renderMonitorStageLabel(stage, status, summary = null){
  const st = String(status || '').toLowerCase();
  if (st === 'completed' || st === 'done' || st === 'complete') return 'Render complete';
  if (st === 'failed' || st === 'interrupted') return 'Render failed';
  const s = String(stage || '').toLowerCase();
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
  const completed = status === 'completed' || status === 'done' || status === 'complete';
  const failed = status === 'failed' || status === 'interrupted';
  const now = Date.now();
  const noProgressMs = _renderMonitorLastProgressAt ? now - _renderMonitorLastProgressAt : 0;
  const stalled = running && _renderMonitorLastProgressAt && noProgressMs > RENDER_MONITOR_STALL_MS;

  let monitorState = 'idle';
  if (running) monitorState = stalled ? 'stalled' : 'running';
  if (completed) monitorState = 'complete';
  if (failed) monitorState = 'failed';
  header.dataset.monitorState = monitorState;

  const pctText = qs('job_percent')?.textContent || '0%';
  const stageText = job ? renderMonitorStageLabel(job.stage, job.status, summary) : (running ? stageLabelPlain(lastStage) : 'Ready to render');
  const primary = qs('render_monitor_primary');
  const secondary = qs('render_monitor_secondary');
  const heartbeat = qs('render_monitor_heartbeat');
  if (primary) {
    if (failed) primary.textContent = `Render failed · ${pctText}`;
    else if (completed) primary.textContent = `Render complete · ${pctText}`;
    else if (running) primary.textContent = `${stageText} · ${pctText}`;
    else primary.textContent = 'Ready to render';
  }
  if (secondary) {
    const clipLine = renderMonitorClipSummary(summary, parts);
    if (stalled) secondary.textContent = clipLine;
    else if (completed) secondary.textContent = `${clipLine} · Final clips saved below`;
    else if (failed) secondary.textContent = `${clipLine} · Check diagnostics`;
    else secondary.textContent = running ? clipLine : 'No active render job.';
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
}
function friendlyJobMessage(job){
  const status = String(job?.status || '').toLowerCase();
  const stage = String(job?.stage || '').toLowerCase();
  if (status === 'completed' || status === 'done' || status === 'complete') return 'Render complete.';
  if (status === 'failed' || status === 'interrupted') return friendlyRenderError(job?.message || '', 'Something went wrong during rendering');
  if (status === 'queued') return 'Waiting to start.';
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
  const status = String(job?.status || '').toLowerCase();
  const stage = String(job?.stage || '').toLowerCase();
  if (status === 'running' || status === 'queued') {
    if (stage === 'scene_detection') return 'Analyzing video and selecting clips...';
    if (stage === 'segment_building') return 'Preparing clips for rendering...';
    if (stage === 'transcribing_full') return 'Generating subtitles...';
    return 'Preparing clips...';
  }
  return 'Clips will appear here once rendering begins.';
}
function updateRenderProgressVisual(job) {
  const status = String(job?.status || '').toLowerCase();
  const stage = String(job?.stage || '').toLowerCase();
  const staticMs = _renderMonitorLastProgressAt ? (Date.now() - _renderMonitorLastProgressAt) : 0;
  const earlyStage = !['rendering', 'rendering_parallel'].includes(stage);
  const isWaitingActive = !!currentJobId && status === 'running' && earlyStage && staticMs > 8000;
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
    done: 'Completed',
    failed: 'Failed'
  };
  return map[s] || s;
}
function setActionState(job){
  const stage = (job.stage || '').toLowerCase();
  const status = (job.status || '').toLowerCase();
  const running = !isTerminalRenderStatus(status);
  if (running && !activeJobStartedAt) activeJobStartedAt = Date.now();
  if (!running && !activeJobStartedAt) activeJobStartedAt = Date.now();
  const elapsed = fmtElapsed(Date.now() - (activeJobStartedAt || Date.now()));
  const friendly = friendlyJobMessage(job);
  const backendDetail = String(job.message || '').trim();
  qs('action_title').textContent = stageLabel(stage);
  qs('action_state').textContent = status || 'running';
  qs('action_message').textContent = friendly;
  qs('action_meta').textContent = `Running for ${elapsed} | Updated ${new Date().toLocaleTimeString()}${backendDetail ? ` | Detail: ${backendDetail}` : ''}`;
  // propagate status/stage as data attributes for CSS visual state
  const _stEl = qs('action_state');
  if (_stEl) _stEl.dataset.status = status || 'running';
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
  const order = RENDER_FLOW_ORDER;
  const force = overrides.force === true;
  const idx = order.indexOf(activeStep);
  if (idx < 0) return;
  const targetIdx = (!force && idx < _renderFlowStepRank) ? _renderFlowStepRank : idx;
  const targetStep = order[targetIdx];
  if (force || targetIdx > _renderFlowStepRank) _renderFlowStepRank = targetIdx;
  const subByStep = {
    source: qs('flow_sub_source'),
    configure: qs('flow_sub_configure'),
    rendering: qs('flow_sub_rendering'),
    complete: qs('flow_sub_complete'),
  };
  Object.entries(subByStep).forEach(([key, el]) => {
    if (!el) return;
    if (key === targetStep && subtitle && el.textContent !== subtitle) {
      el.textContent = subtitle;
      el.classList.remove('flowSubChanging');
      void el.offsetWidth;
      el.classList.add('flowSubChanging');
    }
  });
  document.querySelectorAll('.renderFlowStep[data-flow-step]').forEach((node) => {
    const key = node.getAttribute('data-flow-step');
    let state = 'pending';
    if (overrides[key]) {
      state = overrides[key];
    } else {
      const kIdx = order.indexOf(key);
      if (kIdx < targetIdx) state = 'done';
      if (kIdx === targetIdx) state = 'active';
    }
    const changed = !node.classList.contains(state);
    node.classList.remove('pending', 'active', 'done');
    node.classList.add(state);
    if (changed) {
      node.classList.remove('flowStepChanged');
      void node.offsetWidth;
      node.classList.add('flowStepChanged');
    }
  });
}

function updateRenderFlowByJob(job, summary, parts = []) {
  const stage = String(job?.stage || '').toLowerCase();
  const status = String(job?.status || '').toLowerCase();
  if (status === 'completed' || status === 'done' || status === 'complete') {
    setRenderFlowState('complete', `${getCompletedClipCount(summary, parts)} clips ready`);
    return;
  }
  if (status === 'failed' || status === 'interrupted') {
    setRenderFlowState('complete', status === 'interrupted' ? 'Interrupted' : 'Failed', {
      source: 'done',
      configure: 'done',
      rendering: 'done',
      complete: 'active',
    });
    return;
  }
  if (stage === 'queued' || stage === 'starting' || stage === 'downloading') {
    const step = _renderFlowStepRank >= RENDER_FLOW_ORDER.indexOf('rendering') ? 'rendering' : 'source';
    setRenderFlowState(step, stageLabelPlain(stage));
    return;
  }
  if (stage === 'scene_detection' || stage === 'segment_building' || stage === 'transcribing_full' || stage === 'rendering' || stage === 'rendering_parallel' || stage === 'writing_report') {
    const pct = Math.round(Number(job?.progress_percent || 0));
    setRenderFlowState('rendering', `${stageLabelPlain(stage)} - ${pct}%`);
    return;
  }
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
  bar.classList.remove('hiddenView');
}

function hideRenderCompletionBar() {
  const bar = qs('render_completion_bar');
  if (!bar) return;
  bar.classList.add('hiddenView');
  const summary = qs('render_completion_summary');
  if (summary) summary.textContent = '';
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

function updateRenderMainState(job, summary, parts = []) {
  const activePanel = qs('render_active_panel');
  const homePanel = qs('render_home_panel');
  if (!activePanel || !homePanel) return;

  const status = String(job?.status || '').toLowerCase();
  const hasJob = !!job && !!currentJobId;
  const terminal = isTerminalRenderStatus(status);
  const showActivePanel = hasJob && currentView === 'render';

  homePanel.classList.toggle('hiddenView', !((currentView === 'render') && !showActivePanel));
  activePanel.classList.toggle('hiddenView', !showActivePanel);
  if (!showActivePanel) return;

  const s = summary || computeProgressSummary(parts || []);
  const pct = Math.max(0, Math.min(100, Math.round(Number(job?.progress_percent || 0))));
  const title = terminal
    ? ((status === 'completed' || status === 'done' || status === 'complete') ? 'Render complete' : 'Render failed')
    : stageLabel(job?.stage || 'queued');
  const done = getCompletedClipCount(s, parts);
  const total = Number(s?.total_parts || parts.length || 0);
  const active = Number(s?.processing_parts || 0);
  const failed = Number(s?.failed_parts || 0);
  const sourceText = getRenderWorkspaceSourceText(job);
  const outputText = getRenderWorkspaceOutputText(job);
  const outputLabel = getRenderWorkspaceOutputLabel(job);
  const workspaceStage = terminal
    ? ((status === 'completed' || status === 'done' || status === 'complete')
      ? (failed > 0 ? 'Render finished with some clip failures' : 'Render completed successfully')
      : 'Render failed before all clips finished')
    : `${stageLabel(job?.stage || 'queued')}. This render is using the same source workspace you just configured.`;
  const clipBits = [];
  if (total > 0) clipBits.push(`${done}/${total} clips done`);
  if (active > 0) clipBits.push(`${active} rendering`);
  if (failed > 0) clipBits.push(`${failed} failed`);

  if (qs('render_active_state')) qs('render_active_state').textContent = terminal ? 'Render Complete' : 'Current Render';
  if (qs('render_active_title')) qs('render_active_title').textContent = title;
  if (qs('render_active_pct')) qs('render_active_pct').textContent = `${pct}%`;
  if (qs('render_active_bar')) qs('render_active_bar').style.width = `${pct}%`;
  if (qs('render_active_meta')) {
    if (status === 'completed' || status === 'done' || status === 'complete') {
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
  const previewState = (status === 'failed' || status === 'interrupted') ? 'failed' : (status === 'completed' || status === 'done' || status === 'complete') ? 'complete' : 'active';
  if (qs('render_workspace_preview')) qs('render_workspace_preview').dataset.previewState = previewState;
  if (qs('render_workspace_preview_badge')) qs('render_workspace_preview_badge').textContent = (status === 'completed' || status === 'done' || status === 'complete') ? 'Results' : (status === 'failed' || status === 'interrupted') ? 'Attention' : 'Rendering';
  if (qs('render_workspace_preview_title')) {
    qs('render_workspace_preview_title').textContent = (status === 'completed' || status === 'done' || status === 'complete')
      ? (failed > 0 ? 'Render finished with review items' : 'Results are ready')
      : (status === 'failed' || status === 'interrupted')
      ? 'Render stopped before completion'
      : 'Rendering in progress';
  }
  if (qs('render_workspace_preview_text')) {
    qs('render_workspace_preview_text').textContent = (status === 'completed' || status === 'done' || status === 'complete')
      ? 'This workspace stays tied to the same source and destination so you can confirm where outputs were saved.'
      : (status === 'failed' || status === 'interrupted')
      ? 'Preview is unavailable here, but the same source and destination context is preserved while you review progress below.'
      : 'Preview unavailable during render. This workspace remains tied to the same source and output destination you selected in the editor.';
  }
  if (qs('render_active_actions')) qs('render_active_actions').classList.toggle('hiddenView', !(status === 'completed' || status === 'done' || status === 'complete'));
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
    box.innerHTML = '<div class="renderHistoryEmpty">No recent renders yet<div>Your completed renders will appear here.</div></div>';
    return;
  }
  box.innerHTML = items.map((entry) => {
    const status = _renderHistoryStatusText(entry.status);
    const icon = entry.status === 'failed' ? '✕' : entry.status === 'partial' ? '⚠' : '✓';
    const openDisabled = entry.outputDir ? '' : ' disabled';
    return `<div class="renderHistoryItem ${esc(entry.status || 'completed')}">
      <div class="renderHistoryMain">
        <div class="renderHistoryTop">
          <span class="renderHistoryStatusIcon">${icon}</span>
          <span class="renderHistoryTitle" title="${_renderHistoryAttr(entry.sourceValue)}">${esc(entry.title || 'Untitled render')}</span>
          <span class="renderHistoryTime">${_renderHistoryRelativeTime(entry.timestamp)}</span>
        </div>
        <div class="renderHistoryMeta">${status} · ${esc(_renderHistoryClipSummary(entry))}</div>
      </div>
      <div class="renderHistoryActions">
        <button class="ghostButton" type="button"${openDisabled} onclick="openRenderHistoryOutput('${encodeURIComponent(entry.jobId)}')">Open Output Folder</button>
        <button class="secondaryButton" type="button" onclick="rerunRenderHistory('${encodeURIComponent(entry.jobId)}')">Rerun</button>
      </div>
    </div>`;
  }).join('');
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
  const panel = qs('appBottomPanel');
  if (!panel) return;
  if (typeof _collapseBottomPanel === 'function') _collapseBottomPanel(false);
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function setRenderLogsCollapsed(collapsed, options = {}) {
  const panel = qs('appBottomPanel');
  if (!panel) return;
  panel.classList.toggle('logsCollapsed', !!collapsed);
  const btn = document.querySelector('.abpLogToggle');
  if (btn) btn.textContent = collapsed ? 'Show logs' : 'Hide logs';
  if (options.fromUser) _renderLogsUserToggled = true;
}

function maybeAutoCollapseRenderLogs() {
  if (_renderLogsUserToggled) return;
  if (window.innerWidth >= 900) return;
  setRenderLogsCollapsed(true);
}

function toggleRenderLogs() {
  const panel = qs('appBottomPanel');
  if (!panel) return;
  setRenderLogsCollapsed(!panel.classList.contains('logsCollapsed'), { fromUser: true });
}
function pipelineStateByStage(stage, status){
  const s = (stage || '').toLowerCase();
  const st = (status || '').toLowerCase();
  const idx = pipeline.findIndex(node => node.stages.includes(s));
  return pipeline.map((n, i) => {
    if (idx < 0) return { ...n, state: 'pending' };
    if (st === 'failed' && i === idx) return { ...n, state: 'failed' };
    if (i < idx) return { ...n, state: 'done' };
    if (i === idx) return { ...n, state: st === 'completed' ? 'done' : 'running' };
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
  const btn = qs('start_render_btn');
  if(!btn) return;
  btn.disabled = !!isBusy;
  btn.style.opacity = isBusy ? '0.75' : '1';
  btn.textContent = isBusy ? 'Rendering...' : 'Open Editor';

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
    const panel = qs('appBottomPanel');
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
  qs('steps_grid').innerHTML = steps.map((s, i) => {
    const st = stepStatus(i, progress || 0);
    return `<div class="stepCard ${st}"><div class="stepIconWrap">${st === 'done' ? 'OK' : st === 'running' ? 'RUN' : '...'}</div><div><div class="stepTitle">${s.label}</div><div class="stepStatus">${stateLabel[st] || st}</div></div></div>`;
  }).join('');
}

function renderParts(items, summary){
  const wrap = qs('parts_wrap');
  if(!items || !items.length){
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
  const total = Number(s.total_parts || items.length || 0);
  const done = Number(s.completed_parts || 0);
  const rendering = Number(s.processing_parts || 0);
  const failed = Number(s.failed_parts || 0);
  const pending = Math.max(0, total - done - rendering - failed);
  const pct = Math.round(Number(s.overall_progress_percent ?? s.parts_percent ?? 0));

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
    const rowClass  = `${st || 'queued'}${isRun ? ' running' : ''}${isStuck ? ' stuck' : ''}`.trim();
    const partNo = Number(p.part_no || idx + 1);
    const partName = p.part_name ? esc(p.part_name) : `Clip ${partNo}`;
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const duration = Math.max(0, endSec - startSec);
    return `
    <div class="partRow ${rowClass}">
      <div class="partLeft">
        <div class="rankBadge">C${partNo}</div>
        <div>
          <div class="partName">${partName}</div>
          <div class="partMeta"><span class="clipDuration">${duration.toFixed(1)}s</span> | ${startSec.toFixed(1)}s–${endSec.toFixed(1)}s</div>
          ${errHtml}${stuckHtml}
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
  const _active = ['waiting','cutting','transcribing','rendering'];
  const done    = parts.filter(p=>(p.status||'')==='done').length;
  const failed  = parts.filter(p=>(p.status||'')==='failed').length;
  const inProg  = parts.filter(p=>_active.includes(p.status||''));
  const pending = Math.max(0, total - done - failed - inProg.length);
  const pSum    = parts.reduce((s,p)=>s+Number(p.progress_percent||0),0);
  const overall = total>0 ? Math.round(pSum/total*10)/10 : 0;
  const now = Date.now() / 1000;
  const activeParts = [];
  const stuckParts  = [];
  inProg.forEach(p => {
    activeParts.push({ part_no: p.part_no, status: p.status, progress_percent: Number(p.progress_percent||0) });
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

  const status    = (job.status  || '').toLowerCase();
  const stage     = (job.stage   || '').toLowerCase();
  const pct       = Math.round(Number(job.progress_percent || 0));
  const isRunning = !isTerminalRenderStatus(status) && !!status;
  const isDone    = status === 'completed' || status === 'done' || status === 'complete';
  const isFailed  = status === 'failed' || status === 'interrupted';

  dot.className = 'statusDot ' + (isFailed ? 'statusDotFailed' : isRunning ? 'statusDotRunning' : 'statusDotReady');
  label.textContent = isDone ? 'Done' : isFailed ? 'Failed' : isRunning ? stageLabelPlain(stage) : 'Idle';

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
  const list = qs('render_output_list');
  if (list) list.innerHTML = '<div class="renderOutputEmpty">Clips will appear here when render completes.</div>';
  const badge = qs('render_output_badge');
  if (badge) badge.textContent = '0';
  const path = qs('render_output_path');
  if (path) path.textContent = '';
  hideRenderOutputPanel();
}

function populateRenderOutputPanel(job, parts) {
  const list = qs('render_output_list');
  const badge = qs('render_output_badge');
  const pathEl = qs('render_output_path');
  if (!list) return;

  const items = Array.isArray(parts) ? parts : [];
  const done = items.filter((p) => String(p?.status || '').toLowerCase() === 'done');
  const failed = items.filter((p) => String(p?.status || '').toLowerCase() === 'failed');
  const all = [
    ...done.sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0)),
    ...failed.sort((a, b) => Number(a.part_no || 0) - Number(b.part_no || 0)),
  ];

  if (badge) badge.textContent = String(done.length);

  const outputDir = getCurrentJobOutputDir(job);
  if (pathEl) pathEl.textContent = outputDir ? `Output folder: ${outputDir}` : '';

  if (!all.length) {
    list.innerHTML = '<div class="renderOutputEmpty">No completed clips found for this render.</div>';
    showRenderOutputPanel();
    return;
  }

  const jobId = String(job?.id || job?.job_id || currentJobId || '');
  list.innerHTML = all.map((p) => {
    const partNo = Number(p.part_no || 0);
    const st = String(p?.status || '').toLowerCase();
    const isFailed = st === 'failed';
    const hasFile = !!p.output_file;
    const name = p.part_name ? esc(p.part_name) : `Clip ${partNo}`;
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const dur = Math.max(0, endSec - startSec).toFixed(1);
    const meta = isFailed
      ? `Failed · ${dur}s`
      : hasFile
        ? `${dur}s · ${startSec.toFixed(1)}s–${endSec.toFixed(1)}s`
        : `${dur}s`;
    const previewBtn = (!isFailed && hasFile && jobId)
      ? `<button type="button" onclick="previewClip(${JSON.stringify(jobId)},${partNo})">Preview</button>`
      : '';
    const openBtn = hasFile
      ? `<button type="button" onclick="openClipFile(${JSON.stringify(p.output_file)})">Open</button>`
      : '';
    return `<div class="renderClipItem${isFailed ? ' failed' : ''}">
      <div class="renderClipNum">${partNo}</div>
      <div class="renderClipInfo">
        <div class="renderClipName" title="${esc(p.output_file || '')}">${name}</div>
        <div class="renderClipMeta">${meta}</div>
      </div>
      <div class="renderClipActions">${previewBtn}${openBtn}</div>
    </div>`;
  }).join('');

  showRenderOutputPanel();
  const panel = qs('render_output_panel');
  if (panel) setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80);
}

function previewClip(jobId, partNo) {
  const modal = qs('clip_preview_modal');
  const video = qs('clip_preview_video');
  const title = qs('clip_preview_title');
  if (!modal || !video) return;
  _previewCurrentJobId = jobId;
  _previewCurrentPartNo = partNo;
  const src = `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/stream`;
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
