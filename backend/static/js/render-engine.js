async function startRender(){
  const outputDir = (qs('manual_output_dir')?.value || '').trim();
  const sourceMode = (qs('source_mode').value || 'youtube').trim();
  const youtubeUrl = (qs('youtube_url')?.value || '').trim();
  let localVideoPath = (selectedLocalVideoPath || '').trim();

  hideRenderCompletionBar();
  setRenderFlowState('source', sourceMode === 'youtube' ? 'YouTube source selected' : 'Local source selected', { force: true });

  if(!outputDir){
    addEvent('Validation error: please enter Output Folder before running.', 'render');
    showToast('Please choose an output folder before rendering', 'error');
    return;
  }

  if (sourceMode === 'youtube') {
    const validYouTube = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\//i.test(youtubeUrl || '');
    if (!youtubeUrl) {
      addEvent('Please enter a YouTube URL.', 'render');
      showToast('Please enter a YouTube URL', 'error');
      return;
    }
    if (!validYouTube) {
      addEvent('Please enter a valid YouTube URL (youtube.com or youtu.be).', 'render');
      showToast('Invalid YouTube URL', 'error');
      return;
    }
  }

  if (sourceMode !== 'youtube' && _pendingLocalFile) {
    localVideoPath = await uploadLocalFileIfNeeded();
  }
  if (sourceMode !== 'youtube' && !localVideoPath) {
    addEvent('Please choose a local video first.', 'render');
    showToast('Please choose a local video first', 'error');
    return;
  }

  // Base payload — all render settings will be finalized in the editor screen
  const payload = {
    output_mode: 'manual',
    source_mode: sourceMode,
    youtube_url: sourceMode === 'youtube' ? youtubeUrl : null,
    source_video_path: sourceMode === 'local' ? localVideoPath : null,
    output_dir: outputDir,
    // Defaults (will be overridden by editor UI before submit)
    aspect_ratio: '3:4',
    render_profile: 'balanced',
    render_preset: 'custom',
    render_preset_id: null,
    render_preset_label: null,
    video_codec: 'h264',
    audio_bitrate: '256k',
    transition_sec: 0.25,
    encoder_mode: 'auto',
    output_fps: 60,
    playback_speed: 1.07,
    min_part_sec: 70,
    max_part_sec: 180,
    add_subtitle: true,
    add_title_overlay: false,
    title_overlay_text: '',
    source_quality_mode: 'standard_1080',
    auto_detect_scene: true,
    highlight_per_word: true,
    effect_preset: 'story_clean_01',
    subtitle_style: 'pro_karaoke',
    max_export_parts: 0,
    frame_scale_x: 100,
    frame_scale_y: 106,
    motion_aware_crop: false,
    whisper_model: 'auto',
    retry_count: 2,
    resume_job_id: null,
    keep_source_copy: false,
    cleanup_temp_files: true,
    reup_mode: false,
    reup_overlay_enable: false,
    reup_overlay_opacity: 0.08,
    reup_bgm_enable: false,
    reup_bgm_path: null,
    reup_bgm_gain: 0.18,
    subtitle_only_viral_high: true,
    subtitle_viral_min_score: 68,
    subtitle_viral_top_ratio: 0.6,
    max_parallel_parts: 0,
    part_order: 'viral',
    viral_market: 'US',
    hook_apply_enabled: false,
    hook_applied_text: '',
    hook_score: null,
    text_layers: [],
  };

  // ── YouTube: download first (with cancel support), then open editor ──
  // ── Local: open editor immediately (prepare-source is fast validation only) ──
  if (sourceMode === 'youtube') {
    setRenderFlowState('source', 'Downloading source');
    const btn = qs('start_render_btn');
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Downloading…';
    btn.style.opacity = '0.75';

    // Show download progress panel
    const dlPanel = qs('yt_dl_progress');
    const dlMsg   = qs('yt_dl_msg');
    const dlElapsed = qs('yt_dl_elapsed');
    if (dlPanel) dlPanel.classList.remove('hiddenView');
    if (dlMsg) dlMsg.textContent = 'Downloading YouTube video…';

    // Elapsed-time counter
    let _dlStart = Date.now();
    let _dlTimer = setInterval(() => {
      const s = Math.round((Date.now() - _dlStart) / 1000);
      if (dlElapsed) dlElapsed.textContent = s + 's';
    }, 1000);

    addEvent('Downloading YouTube video…', 'render');
    _ytDownloadAbortCtrl = new AbortController();
    _ytPrepareSid = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    try {
      const pr = await fetch('/api/render/prepare-source', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ source_mode: 'youtube', youtube_url: youtubeUrl, session_id: _ytPrepareSid }),
        signal: _ytDownloadAbortCtrl.signal,
      });
      const pd = await pr.json();
      if (!pr.ok) throw new Error(_formatApiError(pd.detail));
      const dur = _fmtTime(pd.duration || 0);
      if (dlMsg) dlMsg.textContent = `Downloaded: ${pd.title || 'video'} (${dur})`;
      addEvent(`Download complete: ${pd.title} (${dur})`, 'render');
      showToast(`Downloaded: ${pd.title || 'video'} (${dur})`, 'success');
      setRenderFlowState('configure', 'Editing clip');
      payload.edit_session_id = pd.session_id;
      openEditorView_withSession(pd, youtubeUrl, payload);
    } catch(err) {
      const wasCancelled = err.name === 'AbortError';
      if (wasCancelled) {
        addEvent('Download cancelled.', 'render');
        showToast('Download cancelled', 'info');
      } else {
        addEvent(`Download failed: ${err.message}`, 'render');
        showToast('Video could not be downloaded', 'error');
      }
      btn.disabled = false;
      btn.textContent = origText;
      btn.style.opacity = '1';
    } finally {
      if (dlPanel) dlPanel.classList.add('hiddenView');
      clearInterval(_dlTimer);
      _ytDownloadAbortCtrl = null;
      _ytPrepareSid = null;
    }
    return;
  } else {
    setRenderFlowState('configure', 'Preparing editor');
    openEditorView(sourceMode, localVideoPath, payload);
  }
}

