let uploadAccountManagerItems = [];
let uploadVideoLibraryItems = [];
let uploadQueueManagerItems = [];
let selectedUploadQueueId = '';
let selectedUploadEntity = {type: '', id: ''};
let currentUploadQueueHistoryItems = [];
let currentUploadWorkflowStep = 1;

function enforceRenderUploadIndependence(){
  window.addRenderClipToUploadQueue = function(){
    showToast('Render outputs are not connected to Upload Account Manager', 'info');
    addEvent('Render-to-upload queue is disabled for this build.', 'upload');
  };
  const hideQueueButtons = () => {
    document.querySelectorAll('button').forEach((btn) => {
      if(String(btn.textContent || '').trim().toLowerCase() === '+ add to queue'){
        btn.classList.add('hiddenView');
        btn.disabled = true;
        btn.setAttribute('aria-hidden', 'true');
      }
    });
  };
  hideQueueButtons();
  if(!window._uploadIndependenceObserver){
    window._uploadIndependenceObserver = new MutationObserver(hideQueueButtons);
    window._uploadIndependenceObserver.observe(document.body, {childList: true, subtree: true});
  }
}

function initUploadAccountManager(){
  enforceRenderUploadIndependence();
  loadUploadAccounts();
  loadUploadVideoLibrary();
  loadUploadQueueManager();
  if(typeof window.setView === 'function' && !window._uploadAccountManagerSetViewWrapped){
    const originalSetView = window.setView;
    window.setView = function(view){
      const result = originalSetView.apply(this, arguments);
      if(view === 'upload'){
        loadUploadAccounts();
        loadUploadVideoLibrary();
        loadUploadQueueManager();
      }
      return result;
    };
    window._uploadAccountManagerSetViewWrapped = true;
  }
}

document.addEventListener('DOMContentLoaded', initUploadAccountManager);

function _uamValue(id){
  return String(qs(id)?.value || '').trim();
}

