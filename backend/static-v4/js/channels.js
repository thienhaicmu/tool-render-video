function fillSelectOptions(el, items, preferred){
  if(!el) return;
  const old = preferred || el.value;
  const needsPlaceholder = ['upload_channel', 'channel_code'].includes(el.id);
  const prefix = needsPlaceholder ? '<option value="">Please select channel</option>' : '';
  el.innerHTML = prefix + items.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  if(old && items.includes(old)) el.value = old;
  else if(needsPlaceholder) el.value = '';
}

function renderChannelManager(items){
  const box = qs('channel_list_box');
  if(!box) return;
  if(!items || !items.length){
    box.innerHTML = '<div class="emptyState">No channels found.</div>';
    return;
  }
  box.innerHTML = items.map((c, i) => `
    <div class="partRow">
      <div class="partLeft">
        <div class="rankBadge">C${i + 1}</div>
        <div>
          <div class="partName">${esc(c)}</div>
          <div class="partMeta">Folder: channels/${esc(c)}</div>
        </div>
      </div>
      <div><div class="partMeta">Ready</div></div>
      <div class="partRight"><div class="statusBadge done">active</div></div>
    </div>
  `).join('');
}

function getChannelPrefixFilter(){
  return REQUIRED_UPLOAD_CHANNEL_PREFIX;
}

async function loadRenderChannels(opts = {}){
  const silentIfNoRoot = !!opts.silentIfNoRoot;
  try{
    if(!renderChannelsRootPath){
      const renderChannel = qs('channel_code');
      if(renderChannel){
        renderChannel.innerHTML = '<option value="">Select channel</option>';
        renderChannel.value = '';
      }
      if(!silentIfNoRoot) addEvent('Please choose Render Channels Root Folder first.', 'render');
      return;
    }
    const endpoint = `/api/channels/scan?root_path=${encodeURIComponent(renderChannelsRootPath)}&strict=1&prefix=${encodeURIComponent(REQUIRED_UPLOAD_CHANNEL_PREFIX)}`;
    const res = await fetch(endpoint);
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const renderChannel = qs('channel_code');
    const oldRender = renderChannel?.value || '';
    if(renderChannel){
      renderChannel.innerHTML = ['<option value="">Select channel</option>', ...items.map(c => `<option value="${esc(c)}">${esc(c)}</option>`)].join('');
      if(oldRender && items.includes(oldRender)) renderChannel.value = oldRender;
      else renderChannel.value = '';
    }
    if(!items.length && !silentIfNoRoot){
      addEvent(`No valid render channels found in selected root folder (required prefix: ${REQUIRED_UPLOAD_CHANNEL_PREFIX}).`, 'render');
    }
    if(items.length && !silentIfNoRoot){
      addEvent(`Render channels loaded from ${renderChannelsRootPath}: ${items.join(', ')}`, 'render');
    }
    await syncRenderOutputByChannel();
  }catch(e){
    addEvent(`Load render channels failed: ${e.message || e}`, 'render');
  }
}

async function loadChannels(opts = {}){
  const silentIfNoRoot = !!opts.silentIfNoRoot;
  try{
    if(!uploadChannelsRootPath){
      fillSelectOptions(qs('upload_channel'), [], '');
      renderChannelManager([]);
      if(!silentIfNoRoot) addEvent('Please choose Channels Root Folder first to load valid channels.');
      return;
    }
    const prefix = getChannelPrefixFilter();
    const endpoint = `/api/channels/scan?root_path=${encodeURIComponent(uploadChannelsRootPath)}&strict=1${prefix ? `&prefix=${encodeURIComponent(prefix)}` : ''}`;
    const res = await fetch(endpoint);
    const data = await res.json();
    let items = Array.isArray(data.items) ? data.items : [];
    if(!items.length){
      addEvent(`No valid channels found in selected root folder (required prefix: ${prefix}).`);
      fillSelectOptions(qs('upload_channel'), [], '');
      renderChannelManager(items);
      return;
    }
    fillSelectOptions(qs('upload_channel'), items, qs('upload_channel')?.value || '');
    const selectedUploadChannel = String(qs('upload_channel')?.value || '').trim();
    if(selectedUploadChannel){
      await syncUploadSourceDirByChannel();
      await loadUploadChannelConfig(false);
      await loadUploadVideos();
    }else{
      if(qs('upload_video_input_dir')) qs('upload_video_input_dir').value = '';
      const box = qs('upload_video_select_box');
      if(box) box.innerHTML = '<div class="emptyState">Select channel to load videos.</div>';
    }
    renderChannelManager(items);
    addEvent(`Valid channels loaded${uploadChannelsRootPath ? ` from ${uploadChannelsRootPath}` : ''}: ${items.join(', ')}`);
  }catch(e){
    addEvent(`Load channels failed: ${e.message || e}`);
  }
}

