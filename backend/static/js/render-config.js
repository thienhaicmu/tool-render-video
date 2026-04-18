function browseLocalVideo(){
  const picker = qs('local_video_file_picker');
  if(picker) picker.click();
}

let _pendingLocalFile = null;

async function onLocalVideoPicked(ev){
  const file = ev?.target?.files?.[0];
  if(!file){
    selectedLocalVideoPath = '';
    _pendingLocalFile = null;
    if(qs('source_video_path')) qs('source_video_path').value = '';
    if(qs('source_video_name')) qs('source_video_name').textContent = 'No local video selected.';
    return;
  }
  // Electron exposes file.path; browser does not
  const realPath = String(file.path || '').trim();
  if(realPath){
    selectedLocalVideoPath = realPath;
    _pendingLocalFile = null;
    if(qs('source_video_path')) qs('source_video_path').value = realPath;
  } else {
    _pendingLocalFile = file;
    selectedLocalVideoPath = '';
    if(qs('source_video_path')) qs('source_video_path').value = file.name + ' (will upload on render)';
  }
  if(qs('source_video_name')) qs('source_video_name').textContent = file.name || 'Selected';
  addEvent(`Local source selected: ${file.name || 'video'} — nhấn "Tiếp theo" để chỉnh sửa & render.`, 'render');
}

// ── BGM file picker ──────────────────────────────────────────────────────
let selectedBgmPath = '';
let _pendingBgmFile = null;

function syncBgmFieldsVisibility(){
  const bgmFields = qs('bgm_fields');
  const enabled = qs('reup_bgm_enable')?.checked;
  if(bgmFields) bgmFields.classList.toggle('hiddenView', !enabled);
}

function browseBgmFile(){
  const picker = qs('bgm_file_picker');
  if(picker) picker.click();
}

function onBgmFilePicked(ev){
  const file = ev?.target?.files?.[0];
  if(!file){
    selectedBgmPath = '';
    _pendingBgmFile = null;
    if(qs('reup_bgm_path')) qs('reup_bgm_path').value = '';
    return;
  }
  const realPath = String(file.path || '').trim();
  if(realPath){
    selectedBgmPath = realPath;
    _pendingBgmFile = null;
    if(qs('reup_bgm_path')) qs('reup_bgm_path').value = realPath;
  } else {
    _pendingBgmFile = file;
    selectedBgmPath = '';
    if(qs('reup_bgm_path')) qs('reup_bgm_path').value = file.name + ' (will upload on render)';
  }
  addEvent(`BGM selected: ${file.name}`, 'render');
}