function _uamInt(id){
  const n = Number(qs(id)?.value || 0);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

function _uamBadge(value, group){
  const normalized = String(value || 'unknown').toLowerCase();
  return `<span class="uamBadge ${group || ''}" data-state="${esc(normalized)}">${esc(normalized.replace(/_/g, ' '))}</span>`;
}

function _uamShortPath(path){
  const text = String(path || '').trim();
  if(!text) return '-';
  if(text.length <= 48) return text;
  return `...${text.slice(-45)}`;
}

function _uamConflictText(item){
  const conflict = item?.profile_conflict;
  if(!conflict) return '';
  return conflict.display_name || conflict.account_key || conflict.account_id || 'another active account';
}

function _selectUploadEntity(type, id){
  selectedUploadEntity = {type: String(type || ''), id: String(id || '')};
  if(type === 'queue'){
    selectedUploadQueueId = String(id || '');
    loadSelectedUploadQueueHistory();
  }else{
    renderUploadQueueHistory(currentUploadQueueHistoryItems);
  }
  renderUploadInspector();
}

function _selectedUploadId(type){
  return selectedUploadEntity.type === type ? selectedUploadEntity.id : '';
}

function _prettyJson(value){
  if(value == null) return '';
  if(typeof value === 'string'){
    const text = value.trim();
    if(!text) return '';
    try{
      return JSON.stringify(JSON.parse(text), null, 2);
    }catch(_err){
      return text;
    }
  }
  try{
    return JSON.stringify(value, null, 2);
  }catch(_err){
    return String(value);
  }
}

function _detailSection(label, value, pre){
  const safe = value == null || value === '' ? '-' : value;
  return `
    <div class="uploadDetailSection">
      <div class="uploadDetailLabel">${esc(label)}</div>
      ${pre ? `<pre class="uploadDetailValuePre">${esc(String(safe))}</pre>` : `<div class="uploadDetailValue">${esc(String(safe))}</div>`}
    </div>
  `;
}

function renderUploadInspector(){
  const titleEl = qs('upload_detail_title');
  const hintEl = qs('upload_detail_hint');
  const bodyEl = qs('upload_detail_body');
  if(!titleEl || !hintEl || !bodyEl){
    return;
  }

  const type = selectedUploadEntity.type;
  const id = selectedUploadEntity.id;
  if(!type || !id){
    titleEl.textContent = 'Selection Details';
    hintEl.textContent = 'Select an account, video, or queue item to inspect details.';
    bodyEl.innerHTML = '<div class="uploadInspectorPlaceholder">Select an account, video, or queue item to inspect details.</div>';
    return;
  }

  if(type === 'account'){
    const item = uploadAccountManagerItems.find((x) => x.account_id === id);
    if(!item){
      selectedUploadEntity = {type: '', id: ''};
      renderUploadInspector();
      return;
    }
    const name = item.display_name || item.account_key || item.account_id;
    titleEl.textContent = name;
    hintEl.textContent = `Account · ${item.platform || 'tiktok'} · ${item.account_key || 'default'}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Login State', String(item.login_state || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Profile Lock', String(item.profile_lock_state || 'idle').replace(/_/g, ' '), false)}
        ${_detailSection('Usage Today', `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`, false)}
        ${_detailSection('Cooldown', `${Number(item.cooldown_minutes || 0)} min`, false)}
        ${_detailSection('Proxy ID', item.proxy_id || '-', false)}
      </div>
      ${_detailSection('Profile Path', item.profile_path || '-', false)}
      ${item.profile_conflict ? _detailSection('Profile Conflict', _uamConflictText(item), false) : ''}
      ${_detailSection('Health JSON', _prettyJson(item.health_json || {}), true)}
    `;
    return;
  }

  if(type === 'video'){
    const item = uploadVideoLibraryItems.find((x) => x.video_id === id);
    if(!item){
      selectedUploadEntity = {type: '', id: ''};
      renderUploadInspector();
      return;
    }
    titleEl.textContent = item.file_name || item.video_id;
    hintEl.textContent = `Video · ${item.platform || 'tiktok'} · ${String(item.status || 'ready').replace(/_/g, ' ')}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'ready').replace(/_/g, ' '), false)}
        ${_detailSection('Source Type', String(item.source_type || 'manual_file').replace(/_/g, ' '), false)}
        ${_detailSection('Duration', _uvlFormatDuration(item.duration_sec), false)}
        ${_detailSection('File Size', _uvlFormatSize(item.file_size), false)}
      </div>
      ${_detailSection('Video Path', item.video_path || '-', false)}
      ${_detailSection('Caption', item.caption || '-', false)}
      ${_detailSection('Hashtags', _uvlHashtagText(item.hashtags || []) || '-', false)}
      ${_detailSection('Note', item.note || '-', false)}
      ${_detailSection('Cover Path', item.cover_path || '-', false)}
    `;
    return;
  }

  if(type === 'queue'){
    const item = uploadQueueManagerItems.find((x) => x.queue_id === id);
    if(!item){
      selectedUploadEntity = {type: '', id: ''};
      renderUploadInspector();
      return;
    }
    titleEl.textContent = item.video_file_name || item.queue_id;
    hintEl.textContent = `Queue · ${(item.account_display_name || item.account_key || item.account_id || '-')} · ${String(item.status || 'pending').replace(/_/g, ' ')}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'pending').replace(/_/g, ' '), false)}
        ${_detailSection('Platform', item.platform || 'tiktok', false)}
        ${_detailSection('Priority', String(Number(item.priority || 0)), false)}
        ${_detailSection('Attempts', `${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}`, false)}
        ${_detailSection('Scheduled At', item.scheduled_at || '-', false)}
        ${_detailSection('Account', item.account_display_name || item.account_key || item.account_id || '-', false)}
      </div>
      ${_detailSection('Video Path', item.video_path || '-', false)}
      ${_detailSection('Caption', item.caption || '-', false)}
      ${_detailSection('Hashtags', _uvlHashtagText(item.hashtags || []) || '-', false)}
      ${_detailSection('Last Error', item.last_error || '-', false)}
      ${_detailSection('Adapter Result', _historySummary(item.result_json || item.result || {}) || '-', false)}
    `;
  }
}

function collectUploadAccountForm(){
  return {
    platform: _uamValue('uam_platform') || 'tiktok',
    channel_code: _uamValue('uam_channel_code'),
    account_key: _uamValue('uam_account_key') || 'default',
    display_name: _uamValue('uam_display_name'),
    status: _uamValue('uam_status') || 'active',
    login_state: _uamValue('uam_login_state') || 'unknown',
    daily_limit: _uamInt('uam_daily_limit'),
    cooldown_minutes: _uamInt('uam_cooldown_minutes'),
    today_count: _uamInt('uam_today_count'),
    profile_path: _uamValue('uam_profile_path'),
    proxy_id: _uamValue('uam_proxy_id'),
    health_json: {},
    metadata_json: {},
  };
}

function resetUploadAccountForm(){
  const ids = [
    'uam_account_id', 'uam_channel_code', 'uam_display_name', 'uam_profile_path',
    'uam_proxy_id',
  ];
  ids.forEach((id) => { if(qs(id)) qs(id).value = ''; });
  if(qs('uam_platform')) qs('uam_platform').value = 'tiktok';
  if(qs('uam_account_key')) qs('uam_account_key').value = 'default';
  if(qs('uam_status')) qs('uam_status').value = 'active';
  if(qs('uam_login_state')) qs('uam_login_state').value = 'unknown';
  if(qs('uam_daily_limit')) qs('uam_daily_limit').value = '0';
  if(qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = '0';
  if(qs('uam_today_count')) qs('uam_today_count').value = '0';
  if(qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Create Account';
}

function fillUploadAccountForm(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  if(qs('uam_account_id')) qs('uam_account_id').value = item.account_id || '';
  if(qs('uam_platform')) qs('uam_platform').value = item.platform || 'tiktok';
  if(qs('uam_channel_code')) qs('uam_channel_code').value = item.channel_code || '';
  if(qs('uam_account_key')) qs('uam_account_key').value = item.account_key || 'default';
  if(qs('uam_display_name')) qs('uam_display_name').value = item.display_name || '';
  if(qs('uam_status')) qs('uam_status').value = item.status || 'active';
  if(qs('uam_login_state')) qs('uam_login_state').value = item.login_state || 'unknown';
  if(qs('uam_daily_limit')) qs('uam_daily_limit').value = Number(item.daily_limit || 0);
  if(qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = Number(item.cooldown_minutes || 0);
  if(qs('uam_today_count')) qs('uam_today_count').value = Number(item.today_count || 0);
  if(qs('uam_profile_path')) qs('uam_profile_path').value = item.profile_path || '';
  if(qs('uam_proxy_id')) qs('uam_proxy_id').value = item.proxy_id || '';
  if(qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Save Changes';
}

function renderUploadAccounts(items){
  const tbody = qs('upload_accounts_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="9" class="uamEmpty">No upload accounts yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const name = item.display_name || item.account_key || item.account_id;
    const usage = `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`;
    const profile = _uamShortPath(item.profile_path);
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    const lockState = item.profile_lock_state || 'idle';
    return `
      <tr>
        <td>
          <div class="uamAccountName">${esc(name)}</div>
          <div class="uamSub">${esc(item.platform || 'tiktok')} · ${esc(item.channel_code || '-')} · ${esc(item.account_key || 'default')}</div>
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td>${_uamBadge(item.login_state, 'login')}</td>
        <td>${_uamBadge(lockState, 'lock')}</td>
        <td>${esc(usage)}</td>
        <td>${Number(item.cooldown_minutes || 0)} min</td>
        <td title="${esc(item.profile_path || '')}">${esc(profile)}</td>
        <td>${esc(item.proxy_id || '-')}</td>
        <td>
          <div class="uamActions">
            <button class="ghostButton" type="button" onclick="fillUploadAccountForm('${esc(item.account_id)}')">Edit</button>
            <button class="ghostButton" type="button" onclick="checkUploadAccountLogin('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Check Login</button>
            <button class="ghostButton" type="button" onclick="disableUploadAccount('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadAccounts(){
  const tbody = qs('upload_accounts_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="9" class="uamEmpty">Loading accounts...</td></tr>';
  try{
    const res = await fetch('/api/upload/accounts');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadAccountManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueSelectors();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="9" class="uamEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload account load failed: ${e.message || e}`, 'upload');
  }
}

async function saveUploadAccount(event){
  if(event) event.preventDefault();
  const accountId = _uamValue('uam_account_id');
  const payload = collectUploadAccountForm();
  try{
    const res = await fetch(accountId ? `/api/upload/accounts/${encodeURIComponent(accountId)}` : '/api/upload/accounts', {
      method: accountId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadAccountForm();
    await loadUploadAccounts();
    showToast(accountId ? 'Upload account updated' : 'Upload account created', 'success');
  }catch(e){
    showToast(`Account save failed: ${e.message || e}`, 'error');
  }
}

async function disableUploadAccount(accountId){
  if(!accountId) return;
  try{
    const res = await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}`, {method: 'DELETE'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadAccounts();
    showToast('Upload account disabled', 'success');
  }catch(e){
    showToast(`Disable failed: ${e.message || e}`, 'error');
  }
}

async function checkUploadAccountLogin(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  try{
    const res = await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}/login-check`, {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail || data.message));
    await loadUploadAccounts();
    const loginState = data?.item?.login_state || (data?.result?.logged_in ? 'logged_in' : 'logged_out');
    showToast(loginState === 'logged_in' ? 'Login is valid' : (data.message || 'Login check completed'), loginState === 'logged_in' ? 'success' : 'info');
  }catch(e){
    showToast(`Login check failed: ${e.message || e}`, 'error');
  }
}

function _uvlValue(id){
  return String(qs(id)?.value || '').trim();
}

function _uvlParseHashtags(raw){
  return String(raw || '')
    .split(',')
    .map((x) => x.trim().replace(/^#+/, ''))
    .filter(Boolean);
}

function _uvlHashtagText(tags){
  if(!Array.isArray(tags) || !tags.length) return '';
  return tags.map((tag) => `#${String(tag || '').replace(/^#+/, '')}`).join(', ');
}

function _uvlFormatSize(bytes){
  const n = Number(bytes || 0);
  if(!n) return '-';
  if(n < 1024) return `${n} B`;
  if(n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if(n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function _uvlFormatDuration(sec){
  const n = Number(sec || 0);
  if(!n) return '-';
  const minutes = Math.floor(n / 60);
  const seconds = Math.round(n % 60);
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function collectUploadVideoForm(){
  return {
    video_path: _uvlValue('uvl_video_path'),
    platform: _uvlValue('uvl_platform') || 'tiktok',
    source_type: _uvlValue('uvl_source_type') || 'manual_file',
    status: _uvlValue('uvl_status') || 'ready',
    caption: _uvlValue('uvl_caption'),
    hashtags: _uvlParseHashtags(_uvlValue('uvl_hashtags')),
    cover_path: _uvlValue('uvl_cover_path'),
    note: _uvlValue('uvl_note'),
  };
}

function resetUploadVideoForm(){
  ['uvl_video_id', 'uvl_video_path', 'uvl_caption', 'uvl_hashtags', 'uvl_note', 'uvl_cover_path'].forEach((id) => {
    if(qs(id)) qs(id).value = '';
  });
  if(qs('uvl_platform')) qs('uvl_platform').value = 'tiktok';
  if(qs('uvl_source_type')) qs('uvl_source_type').value = 'manual_file';
  if(qs('uvl_status')) qs('uvl_status').value = 'ready';
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => {
    if(qs(id)) qs(id).disabled = false;
  });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Add Video';
}

function fillUploadVideoForm(videoId){
  const item = uploadVideoLibraryItems.find((x) => x.video_id === videoId);
  if(!item) return;
  if(qs('uvl_video_id')) qs('uvl_video_id').value = item.video_id || '';
  if(qs('uvl_video_path')) qs('uvl_video_path').value = item.video_path || '';
  if(qs('uvl_platform')) qs('uvl_platform').value = item.platform || 'tiktok';
  if(qs('uvl_source_type')) qs('uvl_source_type').value = item.source_type || 'manual_file';
  if(qs('uvl_status')) qs('uvl_status').value = item.status || 'ready';
  if(qs('uvl_caption')) qs('uvl_caption').value = item.caption || '';
  if(qs('uvl_hashtags')) qs('uvl_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uvl_note')) qs('uvl_note').value = item.note || '';
  if(qs('uvl_cover_path')) qs('uvl_cover_path').value = item.cover_path || '';
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => {
    if(qs(id)) qs(id).disabled = true;
  });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Save Video';
}

function renderUploadVideoLibrary(items){
  const tbody = qs('upload_videos_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="8" class="uvlEmpty">No upload videos yet. Add a file to start building your library.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    const caption = String(item.caption || '').trim();
    const note = String(item.note || '').trim();
    return `
      <tr class="${disabled ? 'isDisabled' : ''}">
        <td>
          <div class="uvlFileName">${esc(item.file_name || item.video_path || '-')}</div>
          <div class="uvlSub" title="${esc(item.video_path || '')}">${esc(_uamShortPath(item.video_path || ''))}</div>
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td>${esc(item.platform || 'tiktok')}</td>
        <td>
          <div class="uvlClipText">${esc(caption || '-')}</div>
          ${note ? `<div class="uvlSub">${esc(note)}</div>` : ''}
        </td>
        <td><div class="uvlClipText">${esc(_uvlHashtagText(item.hashtags || []) || '-')}</div></td>
        <td>${esc(_uvlFormatDuration(item.duration_sec))}<div class="uvlSub">${esc(_uvlFormatSize(item.file_size))}</div></td>
        <td>${esc(String(item.source_type || 'manual_file').replace(/_/g, ' '))}</td>
        <td>
          <div class="uvlActions">
            <button class="ghostButton" type="button" onclick="fillUploadVideoForm('${esc(item.video_id)}')">Edit</button>
            <button class="ghostButton" type="button" onclick="disableUploadVideo('${esc(item.video_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
            <button class="ghostButton" type="button" onclick="selectVideoForQueue('${esc(item.video_id)}')" ${disabled || String(item.status || '').toLowerCase() !== 'ready' ? 'disabled' : ''}>Add to Queue</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadVideoLibrary(){
  const tbody = qs('upload_videos_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="8" class="uvlEmpty">Loading videos...</td></tr>';
  const params = new URLSearchParams();
  const status = _uvlValue('uvl_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/videos?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadVideoLibraryItems = Array.isArray(data.items) ? data.items : [];
    renderUploadVideoLibrary(uploadVideoLibraryItems);
    renderUploadQueueSelectors();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="8" class="uvlEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload video library load failed: ${e.message || e}`, 'upload');
  }
}

async function saveUploadVideo(event){
  if(event) event.preventDefault();
  const videoId = _uvlValue('uvl_video_id');
  const payload = collectUploadVideoForm();
  if(!videoId && !payload.video_path){
    showToast('Video path is required', 'error');
    return;
  }
  const body = videoId
    ? {
        caption: payload.caption,
        hashtags: payload.hashtags,
        cover_path: payload.cover_path,
        note: payload.note,
        status: payload.status,
      }
    : payload;
  try{
    const res = await fetch(videoId ? `/api/upload/videos/${encodeURIComponent(videoId)}` : '/api/upload/videos/add', {
      method: videoId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadVideoForm();
    await loadUploadVideoLibrary();
    showToast(videoId ? 'Upload video updated' : 'Upload video added', 'success');
  }catch(e){
    showToast(`Video save failed: ${e.message || e}`, 'error');
  }
}

async function disableUploadVideo(videoId){
  if(!videoId) return;
  try{
    const res = await fetch(`/api/upload/videos/${encodeURIComponent(videoId)}`, {method: 'DELETE'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadVideoLibrary();
    showToast('Upload video disabled', 'success');
  }catch(e){
    showToast(`Disable failed: ${e.message || e}`, 'error');
  }
}

function renderUploadQueueSelectors(){
  const videoSelect = qs('uqm_video_id');
  const accountSelect = qs('uqm_account_id');
  if(videoSelect){
    const current = videoSelect.value;
    const options = uploadVideoLibraryItems
      .filter((item) => String(item.status || '').toLowerCase() !== 'disabled')
      .map((item) => `<option value="${esc(item.video_id)}">${esc(item.file_name || item.video_path || item.video_id)}</option>`)
      .join('');
    videoSelect.innerHTML = `<option value="">Select video</option>${options}`;
    if(current) videoSelect.value = current;
  }
  if(accountSelect){
    const current = accountSelect.value;
    const options = uploadAccountManagerItems
      .filter((item) => String(item.status || '').toLowerCase() !== 'disabled')
      .map((item) => {
        const name = item.display_name || item.account_key || item.account_id;
        return `<option value="${esc(item.account_id)}">${esc(name)} (${esc(item.platform || 'tiktok')})</option>`;
      })
      .join('');
    accountSelect.innerHTML = `<option value="">Select account</option>${options}`;
    if(current) accountSelect.value = current;
  }
}

function selectVideoForQueue(videoId){
  const item = uploadVideoLibraryItems.find((x) => x.video_id === videoId);
  if(!item) return;
  if(String(item.status || '').toLowerCase() === 'disabled'){
    showToast('Disabled video cannot be queued', 'error');
    return;
  }
  renderUploadQueueSelectors();
  if(qs('uqm_video_id')) qs('uqm_video_id').value = videoId;
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  const panel = qs('upload_queue_manager');
  if(panel) panel.scrollIntoView({behavior: 'smooth', block: 'start'});
  showToast('Video selected for queue form', 'info');
}

function _uqmValue(id){
  return String(qs(id)?.value || '').trim();
}

function collectUploadQueueForm(){
  return {
    video_id: _uqmValue('uqm_video_id'),
    account_id: _uqmValue('uqm_account_id'),
    caption: _uqmValue('uqm_caption'),
    hashtags: _uvlParseHashtags(_uqmValue('uqm_hashtags')),
    scheduled_at: _uqmValue('uqm_scheduled_at'),
    priority: Number(qs('uqm_priority')?.value || 0) || 0,
    status: _uqmValue('uqm_status') || 'pending',
  };
}

function resetUploadQueueForm(){
  selectedUploadQueueId = '';
  ['uqm_queue_id', 'uqm_caption', 'uqm_hashtags', 'uqm_scheduled_at'].forEach((id) => {
    if(qs(id)) qs(id).value = '';
  });
  if(qs('uqm_video_id')) qs('uqm_video_id').value = '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = '';
  if(qs('uqm_priority')) qs('uqm_priority').value = '0';
  if(qs('uqm_status')) qs('uqm_status').value = 'pending';
  ['uqm_video_id'].forEach((id) => { if(qs(id)) qs(id).disabled = false; });
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Add to Queue';
  renderUploadQueueHistory([]);
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = 'Select a queue item to view attempts.';
}

function fillUploadQueueForm(queueId){
  const item = uploadQueueManagerItems.find((x) => x.queue_id === queueId);
  if(!item) return;
  selectedUploadQueueId = queueId;
  renderUploadQueueSelectors();
  if(qs('uqm_queue_id')) qs('uqm_queue_id').value = item.queue_id || '';
  if(qs('uqm_video_id')) qs('uqm_video_id').value = item.video_id || '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = item.account_id || '';
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uqm_scheduled_at')) qs('uqm_scheduled_at').value = item.scheduled_at || '';
  if(qs('uqm_priority')) qs('uqm_priority').value = Number(item.priority || 0);
  if(qs('uqm_status')) qs('uqm_status').value = ['pending', 'scheduled', 'held'].includes(String(item.status || '')) ? item.status : 'pending';
  if(qs('uqm_video_id')) qs('uqm_video_id').disabled = true;
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Save Queue Item';
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = `Queue ${queueId}`;
  loadSelectedUploadQueueHistory();
}

function renderUploadQueueManager(items){
  const tbody = qs('upload_queue_manager_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="8" class="uqmEmpty">No queue items yet. Select a video and account to create one.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || 'pending').toLowerCase();
    const muted = ['held', 'cancelled'].includes(status);
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    const clipName = item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-';
    let runButton = '';
    if(['pending', 'scheduled', 'held'].includes(status)){
      runButton = `<button class="ghostButton" type="button" onclick="runUploadQueueItem('${esc(item.queue_id)}')">Run</button>`;
    } else if(status === 'failed'){
      runButton = `<button class="ghostButton" type="button" onclick="runUploadQueueItem('${esc(item.queue_id)}')">Retry</button>`;
    } else if(status === 'uploading'){
      runButton = '<button class="ghostButton" type="button" disabled>Uploading...</button>';
    } else if(status === 'success'){
      runButton = '<button class="ghostButton" type="button" disabled>Success</button>';
    }
    return `
      <tr class="${muted ? 'isMuted' : ''}">
        <td>
          <div class="uqmClipName">${esc(clipName)}</div>
          <div class="uqmSub" title="${esc(item.video_path || '')}">${esc(_uamShortPath(item.video_path || ''))}</div>
        </td>
        <td>${esc(accountName)}</td>
        <td>${_uamBadge(status, 'status')}</td>
        <td>${esc(item.platform || 'tiktok')}</td>
        <td>${esc(item.scheduled_at || '-')}</td>
        <td>${Number(item.priority || 0)}</td>
        <td>${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}</td>
        <td>
          ${item.last_error ? `<div class="uqmError">${esc(item.last_error)}</div>` : ''}
          <div class="uqmActions">
            ${runButton}
            <button class="ghostButton" type="button" onclick="fillUploadQueueForm('${esc(item.queue_id)}')" ${['cancelled', 'uploading', 'success'].includes(status) ? 'disabled' : ''}>Edit</button>
            <button class="ghostButton" type="button" onclick="holdUploadQueueItem('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'failed'].includes(status) ? 'disabled' : ''}>Hold</button>
            <button class="ghostButton" type="button" onclick="resumeUploadQueueItem('${esc(item.queue_id)}')" ${status !== 'held' ? 'disabled' : ''}>Resume</button>
            <button class="ghostButton" type="button" onclick="cancelUploadQueueItemUi('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'held', 'failed'].includes(status) ? 'disabled' : ''}>Cancel</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadQueueManager(){
  const tbody = qs('upload_queue_manager_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="8" class="uqmEmpty">Loading queue...</td></tr>';
  const params = new URLSearchParams();
  const status = _uqmValue('uqm_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/queue?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadQueueManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadQueueManager(uploadQueueManagerItems);
    if(selectedUploadQueueId) loadSelectedUploadQueueHistory();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="8" class="uqmEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload queue load failed: ${e.message || e}`, 'upload');
  }
}

async function saveUploadQueueItem(event){
  if(event) event.preventDefault();
  const queueId = _uqmValue('uqm_queue_id');
  const payload = collectUploadQueueForm();
  if(!queueId && !payload.video_id){
    showToast('Missing video: select a video first', 'error');
    return;
  }
  if(!payload.account_id){
    showToast('Missing account: select an account first', 'error');
    return;
  }
  const body = queueId
    ? {
        account_id: payload.account_id,
        caption: payload.caption,
        hashtags: payload.hashtags,
        priority: payload.priority,
        scheduled_at: payload.scheduled_at,
        status: payload.status,
      }
    : payload;
  try{
    const res = await fetch(queueId ? `/api/upload/queue/${encodeURIComponent(queueId)}` : '/api/upload/queue/add', {
      method: queueId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadQueueForm();
    await loadUploadQueueManager();
    showToast(queueId ? 'Queue item updated' : 'Queue item created', 'success');
  }catch(e){
    showToast(`Queue save failed: ${e.message || e}`, 'error');
  }
}

async function _queueAction(queueId, action){
  try{
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(queueId)}/${action}`, {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadQueueManager();
    showToast(`Queue item ${action} ok`, 'success');
  }catch(e){
    showToast(`Queue ${action} failed: ${e.message || e}`, 'error');
  }
}

function holdUploadQueueItem(queueId){ _queueAction(queueId, 'hold'); }
function resumeUploadQueueItem(queueId){ _queueAction(queueId, 'resume'); }
function cancelUploadQueueItemUi(queueId){ _queueAction(queueId, 'cancel'); }

async function runUploadQueueItem(queueId){
  selectedUploadQueueId = queueId;
  showToast('Checking account/profile availability...', 'info');
  try{
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(queueId)}/run`, {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadQueueManager();
    await loadUploadQueueHistory(queueId);
    showToast(data.status === 'success' ? 'Upload completed' : 'Upload failed', data.status === 'success' ? 'success' : 'error');
  }catch(e){
    await loadUploadQueueManager();
    await loadUploadQueueHistory(queueId);
    showToast(`Run failed: ${e.message || e}`, 'error');
  }
}

function _historySummary(result){
  if(!result || typeof result !== 'object') return '';
  if(result.detail && typeof result.detail === 'object'){
    return result.detail.upload_message || result.detail.upload_state || JSON.stringify(result.detail).slice(0, 140);
  }
  return result.uploaded_at || result.adapter || '';
}

function renderUploadQueueHistory(items){
  const list = qs('upload_queue_history_list');
  if(!list) return;
  if(!selectedUploadQueueId){
    list.innerHTML = '<div class="uqmEmpty">No queue item selected.</div>';
    return;
  }
  if(!items || !items.length){
    list.innerHTML = '<div class="uqmEmpty">No attempts recorded for this queue item.</div>';
    return;
  }
  list.innerHTML = items.map((item) => `
    <div class="uqmHistoryItem ${String(item.status || '').toLowerCase()}">
      <div class="uqmHistoryTop">
        ${_uamBadge(item.status || 'failed', 'status')}
        <span>Attempt ${Number(item.attempt_no || 0)}</span>
        <span>${esc(item.started_at || '-')}</span>
        <span>${esc(item.finished_at || '-')}</span>
        <span>${Number(item.duration_seconds || 0).toFixed(1)}s</span>
      </div>
      ${item.error ? `<div class="uqmHistoryError">${esc(item.error)}</div>` : ''}
      ${_historySummary(item.adapter_result) ? `<div class="uqmSub">${esc(_historySummary(item.adapter_result))}</div>` : ''}
    </div>
  `).join('');
}

async function loadUploadQueueHistory(queueId){
  if(!queueId) return;
  selectedUploadQueueId = queueId;
  const list = qs('upload_queue_history_list');
  if(list) list.innerHTML = '<div class="uqmEmpty">Loading history...</div>';
  try{
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(queueId)}/history`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    renderUploadQueueHistory(Array.isArray(data.items) ? data.items : []);
  }catch(e){
    if(list) list.innerHTML = `<div class="uqmEmpty">History load failed: ${esc(e.message || e)}</div>`;
  }
}

async function runUploadQueueItem(queueId){
  selectedUploadQueueId = queueId;
  _selectUploadEntity('queue', queueId);
  showToast('Checking account/profile availability...', 'info');
  try{
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(queueId)}/run`, {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadQueueManager();
    await loadUploadQueueHistory(queueId);
    showToast(data.status === 'success' ? 'Upload completed' : 'Upload failed', data.status === 'success' ? 'success' : 'error');
  }catch(e){
    await loadUploadQueueManager();
    await loadUploadQueueHistory(queueId);
    showToast(`Run failed: ${e.message || e}`, 'error');
  }
}

let uploadManagerActiveTab = 'videos';

function _setEditorOpen(id, open){
  const el = qs(id);
  if(el && typeof open === 'boolean'){
    el.open = open;
  }
}

function openUploadEditor(type){
  if(type === 'account'){
    resetUploadAccountForm();
    _setEditorOpen('uam_editor', true);
    return;
  }
  if(type === 'video'){
    setUploadManagerTab('videos');
    resetUploadVideoForm();
    _setEditorOpen('uvl_editor', true);
    return;
  }
  if(type === 'queue'){
    setUploadManagerTab('queue');
    resetUploadQueueForm();
    _setEditorOpen('uqm_editor', true);
  }
}

function setUploadManagerTab(tab){
  uploadManagerActiveTab = tab === 'queue' ? 'queue' : 'videos';
  document.querySelectorAll('.uploadManagerTab').forEach((btn) => {
    btn.classList.toggle('active', btn.id === `upload_tab_${uploadManagerActiveTab}`);
  });
  document.querySelectorAll('.uploadManagerTabPanel').forEach((panel) => {
    panel.classList.toggle('active', panel.getAttribute('data-tab-panel') === uploadManagerActiveTab);
  });
}

function _selectUploadEntity(type, id){
  selectedUploadEntity = {type: String(type || ''), id: String(id || '')};
  if(type === 'video'){
    setUploadManagerTab('videos');
  } else if(type === 'queue'){
    setUploadManagerTab('queue');
    selectedUploadQueueId = String(id || '');
    loadSelectedUploadQueueHistory();
  } else {
    renderUploadQueueHistory(currentUploadQueueHistoryItems);
  }
  renderUploadInspector();
}

function _rowMoreMenu(label, actionsHtml){
  return `
    <details class="rowActionMenu" onclick="event.stopPropagation()">
      <summary>${esc(label || 'More')}</summary>
      <div class="rowActionMenuBody">
        ${actionsHtml}
      </div>
    </details>
  `;
}

function fillUploadAccountForm(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  _selectUploadEntity('account', accountId);
  _setEditorOpen('uam_editor', true);
  if(qs('uam_account_id')) qs('uam_account_id').value = item.account_id || '';
  if(qs('uam_platform')) qs('uam_platform').value = item.platform || 'tiktok';
  if(qs('uam_channel_code')) qs('uam_channel_code').value = item.channel_code || '';
  if(qs('uam_account_key')) qs('uam_account_key').value = item.account_key || 'default';
  if(qs('uam_display_name')) qs('uam_display_name').value = item.display_name || '';
  if(qs('uam_status')) qs('uam_status').value = item.status || 'active';
  if(qs('uam_login_state')) qs('uam_login_state').value = item.login_state || 'unknown';
  if(qs('uam_daily_limit')) qs('uam_daily_limit').value = Number(item.daily_limit || 0);
  if(qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = Number(item.cooldown_minutes || 0);
  if(qs('uam_today_count')) qs('uam_today_count').value = Number(item.today_count || 0);
  if(qs('uam_profile_path')) qs('uam_profile_path').value = item.profile_path || '';
  if(qs('uam_proxy_id')) qs('uam_proxy_id').value = item.proxy_id || '';
  if(qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Save Changes';
}

function renderUploadAccounts(items){
  const tbody = qs('upload_accounts_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="4" class="uamEmpty">No accounts yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const name = item.display_name || item.account_key || item.account_id;
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    const selected = _selectedUploadId('account') === String(item.account_id || '');
    const usage = `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`;
    const moreMenu = _rowMoreMenu('More', `
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); checkUploadAccountLogin('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Check Login</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); disableUploadAccount('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
    `);
    return `
      <tr class="${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('account', '${esc(item.account_id)}')">
        <td>
          <div class="uamAccountName">${esc(name)}</div>
          <div class="uamSub">${esc(item.platform || 'tiktok')} - ${esc(item.account_key || 'default')}</div>
          ${item.profile_conflict ? `<div class="uamWarn">Conflict: ${esc(_uamConflictText(item))}</div>` : ''}
        </td>
        <td>
          ${_uamBadge(item.status, 'status')}
          <div class="uamSub">${esc(item.profile_lock_state || 'idle')}</div>
        </td>
        <td>
          ${_uamBadge(item.login_state, 'login')}
          <div class="uamSub">${esc(usage)}</div>
        </td>
        <td>
          <div class="uamActions">
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadAccountForm('${esc(item.account_id)}')">Edit</button>
            ${moreMenu}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadAccounts(){
  const tbody = qs('upload_accounts_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="4" class="uamEmpty">Loading accounts...</td></tr>';
  try{
    const res = await fetch('/api/upload/accounts');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadAccountManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="4" class="uamEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload account load failed: ${e.message || e}`, 'upload');
  }
}

function fillUploadVideoForm(videoId){
  const item = uploadVideoLibraryItems.find((x) => x.video_id === videoId);
  if(!item) return;
  _selectUploadEntity('video', videoId);
  _setEditorOpen('uvl_editor', true);
  if(qs('uvl_video_id')) qs('uvl_video_id').value = item.video_id || '';
  if(qs('uvl_video_path')) qs('uvl_video_path').value = item.video_path || '';
  if(qs('uvl_platform')) qs('uvl_platform').value = item.platform || 'tiktok';
  if(qs('uvl_source_type')) qs('uvl_source_type').value = item.source_type || 'manual_file';
  if(qs('uvl_status')) qs('uvl_status').value = item.status || 'ready';
  if(qs('uvl_caption')) qs('uvl_caption').value = item.caption || '';
  if(qs('uvl_hashtags')) qs('uvl_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uvl_note')) qs('uvl_note').value = item.note || '';
  if(qs('uvl_cover_path')) qs('uvl_cover_path').value = item.cover_path || '';
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => {
    if(qs(id)) qs(id).disabled = true;
  });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Save Video';
}

function renderUploadVideoLibrary(items){
  const tbody = qs('upload_videos_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="5" class="uvlEmpty">No videos yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || '').toLowerCase();
    const disabled = status === 'disabled';
    const selected = _selectedUploadId('video') === String(item.video_id || '');
    const tags = _uvlHashtagText(item.hashtags || []);
    const moreMenu = _rowMoreMenu('More', `
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); disableUploadVideo('${esc(item.video_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
    `);
    return `
      <tr class="${disabled ? 'isDisabled' : ''} ${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('video', '${esc(item.video_id)}')">
        <td>
          <div class="uvlFileName">${esc(item.file_name || item.video_path || '-')}</div>
          <div class="uvlSub">${esc(item.platform || 'tiktok')} - ${esc(String(item.source_type || 'manual_file').replace(/_/g, ' '))}</div>
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td><div class="uvlClipText">${esc(item.caption || '-')}</div></td>
        <td><div class="uvlClipText">${esc(tags || '-')}</div></td>
        <td>
          <div class="uvlActions">
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); selectVideoForQueue('${esc(item.video_id)}')" ${disabled || status !== 'ready' ? 'disabled' : ''}>Select</button>
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadVideoForm('${esc(item.video_id)}')">Edit</button>
            ${moreMenu}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadVideoLibrary(){
  const tbody = qs('upload_videos_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="5" class="uvlEmpty">Loading videos...</td></tr>';
  const params = new URLSearchParams();
  const status = _uvlValue('uvl_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/videos?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadVideoLibraryItems = Array.isArray(data.items) ? data.items : [];
    renderUploadVideoLibrary(uploadVideoLibraryItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="5" class="uvlEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload video library load failed: ${e.message || e}`, 'upload');
  }
}

function fillUploadQueueForm(queueId){
  const item = uploadQueueManagerItems.find((x) => x.queue_id === queueId);
  if(!item) return;
  _selectUploadEntity('queue', queueId);
  _setEditorOpen('uqm_editor', true);
  selectedUploadQueueId = queueId;
  renderUploadQueueSelectors();
  if(qs('uqm_queue_id')) qs('uqm_queue_id').value = item.queue_id || '';
  if(qs('uqm_video_id')) qs('uqm_video_id').value = item.video_id || '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = item.account_id || '';
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uqm_scheduled_at')) qs('uqm_scheduled_at').value = item.scheduled_at || '';
  if(qs('uqm_priority')) qs('uqm_priority').value = Number(item.priority || 0);
  if(qs('uqm_status')) qs('uqm_status').value = ['pending', 'scheduled', 'held'].includes(String(item.status || '')) ? item.status : 'pending';
  if(qs('uqm_video_id')) qs('uqm_video_id').disabled = true;
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Save Queue Item';
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = `Queue ${queueId}`;
  loadSelectedUploadQueueHistory();
}

function renderUploadQueueManager(items){
  const tbody = qs('upload_queue_manager_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="6" class="uqmEmpty">No queue items yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || 'pending').toLowerCase();
    const muted = ['held', 'cancelled'].includes(status);
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    const clipName = item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-';
    const selected = _selectedUploadId('queue') === String(item.queue_id || '');
    let primaryAction = '<button class="ghostButton" type="button" disabled>Done</button>';
    if(['pending', 'scheduled', 'held'].includes(status)){
      primaryAction = `<button class="ghostButton" type="button" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Run</button>`;
    } else if(status === 'failed'){
      primaryAction = `<button class="ghostButton" type="button" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Retry</button>`;
    }
    const moreMenu = _rowMoreMenu('More', `
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadQueueForm('${esc(item.queue_id)}')" ${['cancelled', 'uploading', 'success'].includes(status) ? 'disabled' : ''}>Edit</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); holdUploadQueueItem('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'failed'].includes(status) ? 'disabled' : ''}>Hold</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); resumeUploadQueueItem('${esc(item.queue_id)}')" ${status !== 'held' ? 'disabled' : ''}>Resume</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); cancelUploadQueueItemUi('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'held', 'failed'].includes(status) ? 'disabled' : ''}>Cancel</button>
    `);
    return `
      <tr class="${muted ? 'isMuted' : ''} ${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('queue', '${esc(item.queue_id)}')">
        <td>
          <div class="uqmClipName">${esc(clipName)}</div>
          <div class="uqmSub">${esc(item.platform || 'tiktok')}</div>
          ${item.last_error ? `<div class="uqmSub">${esc(item.last_error)}</div>` : ''}
        </td>
        <td><div class="uvlClipText">${esc(accountName)}</div></td>
        <td>${_uamBadge(status, 'status')}</td>
        <td>${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}</td>
        <td><div class="uvlClipText">${esc(item.scheduled_at || '-')}</div></td>
        <td>
          <div class="uqmActions">
            ${primaryAction}
            ${moreMenu}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadQueueManager(){
  const tbody = qs('upload_queue_manager_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="6" class="uqmEmpty">Loading queue...</td></tr>';
  const params = new URLSearchParams();
  const status = _uqmValue('uqm_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/queue?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadQueueManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadQueueManager(uploadQueueManagerItems);
    renderUploadInspector();
    if(selectedUploadQueueId) loadSelectedUploadQueueHistory();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" class="uqmEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload queue load failed: ${e.message || e}`, 'upload');
  }
}

function initUploadManagerCleanUi(){
  setUploadManagerTab(uploadManagerActiveTab);
  _setEditorOpen('uam_editor', false);
  _setEditorOpen('uvl_editor', false);
  _setEditorOpen('uqm_editor', false);
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', initUploadManagerCleanUi);
}else{
  initUploadManagerCleanUi();
}

function _activeUploadAccounts(){
  return uploadAccountManagerItems.filter((item) => String(item.status || '').toLowerCase() !== 'disabled');
}

function _readyUploadVideos(){
  return uploadVideoLibraryItems.filter((item) => String(item.status || '').toLowerCase() !== 'disabled');
}

function _actionableQueueItems(){
  return uploadQueueManagerItems.filter((item) => String(item.status || '').toLowerCase() !== 'cancelled');
}

function getQueueCreateHint(){
  if(!_activeUploadAccounts().length) return 'Select account + video first. Add an account to begin.';
  if(!_readyUploadVideos().length) return 'Select account + video first. Add a video file.';
  if(!_uqmValue('uqm_account_id') || !String(qs('uqm_video_id')?.value || '').trim()){
    return 'Select account + video first.';
  }
  return 'Ready to add this selection to the queue.';
}

function getQueueRunReason(item){
  const status = String(item?.status || '').toLowerCase();
  if(!item) return 'Select account + video first';
  if(status === 'success') return 'Already uploaded successfully';
  if(status === 'cancelled') return 'Cancelled item cannot run';
  if(status === 'uploading') return 'Upload already in progress';
  const account = uploadAccountManagerItems.find((x) => x.account_id === item.account_id);
  if(!account) return 'Select account + video first';
  const accountStatus = String(account.status || '').toLowerCase();
  if(accountStatus === 'disabled') return 'Account is disabled';
  if(accountStatus === 'banned') return 'Account is banned';
  if(String(account.profile_lock_state || '').toLowerCase() === 'locked') return 'Account is busy';
  const loginState = String(account.login_state || '').toLowerCase();
  if(['logged_out', 'expired', 'challenge'].includes(loginState)) return 'Account not logged in';
  return 'Run upload';
}

function renderUploadWorkflowGuide(){
  let step = 4;
  let hint = 'Ready to run a queued upload.';
  if(!_activeUploadAccounts().length){
    step = 1;
    hint = 'Step 1: add an account to begin.';
  } else if(!_readyUploadVideos().length){
    step = 2;
    hint = 'Step 2: add a video file to the library.';
  } else if(!_actionableQueueItems().length){
    step = 3;
    hint = 'Step 3: select a video and account, then add a queue item.';
  }
  currentUploadWorkflowStep = step;
  for(let i = 1; i <= 4; i += 1){
    const el = qs(`upload_workflow_step_${i}`);
    if(!el) continue;
    el.classList.toggle('isActive', i === step);
    el.classList.toggle('isComplete', i < step);
  }
  const hintEl = qs('upload_workflow_hint');
  if(hintEl) hintEl.textContent = hint;
  const queueHint = qs('uqm_form_hint');
  if(queueHint) queueHint.textContent = getQueueCreateHint();
}

function _selectUploadEntity(type, id){
  selectedUploadEntity = {type: String(type || ''), id: String(id || '')};
  if(type === 'video'){
    setUploadManagerTab('videos');
  } else if(type === 'queue'){
    setUploadManagerTab('queue');
    selectedUploadQueueId = String(id || '');
    loadSelectedUploadQueueHistory();
  } else {
    renderUploadQueueHistory(currentUploadQueueHistoryItems);
  }
  renderUploadInspector();
}

function resetUploadAccountForm(){
  ['uam_account_id', 'uam_channel_code', 'uam_display_name', 'uam_profile_path', 'uam_proxy_id'].forEach((id) => {
    if(qs(id)) qs(id).value = '';
  });
  if(qs('uam_platform')) qs('uam_platform').value = 'tiktok';
  if(qs('uam_account_key')) qs('uam_account_key').value = 'default';
  if(qs('uam_status')) qs('uam_status').value = 'active';
  if(qs('uam_login_state')) qs('uam_login_state').value = 'unknown';
  if(qs('uam_daily_limit')) qs('uam_daily_limit').value = '0';
  if(qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = '0';
  if(qs('uam_today_count')) qs('uam_today_count').value = '0';
  if(qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Create Account';
}

function resetUploadQueueForm(){
  selectedUploadQueueId = '';
  ['uqm_queue_id', 'uqm_caption', 'uqm_hashtags', 'uqm_scheduled_at'].forEach((id) => {
    if(qs(id)) qs(id).value = '';
  });
  if(qs('uqm_video_id')) qs('uqm_video_id').value = '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = '';
  if(qs('uqm_priority')) qs('uqm_priority').value = '0';
  if(qs('uqm_status')) qs('uqm_status').value = 'pending';
  if(qs('uqm_video_id')) qs('uqm_video_id').disabled = false;
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Add to Queue';
  renderUploadQueueHistory([]);
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = 'Select a queue item to view attempts.';
  const hint = qs('uqm_form_hint');
  if(hint) hint.textContent = getQueueCreateHint();
}

function renderUploadInspector(){
  const titleEl = qs('upload_detail_title');
  const hintEl = qs('upload_detail_hint');
  const breadcrumbEl = qs('upload_detail_breadcrumb');
  const bodyEl = qs('upload_detail_body');
  if(!titleEl || !hintEl || !bodyEl) return;

  const type = selectedUploadEntity.type;
  const id = selectedUploadEntity.id;
  if(!type || !id){
    titleEl.textContent = 'Selection Details';
    hintEl.textContent = 'Select an account, video, or queue item to inspect details.';
    if(breadcrumbEl) breadcrumbEl.textContent = 'Nothing selected';
    bodyEl.innerHTML = '<div class="uploadInspectorPlaceholder">Select an account, video, or queue item to inspect details.</div>';
    return;
  }

  if(type === 'account'){
    const item = uploadAccountManagerItems.find((x) => x.account_id === id);
    if(!item) return;
    const name = item.display_name || item.account_key || item.account_id;
    titleEl.textContent = name;
    hintEl.textContent = `Account - ${item.platform || 'tiktok'} - ${item.account_key || 'default'}`;
    if(breadcrumbEl) breadcrumbEl.textContent = `Selected Account -> ${name}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Login State', String(item.login_state || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Profile Lock', String(item.profile_lock_state || 'idle').replace(/_/g, ' '), false)}
        ${_detailSection('Usage Today', `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`, false)}
        ${_detailSection('Cooldown', `${Number(item.cooldown_minutes || 0)} min`, false)}
        ${_detailSection('Proxy ID', item.proxy_id || '-', false)}
      </div>
      ${_detailSection('Profile Path', item.profile_path || '-', false)}
      ${item.profile_conflict ? _detailSection('Profile Conflict', _uamConflictText(item), false) : ''}
      ${_detailSection('Health JSON', _prettyJson(item.health_json || {}), true)}
    `;
    return;
  }

  if(type === 'video'){
    const item = uploadVideoLibraryItems.find((x) => x.video_id === id);
    if(!item) return;
    titleEl.textContent = item.file_name || item.video_id;
    hintEl.textContent = `Video - ${item.platform || 'tiktok'} - ${String(item.status || 'ready').replace(/_/g, ' ')}`;
    if(breadcrumbEl) breadcrumbEl.textContent = `Selected Video -> ${item.file_name || item.video_id}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'ready').replace(/_/g, ' '), false)}
        ${_detailSection('Source Type', String(item.source_type || 'manual_file').replace(/_/g, ' '), false)}
        ${_detailSection('Duration', _uvlFormatDuration(item.duration_sec), false)}
        ${_detailSection('File Size', _uvlFormatSize(item.file_size), false)}
      </div>
      ${_detailSection('Video Path', item.video_path || '-', false)}
      ${_detailSection('Caption', item.caption || '-', false)}
      ${_detailSection('Hashtags', _uvlHashtagText(item.hashtags || []) || '-', false)}
      ${_detailSection('Note', item.note || '-', false)}
      ${_detailSection('Cover Path', item.cover_path || '-', false)}
    `;
    return;
  }

  if(type === 'queue'){
    const item = uploadQueueManagerItems.find((x) => x.queue_id === id);
    if(!item) return;
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    titleEl.textContent = item.video_file_name || item.queue_id;
    hintEl.textContent = `Queue - ${accountName} - ${String(item.status || 'pending').replace(/_/g, ' ')}`;
    if(breadcrumbEl) breadcrumbEl.textContent = `Selected Queue Item -> ${(item.video_file_name || item.queue_id)} -> ${accountName}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'pending').replace(/_/g, ' '), false)}
        ${_detailSection('Platform', item.platform || 'tiktok', false)}
        ${_detailSection('Priority', String(Number(item.priority || 0)), false)}
        ${_detailSection('Attempts', `${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}`, false)}
        ${_detailSection('Scheduled At', item.scheduled_at || '-', false)}
        ${_detailSection('Account', accountName, false)}
      </div>
      ${_detailSection('Video Path', item.video_path || '-', false)}
      ${_detailSection('Caption', item.caption || '-', false)}
      ${_detailSection('Hashtags', _uvlHashtagText(item.hashtags || []) || '-', false)}
      ${_detailSection('Last Error', item.last_error || '-', false)}
      ${_detailSection('Adapter Result', _historySummary(item.result_json || item.result || {}) || '-', false)}
    `;
  }
}

function renderUploadAccounts(items){
  const tbody = qs('upload_accounts_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="4" class="uamEmpty">No accounts yet. Create one to start uploading.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const name = item.display_name || item.account_key || item.account_id;
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    const selected = _selectedUploadId('account') === String(item.account_id || '');
    const usage = `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`;
    const moreMenu = _rowMoreMenu('More', `
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); checkUploadAccountLogin('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Check Login</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); disableUploadAccount('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
    `);
    return `
      <tr class="${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('account', '${esc(item.account_id)}')">
        <td>
          <div class="uamAccountName">${esc(name)}</div>
          <div class="uamSub">${esc(item.platform || 'tiktok')} - ${esc(item.account_key || 'default')}</div>
          ${item.profile_conflict ? `<div class="uamWarn">Conflict: ${esc(_uamConflictText(item))}</div>` : ''}
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td>
          ${_uamBadge(item.login_state, 'login')}
          <div class="uamSub">${esc(usage)}</div>
        </td>
        <td>
          <div class="uamActions">
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadAccountForm('${esc(item.account_id)}')">Edit</button>
            ${moreMenu}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderUploadVideoLibrary(items){
  const tbody = qs('upload_videos_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="5" class="uvlEmpty">No videos yet. Add a video file.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || '').toLowerCase();
    const disabled = status === 'disabled';
    const selected = _selectedUploadId('video') === String(item.video_id || '');
    const tags = _uvlHashtagText(item.hashtags || []);
    const queueTitle = disabled ? 'Video disabled' : (status !== 'ready' ? `Video status is ${status}` : 'Select this video for queue');
    const moreMenu = _rowMoreMenu('More', `
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); disableUploadVideo('${esc(item.video_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
    `);
    return `
      <tr class="${disabled ? 'isDisabled' : ''} ${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('video', '${esc(item.video_id)}')">
        <td>
          <div class="uvlFileName">${esc(item.file_name || item.video_path || '-')}</div>
          <div class="uvlSub">${esc(item.platform || 'tiktok')}</div>
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td><div class="uvlClipText">${esc(item.caption || '-')}</div></td>
        <td><div class="uvlClipText">${esc(tags || '-')}</div></td>
        <td>
          <div class="uvlActions">
            <button class="ghostButton" type="button" title="${esc(queueTitle)}" onclick="event.stopPropagation(); selectVideoForQueue('${esc(item.video_id)}')" ${disabled || status !== 'ready' ? 'disabled' : ''}>Select</button>
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadVideoForm('${esc(item.video_id)}')">Edit</button>
            ${moreMenu}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderUploadQueueManager(items){
  const tbody = qs('upload_queue_manager_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="6" class="uqmEmpty">No queue items yet. Select a video and account.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || 'pending').toLowerCase();
    const muted = ['held', 'cancelled'].includes(status);
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    const clipName = item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-';
    const selected = _selectedUploadId('queue') === String(item.queue_id || '');
    const runReason = getQueueRunReason(item);
    let primaryAction = `<button class="ghostButton" type="button" title="${esc(runReason)}" disabled>Run</button>`;
    if(['pending', 'scheduled', 'held'].includes(status)){
      primaryAction = `<button class="ghostButton" type="button" title="${esc(runReason)}" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Run</button>`;
    } else if(status === 'failed'){
      primaryAction = `<button class="ghostButton" type="button" title="${esc(runReason)}" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Retry</button>`;
    }
    if(runReason !== 'Run upload' && ['pending', 'scheduled', 'held', 'failed'].includes(status) === false){
      primaryAction = `<button class="ghostButton" type="button" title="${esc(runReason)}" disabled>${status === 'failed' ? 'Retry' : 'Run'}</button>`;
    }
    const moreMenu = _rowMoreMenu('More', `
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadQueueForm('${esc(item.queue_id)}')" ${['cancelled', 'uploading', 'success'].includes(status) ? 'disabled' : ''}>Edit</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); holdUploadQueueItem('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'failed'].includes(status) ? 'disabled' : ''}>Hold</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); resumeUploadQueueItem('${esc(item.queue_id)}')" ${status !== 'held' ? 'disabled' : ''}>Resume</button>
      <button class="ghostButton" type="button" onclick="event.stopPropagation(); cancelUploadQueueItemUi('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'held', 'failed'].includes(status) ? 'disabled' : ''}>Cancel</button>
    `);
    return `
      <tr class="${muted ? 'isMuted' : ''} ${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('queue', '${esc(item.queue_id)}')">
        <td>
          <div class="uqmClipName">${esc(clipName)}</div>
          ${item.last_error ? `<div class="uqmSub">${esc(item.last_error)}</div>` : `<div class="uqmSub">${esc(item.platform || 'tiktok')}</div>`}
        </td>
        <td><div class="uvlClipText">${esc(accountName)}</div></td>
        <td>${_uamBadge(status, 'status')}</td>
        <td>${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}</td>
        <td><div class="uvlClipText">${esc(item.scheduled_at || '-')}</div></td>
        <td>
          <div class="uqmActions">
            ${primaryAction}
            ${moreMenu}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadAccounts(){
  const tbody = qs('upload_accounts_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="4" class="uamEmpty">Loading accounts...</td></tr>';
  try{
    const res = await fetch('/api/upload/accounts');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadAccountManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
    renderUploadWorkflowGuide();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="4" class="uamEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload account load failed: ${e.message || e}`, 'upload');
  }
}

async function loadUploadVideoLibrary(){
  const tbody = qs('upload_videos_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="5" class="uvlEmpty">Loading videos...</td></tr>';
  const params = new URLSearchParams();
  const status = _uvlValue('uvl_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/videos?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadVideoLibraryItems = Array.isArray(data.items) ? data.items : [];
    renderUploadVideoLibrary(uploadVideoLibraryItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
    renderUploadWorkflowGuide();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="5" class="uvlEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload video library load failed: ${e.message || e}`, 'upload');
  }
}

async function loadUploadQueueManager(){
  const tbody = qs('upload_queue_manager_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="6" class="uqmEmpty">Loading queue...</td></tr>';
  const params = new URLSearchParams();
  const status = _uqmValue('uqm_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/queue?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadQueueManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadQueueManager(uploadQueueManagerItems);
    renderUploadInspector();
    if(selectedUploadQueueId) loadSelectedUploadQueueHistory();
    renderUploadWorkflowGuide();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" class="uqmEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload queue load failed: ${e.message || e}`, 'upload');
  }
}

function fillUploadAccountForm(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  _selectUploadEntity('account', accountId);
  _setEditorOpen('uam_editor', true);
  if(qs('uam_account_id')) qs('uam_account_id').value = item.account_id || '';
  if(qs('uam_platform')) qs('uam_platform').value = item.platform || 'tiktok';
  if(qs('uam_channel_code')) qs('uam_channel_code').value = item.channel_code || '';
  if(qs('uam_account_key')) qs('uam_account_key').value = item.account_key || 'default';
  if(qs('uam_display_name')) qs('uam_display_name').value = item.display_name || '';
  if(qs('uam_status')) qs('uam_status').value = item.status || 'active';
  if(qs('uam_login_state')) qs('uam_login_state').value = item.login_state || 'unknown';
  if(qs('uam_daily_limit')) qs('uam_daily_limit').value = Number(item.daily_limit || 0);
  if(qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = Number(item.cooldown_minutes || 0);
  if(qs('uam_today_count')) qs('uam_today_count').value = Number(item.today_count || 0);
  if(qs('uam_profile_path')) qs('uam_profile_path').value = item.profile_path || '';
  if(qs('uam_proxy_id')) qs('uam_proxy_id').value = item.proxy_id || '';
  if(qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Save Changes';
}

function fillUploadVideoForm(videoId){
  const item = uploadVideoLibraryItems.find((x) => x.video_id === videoId);
  if(!item) return;
  _selectUploadEntity('video', videoId);
  _setEditorOpen('uvl_editor', true);
  if(qs('uvl_video_id')) qs('uvl_video_id').value = item.video_id || '';
  if(qs('uvl_video_path')) qs('uvl_video_path').value = item.video_path || '';
  if(qs('uvl_platform')) qs('uvl_platform').value = item.platform || 'tiktok';
  if(qs('uvl_source_type')) qs('uvl_source_type').value = item.source_type || 'manual_file';
  if(qs('uvl_status')) qs('uvl_status').value = item.status || 'ready';
  if(qs('uvl_caption')) qs('uvl_caption').value = item.caption || '';
  if(qs('uvl_hashtags')) qs('uvl_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uvl_note')) qs('uvl_note').value = item.note || '';
  if(qs('uvl_cover_path')) qs('uvl_cover_path').value = item.cover_path || '';
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => {
    if(qs(id)) qs(id).disabled = true;
  });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Save Video';
}

function fillUploadQueueForm(queueId){
  const item = uploadQueueManagerItems.find((x) => x.queue_id === queueId);
  if(!item) return;
  _selectUploadEntity('queue', queueId);
  _setEditorOpen('uqm_editor', true);
  selectedUploadQueueId = queueId;
  renderUploadQueueSelectors();
  if(qs('uqm_queue_id')) qs('uqm_queue_id').value = item.queue_id || '';
  if(qs('uqm_video_id')) qs('uqm_video_id').value = item.video_id || '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = item.account_id || '';
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uqm_scheduled_at')) qs('uqm_scheduled_at').value = item.scheduled_at || '';
  if(qs('uqm_priority')) qs('uqm_priority').value = Number(item.priority || 0);
  if(qs('uqm_status')) qs('uqm_status').value = ['pending', 'scheduled', 'held'].includes(String(item.status || '')) ? item.status : 'pending';
  if(qs('uqm_video_id')) qs('uqm_video_id').disabled = true;
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Save Queue Item';
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = `Queue ${queueId}`;
  const hint = qs('uqm_form_hint');
  if(hint) hint.textContent = getQueueCreateHint();
  loadSelectedUploadQueueHistory();
}

async function saveUploadAccount(event){
  if(event) event.preventDefault();
  const accountId = _uamValue('uam_account_id');
  const payload = collectUploadAccountForm();
  try{
    const res = await fetch(accountId ? `/api/upload/accounts/${encodeURIComponent(accountId)}` : '/api/upload/accounts', {
      method: accountId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadAccountForm();
    _setEditorOpen('uam_editor', false);
    await loadUploadAccounts();
    showToast(accountId ? 'Account updated' : 'Account added', 'success');
  }catch(e){
    showToast(`Account save failed: ${e.message || e}`, 'error');
  }
}

async function saveUploadVideo(event){
  if(event) event.preventDefault();
  const videoId = _uvlValue('uvl_video_id');
  const payload = collectUploadVideoForm();
  if(!videoId && !payload.video_path){
    showToast('Video path is required', 'error');
    return;
  }
  const body = videoId ? {caption: payload.caption, hashtags: payload.hashtags, cover_path: payload.cover_path, note: payload.note, status: payload.status} : payload;
  try{
    const res = await fetch(videoId ? `/api/upload/videos/${encodeURIComponent(videoId)}` : '/api/upload/videos/add', {
      method: videoId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadVideoForm();
    _setEditorOpen('uvl_editor', false);
    await loadUploadVideoLibrary();
    showToast(videoId ? 'Video updated' : 'Video added', 'success');
  }catch(e){
    showToast(`Video save failed: ${e.message || e}`, 'error');
  }
}

async function saveUploadQueueItem(event){
  if(event) event.preventDefault();
  const queueId = _uqmValue('uqm_queue_id');
  const payload = collectUploadQueueForm();
  if(!queueId && !payload.video_id){
    showToast('Missing video: select a video first', 'error');
    return;
  }
  if(!payload.account_id){
    showToast('Missing account: select an account first', 'error');
    return;
  }
  const body = queueId ? {account_id: payload.account_id, caption: payload.caption, hashtags: payload.hashtags, priority: payload.priority, scheduled_at: payload.scheduled_at, status: payload.status} : payload;
  try{
    const res = await fetch(queueId ? `/api/upload/queue/${encodeURIComponent(queueId)}` : '/api/upload/queue/add', {
      method: queueId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadQueueForm();
    _setEditorOpen('uqm_editor', false);
    setUploadManagerTab('queue');
    await loadUploadQueueManager();
    showToast(queueId ? 'Queue item updated' : 'Added to queue', 'success');
  }catch(e){
    showToast(`Queue save failed: ${e.message || e}`, 'error');
  }
}

async function runUploadQueueItem(queueId){
  selectedUploadQueueId = queueId;
  _selectUploadEntity('queue', queueId);
  showToast('Upload started', 'info');
  try{
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(queueId)}/run`, {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadQueueManager();
    await loadUploadQueueHistory(queueId);
    showToast(data.status === 'success' ? 'Upload completed' : 'Upload failed', data.status === 'success' ? 'success' : 'error');
  }catch(e){
    await loadUploadQueueManager();
    await loadUploadQueueHistory(queueId);
    showToast(`Upload failed: ${e.message || e}`, 'error');
  }
}

function initUploadManagerUxFlow(){
  renderUploadWorkflowGuide();
  const accountSelect = qs('uqm_account_id');
  const videoSelect = qs('uqm_video_id');
  if(accountSelect) accountSelect.addEventListener('change', renderUploadWorkflowGuide);
  if(videoSelect) videoSelect.addEventListener('change', renderUploadWorkflowGuide);
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', initUploadManagerUxFlow);
}else{
  initUploadManagerUxFlow();
}

function loadSelectedUploadQueueHistory(){
  if(!selectedUploadQueueId){
    renderUploadQueueHistory([]);
    return;
  }
  loadUploadQueueHistory(selectedUploadQueueId);
}

function renderUploadInspector(){
  const titleEl = qs('upload_detail_title');
  const hintEl = qs('upload_detail_hint');
  const bodyEl = qs('upload_detail_body');
  if(!titleEl || !hintEl || !bodyEl) return;

  const type = selectedUploadEntity.type;
  const id = selectedUploadEntity.id;
  if(!type || !id){
    titleEl.textContent = 'Selection Details';
    hintEl.textContent = 'Select an account, video, or queue item to inspect details.';
    bodyEl.innerHTML = '<div class="uploadInspectorPlaceholder">Select an account, video, or queue item to inspect details.</div>';
    return;
  }

  if(type === 'account'){
    const item = uploadAccountManagerItems.find((x) => x.account_id === id);
    if(!item){
      selectedUploadEntity = {type: '', id: ''};
      renderUploadInspector();
      return;
    }
    const name = item.display_name || item.account_key || item.account_id;
    titleEl.textContent = name;
    hintEl.textContent = `Account - ${item.platform || 'tiktok'} - ${item.account_key || 'default'}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Login State', String(item.login_state || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Profile Lock', String(item.profile_lock_state || 'idle').replace(/_/g, ' '), false)}
        ${_detailSection('Usage Today', `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`, false)}
        ${_detailSection('Cooldown', `${Number(item.cooldown_minutes || 0)} min`, false)}
        ${_detailSection('Proxy ID', item.proxy_id || '-', false)}
      </div>
      ${_detailSection('Profile Path', item.profile_path || '-', false)}
      ${item.profile_conflict ? _detailSection('Profile Conflict', _uamConflictText(item), false) : ''}
      ${_detailSection('Health JSON', _prettyJson(item.health_json || {}), true)}
    `;
    return;
  }

  if(type === 'video'){
    const item = uploadVideoLibraryItems.find((x) => x.video_id === id);
    if(!item){
      selectedUploadEntity = {type: '', id: ''};
      renderUploadInspector();
      return;
    }
    titleEl.textContent = item.file_name || item.video_id;
    hintEl.textContent = `Video - ${item.platform || 'tiktok'} - ${String(item.status || 'ready').replace(/_/g, ' ')}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'ready').replace(/_/g, ' '), false)}
        ${_detailSection('Source Type', String(item.source_type || 'manual_file').replace(/_/g, ' '), false)}
        ${_detailSection('Duration', _uvlFormatDuration(item.duration_sec), false)}
        ${_detailSection('File Size', _uvlFormatSize(item.file_size), false)}
      </div>
      ${_detailSection('Video Path', item.video_path || '-', false)}
      ${_detailSection('Caption', item.caption || '-', false)}
      ${_detailSection('Hashtags', _uvlHashtagText(item.hashtags || []) || '-', false)}
      ${_detailSection('Note', item.note || '-', false)}
      ${_detailSection('Cover Path', item.cover_path || '-', false)}
    `;
    return;
  }

  if(type === 'queue'){
    const item = uploadQueueManagerItems.find((x) => x.queue_id === id);
    if(!item){
      selectedUploadEntity = {type: '', id: ''};
      renderUploadInspector();
      return;
    }
    titleEl.textContent = item.video_file_name || item.queue_id;
    hintEl.textContent = `Queue - ${(item.account_display_name || item.account_key || item.account_id || '-')} - ${String(item.status || 'pending').replace(/_/g, ' ')}`;
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'pending').replace(/_/g, ' '), false)}
        ${_detailSection('Platform', item.platform || 'tiktok', false)}
        ${_detailSection('Priority', String(Number(item.priority || 0)), false)}
        ${_detailSection('Attempts', `${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}`, false)}
        ${_detailSection('Scheduled At', item.scheduled_at || '-', false)}
        ${_detailSection('Account', item.account_display_name || item.account_key || item.account_id || '-', false)}
      </div>
      ${_detailSection('Video Path', item.video_path || '-', false)}
      ${_detailSection('Caption', item.caption || '-', false)}
      ${_detailSection('Hashtags', _uvlHashtagText(item.hashtags || []) || '-', false)}
      ${_detailSection('Last Error', item.last_error || '-', false)}
      ${_detailSection('Adapter Result', _historySummary(item.result_json || item.result || {}) || '-', false)}
    `;
  }
}

function fillUploadAccountForm(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  _selectUploadEntity('account', accountId);
  if(qs('uam_account_id')) qs('uam_account_id').value = item.account_id || '';
  if(qs('uam_platform')) qs('uam_platform').value = item.platform || 'tiktok';
  if(qs('uam_channel_code')) qs('uam_channel_code').value = item.channel_code || '';
  if(qs('uam_account_key')) qs('uam_account_key').value = item.account_key || 'default';
  if(qs('uam_display_name')) qs('uam_display_name').value = item.display_name || '';
  if(qs('uam_status')) qs('uam_status').value = item.status || 'active';
  if(qs('uam_login_state')) qs('uam_login_state').value = item.login_state || 'unknown';
  if(qs('uam_daily_limit')) qs('uam_daily_limit').value = Number(item.daily_limit || 0);
  if(qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = Number(item.cooldown_minutes || 0);
  if(qs('uam_today_count')) qs('uam_today_count').value = Number(item.today_count || 0);
  if(qs('uam_profile_path')) qs('uam_profile_path').value = item.profile_path || '';
  if(qs('uam_proxy_id')) qs('uam_proxy_id').value = item.proxy_id || '';
  if(qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Save Changes';
}

function renderUploadAccounts(items){
  const tbody = qs('upload_accounts_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="9" class="uamEmpty">No upload accounts yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const name = item.display_name || item.account_key || item.account_id;
    const usage = `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`;
    const profile = _uamShortPath(item.profile_path);
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    const lockState = item.profile_lock_state || 'idle';
    const selected = _selectedUploadId('account') === String(item.account_id || '');
    const loginDisabledTitle = disabled ? 'Account disabled' : 'Check current login state for this account';
    const disableTitle = disabled ? 'Account already disabled' : 'Soft-disable this account';
    return `
      <tr class="${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('account', '${esc(item.account_id)}')">
        <td>
          <div class="uamAccountName">${esc(name)}</div>
          <div class="uamSub">${esc(item.platform || 'tiktok')} - ${esc(item.channel_code || '-')} - ${esc(item.account_key || 'default')}</div>
          ${item.profile_conflict ? `<div class="uamWarn">Profile path conflict: ${esc(_uamConflictText(item))}</div>` : ''}
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td>${_uamBadge(item.login_state, 'login')}</td>
        <td>${_uamBadge(lockState, 'lock')}</td>
        <td>${esc(usage)}</td>
        <td>${Number(item.cooldown_minutes || 0)} min</td>
        <td title="${esc(item.profile_path || '')}">${esc(profile)}</td>
        <td>${esc(item.proxy_id || '-')}</td>
        <td>
          <div class="uamActions">
            <button class="ghostButton" type="button" title="Edit account" onclick="fillUploadAccountForm('${esc(item.account_id)}')">Edit</button>
            <button class="ghostButton" type="button" title="${esc(loginDisabledTitle)}" onclick="checkUploadAccountLogin('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Check Login</button>
            <button class="ghostButton" type="button" title="${esc(disableTitle)}" onclick="disableUploadAccount('${esc(item.account_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadAccounts(){
  const tbody = qs('upload_accounts_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="9" class="uamEmpty">Loading accounts...</td></tr>';
  try{
    const res = await fetch('/api/upload/accounts');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadAccountManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="9" class="uamEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload account load failed: ${e.message || e}`, 'upload');
  }
}

function fillUploadVideoForm(videoId){
  const item = uploadVideoLibraryItems.find((x) => x.video_id === videoId);
  if(!item) return;
  _selectUploadEntity('video', videoId);
  if(qs('uvl_video_id')) qs('uvl_video_id').value = item.video_id || '';
  if(qs('uvl_video_path')) qs('uvl_video_path').value = item.video_path || '';
  if(qs('uvl_platform')) qs('uvl_platform').value = item.platform || 'tiktok';
  if(qs('uvl_source_type')) qs('uvl_source_type').value = item.source_type || 'manual_file';
  if(qs('uvl_status')) qs('uvl_status').value = item.status || 'ready';
  if(qs('uvl_caption')) qs('uvl_caption').value = item.caption || '';
  if(qs('uvl_hashtags')) qs('uvl_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uvl_note')) qs('uvl_note').value = item.note || '';
  if(qs('uvl_cover_path')) qs('uvl_cover_path').value = item.cover_path || '';
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => {
    if(qs(id)) qs(id).disabled = true;
  });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Save Video';
}

function renderUploadVideoLibrary(items){
  const tbody = qs('upload_videos_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="8" class="uvlEmpty">No upload videos yet. Add a file to start building your library.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || '').toLowerCase();
    const disabled = status === 'disabled';
    const caption = String(item.caption || '').trim();
    const note = String(item.note || '').trim();
    const selected = _selectedUploadId('video') === String(item.video_id || '');
    const queueTitle = disabled ? 'Video disabled' : (status !== 'ready' ? `Video status is ${status}` : 'Select this video for the queue form');
    return `
      <tr class="${disabled ? 'isDisabled' : ''} ${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('video', '${esc(item.video_id)}')">
        <td>
          <div class="uvlFileName">${esc(item.file_name || item.video_path || '-')}</div>
          <div class="uvlSub" title="${esc(item.video_path || '')}">${esc(_uamShortPath(item.video_path || ''))}</div>
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td>${esc(item.platform || 'tiktok')}</td>
        <td>
          <div class="uvlClipText">${esc(caption || '-')}</div>
          ${note ? `<div class="uvlSub">${esc(note)}</div>` : ''}
        </td>
        <td><div class="uvlClipText">${esc(_uvlHashtagText(item.hashtags || []) || '-')}</div></td>
        <td>${esc(_uvlFormatDuration(item.duration_sec))}<div class="uvlSub">${esc(_uvlFormatSize(item.file_size))}</div></td>
        <td>${esc(String(item.source_type || 'manual_file').replace(/_/g, ' '))}</td>
        <td>
          <div class="uvlActions">
            <button class="ghostButton" type="button" title="Edit video metadata" onclick="fillUploadVideoForm('${esc(item.video_id)}')">Edit</button>
            <button class="ghostButton" type="button" title="${disabled ? 'Video already disabled' : 'Disable this video'}" onclick="disableUploadVideo('${esc(item.video_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
            <button class="ghostButton" type="button" title="${esc(queueTitle)}" onclick="selectVideoForQueue('${esc(item.video_id)}')" ${disabled || status !== 'ready' ? 'disabled' : ''}>Select for Queue</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadVideoLibrary(){
  const tbody = qs('upload_videos_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="8" class="uvlEmpty">Loading videos...</td></tr>';
  const params = new URLSearchParams();
  const status = _uvlValue('uvl_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/videos?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadVideoLibraryItems = Array.isArray(data.items) ? data.items : [];
    renderUploadVideoLibrary(uploadVideoLibraryItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="8" class="uvlEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload video library load failed: ${e.message || e}`, 'upload');
  }
}

function selectVideoForQueue(videoId){
  const item = uploadVideoLibraryItems.find((x) => x.video_id === videoId);
  if(!item) return;
  _selectUploadEntity('video', videoId);
  if(String(item.status || '').toLowerCase() === 'disabled'){
    showToast('Disabled video cannot be queued', 'error');
    return;
  }
  renderUploadQueueSelectors();
  if(qs('uqm_video_id')) qs('uqm_video_id').value = videoId;
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  const panel = qs('upload_queue_manager');
  if(panel) panel.scrollIntoView({behavior: 'smooth', block: 'start'});
  showToast('Video selected for queue form', 'info');
}

function fillUploadQueueForm(queueId){
  const item = uploadQueueManagerItems.find((x) => x.queue_id === queueId);
  if(!item) return;
  _selectUploadEntity('queue', queueId);
  selectedUploadQueueId = queueId;
  renderUploadQueueSelectors();
  if(qs('uqm_queue_id')) qs('uqm_queue_id').value = item.queue_id || '';
  if(qs('uqm_video_id')) qs('uqm_video_id').value = item.video_id || '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = item.account_id || '';
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  if(qs('uqm_scheduled_at')) qs('uqm_scheduled_at').value = item.scheduled_at || '';
  if(qs('uqm_priority')) qs('uqm_priority').value = Number(item.priority || 0);
  if(qs('uqm_status')) qs('uqm_status').value = ['pending', 'scheduled', 'held'].includes(String(item.status || '')) ? item.status : 'pending';
  if(qs('uqm_video_id')) qs('uqm_video_id').disabled = true;
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Save Queue Item';
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = `Queue ${queueId}`;
  loadSelectedUploadQueueHistory();
}

function renderUploadQueueManager(items){
  const tbody = qs('upload_queue_manager_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="8" class="uqmEmpty">No queue items yet. Select a video and account to create one.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || 'pending').toLowerCase();
    const muted = ['held', 'cancelled'].includes(status);
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    const clipName = item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-';
    const selected = _selectedUploadId('queue') === String(item.queue_id || '');
    const runDisabledReason =
      status === 'success' ? 'Successful items cannot run again from this table' :
      status === 'cancelled' ? 'Cancelled items cannot run' :
      status === 'uploading' ? 'Item is already uploading' :
      'Run this queue item now';
    let runButton = '';
    if(['pending', 'scheduled', 'held'].includes(status)){
      runButton = `<button class="ghostButton" type="button" title="${esc(runDisabledReason)}" onclick="runUploadQueueItem('${esc(item.queue_id)}')">Run</button>`;
    } else if(status === 'failed'){
      runButton = `<button class="ghostButton" type="button" title="Retry failed queue item" onclick="runUploadQueueItem('${esc(item.queue_id)}')">Retry</button>`;
    } else if(status === 'uploading'){
      runButton = '<button class="ghostButton" type="button" title="Item is already uploading" disabled>Uploading...</button>';
    } else if(status === 'success'){
      runButton = '<button class="ghostButton" type="button" title="Successful item cannot run again here" disabled>Success</button>';
    } else {
      runButton = `<button class="ghostButton" type="button" title="${esc(runDisabledReason)}" disabled>Run</button>`;
    }
    return `
      <tr class="${muted ? 'isMuted' : ''} ${selected ? 'isSelected' : ''}" onclick="_selectUploadEntity('queue', '${esc(item.queue_id)}')">
        <td>
          <div class="uqmClipName">${esc(clipName)}</div>
          <div class="uqmSub" title="${esc(item.video_path || '')}">${esc(_uamShortPath(item.video_path || ''))}</div>
        </td>
        <td>${esc(accountName)}</td>
        <td>${_uamBadge(status, 'status')}</td>
        <td>${esc(item.platform || 'tiktok')}</td>
        <td>${esc(item.scheduled_at || '-')}</td>
        <td>${Number(item.priority || 0)}</td>
        <td>${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}</td>
        <td>
          ${item.last_error ? `<div class="uqmError">${esc(item.last_error)}</div>` : ''}
          <div class="uqmActions">
            ${runButton}
            <button class="ghostButton" type="button" title="${['cancelled', 'uploading', 'success'].includes(status) ? 'This queue item is not editable in its current state' : 'Edit queue item'}" onclick="fillUploadQueueForm('${esc(item.queue_id)}')" ${['cancelled', 'uploading', 'success'].includes(status) ? 'disabled' : ''}>Edit</button>
            <button class="ghostButton" type="button" title="${!['pending', 'scheduled', 'failed'].includes(status) ? 'Only pending, scheduled, or failed items can be held' : 'Hold this queue item'}" onclick="holdUploadQueueItem('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'failed'].includes(status) ? 'disabled' : ''}>Hold</button>
            <button class="ghostButton" type="button" title="${status !== 'held' ? 'Only held items can be resumed' : 'Resume this queue item'}" onclick="resumeUploadQueueItem('${esc(item.queue_id)}')" ${status !== 'held' ? 'disabled' : ''}>Resume</button>
            <button class="ghostButton" type="button" title="${!['pending', 'scheduled', 'held', 'failed'].includes(status) ? 'Only pending, scheduled, held, or failed items can be cancelled' : 'Cancel this queue item'}" onclick="cancelUploadQueueItemUi('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'held', 'failed'].includes(status) ? 'disabled' : ''}>Cancel</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadUploadQueueManager(){
  const tbody = qs('upload_queue_manager_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="8" class="uqmEmpty">Loading queue...</td></tr>';
  const params = new URLSearchParams();
  const status = _uqmValue('uqm_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/queue?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadQueueManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadQueueManager(uploadQueueManagerItems);
    renderUploadInspector();
    if(selectedUploadQueueId) loadSelectedUploadQueueHistory();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="8" class="uqmEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload queue load failed: ${e.message || e}`, 'upload');
  }
}

function renderUploadQueueHistory(items){
  currentUploadQueueHistoryItems = Array.isArray(items) ? items : [];
  const list = qs('upload_queue_history_list');
  if(!list) return;
  if(!selectedUploadQueueId){
    list.innerHTML = '<div class="uqmEmpty">No queue item selected.</div>';
    return;
  }
  if(!items || !items.length){
    list.innerHTML = '<div class="uqmEmpty">No attempts recorded for this queue item.</div>';
    return;
  }
  list.innerHTML = items.map((item) => `
    <div class="uqmHistoryItem ${String(item.status || '').toLowerCase()}">
      <div class="uqmHistoryTop">
        ${_uamBadge(item.status || 'failed', 'status')}
        <span>Attempt ${Number(item.attempt_no || 0)}</span>
        <span>${esc(item.started_at || '-')}</span>
        <span>${esc(item.finished_at || '-')}</span>
        <span>${Number(item.duration_seconds || 0).toFixed(1)}s</span>
      </div>
      ${item.error ? `<div class="uqmHistoryError">${esc(item.error)}</div>` : ''}
      ${_historySummary(item.adapter_result) ? `<div class="uqmSub">${esc(_historySummary(item.adapter_result))}</div>` : ''}
    </div>
  `).join('');
}

async function loadUploadQueueHistory(queueId){
  if(!queueId) return;
  selectedUploadQueueId = queueId;
  const list = qs('upload_queue_history_list');
  if(list) list.innerHTML = '<div class="uqmEmpty">Loading history...</div>';
  try{
    const res = await fetch(`/api/upload/queue/${encodeURIComponent(queueId)}/history`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    renderUploadQueueHistory(Array.isArray(data.items) ? data.items : []);
    renderUploadInspector();
  }catch(e){
    if(list) list.innerHTML = `<div class="uqmEmpty">History load failed: ${esc(e.message || e)}</div>`;
  }
}
