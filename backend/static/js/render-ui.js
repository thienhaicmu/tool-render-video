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
  const _vmReset = qs('view_monitor');
  if (_vmReset) _vmReset.dataset.jmStatus = 'idle';
  renderPipeline('queued', 'queued');
  renderSteps(0);
  renderParts([]);
  renderPartFocus([]);
  if(RENDER_SESSION_ONLY && qs('jobs_out')){
    qs('jobs_out').innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
  }
}
function fmtElapsed(ms){
  const sec = Math.max(0, Math.floor(ms / 1000));
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss = String(sec % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}
function stageLabel(stage){
  const map = {
    queued: 'Queued',
    starting: 'Initializing render resources',
    downloading: 'Downloading source video',
    scene_detection: 'Detecting scene boundaries',
    segment_building: 'Building smart segments',
    transcribing_full: 'Generating full subtitles',
    rendering: 'Rendering parts',
    rendering_parallel: 'Rendering parts (parallel)',
    writing_report: 'Writing report and outputs',
    done: 'Completed',
    failed: 'Failed',
  };
  return map[stage] || 'Processing';
}
function stageLabelPlain(stage){
  const map = {
    queued: 'Queued',
    starting: 'Starting',
    downloading: 'Download',
    scene_detection: 'Scene Detection',
    segment_building: 'Segment Build',
    transcribing_full: 'Subtitle (Full)',
    rendering: 'Render',
    rendering_parallel: 'Render (Parallel)',
    writing_report: 'Report',
    done: 'Done',
    failed: 'Failed',
  };
  return map[(stage || '').toLowerCase()] || (stage || '-');
}
function partStatusLabel(status){
  const s = (status || '').toLowerCase();
  const map = {
    queued: 'queued',
    waiting: 'waiting',
    cutting: 'cutting',
    transcribing: 'transcribing',
    rendering: 'rendering',
    done: 'done',
    failed: 'failed'
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
  qs('action_title').textContent = stageLabel(stage);
  qs('action_state').textContent = status || 'running';
  qs('action_message').textContent = job.message || stageLabel(stage);
  qs('action_meta').textContent = `Elapsed ${elapsed} | Updated ${new Date().toLocaleTimeString()}`;
  // Phase 6: propagate status/stage as data attributes for CSS visual state
  const _vm = qs('view_monitor');
  if (_vm) _vm.dataset.jmStatus = status || 'running';
  const _stEl = qs('action_state');
  if (_stEl) _stEl.dataset.status = status || 'running';
  const _pill = qs('job_stage_pill');
  if (_pill) _pill.dataset.stage = stage;
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
  const stateLabel = { pending: 'pending', running: 'running', done: 'done', failed: 'failed' };
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
  btn.textContent = isBusy ? 'Running...' : 'Download + Render';

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
  const stateLabel = { pending: 'pending', running: 'running', done: 'done' };
  qs('steps_grid').innerHTML = steps.map((s, i) => {
    const st = stepStatus(i, progress || 0);
    return `<div class="stepCard ${st}"><div class="stepIconWrap">${st === 'done' ? 'OK' : st === 'running' ? 'RUN' : '...'}</div><div><div class="stepTitle">${s.label}</div><div class="stepStatus">${stateLabel[st] || st}</div></div></div>`;
  }).join('');
}

function renderParts(items, summary){
  const wrap = qs('parts_wrap');
  if(!items || !items.length){ wrap.innerHTML = '<div class="emptyState">No parts yet.</div>'; return; }
  const ordered = [...items].sort((a,b)=>Number(a.part_no||0)-Number(b.part_no||0));
  const stuckMap = _stuckPartsMap(summary, items);
  wrap.innerHTML = ordered.map((p, idx) => {
    const st     = (p.status || '').toLowerCase();
    const isRun  = st === 'waiting' || st === 'cutting' || st === 'transcribing' || st === 'rendering';
    const key    = String(p.part_no ?? idx + 1);
    const isStuck = isRun && stuckMap.has(key);
    const errMsg  = st === 'failed' ? esc(p.message || '') : '';
    const errHtml = errMsg ? `<div class="partError">${errMsg}</div>` : '';
    const stuckHtml = isStuck ? `<div class="partStuckNote">${_stuckLabel(stuckMap.get(key))}</div>` : '';
    const rowClass  = isRun ? (isStuck ? 'running stuck' : 'running') : '';
    return `
    <div class="partRow ${rowClass}">
      <div class="partLeft">
        <div class="rankBadge">P${Number(p.part_no || idx + 1)}</div>
        <div>
          <div class="partName">${esc(p.part_name)}</div>
          <div class="partMeta">${Number(p.start_sec || 0).toFixed(1)}s -> ${Number(p.end_sec || 0).toFixed(1)}s | Motion ${Number(p.motion_score || 0).toFixed(0)} | Hook ${Number(p.hook_score || 0).toFixed(0)}</div>
          ${errHtml}${stuckHtml}
        </div>
      </div>
      <div>
        <div class="miniProgress"><div class="miniProgressValue" style="width:${Number(p.progress_percent || 0)}%"></div></div>
        <div class="partMeta">${Number(p.progress_percent || 0)}%</div>
      </div>
      <div class="partRight">
        <div class="statusBadge ${esc((p.status || '').toLowerCase())}">${partStatusLabel(p.status)}</div>
        <div class="scoreBox">Viral ${Number(p.viral_score || 0).toFixed(0)}</div>
      </div>
    </div>
  `}).join('');
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
    box.innerHTML = '<div class="partFocusTitle">Live Part Tracking</div><div class="partFocusLine">No parts yet.</div>';
    return;
  }

  // ── Sync smooth-animation targets from backend data ─────────────────
  ordered.forEach(p => {
    const key = String(p.part_no || 0);
    const backendPct = Number(p.progress_percent || 0);
    _partTarget[key] = backendPct;
    // On first sight of a part, seed display at backend value (no fake lag on fresh data)
    if(_partDisplay[key] == null) _partDisplay[key] = backendPct;
    // If part completed or failed, snap display to final value immediately
    const st = (p.status||'').toLowerCase();
    if(st === 'done' || st === 'failed') _partDisplay[key] = backendPct;
  });
  _scheduleSmooth();

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