async function initChannelsRoot(){
  try{
    const res = await fetch('/api/channels/root');
    const data = await res.json();
    defaultChannelsRootPath = String(data.channels_root || '').trim();
    // Pre-fill both root inputs with the server default so user can start immediately
    renderChannelsRootPath = defaultChannelsRootPath;
    uploadChannelsRootPath = defaultChannelsRootPath;
    createChannelsRootPath = defaultChannelsRootPath;
    if(qs('render_channels_root')) qs('render_channels_root').value = defaultChannelsRootPath;
    if(qs('upload_channels_root')) qs('upload_channels_root').value = defaultChannelsRootPath;
    if(qs('new_channel_channels_root')) qs('new_channel_channels_root').value = defaultChannelsRootPath;
    syncNewChannelPathUI();
    if(defaultChannelsRootPath){
      await loadRenderChannels({ silentIfNoRoot: true });
      await loadChannels({ silentIfNoRoot: true });
    }
  }catch(_){
    // keep empty
  }
}

function _deriveRootPathFromPickedFiles(fileInput){
  const files = fileInput?.files ? Array.from(fileInput.files) : [];
  if(!files.length) return '';
  const first = files[0];
  const fullPath = String(first.path || '').replace(/\//g, '\\');
  const relPath = String(first.webkitRelativePath || '').replace(/\//g, '\\');
  if(!fullPath || !relPath) return '';
  const relParts = relPath.split('\\').filter(Boolean);
  const rootName = relParts[0] || '';
  if(!rootName) return '';
  const suffix = `\\${relPath}`;
  if(fullPath.toLowerCase().endsWith(suffix.toLowerCase())){
    return fullPath.slice(0, fullPath.length - suffix.length) + `\\${rootName}`;
  }
  const marker = `\\${rootName}\\`;
  const idx = fullPath.toLowerCase().indexOf(marker.toLowerCase());
  if(idx >= 0) return fullPath.slice(0, idx + marker.length - 1);
  return '';
}

async function pickChannelsRoot(source){
  let picked = '';
  if(window.electronAPI && typeof window.electronAPI.pickDirectory === 'function'){
    // Electron desktop app: native folder picker
    try{
      picked = String(await window.electronAPI.pickDirectory()).trim();
    }catch(_){
      picked = '';
    }
  } else {
    // Browser fallback: prompt to type/paste path
    const currentVal = source === 'channels'
      ? (qs('new_channel_channels_root')?.value || '').trim()
      : (qs('upload_channels_root')?.value || '').trim();
    picked = (prompt('Enter full path to Channels Root Folder:', currentVal || defaultChannelsRootPath || '') || '').trim();
  }
  if(!picked){
    addEvent('Folder selection canceled.');
    return;
  }
  if(source === 'channels'){
    createChannelsRootPath = picked;
    if(qs('new_channel_channels_root')) qs('new_channel_channels_root').value = picked;
    syncNewChannelPathUI();
    addEvent(`Create Channel root selected: ${picked}`);
    return;
  }
  if(source === 'render'){
    renderChannelsRootPath = picked;
    if(qs('render_channels_root')) qs('render_channels_root').value = picked;
    addEvent(`Render root selected: ${picked}`, 'render');
    await loadRenderChannels();
    return;
  }
  uploadChannelsRootPath = picked;
  if(qs('upload_channels_root')) qs('upload_channels_root').value = picked;
  addEvent(`Login/Upload root selected: ${picked}`);
  await loadChannels();
}

async function createChannel(){
  const logCreate = (msg) => {
    const line = `[CreateChannel] ${msg}`;
    try{ console.log(line); }catch(_){}
    addEvent(line, 'channels');
  };
  logCreate('action started');
  const input = qs('new_channel_code');
  const channelCode = (input?.value || '').trim();
  if(!channelCode){
    logCreate('missing New Channel Code');
    try{ window.alert('Please enter New Channel Code first.'); }catch(_){}
    return;
  }
  const channelsRoot = (qs('new_channel_channels_root')?.value || createChannelsRootPath || '').trim();
  if(!channelsRoot){
    logCreate('missing Channels Root Folder');
    try{ window.alert('Please choose Channels Root Folder first.'); }catch(_){}
    return;
  }
  const rawSlots = (qs('new_channel_schedule_slots')?.value || '').trim();
  const parsedSlots = rawSlots
    ? rawSlots.split(',').map(x => x.trim()).filter(Boolean).filter(x => /^\d{1,2}:\d{2}$/.test(x))
      .map((x) => {
        const [h, m] = x.split(':').map(Number);
        return `${String(Math.max(0, Math.min(23, h))).padStart(2,'0')}:${String(Math.max(0, Math.min(59, m))).padStart(2,'0')}`;
      })
    : [];
  const payload = {
    channel_code: channelCode,
    channel_path: `${channelsRoot}\\${channelCode}`,
    account_key: (qs('new_channel_account_key')?.value || 'default').trim() || 'default',
    video_output_subdir: (qs('new_channel_video_output_subdir')?.value || 'video_out').trim() || 'video_out',
    default_hashtags: (qs('new_channel_default_hashtags')?.value || '').trim(),
    browser_preference: (qs('new_channel_browser_preference')?.value || 'chromeportable').trim().toLowerCase(),
    network_mode: (qs('new_channel_network_mode')?.value || 'direct').trim().toLowerCase(),
    proxy_server: (qs('new_channel_proxy_server')?.value || '').trim(),
    proxy_username: (qs('new_channel_proxy_username')?.value || '').trim(),
    proxy_password: (qs('new_channel_proxy_password')?.value || '').trim(),
    schedule_slots: parsedSlots.length ? parsedSlots : ['07:00','17:00'],
    credential_line: (qs('new_channel_credential_line')?.value || '').trim(),
  };
  logCreate(`request payload prepared | channel=${channelCode} | target=${channelsRoot}\\${channelCode}`);
  if(payload.network_mode === 'direct'){
    payload.proxy_server = '';
    payload.proxy_username = '';
    payload.proxy_password = '';
  } else if(!payload.proxy_server){
    logCreate('validation failed: Proxy Server required in proxy mode');
    try{ window.alert('Proxy Server is required when Network Mode = Proxy.'); }catch(_){}
    return;
  }
  let res;
  let data = {};
  try{
    logCreate('POST /api/channels');
    res = await fetch('/api/channels', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const raw = await res.text();
    try{
      data = raw ? JSON.parse(raw) : {};
    }catch(_){
      data = { raw };
    }
    logCreate(`response status=${res.status}`);
    if(!res.ok){
      const preview = String(data.detail || data.raw || '').slice(0, 300);
      if(preview) logCreate(`response body: ${preview}`);
    }
  }catch(e){
    logCreate(`fetch error: ${e.message || e}`);
    try{ window.alert(`Create channel failed: ${e.message || e}`); }catch(_){}
    return;
  }
  if(!res.ok){
    const msg = data.detail || 'unknown error';
    logCreate(`failed: ${msg}`);
    try{ window.alert(`Create channel failed: ${msg}`); }catch(_){}
    return;
  }
  if(input) input.value = '';
  logCreate(`success | path=${data.path || ''}`);
  if(data.video_output_dir) logCreate(`video_output_dir=${data.video_output_dir}`);
  if(data.upload_settings) logCreate(`upload_settings=${data.upload_settings}`);
  if(data.profile_config) logCreate(`profile_config=${data.profile_config}`);
  if(Array.isArray(data.portable_installers_seeded) && data.portable_installers_seeded.length){
    logCreate(`portable installers seeded: ${data.portable_installers_seeded.join(', ')}`);
  } else {
    logCreate('portable installers seeded: none (no source installers found or already present)');
  }
  // Sync Upload root to same folder so the new channel appears in the Upload dropdown
  if(channelsRoot){
    renderChannelsRootPath = channelsRoot;
    if(qs('render_channels_root')) qs('render_channels_root').value = channelsRoot;
    await loadRenderChannels({ silentIfNoRoot: true });
    uploadChannelsRootPath = channelsRoot;
    if(qs('upload_channels_root')) qs('upload_channels_root').value = channelsRoot;
    await loadChannels({ silentIfNoRoot: true });
  }
  try{ window.alert(`Channel created successfully:\n${data.path || `${channelsRoot}\\${channelCode}`}`); }catch(_){}
}

function syncNewChannelNetworkModeUI(){
  const mode = (qs('new_channel_network_mode')?.value || 'direct').toLowerCase();
  const showProxy = mode === 'proxy';
  if(qs('new_channel_proxy_server_wrap')) qs('new_channel_proxy_server_wrap').classList.toggle('hiddenView', !showProxy);
  if(qs('new_channel_proxy_username_wrap')) qs('new_channel_proxy_username_wrap').classList.toggle('hiddenView', !showProxy);
  if(qs('new_channel_proxy_password_wrap')) qs('new_channel_proxy_password_wrap').classList.toggle('hiddenView', !showProxy);
}

function syncNewChannelPathUI(){
  const root = (qs('new_channel_channels_root')?.value || '').trim();
  const code = (qs('new_channel_code')?.value || '').trim();
  if(qs('new_channel_path')){
    qs('new_channel_path').textContent = (root && code) ? `${root}\\${code}` : 'Choose folder and enter channel code';
  }
}

async function cleanupLogs(){
  const keepLast = Number(qs('cleanup_keep_last')?.value || 30);
  const olderDays = Number(qs('cleanup_older_days')?.value || 10);
  const res = await fetch(`/api/jobs/cleanup/logs?keep_last=${keepLast}&older_than_days=${olderDays}`, { method: 'POST' });
  const data = await res.json();
  if(!res.ok){
    addEvent(`Log cleanup failed: ${data.detail || 'unknown error'}`);
    return;
  }
  addEvent(`Log cleanup done: removed ${data.removed}/${data.scanned} files across ${data.channels} channel(s).`);
}

function bindUploadRealtimeValidation(){
  const root = qs('card_upload');
  if(!root) return;
  root.querySelectorAll('input, select, textarea').forEach((el) => {
    const evt = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(evt, () => {
      if(el.id === 'upload_channel') return;
      refreshUploadValidationState();
    });
  });
}