async function uploadBgmFileIfNeeded(){
  if(!_pendingBgmFile) return selectedBgmPath;
  const channel = (qs('channel_code')?.value || qs('upload_channel')?.value || 'T1').trim();
  const formData = new FormData();
  formData.append('file', _pendingBgmFile);
  formData.append('channel_code', channel);
  addEvent('Uploading BGM to server...', 'render');
  try {
    const resp = await fetch('/api/render/upload-local', { method: 'POST', body: formData });
    if(!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
    const data = await resp.json();
    selectedBgmPath = data.path;
    _pendingBgmFile = null;
    if(qs('reup_bgm_path')) qs('reup_bgm_path').value = data.path;
    addEvent(`BGM uploaded: ${data.filename}`, 'render');
    return data.path;
  } catch(e){
    addEvent(`BGM upload error: ${e.message}`, 'render');
    return '';
  }
}
// ── End BGM ─────────────────────────────────────────────────────────────

async function uploadLocalFileIfNeeded(){
  if(!_pendingLocalFile) return selectedLocalVideoPath;
  const channel = (qs('channel_code')?.value || qs('upload_channel')?.value || 'T1').trim();
  const formData = new FormData();
  formData.append('file', _pendingLocalFile);
  formData.append('channel_code', channel);
  addEvent('Uploading local video to server...', 'render');
  if(qs('source_video_name')) qs('source_video_name').textContent = 'Uploading...';
  try {
    const resp = await fetch('/api/render/upload-local', { method: 'POST', body: formData });
    if(!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
    const data = await resp.json();
    selectedLocalVideoPath = data.path;
    _pendingLocalFile = null;
    if(qs('source_video_path')) qs('source_video_path').value = data.path;
    if(qs('source_video_name')) qs('source_video_name').textContent = data.filename + ' (uploaded)';
    addEvent(`Video uploaded: ${data.filename} (${(data.size / 1048576).toFixed(1)} MB)`, 'render');
    return data.path;
  } catch(e){
    addEvent(`Upload error: ${e.message}`, 'render');
    if(qs('source_video_name')) qs('source_video_name').textContent = 'Upload failed!';
    return '';
  }
}

function setYoutubeHealthState(state, message){
  const input = qs('youtube_url');
  const hint = qs('youtube_health_hint');
  if(input){
    input.classList.remove('healthOk', 'healthWarn');
    if(state === 'ok') input.classList.add('healthOk');
    if(state === 'warn') input.classList.add('healthWarn');
  }
  if(hint){
    hint.classList.remove('ok', 'warn');
    if(state === 'ok') hint.classList.add('ok');
    if(state === 'warn') hint.classList.add('warn');
    hint.textContent = message || 'Health status: not checked.';
  }
}

function syncYoutubeUrlsHidden(){
  const hidden = qs('youtube_urls');
  if(hidden) hidden.value = batchYoutubeUrls.join('\n');
}

function renderYoutubeUrlBatch(){
  const box = qs('youtube_urls_box');
  if(!box) return;
  if(!batchYoutubeUrls.length){
    box.innerHTML = '<div class="ytQueueEmpty">No links added yet. Enter URL above then click Add.</div>';
    syncYoutubeUrlsHidden();
    return;
  }
  box.innerHTML = batchYoutubeUrls.map((url, idx) => `
    <div class="ytQueueItem">
      <div class="ytQueueIdx">${idx + 1}</div>
      <div class="ytQueueUrl" title="${esc(url)}">${esc(url)}</div>
      <button type="button" class="secondaryButton" onclick="removeYoutubeUrlAt(${idx})">Remove</button>
    </div>
  `).join('');
  syncYoutubeUrlsHidden();
}

function removeYoutubeUrlAt(index){
  const idx = Number(index);
  if(Number.isNaN(idx) || idx < 0 || idx >= batchYoutubeUrls.length) return;
  const removed = batchYoutubeUrls[idx];
  batchYoutubeUrls.splice(idx, 1);
  renderYoutubeUrlBatch();
  addEvent(`Removed URL from batch: ${removed}`, 'render');
}

function addYoutubeUrlToBatch(){
  const input = qs('youtube_url');
  const value = String(input?.value || '').trim();
  if(!value){
    addEvent('Please enter YouTube URL before adding.', 'render');
    return;
  }
  if(batchYoutubeUrls.includes(value)){
    addEvent('URL already exists in batch list.', 'render');
    return;
  }
  batchYoutubeUrls.push(value);
  renderYoutubeUrlBatch();
  if(input) input.value = '';
  setYoutubeHealthState('idle', 'Health status: not checked.');
  addEvent(`Added URL to batch list (${batchYoutubeUrls.length} total).`, 'render');
}

function collectYoutubeUrls(){
  return [...batchYoutubeUrls];
}

async function checkDownloadHealth(){
  const sourceMode = (qs('source_mode')?.value || 'youtube').trim().toLowerCase();
  if(sourceMode !== 'youtube'){
    addEvent('Download Health is available only for YouTube source mode.', 'render');
    return;
  }
  const typedUrl = (qs('youtube_url')?.value || '').trim();
  if(!typedUrl){
    setYoutubeHealthState('warn', 'Health status: enter URL first.');
    addEvent('Download Health: please enter at least one YouTube URL.', 'render');
    return;
  }
  const targetUrl = typedUrl;
  addEvent(`Checking download health for: ${targetUrl}`, 'render');
  try{
    const res = await fetch('/api/render/download-health', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ youtube_url: targetUrl }),
    });
    const data = await res.json();
    if(!res.ok){
      setYoutubeHealthState('warn', `Health status: warning (${_formatApiError(data.detail)})`);
      addEvent(`Download Health failed: ${_formatApiError(data.detail)}`, 'render');
      return;
    }
    if(data.ok){
      setYoutubeHealthState('ok', `Health status: OK (${Number(data.best_height || 0)}p ${Number(data.best_fps || 0)}fps, ${data.client || 'auto'})`);
      addEvent(`Download Health OK | client=${data.client || '-'} | best=${Number(data.best_height || 0)}p ${Number(data.best_fps || 0)}fps | streams=${Number(data.video_stream_count || 0)}`, 'render');
      (data.warnings || []).slice(-2).forEach((w) => addEvent(`Health warning: ${w}`, 'render'));
      return;
    }
    setYoutubeHealthState('warn', `Health status: warning (${data.reason || 'unknown'})`);
    addEvent(`Download Health NOT OK | reason=${data.reason || 'unknown'} | client=${data.client || '-'} | ${data.message || ''}`, 'render');
    (data.warnings || []).slice(-2).forEach((w) => addEvent(`Health warning: ${w}`, 'render'));
    (data.errors || []).slice(-2).forEach((e) => addEvent(`Health error: ${e}`, 'render'));
  } catch(e){
    setYoutubeHealthState('warn', 'Health status: warning (request error).');
    addEvent(`Download Health request failed: ${e.message || e}`, 'render');
  }
}