function cancelYtDownload() {
  const sid = _ytPrepareSid;
  if (_ytDownloadAbortCtrl) {
    _ytDownloadAbortCtrl.abort();
    _ytDownloadAbortCtrl = null;
  }
  if (sid) {
    fetch(`/api/render/prepare-source/${encodeURIComponent(sid)}`, { method: 'DELETE' }).catch(() => {});
    _ytPrepareSid = null;
  }
}

async function resumeRender(){
  const jobId = (qs('resume_job_id').value || '').trim();
  if(!jobId){
    addEvent('Please provide job id to resume', 'render');
    showToast('Please enter a job ID to resume', 'error');
    return;
  }
  const res = await fetch(`/api/render/resume/${jobId}`, { method:'POST' });
  const data = await res.json();
  if(!res.ok){
    const errMsg = (typeof friendlyRenderError === 'function')
      ? friendlyRenderError(data.detail, 'Render could not start')
      : 'Render could not start';
    const detail = Array.isArray(data.detail)
      ? data.detail.map((e) => e?.msg || JSON.stringify(e)).join(' | ')
      : String(data.detail || 'unknown error');
    addEvent(`Resume failed: ${detail}`, 'render');
    showToast(errMsg, 'error');
    setRenderFlowState('configure', 'Render could not start', { force: true });
    return;
  }
  currentJobId = data.job_id;
  activeJobStartedAt = Date.now();
  lastStage = '';
  lastMessage = '';
  lastStatus = '';
  lastProgressBucket = -1;
  // Reset smooth animation state for fresh job
  _jobTargetPct = 0; _jobDisplayPct = 0;
  for(const k of Object.keys(_partTarget)) delete _partTarget[k];
  for(const k of Object.keys(_partDisplay)) delete _partDisplay[k];
  hideRenderCompletionBar();
  resetRenderMonitorHeartbeat();
  updateRenderMainState(null, null, []);
  setRenderActionBusy(true);
  setHeaderJob('Render resumed');
  setRenderFlowState('rendering', 'Resumed render', { force: true });
  addEvent('Resume queued', 'render');
  startPolling(currentJobId);
  if (typeof _startQueueStatusPolling === 'function') _startQueueStatusPolling();
}

