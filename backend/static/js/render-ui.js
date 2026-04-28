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
let _logAutoScroll = true;
let _rcLastActivePartNo = -1;
let _rcScrollDebounceId = null;
let _rcUserIsScrolling = false;
let _rcUserScrollTimerId = null;
const RENDER_MONITOR_STALL_MS = 45000;

// ── Skill metadata: user-visible descriptions (no raw key names shown) ────────
const _SKILL_META = {
  better_audio:         { label: 'Better Audio',    desc: 'Audio balanced & normalized' },
  subtitle_readability: { label: 'Subtitles',       desc: 'Subtitles easier to read' },
  video_quality_preset: { label: 'Video Quality',   desc: 'Video quality improved' },
  smart_crop:           { label: 'Smart Crop',      desc: 'Smart framing applied' },
  fast_captions:        { label: 'Fast Captions',   desc: 'Captions generated faster' },
  // highlight_detection is excluded from "applied" display — viral scoring always
  // runs; reporting it as a discrete skill improvement would mislead users.
};

function _getRenderModeFromJob(job) {
  if (!job) return 'stable';
  try {
    const p = typeof job.payload_json === 'string' ? JSON.parse(job.payload_json) : (job.payload_json || {});
    return String(p.render_mode || 'stable').toLowerCase();
  } catch (_) { return 'stable'; }
}

function _getSkillDetails(job) {
  try {
    const r = typeof job?.result_json === 'string' ? JSON.parse(job.result_json) : (job?.result_json || {});
    const enabledKeys = Array.isArray(r.skill_enabled) ? r.skill_enabled : [];
    const skippedKeys = Array.isArray(r.skill_skipped) ? r.skill_skipped : [];
    const fallbacks   = Number(r.skill_fallback_count || 0);
    // applied = skills with real user-visible effects (highlight_detection excluded)
    const applied = enabledKeys
      .filter((k) => k !== 'highlight_detection' && _SKILL_META[k])
      .map((k) => ({ key: k, label: _SKILL_META[k].label, desc: _SKILL_META[k].desc }));
    // skipped = skills that were not applied; if highlight_detection is here it was
    // genuinely unavailable, so keep it in the count
    const skipped = skippedKeys.filter((k) => k !== 'highlight_detection');
    const confidence     = fallbacks === 0 ? 'high' : fallbacks === 1 ? 'medium' : 'low';
    const confidenceText = fallbacks === 0 ? 'High confidence' : fallbacks === 1 ? 'Medium confidence' : 'Low confidence';
    return { applied, skipped, confidence, confidenceText, fallbacks };
  } catch (_) {
    return { applied: [], skipped: [], confidence: 'high', confidenceText: 'High confidence', fallbacks: 0 };
  }
}

function _computeRenderDuration(job) {
  try {
    const _toMs = (s) => {
      const t = String(s || '').trim();
      if (!t) return 0;
      return Date.parse(t.replace(' ', 'T') + (t.includes('Z') || t.includes('+') ? '' : 'Z'));
    };
    const created = _toMs(job?.created_at);
    const updated = _toMs(job?.updated_at);
    if (!created || !updated || updated <= created) return null;
    return Math.round((updated - created) / 1000);
  } catch (_) { return null; }
}

