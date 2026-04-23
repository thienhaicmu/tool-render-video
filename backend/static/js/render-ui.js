const RENDER_FLOW_ORDER = ['source', 'configure', 'rendering', 'complete'];
let _renderFlowStepRank = 0;

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
  qs('job_meta_2').textContent = '0/0 parts done | 0 scenes';
  qs('job_percent').textContent = '0%';
  qs('job_message').textContent = 'Initializing';
  qs('job_bar').style.width = '0%';
  qs('action_title').textContent = 'Waiting for job';
  qs('action_state').textContent = 'idle';
  if (qs('action_state')) qs('action_state').dataset.status = 'idle';
  qs('action_message').textContent = 'No active processing task.';
  qs('action_meta').textContent = 'Elapsed 00:00 | Updated -';
  renderPipeline('queued', 'queued');
  renderSteps(0);
  renderParts([]);
  renderPartFocus([]);
  if(RENDER_SESSION_ONLY && qs('jobs_out')){
    qs('jobs_out').innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
  }
  setRenderFlowState('source', 'Select source', { source: 'active', force: true });
  hideRenderCompletionBar();
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
function friendlyJobMessage(job){
  const status = String(job?.status || '').toLowerCase();
  const stage = String(job?.stage || '').toLowerCase();
  if (status === 'completed') return 'Render complete.';
  if (status === 'failed') return 'Render failed. Check details below.';
  if (status === 'queued') return 'Waiting to start.';
  return stageLabel(stage);
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
    rendering: 'Rendering',
    done: 'Done',
    failed: 'Failed'
  };
  return map[s] || s;
}
function setActionState(job){
  const stage = (job.stage || '').toLowerCase();
  const status = (job.status || '').toLowerCase();
  const running = !(status === 'completed' || status === 'failed');
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
  if (status === 'completed') {
    setRenderFlowState('complete', `${getCompletedClipCount(summary, parts)} clips ready`);
    return;
  }
  if (status === 'failed') {
    setRenderFlowState('rendering', 'Failed', { source: 'done', configure: 'done', rendering: 'active', complete: 'pending' });
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
  const items = Array.isArray(parts) ? parts : [];
  const failed = Number(summary?.failed_parts ?? items.filter((p) => String(p?.status || '').toLowerCase() === 'failed').length) || 0;
  const total = Number(summary?.total_parts ?? items.length) || 0;
  const summaryCompleted = Number(summary?.completed_parts);
  const doneParts = items.filter((p) => String(p?.status || '').toLowerCase() === 'done').length;
  const completed = Number.isFinite(summaryCompleted)
    ? summaryCompleted
    : (doneParts || Math.max(0, total - failed));
  const totalLabel = total || (completed + failed);
  const outputDir = getCurrentJobOutputDir(job);
  const main = failed > 0
    ? `Render complete - ${completed} clips completed, ${failed} failed`
    : `✓ Render complete - ${completed} clips ready`;
  const detailParts = [];
  if (totalLabel > 0) detailParts.push(`${totalLabel} total clips`);
  detailParts.push(failed > 0 ? 'Review failed clips in the log' : 'Report generated successfully');
  detailParts.push(outputDir ? 'Saved to output folder' : 'Output folder path unavailable');
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

function getCurrentJobOutputDir(job) {
  try {
    const payload = JSON.parse(job?.payload_json || '{}');
    return String(payload.output_dir || '').trim();
  } catch (_) {
    return '';
  }
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

function focusBottomPanel() {
  const panel = qs('appBottomPanel');
  if (!panel) return;
  if (typeof _collapseBottomPanel === 'function') _collapseBottomPanel(false);
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
  const stateLabel = { pending: 'Waiting', running: 'In Progress', done: 'Done', failed: 'Failed' };
  const nodes = pipelineStateByStage(stage, status);
  qs('pipeline_wrap').innerHTML = nodes.map(n => `
    <div class="pipelineNode ${n.state}">
      <div class="nTitle">${n.label}</div>
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
    focusBottomPanel();
    const panel = qs('appBottomPanel');
    if (panel) {
      panel.classList.remove('renderStartPulse');
      void panel.offsetWidth;
      panel.classList.add('renderStartPulse');
    }
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
  if(!items || !items.length){ wrap.innerHTML = '<div class="emptyState">Parts will appear here once rendering begins.</div>'; return; }
  const ordered = [...items].sort((a,b)=>Number(a.part_no||0)-Number(b.part_no||0));
  const stuckMap = _stuckPartsMap(summary, items);
  syncPartProgressTargets(ordered);
  wrap.innerHTML = ordered.map((p, idx) => {
    const st     = (p.status || '').toLowerCase();
    const isRun  = st === 'waiting' || st === 'cutting' || st === 'transcribing' || st === 'rendering';
    const key    = String(p.part_no ?? idx + 1);
    const isStuck = isRun && stuckMap.has(key);
    const disp   = Math.round(_partDisplay[key] ?? Number(p.progress_percent || 0));
    const errMsg  = st === 'failed' ? esc(p.message || '') : '';
    const errHtml = errMsg ? `<div class="partError">${errMsg}</div>` : '';
    const stuckHtml = isStuck ? `<div class="partStuckNote">${_stuckLabel(stuckMap.get(key))}</div>` : '';
    const rowClass  = `${st || 'queued'}${isRun ? ' running' : ''}${isStuck ? ' stuck' : ''}`.trim();
    const partName = p.part_name ? esc(p.part_name) : `Part ${Number(p.part_no || idx + 1)}`;
    return `
    <div class="partRow ${rowClass}">
      <div class="partLeft">
        <div class="rankBadge">P${Number(p.part_no || idx + 1)}</div>
        <div>
          <div class="partName">${partName}</div>
          <div class="partMeta">${Number(p.start_sec || 0).toFixed(1)}s -> ${Number(p.end_sec || 0).toFixed(1)}s | Motion ${Number(p.motion_score || 0).toFixed(0)} | Hook ${Number(p.hook_score || 0).toFixed(0)}</div>
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
        <div class="scoreBox">Viral ${Number(p.viral_score || 0).toFixed(0)}</div>
      </div>
    </div>
  `}).join('');
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
    box.innerHTML = '<div class="partFocusTitle">Live Part Tracking</div><div class="partFocusLine">Parts will appear here once rendering begins.</div>';
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
    <span class="partsSummaryLabel">Parts</span>
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

  box.innerHTML = `<div class="partFocusTitle">Live Part Tracking</div>${activeBarHtml}${stripHtml}<div class="partsProgressGrid">${cardsHtml}</div>`;
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
  const isRunning = status === 'running';
  const isDone    = status === 'completed';
  const isFailed  = status === 'failed';

  dot.className = 'statusDot ' + (isFailed ? 'statusDotFailed' : isRunning ? 'statusDotRunning' : 'statusDotReady');
  label.textContent = isDone ? 'Done' : isFailed ? 'Failed' : isRunning ? stageLabelPlain(stage) : 'Idle';

  if (sumEl) {
    if (summary && summary.total_parts > 0) {
      const d = summary.completed_parts || 0;
      const t = summary.total_parts || 0;
      const a = summary.processing_parts > 0 ? ` · ${summary.processing_parts} active` : '';
      sumEl.textContent = `— ${d}/${t} parts${a}`;
    } else {
      sumEl.textContent = '';
    }
  }

  if (pctEl) pctEl.textContent = (isRunning || isDone) ? pct + '%' : '';
  if (area)  area.style.cursor = currentJobId ? 'pointer' : 'default';
}

