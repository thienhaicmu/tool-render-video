async function startRender(){
  console.log('[EditorOpen] clicked');
  const outputMode = (qs('output_mode')?.value || 'channel').trim().toLowerCase();
  const channel = (qs('channel_code').value || '').trim();
  const sourceMode = (qs('source_mode').value || 'youtube').trim();
  const youtubeUrl = (qs('youtube_url')?.value || '').trim();
  let localVideoPath = (selectedLocalVideoPath || '').trim();
  const outputDir = outputMode === 'channel'
    ? (selectedRenderOutputDir || qs('render_output_dir').value || '').trim()
    : (qs('manual_output_dir')?.value || '').trim();

  hideRenderCompletionBar();
  setRenderFlowState('source', sourceMode === 'youtube' ? 'YouTube source selected' : 'Local source selected', { force: true });

  if(outputMode === 'channel' && !channel){
    addEvent('Validation error: please select target channel first.', 'render');
    showToast('Please select a target channel first', 'error');
    return;
  }
  if(!outputDir){
    addEvent(outputMode === 'channel'
      ? 'Validation error: cannot resolve output folder from channel. Please re-select channel.'
      : 'Validation error: please enter Manual Output Folder before running.', 'render');
    showToast(outputMode === 'channel'
      ? 'Please re-select the channel output folder'
      : 'Please choose an output folder before rendering', 'error');
    return;
  }

  const outNorm = outputDir.replace(/\\/g, '/').toLowerCase();
  let renderSubdir = 'upload/video_output';
  if(outputMode === 'channel'){
    const root = String(renderChannelsRootPath || defaultChannelsRootPath || '').trim();
    const basePath = root ? _joinWinPath(root, channel) : '';
    const baseNorm = basePath.replace(/\\/g, '/').toLowerCase();
    if(baseNorm && !outNorm.startsWith(baseNorm)){
      addEvent(`Validation error: output folder must be inside channel '${channel}' (example: ${_joinWinPath(root, channel, 'upload', 'video_output')}).`, 'render');
      showToast(`Output folder must be inside channel '${channel}'`, 'error');
      return;
    }
    if(baseNorm){
      const rawTail = outputDir.replace(/\\/g, '/').slice(baseNorm.length).replace(/^\/+/, '');
      renderSubdir = rawTail || 'upload/video_output';
    } else {
      // Fallback for unknown root: keep old relative extraction by '/channels/<code>/' if present.
      const channelNeedle = `/channels/${channel.toLowerCase()}/`;
      const idx = outNorm.indexOf(channelNeedle);
      if(idx >= 0){
        const rawTail = outputDir.replace(/\\/g, '/').slice(idx + channelNeedle.length).replace(/^\/+/, '');
        renderSubdir = rawTail || 'upload/video_output';
      } else {
        renderSubdir = 'upload/video_output';
      }
    }
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
    output_mode: outputMode,
    source_mode: sourceMode,
    youtube_url: sourceMode === 'youtube' ? youtubeUrl : null,
    source_video_path: sourceMode === 'local' ? localVideoPath : null,
    channel_code: outputMode === 'channel' ? channel : '',
    output_dir: outputDir,
    render_output_subdir: renderSubdir,
    // Defaults (will be overridden by editor UI before submit)
    aspect_ratio: '3:4',
    render_profile: 'balanced',
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
    keep_source_copy: true,
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
    try {
      const pr = await fetch('/api/render/prepare-source', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ source_mode: 'youtube', youtube_url: youtubeUrl }),
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
    }
    return;
  } else {
    setRenderFlowState('configure', 'Preparing editor');
    openEditorView(sourceMode, localVideoPath, payload);
  }
}

