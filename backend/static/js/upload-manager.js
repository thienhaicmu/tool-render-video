let uploadAccountManagerItems = [];

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
  if(typeof window.setView === 'function' && !window._uploadAccountManagerSetViewWrapped){
    const originalSetView = window.setView;
    window.setView = function(view){
      const result = originalSetView.apply(this, arguments);
      if(view === 'upload') loadUploadAccounts();
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
    tbody.innerHTML = '<tr><td colspan="8" class="uamEmpty">No upload accounts yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const name = item.display_name || item.account_key || item.account_id;
    const usage = `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`;
    const profile = _uamShortPath(item.profile_path);
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    return `
      <tr>
        <td>
          <div class="uamAccountName">${esc(name)}</div>
          <div class="uamSub">${esc(item.platform || 'tiktok')} · ${esc(item.channel_code || '-')} · ${esc(item.account_key || 'default')}</div>
        </td>
        <td>${_uamBadge(item.status, 'status')}</td>
        <td>${_uamBadge(item.login_state, 'login')}</td>
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
  if(tbody) tbody.innerHTML = '<tr><td colspan="8" class="uamEmpty">Loading accounts...</td></tr>';
  try{
    const res = await fetch('/api/upload/accounts');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadAccountManagerItems = Array.isArray(data.items) ? data.items : [];
    renderUploadAccounts(uploadAccountManagerItems);
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="8" class="uamEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
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
  if(!item.channel_code){
    showToast('Channel code is required for login check', 'error');
    return;
  }
  try{
    const res = await fetch('/api/upload/login/check', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        channel_code: item.channel_code,
        account_key: item.account_key || 'default',
        config_mode: 'mixed',
        user_data_dir: item.profile_path || '',
      }),
    });
    const data = await res.json();
    const loginState = res.ok && data.logged_in ? 'logged_in' : 'logged_out';
    const status = loginState === 'logged_in' ? item.status : 'login_required';
    await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        login_state: loginState,
        status,
        last_login_check_at: new Date().toISOString(),
        health_json: data || {},
      }),
    });
    await loadUploadAccounts();
    showToast(loginState === 'logged_in' ? 'Login is valid' : 'Login required', loginState === 'logged_in' ? 'success' : 'info');
  }catch(e){
    try{
      await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}`, {
        method: 'PATCH',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          login_state: 'unknown',
          last_login_check_at: new Date().toISOString(),
          health_json: {error: String(e.message || e)},
        }),
      });
      await loadUploadAccounts();
    }catch(_){}
    showToast(`Login check failed: ${e.message || e}`, 'error');
  }
}