function _applyJobUpdate(job, parts, summary){
  const s = summary || computeProgressSummary(parts||[]);
  const stage = (typeof normalizeRenderStage === 'function') ? normalizeRenderStage(job.stage, job.status) : (job.stage || '').toLowerCase();
  const status = (typeof normalizeRenderStatus === 'function') ? normalizeRenderStatus(job.status, stage) : String(job.status || '').toLowerCase();
  const isPartial = typeof isPartialRenderStatus === 'function' ? isPartialRenderStatus(status) : (status === 'completed_with_errors' || status === 'partial_failed');
  const isCompleted = typeof isCompletedRenderStatus === 'function' ? (isCompletedRenderStatus(status) || isPartial) : (status === 'completed' || status === 'done' || status === 'complete' || isPartial);
  const isFailed = status === 'failed';
  const isTerminal = typeof isTerminalRenderStatus === 'function'
    ? isTerminalRenderStatus(status)
    : (isCompleted || isFailed);

  // During rendering, derive finer progress from parts aggregate.
  // Rendering occupies 30–90 % of the overall bar.
  const targetPercent = (typeof deriveRenderProgress === 'function')
    ? deriveRenderProgress(job, s, parts || [])
    : Math.max(0, Math.min(100, Math.round(Number(job.progress_percent || 0))));

  // Feed the smooth animation target; the RAF loop updates DOM for job bar
  _jobTargetPct = Math.max(_jobTargetPct, targetPercent);
  if(isTerminal){
    _jobTargetPct = targetPercent;
    _jobDisplayPct = targetPercent;
    const bar = document.getElementById('job_bar');
    const pctEl = document.getElementById('job_percent');
    if(bar) bar.style.width = targetPercent + '%';
    if(pctEl) pctEl.textContent = targetPercent + '%';
  } else {
    _scheduleSmooth();
  }
  markRenderMonitorUpdate(job, s, parts, targetPercent);
  if (typeof updateRenderProgressVisual === 'function') updateRenderProgressVisual(job);

  qs('job_stage_pill').textContent = typeof renderUxStageLabel === 'function' ? renderUxStageLabel(job, s, parts || []) : stageLabelPlain(stage);
  const sourceLabel = (typeof getRenderMonitorSourceText === 'function')
    ? getRenderMonitorSourceText(job)
    : 'Source unavailable';
  qs('job_title').textContent = status === 'pending' ? `Queued · ${sourceLabel}` : sourceLabel;
  qs('job_meta_1').textContent = `Channel ${job.channel_code || '-'} | ${sourceLabel}`;
  qs('job_message').textContent = String(job.message || '').trim() || friendlyJobMessage(job);
  setActionState(job);
  renderPipeline(stage, status);
  renderSteps(targetPercent);
  updateRenderFlowByJob(job, s, parts);

  renderParts(parts, s);
  renderPartFocus(parts, s);
  updateRenderMainState(job, s, parts);
  updateRenderMonitorHeartbeat(job, s, parts);
  updateStatusBar(job, s);
  const doneCount = getCompletedClipCount(s, parts);
  const totalCount = s.total_parts || parts.length;
  const parallelNote = s.processing_parts > 1 ? ` | ${s.processing_parts} parallel` : '';
  qs('job_meta_2').textContent = `${doneCount}/${totalCount} clips done | ${(typeof renderUxStageLabel === 'function' ? renderUxStageLabel(job, s, parts || []) : stageLabelPlain(stage))}${parallelNote}`;

  if(job.stage && job.stage !== lastStage){
    if(lastStage) addEvent(`Finished step: ${stageLabelPlain(lastStage)}`, 'render');
    addEvent(`Stage: ${stageLabelPlain(stage)} (${targetPercent}%)`, 'render');
    lastStage = job.stage;
  }
  if(job.message && job.message !== lastMessage){
    addEvent(`Action: ${job.message}`, 'render');
    lastMessage = job.message;
  }
  if(job.status && job.status !== lastStatus){
    addEvent(`Status: ${job.status}`, 'render');
    lastStatus = job.status;
  }
  const bucket = Math.floor(targetPercent / 10);
  if(!isTerminal && bucket !== lastProgressBucket){
    addEvent(`Running: ${stageLabelPlain(stage)} (${targetPercent}%)`, 'render');
    lastProgressBucket = bucket;
  }

  if(isTerminal){
    _stopJobWs();
    if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
    if (typeof _stopQueueStatusPolling === 'function') _stopQueueStatusPolling();
    setRenderActionBusy(false);
    saveRenderHistoryEntry(job, s, parts);
    if(isFailed && currentJobId && lastFailLogJobId !== currentJobId){
      fetch(`/api/jobs/${currentJobId}/logs?lines=1`)
        .then(r => r.json()).then(ldata => {
          const lf = ldata?.log_file || '';
          if(lf) addEvent(`Render failed. Diagnostics log: ${lf}`, 'render');
          else addEvent('Render failed. Review clips first, then diagnostics if needed.', 'render');
          lastFailLogJobId = currentJobId;
        }).catch(_=>{ addEvent('Render failed. Review clips first, then diagnostics if needed.', 'render'); });
    }
    if (isCompleted) {
      const handoff = buildCompletionHandoff(s, parts, job);
      showRenderCompletionBar(handoff.main, handoff.detail);
      setRenderFlowState('complete', isPartial ? `${doneCount} clips ready with errors` : `${doneCount} clips ready`);
      if (typeof populateRenderOutputPanel === 'function') {
        populateRenderOutputPanel(job, parts);
        augmentRenderOutputRanking(job);
      }
    } else {
      hideRenderCompletionBar();
      if (typeof clearRenderOutputPanel === 'function') clearRenderOutputPanel();
    }
    addEvent(`Job ${job.status}`, 'render');
  }
}