function _fmtRenderDuration(secs) {
  if (!secs || secs < 1) return null;
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// Kept for backward compat — used by active monitor skill summary line
function _getRenderSkillSummaryFromJob(job) {
  const d = _getSkillDetails(job);
  const parts = d.applied.map((s) => s.desc);
  if (d.skipped.length) parts.push(`${d.skipped.length} skipped`);
  if (d.fallbacks > 0) parts.push(`${d.fallbacks} fallback${d.fallbacks > 1 ? 's' : ''}`);
  return parts.join(' · ');
}

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
  if(qs('event_log_render')) qs('event_log_render').innerHTML = '<div class="rcLogEmpty">Logs will appear here during render.</div>';
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
  qs('action_title').textContent = 'Waiting for job';
  qs('action_state').textContent = 'idle';
  if (qs('action_state')) qs('action_state').dataset.status = 'idle';
  qs('action_message').textContent = 'No active processing task.';
  qs('action_meta').textContent = 'Elapsed 00:00 | Updated -';
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
  if(RENDER_SESSION_ONLY && qs('jobs_out')){
    qs('jobs_out').innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
  }
  setRenderFlowState('source', 'Select source', { source: 'active', force: true });
  hideRenderCompletionBar();
  resetRenderMonitorHeartbeat();
  _renderLogsUserToggled = false;
  setRenderLogsCollapsed(false);
  renderBottomActiveQueue(null, null, []);
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
    starting: 'Preparing',
    downloading: 'Preparing source',
    scene_detection: 'Scene detect',
    segment_building: 'Building clips',
    transcribing_full: 'Subtitles',
    rendering: 'Rendering',
    rendering_parallel: 'Rendering',
    writing_report: 'Writing report',
    done: 'Complete',
    failed: 'Failed',
  };
  return map[stage] || 'Processing';
}
function stageLabelPlain(stage){
  const map = {
    queued: 'Queued',
    starting: 'Preparing',
    downloading: 'Preparing source',
    scene_detection: 'Scene detect',
    segment_building: 'Building clips',
    transcribing_full: 'Subtitles',
    rendering: 'Rendering',
    rendering_parallel: 'Rendering',
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
  const latestDetail = String(job?.message || '').trim();
  const latestShort = latestDetail.length > 96 ? `${latestDetail.slice(0, 93)}...` : latestDetail;
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
    completed: 'Completed',
    done: 'Completed',
    error: 'Failed',
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
  const status = String(job?.status || '').toLowerCase();
  const terminal = isTerminalRenderStatus(status);
  const done = getCompletedClipCount(s, items);
  const total = Number(s?.total_parts || items.length || 0);
  const active = Number(s?.processing_parts || 0);
  const failed = Number(s?.failed_parts || 0);
  const pct = Math.max(0, Math.min(100, Math.round(Number(job?.progress_percent ?? s?.overall_progress_percent ?? 0))));
  const activeParts = Array.isArray(s?.active_parts) ? s.active_parts : [];
  const activeText = activeParts.length === 1
    ? `Clip ${Number(activeParts[0]?.part_no || 0)}`
    : activeParts.length > 1
    ? `${activeParts.length} clips active`
    : 'No active clip';
  const latest = String(job?.message || qs('rc_latest')?.textContent || qs('abp_summary_latest')?.textContent || 'Waiting for render...').trim();
  const statusText = !job ? 'Ready' : status === 'failed' || status === 'interrupted' ? 'Failed' : terminal ? 'Completed' : 'Rendering';
  const stageText = job ? stageLabel(job?.stage || 'queued') : 'Idle';
  const waitingCount = Math.max(0, total - done - active - failed);
  const queueSummary = [
    `${done} completed`,
    active > 0 ? `${active} rendering` : null,
    waitingCount > 0 ? `${waitingCount} waiting` : null,
    failed > 0 ? `${failed} failed` : null
  ].filter(Boolean).join(' · ') || 'Waiting for render...';

  if (qs('rc_status')) {
    qs('rc_status').textContent = statusText;
    qs('rc_status').dataset.state = !job ? 'ready' : (status === 'failed' || status === 'interrupted' ? 'failed' : terminal ? 'completed' : 'running');
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
    const stage = partStatusLabel(st);
    const message = String(p?.message || '').trim() || (cls === 'isWaiting' ? 'Waiting in queue' : cls === 'isCompleted' ? 'Ready in output folder' : cls === 'isFailed' ? 'Needs review' : 'Processing');
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const duration = Math.max(0, endSec - startSec);
    const meta = p.output_file
      ? `Output ready · ${esc(String(p.output_file).split(/[\\\\/]/).pop())}`
      : duration > 0
      ? `${duration.toFixed(1)}s · ${startSec.toFixed(1)}s–${endSec.toFixed(1)}s`
      : '';
    return `<article class="rcPartCard ${cls}" data-part-status="${esc(st || 'queued')}">
      <div class="rcPartTop">
        <div class="rcPartTitle">Clip ${partNo} · ${partTitle}</div>
        <div class="rcPartStatus">${esc(partStatusLabel(st))}</div>
      </div>
      <div class="rcPartStage">Stage: ${esc(stage)}</div>
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
        score:   Number(score),
        tier:    String(seg.mv_viral_tier   || 'weak'),
        market:  String(seg.mv_viral_market || 'US'),
        reasons: Array.isArray(seg.mv_viral_reasons) ? seg.mv_viral_reasons : [],
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
  el.closest('.renderClipItem, .rcQueueRow')?.classList.toggle('isSelected', el.checked);
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

function renderBottomActiveQueue(job, summary, parts = []) {
  const items = Array.isArray(parts) ? parts : [];
  const s = summary || computeProgressSummary(items || []);
  const status = String(job?.status || '').toLowerCase();
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
  const pct = clampRcProgress(job?.progress_percent ?? s?.overall_progress_percent ?? s?.parts_percent ?? 0);
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
  const queueSummary = [
    completed > 0 ? `${completed} done` : null,
    renderingParts.length > 0 ? `${renderingParts.length} active` : null,
    waiting > 0 ? `${waiting} queued` : null,
    failed > 0 ? `${failed} failed` : null
  ].filter(Boolean).join(' · ') || (job ? stageText : '');
  const statusLabel = overallState === 'failed'
    ? 'Failed'
    : overallState === 'completed'
    ? 'Completed'
    : overallState === 'running'
    ? 'Rendering'
    : 'Ready';

  // Header primary: "Ready" | "Rendering · 15%" | "Completed" | "Failed · 15%"
  const headerPrimary = overallState === 'ready' ? 'Ready'
    : overallState === 'completed' ? 'Completed'
    : overallState === 'failed' ? `Failed · ${pct}%`
    : `Rendering · ${pct}%`;
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
    badge.textContent = activePart ? 'Rendering' : statusLabel;
    badge.dataset.state = activePart ? 'rendering' : overallState === 'completed' ? 'completed' : overallState === 'failed' ? 'failed' : 'idle';
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
      title = 'All clips completed';
      subtitle = `${completed}/${total || 0} clips finished`;
      stageLine = 'Complete';
      message = latest || 'All clips finished successfully.';
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
      const jobStage = String(job?.stage || '').toLowerCase();
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
        subtitle = 'Preparing…';
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
    if (activeMessage) activeMessage.textContent = message;
  }

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
    const isBest = idx === _bestIdx;
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
      bottom.textContent = `Rendering · ${progress}%`;
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

  const status = String(job?.status || '').toLowerCase();
  const hasJob = !!job && !!currentJobId;
  const terminal = isTerminalRenderStatus(status);
  const showActivePanel = hasJob && currentView === 'render';

  homePanel.classList.toggle('hiddenView', !((currentView === 'render') && !showActivePanel));
  activePanel.classList.toggle('hiddenView', !showActivePanel);
  if (!showActivePanel) return;

  const s = summary || computeProgressSummary(parts || []);
  renderBottomActiveQueue(job, s, parts || []);
  const pct = Math.max(0, Math.min(100, Math.round(Number(job?.progress_percent || 0))));
  const title = terminal
    ? ((status === 'completed' || status === 'done' || status === 'complete') ? 'Render complete' : 'Render failed')
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
  const failureSummary = (typeof friendlyRenderError === 'function')
    ? friendlyRenderError(job?.message || '', 'Render failed')
    : 'Render failed';
  const hasFailure = status === 'failed' || status === 'interrupted';
  const statusLabel = terminal
    ? ((status === 'completed' || status === 'done' || status === 'complete') ? 'Completed' : 'Failed')
    : 'Rendering';
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
  if (qs('render_active_panel')) qs('render_active_panel').dataset.renderState = failed > 0 && terminal ? 'failed' : terminal ? 'complete' : 'running';
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
    ? ((status === 'completed' || status === 'done' || status === 'complete') ? 'Render complete.' : `${failureSummary}.`)
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

  // Render Mode badge + skill summary + elapsed time
  const _rdModeLine    = qs('rd_render_mode_line');
  const _rdModeBadge   = qs('rd_render_mode_badge');
  const _rdSkillSummary = qs('rd_skill_summary');
  const _rdElapsed     = qs('rd_elapsed_time');
  if (_rdModeLine && hasJob) {
    const _jRenderMode = _getRenderModeFromJob(job);
    _rdModeLine.style.display = 'flex';
    if (_rdModeBadge) {
      _rdModeBadge.textContent = _jRenderMode === 'skill_enhanced' ? 'Skill Enhanced' : 'Stable';
      _rdModeBadge.dataset.mode = _jRenderMode;
    }
    if (_rdSkillSummary) {
      if (_jRenderMode === 'skill_enhanced') {
        const _d = _getSkillDetails(job);
        const _descs = _d.applied.map((s) => s.desc);
        const _confSuffix = _d.confidence !== 'high' ? ` · ${_d.confidenceText}` : '';
        _rdSkillSummary.textContent = _descs.length
          ? `${_descs.join(' · ')}${_confSuffix}`
          : 'Skills activating…';
      } else {
        _rdSkillSummary.textContent = '';
      }
    }
    if (_rdElapsed && activeJobStartedAt) {
      _rdElapsed.textContent = fmtElapsed(Date.now() - activeJobStartedAt);
    }
  } else if (_rdModeLine && !hasJob) {
    _rdModeLine.style.display = 'none';
    if (_rdElapsed) _rdElapsed.textContent = '';
  }

  const _rcPrimary = hasFailure ? `Failed · ${pct}%` : terminal ? 'Completed' : `Rendering · ${pct}%`;
  const _rcSecondary = total > 0 ? renderMonitorClipSummary(s, parts) : stageLabel(job?.stage || 'queued');
  if (qs('rc_status')) { qs('rc_status').textContent = _rcPrimary; qs('rc_status').dataset.state = hasFailure ? 'failed' : terminal ? 'completed' : 'running'; }
  if (qs('rc_progress')) qs('rc_progress').textContent = '';
  if (qs('rc_stage')) qs('rc_stage').textContent = _rcSecondary;
  if (qs('rc_parts')) qs('rc_parts').textContent = '';
  if (qs('rc_active')) qs('rc_active').textContent = '';
  if (qs('abp_error_text')) {
    qs('abp_error_text').textContent = hasFailure
      ? `Error: ${latestShort || failureSummary}`
      : 'No blocking errors.';
  }
  if (qs('abp_error_block')) qs('abp_error_block').classList.toggle('hiddenView', !hasFailure);
  if (qs('abp_retry_btn')) qs('abp_retry_btn').classList.toggle('hiddenView', !(hasFailure && currentJobId));
  if (qs('rc_open_output_btn')) qs('rc_open_output_btn').disabled = !(status === 'completed' || status === 'done' || status === 'complete' || String(outputText || '').trim());
  if (qs('render_active_actions')) qs('render_active_actions').classList.toggle('hiddenView', !(status === 'completed' || status === 'done' || status === 'complete'));
  updateRdCard(job, s, parts || []);
}

// ── RD — Dominant Active Render Card helpers ──────────────────────────────────

function _rdBadgeConfig(job, terminal, status, failed, total) {
  if (!job) return { text: '○ Idle', state: 'idle' };
  if (status === 'queued' || status === 'pending') return { text: '○ Queued', state: 'queued' };
  if (terminal) {
    if (status === 'completed' || status === 'done' || status === 'complete') {
      return failed > 0 && total > 0
        ? { text: '⚠ Partial', state: 'partial' }
        : { text: '✓ Done', state: 'completed' };
    }
    return { text: '✕ Failed', state: 'failed' };
  }
  return { text: '● Running', state: 'running' };
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
      const upBtn = document.createElement('button');
      upBtn.className = 'rdQueueBtn';
      upBtn.textContent = 'Upload';
      upBtn.onclick = () => setView('upload');
      acts.appendChild(openBtn);
      acts.appendChild(upBtn);
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
  renderRdClipQueue(qs('rd_clip_queue'), Array.isArray(parts) ? parts : [], job);
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
  const renderMode   = _getRenderModeFromJob(job);
  const skillDetails = renderMode === 'skill_enhanced' ? _getSkillDetails(job) : null;
  const skillSummary = skillDetails ? skillDetails.applied.map((s) => s.desc).join(' · ') : '';
  const renderTime   = _computeRenderDuration(job);
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
    renderMode,
    skillSummary,
    skillDetails,
    renderTime,
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

  // Build compare index: sourceValue → { stable: jobId, skill: jobId }
  const _cmpMap = {};
  items.forEach((e) => {
    const k = String(e.sourceValue || '').trim().toLowerCase();
    if (!k) return;
    if (!_cmpMap[k]) _cmpMap[k] = {};
    if (e.renderMode === 'skill_enhanced') _cmpMap[k].skill = e.jobId;
    else _cmpMap[k].stable = e.jobId;
  });

  box.innerHTML = items.map((entry) => {
    const statusText  = _renderHistoryStatusText(entry.status);
    const icon        = entry.status === 'failed' ? '✕' : entry.status === 'partial' ? '⚠' : '✓';
    const openDisabled = entry.outputDir ? '' : ' disabled';
    const rmLabel = entry.renderMode === 'skill_enhanced' ? 'Skill Enhanced' : 'Stable';
    const rmClass = entry.renderMode === 'skill_enhanced' ? 'skill_enhanced' : 'stable';

    // Render time
    const timeLabel = _fmtRenderDuration(entry.renderTime);
    const timeHtml  = timeLabel ? ` · <span class="rhRenderTime">&#9201; ${esc(timeLabel)}</span>` : '';

    // Skill block (skill_enhanced only)
    let skillBlockHtml = '';
    if (entry.renderMode === 'skill_enhanced') {
      // Re-derive details if missing (old entries without skillDetails stored)
      const details = entry.skillDetails || { applied: [], skipped: [], confidence: 'high', confidenceText: 'High confidence', fallbacks: 0 };
      const chipHtml = details.applied.length
        ? details.applied.map((s) => `<span class="rhSkillItem">${esc(s.desc)}</span>`).join('')
        : '';
      const confHtml = `<span class="rhConfidenceBadge ${esc(details.confidence)}">${esc(details.confidenceText)}</span>`;
      if (chipHtml || details.applied.length === 0) {
        skillBlockHtml = `<div class="renderHistorySkills">${chipHtml}${confHtml}</div>`;
      }
    }

    // Compare button — only when this source has both stable and skill renders
    const sourceKey  = String(entry.sourceValue || '').trim().toLowerCase();
    const cmpEntry   = _cmpMap[sourceKey] || {};
    const canCompare = cmpEntry.stable && cmpEntry.skill && cmpEntry.stable !== cmpEntry.skill;
    const compareBtn = canCompare
      ? `<button class="ghostButton rhCompareBtn" type="button" onclick="_showRenderCompare('${encodeURIComponent(cmpEntry.stable)}','${encodeURIComponent(cmpEntry.skill)}')">&#9654; Compare</button>`
      : '';

    return `<div class="renderHistoryItem ${esc(entry.status || 'completed')}">
      <div class="renderHistoryMain">
        <div class="renderHistoryTop">
          <span class="renderHistoryStatusIcon">${icon}</span>
          <span class="renderHistoryTitle" title="${_renderHistoryAttr(entry.sourceValue)}">${esc(entry.title || 'Untitled render')}</span>
          <span class="renderHistoryTime">${_renderHistoryRelativeTime(entry.timestamp)}</span>
        </div>
        <div class="renderHistoryMeta">
          ${esc(statusText)} · ${esc(_renderHistoryClipSummary(entry))} · <span class="renderHistoryModeBadge ${esc(rmClass)}">${esc(rmLabel)}</span>${timeHtml}
        </div>
        ${skillBlockHtml}
      </div>
      <div class="renderHistoryActions">
        ${compareBtn}
        <button class="ghostButton" type="button"${openDisabled} onclick="openRenderHistoryOutput('${encodeURIComponent(entry.jobId)}')">Open Folder</button>
        <button class="secondaryButton" type="button" onclick="rerunRenderHistory('${encodeURIComponent(entry.jobId)}')">Rerun</button>
      </div>
    </div>`;
  }).join('');
}