async function syncRenderOutputByChannel(){
  const outputMode = (qs('output_mode')?.value || 'channel').toLowerCase();
  if(outputMode !== 'channel'){
    selectedRenderOutputDir = '';
    return;
  }
  const channel = (qs('channel_code')?.value || '').trim();
  if(!channel){
    selectedRenderOutputDir = '';
    if(qs('render_output_dir')) qs('render_output_dir').value = '';
    if(qs('render_output_dir_hint')) qs('render_output_dir_hint').textContent = 'Choose channel to auto-fill output folder.';
    return;
  }
  try{
    // By-channel render output is fixed to channel/upload/video_output
    // so Upload flow can consume rendered files directly.
    let out = '';
    if(String(renderChannelsRootPath || '').trim()){
      out = _joinWinPath(renderChannelsRootPath, channel, 'upload', 'video_output');
    } else if(String(defaultChannelsRootPath || '').trim()){
      out = _joinWinPath(defaultChannelsRootPath, channel, 'upload', 'video_output');
    }
    if(!out){
      const rootParam = renderChannelsRootPath ? `?root_path=${encodeURIComponent(renderChannelsRootPath)}` : '';
      const res = await fetch(`/api/channels/${encodeURIComponent(channel)}${rootParam}`);
      const data = await res.json();
      if(!res.ok) throw new Error(data.detail || 'load channel info failed');
      out = String(data.input_dir || '').trim();
    }
    selectedRenderOutputDir = out;
    if(qs('render_output_dir')) qs('render_output_dir').value = out;
    if(qs('render_output_dir_hint')) qs('render_output_dir_hint').textContent = out ? `Auto output: ${out}` : 'Channel output not found.';
    if(out) addEvent(`Render output auto-set: ${out}`, 'render');
  }catch(e){
    selectedRenderOutputDir = '';
    if(qs('render_output_dir')) qs('render_output_dir').value = '';
    if(qs('render_output_dir_hint')) qs('render_output_dir_hint').textContent = 'Cannot resolve output folder from channel.';
    addEvent(`Resolve channel output failed: ${e.message || e}`, 'render');
  }
}

async function syncUploadSourceDirByChannel(){
  const channel = (qs('upload_channel')?.value || '').trim();
  if(!channel){
    if(qs('upload_video_input_dir')) qs('upload_video_input_dir').value = '';
    setUploadAction('idle', 'idle', 'Choose upload channel to continue.', 'Run ID -', 0);
    syncUploadJsonModeUI();
    return;
  }
  try{
    const rootParam = uploadChannelsRootPath ? `?root_path=${encodeURIComponent(uploadChannelsRootPath)}` : '';
    const res = await fetch(`/api/channels/${encodeURIComponent(channel)}${rootParam}`);
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'load channel info failed');
    const out = String(data.input_dir || '').trim();
    if(qs('upload_video_input_dir')) qs('upload_video_input_dir').value = out;
    setUploadAction('channel', 'running', `Channel ${channel} selected. Source folder is ready.`, out || '-');
  }catch(_){
    // keep silent for upload panel convenience
  }
  syncUploadJsonModeUI();
}