// Legacy HTTP polling (fallback when WebSocket unavailable)
async function loadJobProgress(){
  if(!currentJobId) return;
  if (_pollStartedAt && (Date.now() - _pollStartedAt) > 3 * 3600 * 1000) {
    clearInterval(pollTimer); pollTimer = null; _pollStartedAt = 0;
    addEvent('Polling stopped after 3 hours — job may be stuck. Check diagnostics.', 'render');
    setRenderActionBusy(false);
    return;
  }
  try {
    const [jobRes, partsRes] = await Promise.all([
      fetch(`/api/jobs/${currentJobId}`),
      fetch(`/api/jobs/${currentJobId}/parts`),
    ]);
    const job = await jobRes.json();
    const partsData = await partsRes.json();
    _applyJobUpdate(job, partsData.items || [], computeProgressSummary(partsData.items || []));
  } catch(_) {}
}

function _stopJobWs(){
  if(jobWs){ try{ jobWs.close(); }catch(_){} jobWs = null; }
}

function startPolling(jobId = null){
  if (jobId) currentJobId = jobId;
  if (!currentJobId) return;
  _pollStartedAt = Date.now();
  // Try WebSocket first; fall back to HTTP polling on error
  _stopJobWs();
  if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
  loadJobProgress();
  pollTimer = setInterval(loadJobProgress, pollIntervalMs);

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/api/jobs/${currentJobId}/ws`);
  jobWs = ws;

  ws.onmessage = (ev) => {
    try {
      const d = JSON.parse(ev.data);
      if(d.error) return;
      _applyJobUpdate(d.job, d.parts || [], d.summary || null);
    } catch(_) {}
  };

  ws.onerror = () => {
    // WebSocket failed — degrade gracefully to polling
    jobWs = null;
  };

  ws.onclose = () => {
    jobWs = null;
    if (!currentJobId) return;
    if (isTerminalRenderStatus(lastStatus)) return;
    if (!pollTimer) {
      loadJobProgress();
      pollTimer = setInterval(loadJobProgress, pollIntervalMs);
    }
  };
}

async function loadJobs(){
  const jobsOut = qs('jobs_out');
  if(!jobsOut) return;
  if(RENDER_SESSION_ONLY){
    jobsOut.innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
    return;
  }
  const res = await fetch('/api/jobs');
  const data = await res.json();
  const items = (data.items || []).slice(0, 12);
  if(!items.length){ jobsOut.innerHTML = '<div class="emptyState">No jobs yet.</div>'; return; }
  jobsOut.innerHTML = items.map(j => `
    <div class="partRow">
      <div class="partLeft"><div class="rankBadge">J</div><div><div class="partName">${esc(j.job_id)}</div><div class="partMeta">${esc(j.updated_at || '')}</div></div></div>
      <div><div class="miniProgress"><div class="miniProgressValue" style="width:${Number(j.progress_percent || 0)}%"></div></div><div class="partMeta">${Number(j.progress_percent || 0)}%</div></div>
      <div class="partRight"><div class="statusBadge ${esc((j.status || '').toLowerCase())}">${esc(j.status || '')}</div><div class="scoreBox">${esc(j.stage || '')}</div></div>
    </div>
  `).join('');
}

// Upload domain removed (Phase 4F.5B). Functions collectUploadPayload through _stopUploadWs deleted.

async function _submitRenderPayload(payload, isBatch) {
  const endpoint = isBatch ? '/api/render/process/batch' : '/api/render/process';
  const res  = await fetch(endpoint, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok) {
    const errMsg = _formatApiError(data.detail);
    addEvent(`Start render failed: ${errMsg}`, 'render');
    setRenderActionBusy(false);
    return { ok: false, error: errMsg };
  }
  currentJobId = isBatch ? data.batch_id : data.job_id;
  try { sessionStorage.setItem('rc_last_job_id', currentJobId); } catch(_) {}
  activeJobStartedAt = Date.now();
  lastStage = ''; lastMessage = ''; lastStatus = ''; lastProgressBucket = -1;
  _jobTargetPct = 0; _jobDisplayPct = 0;
  for(const k of Object.keys(_partTarget)) delete _partTarget[k];
  for(const k of Object.keys(_partDisplay)) delete _partDisplay[k];
  setRenderActionBusy(true);
  setHeaderJob('Render running');
  addEvent(isBatch ? `Queued render batch (${data.count || '?'} links)` : 'Queued render job', 'render');
  startPolling(currentJobId);
  if (typeof _startQueueStatusPolling === 'function') _startQueueStatusPolling();
  return { ok: true, error: null };
}

function _renderJobRankingMap(job) {
  const map = new Map();
  try {
    const raw = job?.result_json;
    const result = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
    const ranking = Array.isArray(result?.output_ranking) ? result.output_ranking : [];
    for (const r of ranking) {
      const partNo = Number(r?.part_no || 0);
      if (!partNo) continue;
      map.set(partNo, {
        rank: Number(r.output_rank || 0),
        score: Number(r.output_score ?? r.output_rank_score ?? 0),
        isBest: !!(r.is_best_clip ?? r.is_best_output),
        reason: String(r.ranking_reason || r.reasons || '').trim(),
      });
    }
  } catch (_) {}
  return map;
}

function augmentRenderOutputRanking(job) {
  const list = qs('render_output_list');
  if (!list) return;
  const ranking = _renderJobRankingMap(job);
  if (!ranking.size) return;

  list.querySelectorAll('.renderClipItem').forEach((item) => {
    const partNo = Number(item.querySelector('.renderClipNum')?.textContent || 0);
    const data = ranking.get(partNo);
    if (!data) return;

    item.classList.toggle('isBestClip', data.isBest);
    item.querySelectorAll('.renderClipRanking, .renderClipBestBadge').forEach((el) => el.remove());

    const nameEl = item.querySelector('.renderClipName');
    if (nameEl && data.isBest) {
      const badge = document.createElement('span');
      badge.className = 'renderClipBestBadge';
      badge.textContent = 'Best Clip';
      badge.style.cssText = 'display:inline-flex;margin-left:8px;padding:2px 6px;border-radius:999px;background:rgba(34,197,94,.14);border:1px solid rgba(34,197,94,.35);color:#86efac;font-size:10px;font-weight:700;vertical-align:middle;';
      nameEl.appendChild(badge);
    }

    const infoEl = item.querySelector('.renderClipInfo');
    if (!infoEl) return;
    const row = document.createElement('div');
    row.className = 'renderClipRanking';
    row.textContent = `Rank #${data.rank || '-'} · Score ${Number(data.score || 0).toFixed(1)}${data.reason ? ` · ${data.reason}` : ''}`;
    row.style.cssText = 'margin-top:3px;font-size:11px;color:rgba(148,163,184,.72);line-height:1.35;';
    infoEl.appendChild(row);
  });
}