function _showRenderCompare(encodedStableId, encodedSkillId) {
  const stableId = decodeURIComponent(String(encodedStableId || ''));
  const skillId  = decodeURIComponent(String(encodedSkillId  || ''));
  const items    = _renderHistoryRead();
  const sEntry   = items.find((e) => e.jobId === stableId);
  const kEntry   = items.find((e) => e.jobId === skillId);
  if (!sEntry && !kEntry) { showToast('Cannot find both renders to compare', 'info'); return; }

  function _sideHtml(entry, modeLabel, modeClass) {
    if (!entry) return `<div class="renderCompareSide"><div class="rcSideLabel ${esc(modeClass)}">${esc(modeLabel)}</div><div class="rcSideEmpty">No data</div></div>`;
    const timeLabel  = _fmtRenderDuration(entry.renderTime);
    const statusText = _renderHistoryStatusText(entry.status);
    const clips      = _renderHistoryClipSummary(entry);
    const details    = (entry.skillDetails && entry.renderMode === 'skill_enhanced') ? entry.skillDetails : null;
    const chipsHtml  = details && details.applied.length
      ? details.applied.map((s) => `<span class="rhSkillItem">${esc(s.desc)}</span>`).join('')
      : '';
    const confHtml   = details ? `<span class="rhConfidenceBadge ${esc(details.confidence)}">${esc(details.confidenceText)}</span>` : '';
    const skillsRow  = (chipsHtml || confHtml)
      ? `<div class="rcSideRow rcSideSkills"><span class="rcSideKey">Skills</span><div class="rcSideVal rcSkillList">${chipsHtml}${confHtml}</div></div>`
      : '';
    const timeRow    = timeLabel
      ? `<div class="rcSideRow"><span class="rcSideKey">Time</span><span class="rcSideVal">${esc(timeLabel)}</span></div>`
      : '';
    return `<div class="renderCompareSide">
      <div class="rcSideLabel ${esc(modeClass)}">${esc(modeLabel)}</div>
      <div class="rcSideRow"><span class="rcSideKey">Status</span><span class="rcSideVal">${esc(statusText)}</span></div>
      <div class="rcSideRow"><span class="rcSideKey">Clips</span><span class="rcSideVal">${esc(clips)}</span></div>
      ${timeRow}
      ${skillsRow}
      <div class="rcSideRow"><span class="rcSideKey">Output</span><span class="rcSideVal rcOutputPath" title="${_renderHistoryAttr(entry.outputDir)}">${esc(entry.outputDir || '—')}</span></div>
    </div>`;
  }

  const title = sEntry?.title || kEntry?.title || 'Render comparison';
  const panelHtml = `<div class="renderComparePanel" id="renderComparePanel">
    <div class="rcPanelHeader">
      <span class="rcPanelTitle">&#9654; Compare</span>
      <span class="rcPanelSource">${esc(title)}</span>
      <button class="ghostButton rcCloseBtn" type="button" onclick="_closeRenderCompare()">&#10005;</button>
    </div>
    <div class="renderCompareCards">
      ${_sideHtml(sEntry, '⚡ Stable', 'stable')}
      ${_sideHtml(kEntry, '✨ Skill Enhanced', 'skill_enhanced')}
    </div>
    <div class="rcPanelNote">Open both output folders to compare clips side by side.</div>
  </div>`;

  _closeRenderCompare();
  const box = qs('render_history_list');
  if (box) box.insertAdjacentHTML('beforebegin', panelHtml);
  document.getElementById('renderComparePanel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function _closeRenderCompare() {
  document.getElementById('renderComparePanel')?.remove();
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

function focusRenderLogPanel() {
  const panel = qs('appBottomPanel');
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
  const panel = qs('appBottomPanel');
  if (!panel) return;
  panel.classList.toggle('logsCollapsed', !!collapsed);
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
  const panel = qs('appBottomPanel');
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
    const partNo = Number(p.part_no || idx + 1);
    const isMvTop = _ptTop3.has(partNo);
    const rowClass  = `${st || 'queued'}${isRun ? ' running isActive' : ''}${st === 'done' ? ' isDone' : ''}${st === 'failed' ? ' isFailed' : ''}${isStuck ? ' stuck' : ''}${isMvTop ? ' mvTop3' : ''}`.trim();
    const partName = p.part_name ? esc(p.part_name) : `Clip ${partNo}`;
    const startSec = Number(p.start_sec || 0);
    const endSec = Number(p.end_sec || 0);
    const duration = Math.max(0, endSec - startSec);
    const mvRow = _ptMvMap.get(partNo);
    const mvPillHtml = mvRow
      ? `<span class="mvScorePill" data-mv-tier="${esc(mvRow.tier)}"${mvRow.reasons.length ? ` title="${esc(mvRow.reasons.slice(0,2).join(' | '))}"` : ''}>&#127758; ${mvRow.score} ${esc(mvRow.market)}</span>`
      : '';
    return `
    <div class="partRow ${rowClass}" data-part-status="${esc(st || 'queued')}">
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
  _selectedClipPaths = new Set();
  const _sumEl = qs('mvRenderSummary');
  if (_sumEl) { _sumEl.innerHTML = ''; _sumEl.hidden = true; }
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
  if (pathEl) pathEl.textContent = outputDir ? `Output folder: ${outputDir}` : '';
  if (qs('abp_output_text')) qs('abp_output_text').textContent = outputDir ? `Output folder: ${outputDir}` : 'Output folder not set.';
  if (qs('abp_output_meta')) qs('abp_output_meta').textContent = 'Latest file will appear here.';
  if (qs('rc_open_output_btn')) qs('rc_open_output_btn').disabled = !outputDir;

  if (!all.length) {
    if (qs('abp_output_meta')) qs('abp_output_meta').textContent = 'Latest file will appear here.';
    list.innerHTML = '<div class="renderOutputEmpty">No completed clips found for this render.</div>';
    showRenderOutputPanel();
    return;
  }

  const jobId = String(job?.id || job?.job_id || currentJobId || '');
  list.innerHTML = all.map((p) => {
    const partNo = Number(p.part_no || 0);
    const st = String(p?.status || '').toLowerCase();
    const isFailed = st === 'failed';
    const isDone = st === 'done';
    const isActive = st === 'rendering' || st === 'transcribing' || st === 'cutting' || st === 'waiting';
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
    if (qs('abp_output_meta') && hasFile) qs('abp_output_meta').textContent = `Latest file: ${String(p.output_file || '').split(/[\\\\/]/).pop()}`;
    const isSelected = isDone && hasFile && _selectedClipPaths.has(p.output_file);
    const itemClass = `renderClipItem${isFailed ? ' failed isFailed' : ''}${isDone ? ' isDone' : ''}${isActive ? ' isActive' : ''}${isSelected ? ' isSelected' : ''}`;
    const chkHtml = (isDone && hasFile)
      ? `<input type="checkbox" class="renderClipCheck" data-path="${esc(p.output_file)}"${isSelected ? ' checked' : ''} onchange="rcToggleClip(this)">`
      : '';
    return `<div class="${itemClass}" data-clip-status="${esc(st || 'queued')}">
      ${chkHtml}
      <div class="renderClipNum">${partNo}</div>
      <div class="renderClipInfo">
        <div class="renderClipName" title="${esc(p.output_file || '')}">${name}</div>
        <div class="renderClipMeta">${meta}</div>
      </div>
      <div class="renderClipActions">${previewBtn}${openBtn}</div>
    </div>`;
  }).join('');

  // Inject "Use Top Clips" button into panel header actions
  const _opActionsEl = qs('render_output_panel')?.querySelector('.renderOutputActions');
  if (_opActionsEl) {
    const _existing = _opActionsEl.querySelector('.rcUseTopBtn');
    if (_existing) _existing.remove();
    if (done.length) {
      const _useBtn = document.createElement('button');
      _useBtn.type = 'button';
      _useBtn.className = 'ghostButton renderOutputBtn rcUseTopBtn';
      _useBtn.textContent = 'Use Top Clips';
      _useBtn.onclick = useTopClips;
      _opActionsEl.insertBefore(_useBtn, _opActionsEl.firstChild);
    }
  }

  showRenderOutputPanel();
  renderBottomActiveQueue(job, computeProgressSummary(items), items);
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

// ── Skill Job Monitor ─────────────────────────────────────────────────────────
//
// Separate from the render job monitor so skill jobs never conflict with
// the normal render pipeline display.  Uses its own polling loop and injects
// a dedicated card into the queue panel.

let _srJobId        = null;
let _srJobSkills    = [];
let _srJobPollTimer = null;
// Transition-tracking for console logs — reset on each new job
let _srPrevCurrentSkill = null;
let _srPrevApplied      = [];
let _srPrevFailed       = [];
let _srPrevStatus       = null;

function startSkillJobMonitor(jobId, selectedSkills) {
  console.log('[SKILL JOB START]', jobId, selectedSkills);
  _stopSkillJobMonitor();
  _srJobId     = jobId;
  _srJobSkills = Array.isArray(selectedSkills) ? selectedSkills : [];

  // Expand bottom panel — collapse is controlled via abpCollapsed on .appShell
  if (typeof _collapseBottomPanel === 'function') {
    _collapseBottomPanel(false);
  }
  // Ensure render-studio body class is set (panel requires is-render-studio-active)
  document.body.classList.add('is-render-studio-active');

  _ensureSkillJobCard();
  _pollSkillJob(); // immediate first poll
  _srJobPollTimer = setInterval(_pollSkillJob, 1200);
}

function _stopSkillJobMonitor() {
  if (_srJobPollTimer) { clearInterval(_srJobPollTimer); _srJobPollTimer = null; }
  _srPrevCurrentSkill = null;
  _srPrevApplied      = [];
  _srPrevFailed       = [];
  _srPrevStatus       = null;
}

function _ensureSkillJobCard() {
  document.getElementById('sr_active_card')?.remove();

  const html = `
<div id="sr_active_card" class="srActiveCard" data-status="queued">
  <div class="srActiveHeader">
    <span class="srJobTypeBadge">⚡ Skill Job</span>
    <span class="srJobStatusBadge" id="sr_status_badge" data-status="queued">Queued</span>
    <span class="srDurationBadge hiddenView" id="sr_duration_badge" title="Video looped to meet TikTok 70 s minimum">⏱ 70 s min</span>
  </div>
  <div class="srActiveProgress"><div class="srActiveProgressFill" id="sr_progress_fill" style="width:0%"></div></div>
  <div class="srSkillSteps" id="sr_skill_steps"></div>
  <div class="srJobMeta" id="sr_job_meta">Waiting to start…</div>
  <div class="srJobLog hiddenView" id="sr_job_log"></div>
  <div class="srJobOutput hiddenView" id="sr_job_output"></div>
  <button class="srDismissBtn" onclick="_dismissSkillJobCard()" title="Dismiss">✕</button>
</div>`;

  // Insert at the top of rcQueuePanel (after its header) — always visible regardless of render state
  const queuePanel = document.querySelector('.rcQueuePanel');
  if (queuePanel) {
    const header = queuePanel.querySelector('.rcPanelHeader');
    if (header) {
      header.insertAdjacentHTML('afterend', html);
    } else {
      queuePanel.insertAdjacentHTML('afterbegin', html);
    }
    console.log('[SKILL JOB CARD] inserted into rcQueuePanel');
    return;
  }
  // Fallback: insert before rc_part_cards
  const fallback = document.getElementById('rc_part_cards');
  if (fallback) {
    fallback.insertAdjacentHTML('beforebegin', html);
    console.log('[SKILL JOB CARD] inserted via fallback anchor');
  } else {
    console.warn('[SKILL JOB CARD] no anchor found — card not inserted');
  }
}

async function _pollSkillJob() {
  if (!_srJobId) return;
  try {
    const resp = await fetch(`/api/skills/jobs/${encodeURIComponent(_srJobId)}`);
    if (!resp.ok) return;
    const job = await resp.json();
    _renderSkillJobCard(job);
    const st = String(job.status || '').toLowerCase();
    if (st === 'completed' || st === 'failed') _stopSkillJobMonitor();
  } catch (_) {}
}

function _renderSkillJobCard(job) {
  const card = document.getElementById('sr_active_card');
  if (!card) return;

  const result      = _srParseJson(job.result_json);
  const status      = String(job.status || '').toLowerCase();
  const terminal    = status === 'completed' || status === 'failed';
  const appliedList = Array.isArray(result.applied_skills) ? result.applied_skills : [];
  const skippedList = Array.isArray(result.skipped_skills) ? result.skipped_skills : [];
  const failedList  = Array.isArray(result.failed_skills)  ? result.failed_skills  : [];
  const stepErrors  = (result.step_errors && typeof result.step_errors === 'object') ? result.step_errors : {};
  const currentSk   = result.current_skill || null;
  const outputPath  = String(result.output_path || '');
  const pct         = Math.min(100, Math.max(0, Math.round(Number(job.progress_percent || 0))));

  card.dataset.status = status;

  // ── Console log transitions ────────────────────────────────────────────────
  if (currentSk && currentSk !== _srPrevCurrentSkill) {
    console.log('[SKILL STEP START]', currentSk);
  }
  appliedList.forEach((id) => {
    if (!_srPrevApplied.includes(id)) console.log('[SKILL STEP DONE]', id);
  });
  failedList.forEach((id) => {
    if (!_srPrevFailed.includes(id)) console.log('[SKILL STEP FAIL]', id, stepErrors[id] || '');
  });
  if (terminal && _srPrevStatus !== status) {
    console.log('[SKILL JOB DONE]', status,
      'applied:', appliedList.length, 'failed:', failedList.length, 'skipped:', skippedList.length);
  }
  _srPrevCurrentSkill = currentSk;
  _srPrevApplied      = [...appliedList];
  _srPrevFailed       = [...failedList];
  _srPrevStatus       = status;

  // ── Status badge ──────────────────────────────────────────────────────────
  const badgeEl = document.getElementById('sr_status_badge');
  if (badgeEl) {
    const labels = { queued: '○ Queued', running: '● Running', completed: '✓ Done', failed: '✕ Failed' };
    badgeEl.textContent = labels[status] || status;
    badgeEl.dataset.status = status;
  }

  // ── Duration badge (TikTok 70 s min) ─────────────────────────────────────
  const durBadge = document.getElementById('sr_duration_badge');
  if (durBadge) durBadge.classList.toggle('hiddenView', !result.duration_extended);

  // ── Progress fill ─────────────────────────────────────────────────────────
  const fillEl = document.getElementById('sr_progress_fill');
  if (fillEl) fillEl.style.width = `${pct}%`;

  // ── Skill step chips (duration_prepare + selected skills + finalize) ───────
  const stepsEl = document.getElementById('sr_skill_steps');
  if (stepsEl) {
    const chips = [];

    // duration_prepare chip — only shown if extension was applied
    if (result.duration_extended) {
      const durCtx   = result.duration_context || {};
      const durLabel = durCtx.original_duration != null
        ? `${durCtx.original_duration}s → ${durCtx.final_duration}s`
        : '70 s min';
      chips.push(`<span class="srStep srStepDone" title="Video looped to reach 70 s">⏱ ${_srEsc(durLabel)}</span>`);
    }

    // selected skill chips
    _srJobSkills.forEach((skillId) => {
      const done    = appliedList.includes(skillId);
      const fail    = failedList.includes(skillId);
      const skipped = skippedList.includes(skillId);
      const active  = !terminal && currentSk === skillId;
      const cls  = done ? 'srStepDone' : fail ? 'srStepFail' : skipped ? 'srStepSkip' : active ? 'srStepActive' : 'srStepWait';
      const icon = done ? '✓'         : fail ? '✗'          : skipped ? '—'          : active ? '●'            : '○';
      const label  = (_SKILL_META[skillId]?.label || skillId.replace(/_/g, ' '));
      const errTip = fail && stepErrors[skillId] ? ` title="${_srEsc(stepErrors[skillId])}"` : '';
      chips.push(`<span class="srStep ${cls}"${errTip}>${icon} ${label}</span>`);
    });

    // finalize chip — shown once we know whether it ran
    if (status === 'completed') {
      chips.push(`<span class="srStep srStepDone">✓ Finalize</span>`);
    } else if (status === 'failed') {
      chips.push(`<span class="srStep srStepSkip">— Finalize</span>`);
    } else if (pct >= 93) {
      chips.push(`<span class="srStep srStepActive">● Finalize</span>`);
    }

    stepsEl.innerHTML = chips.join('');
  }

  // ── Meta summary line ─────────────────────────────────────────────────────
  const metaEl = document.getElementById('sr_job_meta');
  if (metaEl) {
    const bits = [];
    if (pct > 0 && !terminal)   bits.push(`${pct}%`);
    if (appliedList.length)      bits.push(`${appliedList.length} applied`);
    if (failedList.length)       bits.push(`${failedList.length} failed`);
    if (skippedList.length)      bits.push(`${skippedList.length} skipped`);
    const msg = String(job.message || '').trim();
    if (msg && !terminal)        bits.push(msg);
    metaEl.textContent = bits.length
      ? bits.join(' · ')
      : (terminal ? (status === 'completed' ? 'Completed' : 'Failed') : 'Running…');
  }

  // ── Log timeline (last 8 events) ──────────────────────────────────────────
  _renderSkillJobLog(Array.isArray(result.events) ? result.events : []);

  // ── Output row on completion ──────────────────────────────────────────────
  const outEl = document.getElementById('sr_job_output');
  if (outEl) {
    if (terminal && outputPath) {
      outEl.classList.remove('hiddenView');
      const normalized = outputPath.replace(/\\/g, '/');
      const shortName  = normalized.split('/').pop();
      const folderPath = normalized.includes('/') ? normalized.split('/').slice(0, -1).join('/') : normalized;
      outEl.innerHTML = `
<div class="srOutputRow">
  <span class="srOutputName" title="${_srEsc(outputPath)}">${_srEsc(shortName)}</span>
  <div class="srOutputActions">
    <button class="srOutputBtn" data-path="${_srEsc(outputPath)}" onclick="_srOpenPath(this)" title="Open output file">Open Output</button>
    <button class="srOutputBtn" data-path="${_srEsc(folderPath)}" onclick="_srOpenPath(this)" title="Open containing folder">Open Folder</button>
  </div>
</div>`;
    } else {
      outEl.classList.add('hiddenView');
    }
  }
}

function _renderSkillJobLog(events) {
  const logEl = document.getElementById('sr_job_log');
  if (!logEl) return;
  const visible = events.length > 0;
  logEl.classList.toggle('hiddenView', !visible);
  if (!visible) return;

  logEl.innerHTML = events.slice(-8).map((ev) => {
    const ts  = ev.timestamp
      ? new Date(ev.timestamp).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
      : '';
    const lvl = String(ev.level || 'info').toLowerCase();
    const msg = ev.message || ev.event || '';
    return `<div class="srLogEntry" data-level="${lvl}">`
      + (ts ? `<span class="srLogTs">${_srEsc(ts)}</span>` : '')
      + `<span class="srLogMsg">${_srEsc(msg)}</span></div>`;
  }).join('');
}

function _srOpenPath(btn) {
  const p = (btn && btn.dataset && btn.dataset.path) ? btn.dataset.path.trim() : '';
  if (!p) return;
  if (typeof openStoredOutputPath === 'function') {
    openStoredOutputPath(p);
  } else {
    // Electron not available — copy path to clipboard as fallback
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(p).catch(() => {});
    }
    if (typeof showToast === 'function') showToast(`Path: ${p}`, 'info');
  }
}

function _dismissSkillJobCard() {
  _stopSkillJobMonitor();
  document.getElementById('sr_active_card')?.remove();
  _srJobId = null;
}

function _srParseJson(raw) {
  try { return (raw && typeof raw === 'string') ? JSON.parse(raw) : (raw || {}); } catch (_) { return {}; }
}

function _srEsc(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