function cancelYtDownload() {
  if (_ytDownloadAbortCtrl) {
    _ytDownloadAbortCtrl.abort();
    _ytDownloadAbortCtrl = null;
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
  startPolling();
}

function _applyJobUpdate(job, parts, summary){
  const s = summary || computeProgressSummary(parts||[]);
  const jobProgress = Number(job.progress_percent || 0);
  const stage = (job.stage || '').toLowerCase();
  const status = String(job.status || '').toLowerCase();
  const isCompleted = status === 'completed' || status === 'done' || status === 'complete';
  const isFailed = status === 'failed' || status === 'interrupted';
  const isTerminal = typeof isTerminalRenderStatus === 'function'
    ? isTerminalRenderStatus(status)
    : (isCompleted || isFailed);

  // During rendering, derive finer progress from parts aggregate.
  // Rendering occupies 30–90 % of the overall bar.
  const overallPct = s.overall_progress_percent ?? s.parts_percent ?? 0;
  let targetPercent = jobProgress;
  if((stage === 'rendering' || stage === 'rendering_parallel') && s.total_parts > 0 && overallPct > 0){
    targetPercent = Math.min(90, Math.round(30 + (overallPct / 100) * 60));
  }
  // Snap to 100 immediately on terminal states
  if(isCompleted) targetPercent = 100;

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

  qs('job_stage_pill').textContent = stageLabelPlain(job.stage);
  const sourceLabel = (typeof getRenderMonitorSourceText === 'function')
    ? getRenderMonitorSourceText(job)
    : 'Source unavailable';
  qs('job_title').textContent = job.status === 'queued' ? `Queued · ${sourceLabel}` : sourceLabel;
  qs('job_meta_1').textContent = `Channel ${job.channel_code || '-'} | ${sourceLabel}`;
  qs('job_message').textContent = friendlyJobMessage(job);
  setActionState(job);
  renderPipeline(job.stage, job.status);
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
  qs('job_meta_2').textContent = `${doneCount}/${totalCount} clips done | ${stageLabelPlain(job.stage)}${parallelNote}`;

  if(job.stage && job.stage !== lastStage){
    if(lastStage) addEvent(`Finished step: ${stageLabelPlain(lastStage)}`, 'render');
    addEvent(`Stage: ${stageLabelPlain(job.stage)} (${targetPercent}%)`, 'render');
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
  if(status === 'running' && bucket !== lastProgressBucket){
    addEvent(`Running: ${stageLabelPlain(job.stage)} (${targetPercent}%)`, 'render');
    lastProgressBucket = bucket;
  }

  if(isTerminal){
    _stopJobWs();
    if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
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
      setRenderFlowState('complete', `${doneCount} clips ready`);
      if (typeof populateRenderOutputPanel === 'function') populateRenderOutputPanel(job, parts);
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

function startPolling(){
  // Try WebSocket first; fall back to HTTP polling on error
  _stopJobWs();
  if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }

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
    if(!pollTimer){
      loadJobProgress();
      pollTimer = setInterval(loadJobProgress, pollIntervalMs);
    }
  };

  ws.onclose = () => {
    jobWs = null;
    if (!currentJobId) return;
    if (isTerminalRenderStatus(lastStatus)) return;
    if (pollTimer) return;
    loadJobProgress();
    pollTimer = setInterval(loadJobProgress, pollIntervalMs);
  };
}

async function loadJobs(){
  if(RENDER_SESSION_ONLY){
    qs('jobs_out').innerHTML = '<div class="emptyState">Session mode: old jobs are hidden.</div>';
    return;
  }
  const res = await fetch('/api/jobs');
  const data = await res.json();
  const items = (data.items || []).slice(0, 12);
  if(!items.length){ qs('jobs_out').innerHTML = '<div class="emptyState">No jobs yet.</div>'; return; }
  qs('jobs_out').innerHTML = items.map(j => `
    <div class="partRow">
      <div class="partLeft"><div class="rankBadge">J</div><div><div class="partName">${esc(j.job_id)}</div><div class="partMeta">${esc(j.updated_at || '')}</div></div></div>
      <div><div class="miniProgress"><div class="miniProgressValue" style="width:${Number(j.progress_percent || 0)}%"></div></div><div class="partMeta">${Number(j.progress_percent || 0)}%</div></div>
      <div class="partRight"><div class="statusBadge ${esc((j.status || '').toLowerCase())}">${esc(j.status || '')}</div><div class="scoreBox">${esc(j.stage || '')}</div></div>
    </div>
  `).join('');
}

function collectUploadPayload(){
  const uploadMode = (qs('upload_mode')?.value || 'scheduled').trim().toLowerCase();
  const actionMode = (qs('upload_action_mode')?.value || 'upload').trim().toLowerCase();
  const uiLevel = (qs('upload_ui_level')?.value || 'simple').trim().toLowerCase();
  let configMode = (qs('upload_config_mode')?.value || 'ui').trim().toLowerCase();
  if(actionMode === 'login' || uiLevel === 'simple') configMode = 'ui';
  const useSchedule = uploadMode === 'scheduled';
  const scheduleSlots = parseUploadScheduleSlots();
  const browserPref = (qs('upload_browser_preference')?.value || 'chromeportable').trim().toLowerCase();
  const browserExecRaw = (qs('upload_browser_executable')?.value || '').trim();
  const uploadVideoInputDir = (qs('upload_video_input_dir')?.value || '').trim();
  _syncSelectedUploadVideosFromUI();
  const rawCred = (qs('upload_credential_line')?.value || '').trim();
  const parsedCred = _parseCredentialLineRaw(rawCred);
  const fallbackTiktokUser = parsedCred?.tiktokUser || '';
  const fallbackTiktokPass = parsedCred?.tiktokPass || '';
  const fallbackMailUser = parsedCred?.mailUser || '';
  const fallbackMailPass = parsedCred?.mailPass || '';
  const typedAccountKey = (qs('upload_account_key')?.value || '').trim();
  const effectiveAccountKey = _safeAccountKeyUi(
    typedAccountKey && typedAccountKey.toLowerCase() !== 'default'
      ? typedAccountKey
      : (qs('upload_tiktok_username')?.value || fallbackTiktokUser || typedAccountKey || 'default')
  );
  const channelCode = String(qs('upload_channel')?.value || '').trim();
  const resolvedUserDataDir = _resolveUploadUserDataDir(channelCode, effectiveAccountKey, browserPref);
  const resolvedBrowserExec = browserExecRaw || _resolveUploadBrowserExecutable(channelCode, browserPref);
  return {
    channel_code: channelCode,
    root_path: String(uploadChannelsRootPath || '').trim(),
    config_mode: configMode,
    upload_mode: uploadMode,
    account_key: effectiveAccountKey,
    dry_run: qs('upload_dry_run').checked,
    max_items: Number(qs('upload_max_items').value || 0),
    include_hashtags: qs('upload_include_hashtags').checked,
    caption_prefix: qs('upload_caption_prefix').value || '',
    caption_mode: qs('upload_caption_mode').value || 'template',
    ollama_model: qs('upload_ollama_model').value || 'llama3.2:3b',
    use_schedule: useSchedule,
    retry_count: 1,
    headless: qs('upload_headless').checked,
    network_mode: qs('upload_network_mode').value || 'direct',
    proxy_server: qs('upload_proxy_server').value || '',
    proxy_username: qs('upload_proxy_username').value || '',
    proxy_password: qs('upload_proxy_password').value || '',
    proxy_bypass: '',
    use_gpm: false,
    gpm_profile_id: '',
    gpm_browser_ws: '',
    browser_preference: browserPref,
    browser_executable: resolvedBrowserExec,
    user_data_dir: resolvedUserDataDir,
    login_username: (qs('upload_login_username')?.value || '').trim(),
    login_password: (qs('upload_login_password')?.value || '').trim(),
    tiktok_username: (qs('upload_tiktok_username')?.value || fallbackTiktokUser || '').trim(),
    tiktok_password: (qs('upload_tiktok_password')?.value || fallbackTiktokPass || '').trim(),
    mail_username: (qs('upload_mail_username')?.value || fallbackMailUser || '').trim(),
    mail_password: (qs('upload_mail_password')?.value || fallbackMailPass || '').trim(),
    video_input_dir: uploadVideoInputDir,
    schedule_slot_1: scheduleSlots[0] || '07:00',
    schedule_slot_2: scheduleSlots[1] || scheduleSlots[0] || '17:00',
    schedule_slots: scheduleSlots,
    schedule_use_local_tz: true,
    selected_files: useSchedule ? [] : selectedUploadVideos
  };
}

function uploadStageLabel(stage){
  const s = String(stage || '').toLowerCase();
  const map = {
    idle: 'Upload idle',
    channel: 'Channel selected',
    profile: 'Preparing account profile',
    login_check: 'Checking login session',
    login: 'Running login flow',
    queue: 'Queueing upload run',
    queued: 'Upload queued',
    starting: 'Starting upload run',
    uploading: 'Uploading videos',
    done: 'Upload completed',
    failed: 'Upload failed',
  };
  return map[s] || 'Upload processing';
}

function uploadPipelineState(stage, status){
  const s = String(stage || '').toLowerCase();
  const st = String(status || '').toLowerCase();
  const order = ['channel', 'profile', 'login_check', 'login', 'queue', 'uploading', 'done'];
  let idx = order.indexOf(s);
  if (idx < 0){
    if (s === 'queued' || s === 'starting') idx = order.indexOf('queue');
    else if (s === 'failed') idx = order.indexOf('uploading');
  }
  return uploadPipeline.map((node, i) => {
    if (idx < 0) return { ...node, state: 'pending' };
    if (st === 'failed'){
      if (i < idx) return { ...node, state: 'done' };
      if (i === idx) return { ...node, state: 'failed' };
      return { ...node, state: 'pending' };
    }
    if (i < idx) return { ...node, state: 'done' };
    if (i === idx) return { ...node, state: st === 'completed' || s === 'done' ? 'done' : 'running' };
    return { ...node, state: 'pending' };
  });
}

function renderUploadPipeline(stage, status){
  const box = qs('upload_action_steps');
  if(!box) return;
  const nodes = uploadPipelineState(stage, status);
  box.innerHTML = nodes.map((n) => `
    <div class="uploadStepNode ${n.state}">
      <div class="uTitle">${n.label}</div>
      <div class="uState">${n.state}</div>
    </div>
  `).join('');
}

function setUploadAction(stage, status, message, meta = '', progress = null){
  uploadActionStage = String(stage || uploadActionStage || 'idle').toLowerCase();
  const st = String(status || 'running').toLowerCase();
  if(qs('upload_action_title')) qs('upload_action_title').textContent = uploadStageLabel(uploadActionStage);
  if(qs('upload_action_state')) qs('upload_action_state').textContent = st;
  if(qs('upload_action_message')) qs('upload_action_message').textContent = message || uploadStageLabel(uploadActionStage);
  if(qs('upload_action_meta')) qs('upload_action_meta').textContent = meta || `Updated ${new Date().toLocaleTimeString()}`;
  if(progress !== null && qs('upload_progress_bar')){
    const p = Math.max(0, Math.min(100, Number(progress) || 0));
    qs('upload_progress_bar').style.width = `${p}%`;
  }
  renderUploadPipeline(uploadActionStage, st);
}

function renderUploadRun(state){
  if(!state){
    setUploadAction('idle', 'idle', 'No active upload run.', 'Run ID -', 0);
    qs('upload_items_box').innerHTML = '<div class="emptyState">No upload items yet.</div>';
    return;
  }
  const progress = Number(state.progress_percent || 0);
  setUploadAction(
    state.stage || 'uploading',
    state.status || 'running',
    state.message || '-',
    `Run ${state.run_id || '-'} | ${state.current_index || 0}/${state.total || 0}`,
    progress
  );
  const items = state.items || [];
  if(!items.length){
    qs('upload_items_box').innerHTML = '<div class="emptyState">No upload items yet.</div>';
  } else {
    qs('upload_items_box').innerHTML = items.slice(-20).reverse().map((it) => `
      <div class="partRow">
        <div class="partLeft"><div class="rankBadge">U</div><div><div class="partName">${esc(it.file_name || '-')}</div><div class="partMeta">${esc(it.message || '')}</div></div></div>
        <div class="partRight"><div class="statusBadge ${esc((it.status || '').toLowerCase())}">${esc(it.status || '-')}</div></div>
      </div>
    `).join('');
  }
}

async function ensureUploadAccount(){
  const restore = _setBtnLoading('ensure_upload_btn', 'Preparing…');
  const payload = collectUploadPayload();
  setUploadAction('profile', 'running', `Ensuring profile for ${payload.account_key}...`);
  const res = await fetch('/api/upload/accounts/ensure', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await res.json();
  restore();
  if(!res.ok){
    setUploadAction('profile', 'failed', `Ensure account failed: ${_formatApiError(data.detail)}`);
    addEvent(`Ensure account failed: ${_formatApiError(data.detail)}`);
    showToast(`Profile failed: ${_formatApiError(data.detail)}`, 'error');
    return;
  }
  uploadLoginValid = false;
  setUploadAction('profile', 'completed', `Profile ready for ${data.account_key}`, data.user_data_dir || '-');
  addEvent(`Upload account ready: ${data.account_key}`);
  showToast(`Profile ready: ${data.account_key}`, 'success');
}

async function checkUploadLoginStatus(showLog = true){
  const restore = _setBtnLoading('check_upload_btn', 'Checking…');
  const payload = collectUploadPayload();
  setUploadAction('login_check', 'running', `Checking login status for ${payload.account_key}...`);
  const res = await fetch('/api/upload/login/check', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await res.json();
  restore();
  if(!res.ok){
    uploadLoginValid = false;
    setUploadAction('login_check', 'failed', `Login check failed: ${_formatApiError(data.detail)}`);
    if(showLog) addEvent(`Login check failed: ${_formatApiError(data.detail)}`);
    return false;
  }
  uploadLoginValid = !!data.logged_in;
  if(uploadLoginValid){
    setUploadAction('login_check', 'completed', `Login session is valid for ${payload.account_key}.`);
  } else {
    setUploadAction('login_check', 'failed', `No active login session for ${payload.account_key}.`);
  }
  if(showLog){
    if(uploadLoginValid){
      addEvent(`Login OK for ${payload.account_key}`);
      showToast('Login session is valid', 'success');
    } else {
      addEvent(`Login required for ${payload.account_key}. Please click TikTok Login.`);
      showToast('Not logged in — run Login Flow first', 'error');
    }
  }
  return uploadLoginValid;
}

async function startLogin(){
  const restore = _setBtnLoading('start_upload_login_btn', 'Opening…');
  const payload = collectUploadPayload();
  setUploadAction('login', 'running', `Opening login flow for ${payload.account_key} (mail first, then TikTok)...`);
  const res = await fetch('/api/upload/login/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await res.json();
  restore();
  uploadLoginValid = false;
  if(!res.ok){
    setUploadAction('login', 'failed', `Login start failed: ${_formatApiError(data.detail)}`);
    addEvent(`Upload login failed: ${_formatApiError(data.detail)}`);
    showToast(`Login failed: ${_formatApiError(data.detail)}`, 'error');
    return;
  }
  setUploadAction('login', 'running', data.message || 'Login browser opened. Complete login then close tab.', `account=${payload.account_key}`);
  addEvent(`Upload login: ${data.message || 'started'} (account=${payload.account_key})`);
  showToast('Login browser opened — complete login in the browser window', 'info');
  if(data && typeof data === 'object'){
    addEvent(`Login runtime: browser=${data.browser_type || '-'} exe=${data.browser_executable || 'auto'} profile=${data.user_data_dir || '-'}`);
    addEvent(`Mail credential present: ${data.mail_credential_present ? 'yes' : 'no'}`);
    if(data.login_confirmed){
      uploadLoginValid = true;
      setUploadAction('done', 'completed', 'Login confirmed. Browser tabs were closed. Ready to upload.', `account=${payload.account_key}`);
      if(qs('upload_action_mode')){
        qs('upload_action_mode').value = 'upload';
      }
      syncUploadJsonModeUI();
      refreshUploadValidationState();
      addEvent('Login confirmed: switched UI to Upload mode.');
      showToast('Login confirmed — switched to Upload mode', 'success');
    }
  }
}

function _stopUploadWs(){
  if(uploadWs){ try{ uploadWs.close(); }catch(_){} uploadWs = null; }
}

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
  activeJobStartedAt = Date.now();
  lastStage = ''; lastMessage = ''; lastStatus = ''; lastProgressBucket = -1;
  _jobTargetPct = 0; _jobDisplayPct = 0;
  for(const k of Object.keys(_partTarget)) delete _partTarget[k];
  for(const k of Object.keys(_partDisplay)) delete _partDisplay[k];
  setRenderActionBusy(true);
  setHeaderJob('Render running');
  addEvent(isBatch ? `Queued render batch (${data.count || '?'} links)` : 'Queued render job', 'render');
  startPolling();
  return { ok: true, error: null };
}

