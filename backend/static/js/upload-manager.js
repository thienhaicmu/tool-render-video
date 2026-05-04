// =============================================================================
// UPLOAD ACCOUNT MANAGER — Phase 0 consolidation: one definition per function.
// =============================================================================

// --- GLOBALS ---
let uploadAccountManagerItems = [];
let uploadVideoLibraryItems = [];
let uploadQueueManagerItems = [];
let selectedUploadQueueId = '';
let selectedUploadEntity = {type: '', id: ''};
let currentUploadQueueHistoryItems = [];
let currentUploadWorkflowStep = 1;
let __uploadRefreshing = false;
let _cachedSchedulerData = null;
let selectedUploadVideoIds = new Set();
let _batchModalStep = 'configure';
let _batchPreviewData = null;
let _batchSelectedAccountIds = new Set();
let _batchMode = 'smart';
let _batchSpaceMinutes = 30;

// --- HEALTH LAYER GLOBALS ---
let _uploadAccountHealthFilter = 'all';
let _batchIncludeRisky = false;
const _proxyTestCache = {};

// --- PHASE 5: FAILURE TIER CLASSIFICATION ---
const _QUEUE_TIER_MAP = {
  'cooldown':           'wait',
  'daily limit':        'wait',
  'login required':     'action',
  'attempts exhausted': 'fatal',
};
const _RETRY_BACKOFF_MINUTES = [5, 15, 45];

// --- UPLOAD STORE ---
const UploadStore = {
  _accounts: [],
  _queueItems: [],
  _listeners: [],
  selectedAccountId: '',
  selectedQueueItemId: '',
  setAccounts(items) {
    this._accounts = Array.isArray(items) ? items : [];
    this._notify('accounts');
  },
  setQueueItems(items) {
    this._queueItems = Array.isArray(items) ? items : [];
    this._notify('queueItems');
  },
  setSelectedAccountId(id) { this.selectedAccountId = String(id || ''); },
  setSelectedQueueItemId(id) { this.selectedQueueItemId = String(id || ''); },
  getAccounts() { return this._accounts; },
  getQueueItems() { return this._queueItems; },
  subscribe(fn) { this._listeners.push(fn); },
  _notify(key) { this._listeners.forEach(fn => fn(key)); },
};

UploadStore.subscribe(function(key){
  if(__uploadRefreshing) return;
  try{
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueManager(uploadQueueManagerItems);
    _renderAccountWorkspaceSummary();
    renderUploadSchedulerStatus(_cachedSchedulerData);
  }catch(err){
    console.warn('[UploadStore] render failed', err);
  }
});

// --- INDEPENDENCE GUARD ---
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

// --- INIT ---
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

// =============================================================================
// UTILITY HELPERS
// =============================================================================

function _uamValue(id){ return String(qs(id)?.value || '').trim(); }
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

function _uvlValue(id){ return String(qs(id)?.value || '').trim(); }
function _uvlParseHashtags(raw){
  return String(raw || '').split(',').map((x) => x.trim().replace(/^#+/, '')).filter(Boolean);
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

function _uqmValue(id){ return String(qs(id)?.value || '').trim(); }

function _prettyJson(value){
  if(value == null) return '';
  if(typeof value === 'string'){
    const text = value.trim();
    if(!text) return '';
    try{ return JSON.stringify(JSON.parse(text), null, 2); }catch(_err){ return text; }
  }
  try{ return JSON.stringify(value, null, 2); }catch(_err){ return String(value); }
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
function _rowMoreMenu(label, actionsHtml){
  return `
    <details class="rowActionMenu" onclick="event.stopPropagation()">
      <summary>${esc(label || 'More')}</summary>
      <div class="rowActionMenuBody">${actionsHtml}</div>
    </details>
  `;
}
function _historySummary(result){
  if(!result || typeof result !== 'object') return '';
  if(result.detail && typeof result.detail === 'object'){
    return result.detail.upload_message || result.detail.upload_state || JSON.stringify(result.detail).slice(0, 140);
  }
  return result.uploaded_at || result.adapter || '';
}

// =============================================================================
// ACCOUNT HEALTH MODEL
// =============================================================================

function _computeAccountHealth(account){
  if(!account) return {status: 'unknown', login_state: 'unknown', proxy_status: 'none', last_upload_result: null, fail_count_24h: 0, reasons: []};
  const loginState = String(account.login_state || 'unknown').toLowerCase();
  const accountStatus = String(account.status || 'active').toLowerCase();
  const proxyId = String(account.proxy_id || '').trim();
  const cached = _proxyTestCache[String(account.account_id || '')];
  const proxyStatus = cached ? (cached.ok ? 'ok' : 'failed') : (proxyId ? 'untested' : 'none');
  let loginHealth = 'ok';
  if(['logged_out', 'expired', 'challenge'].includes(loginState)) loginHealth = loginState;
  else if(loginState === 'unknown') loginHealth = 'unknown';
  const queueItems = uploadQueueManagerItems.filter((q) => String(q.account_id || '') === String(account.account_id || ''));
  const failCount = queueItems.filter((q) => String(q.status || '').toLowerCase() === 'failed').length;
  const hasSuccess = queueItems.some((q) => String(q.status || '').toLowerCase() === 'success');
  const hasFail = failCount > 0;
  let status = 'healthy';
  const reasons = [];
  if(['disabled', 'banned'].includes(accountStatus)){
    status = 'risky'; reasons.push('Account disabled');
  } else if(['logged_out', 'expired', 'challenge'].includes(loginState)){
    status = 'risky'; reasons.push(`Login: ${loginState.replace(/_/g, ' ')}`);
  } else if(cached && !cached.ok){
    status = 'risky'; reasons.push('Proxy failed');
  } else if(failCount >= 3){
    status = 'risky'; reasons.push(`${failCount} recent failures`);
  } else if(loginState === 'unknown'){
    status = 'warning'; reasons.push('Login unknown');
  } else if(proxyId && proxyStatus === 'untested'){
    status = 'warning'; reasons.push('Proxy untested');
  } else if(hasFail){
    status = 'warning'; reasons.push(`${failCount} recent failure(s)`);
  }
  return {status, login_state: loginHealth, proxy_status: proxyStatus, last_upload_result: hasFail ? 'fail' : (hasSuccess ? 'success' : null), last_upload_at: account.last_upload_at || null, fail_count_24h: failCount, reasons};
}

function _healthBadgeHtml(health){
  const icons = {healthy: '🟢', warning: '🟡', risky: '🔴'};
  const labels = {healthy: 'Healthy', warning: 'Warning', risky: 'Risky'};
  const s = health.status || 'unknown';
  const tooltip = health.reasons && health.reasons.length ? health.reasons.join(', ') : (labels[s] || s);
  return `<span class="uamHealthBadge" data-health="${esc(s)}" title="${esc(tooltip)}">${icons[s] || '⬜'} ${esc(labels[s] || s)}</span>`;
}

function _healthRowHtml(label, value, state){
  return `<div class="uploadHealthRow"><span class="uploadHealthRowLabel">${esc(label)}</span><span class="uploadHealthRowValue" data-state="${esc(state)}">${esc(String(value))}</span></div>`;
}

function _inspectorHealthPanelHtml(account){
  const h = _computeAccountHealth(account);
  const loginLabels = {ok: 'OK', logged_out: 'Logged Out', expired: 'Session Expired', challenge: 'Captcha Required', unknown: 'Unknown'};
  const loginLabel = loginLabels[h.login_state] || h.login_state;
  const loginState = ['logged_out', 'expired', 'challenge'].includes(h.login_state) ? 'risky' : (h.login_state === 'ok' ? 'ok' : 'warning');
  const proxyLabels = {ok: 'OK', failed: 'Failed', untested: 'Untested', none: 'None (no proxy)'};
  const proxyLabel = proxyLabels[h.proxy_status] || h.proxy_status;
  const proxyState = h.proxy_status === 'ok' ? 'ok' : (h.proxy_status === 'failed' ? 'risky' : 'warning');
  const lastLabel = h.last_upload_result === 'success' ? 'Success' : (h.last_upload_result === 'fail' ? 'Failed' : 'No data');
  const lastState = h.last_upload_result === 'success' ? 'ok' : (h.last_upload_result === 'fail' ? 'risky' : 'unknown');
  const failState = h.fail_count_24h >= 3 ? 'risky' : (h.fail_count_24h > 0 ? 'warning' : 'ok');
  const cached = _proxyTestCache[String(account.account_id || '')];
  const proxyResultHtml = cached
    ? `<div class="uploadProxyTestResult" data-ok="${cached.ok}">${cached.ok ? `OK · ${Number(cached.latency || 0)}ms` : `Failed: ${esc(String(cached.error || 'error'))}`}</div>` : '';
  const id = esc(String(account.account_id || ''));
  return `
    <div class="uploadHealthPanel">
      <div class="uploadHealthPanelTitle">Account Health</div>
      ${_healthRowHtml('Login', loginLabel, loginState)}
      ${_healthRowHtml('Proxy', proxyLabel, proxyState)}
      <div class="uploadHealthRow">
        <span class="uploadHealthRowLabel">Proxy Test</span>
        <button class="ghostButton" style="font-size:11px;padding:2px 8px;min-height:0" type="button"
          onclick="testUploadAccountProxy('${id}')">Test Proxy</button>
      </div>
      ${proxyResultHtml}
      ${_healthRowHtml('Last Upload', lastLabel, lastState)}
      ${_healthRowHtml('Failures (24h)', String(h.fail_count_24h), failState)}
      ${h.status === 'risky' ? '<div class="uploadHealthWarning">⚠ This account may fail uploads</div>' : ''}
    </div>
  `;
}

function setUploadAccountHealthFilter(filter){
  _uploadAccountHealthFilter = filter || 'all';
  document.querySelectorAll('.uamHealthFilterBtn').forEach((btn) => {
    btn.classList.toggle('active', (btn.dataset.filter || '') === _uploadAccountHealthFilter);
  });
  renderUploadAccounts(uploadAccountManagerItems);
}

async function testUploadAccountProxy(accountId){
  showToast('Testing proxy…', 'info');
  try{
    const res = await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}/test-proxy`, {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail || data.message));
    _proxyTestCache[accountId] = {ok: !!data.ok, latency: Number(data.latency || 0), error: data.error || '', tested_at: Date.now()};
    showToast(data.ok ? `Proxy OK · ${Number(data.latency || 0)}ms` : `Proxy failed: ${data.error || 'timeout'}`, data.ok ? 'success' : 'error');
  }catch(e){
    _proxyTestCache[accountId] = {ok: false, latency: 0, error: e.message || String(e), tested_at: Date.now()};
    showToast(`Proxy test: ${e.message || e}`, 'info');
  }
  renderUploadInspector();
  renderUploadAccounts(uploadAccountManagerItems);
}

// =============================================================================
// ACCOUNT WORKSPACE STATE + HELPERS
// =============================================================================

let selectedUploadAccountWorkspaceId = '';
let currentSelectedAccountHistoryItems = [];

function _accountWorkspaceSelectedId(){
  if(selectedUploadAccountWorkspaceId) return selectedUploadAccountWorkspaceId;
  if(selectedUploadEntity.type === 'account') return selectedUploadEntity.id;
  if(selectedUploadEntity.type === 'queue'){
    const row = uploadQueueManagerItems.find((item) => String(item.queue_id || '') === String(selectedUploadEntity.id || ''));
    return row ? String(row.account_id || '') : '';
  }
  return _uqmValue('uqm_account_id') || '';
}
function _selectedAccountWorkspaceItem(){
  const accountId = _accountWorkspaceSelectedId();
  return uploadAccountManagerItems.find((item) => String(item.account_id || '') === accountId) || null;
}
function _accountWorkspaceQueueItems(accountId){
  return uploadQueueManagerItems.filter((item) => String(item.account_id || '') === String(accountId || ''));
}
function _accountWorkspaceActivity(accountId){
  const items = _accountWorkspaceQueueItems(accountId);
  const uploading = items.find((item) => String(item.status || '').toLowerCase() === 'uploading');
  if(uploading){
    return {
      state: 'running', label: 'Uploading',
      currentVideo: uploading.video_file_name || String(uploading.video_path || '').split(/[\\/]/).pop() || 'Current upload',
      lastError: uploading.last_error || '',
      current: uploading.video_file_name || String(uploading.video_path || '').split(/[\\/]/).pop() || '',
      attempt: `${Number(uploading.attempt_count || 0)} / ${Number(uploading.max_attempts || 3)}`,
      error: uploading.last_error || '',
    };
  }
  const busy = items.find((item) => String(item.blocked_reason || '') === 'profile busy');
  if(busy) return {state: 'busy', label: 'Busy', currentVideo: '', lastError: busy.blocked_reason || '', current: '', error: busy.blocked_reason || ''};
  const cooldown = items.find((item) => String(item.blocked_reason || '') === 'cooldown');
  if(cooldown) return {state: 'cooldown', label: 'Cooldown', currentVideo: '', lastError: cooldown.blocked_reason || '', current: '', error: cooldown.blocked_reason || ''};
  const failed = items.find((item) => String(item.status || '').toLowerCase() === 'failed');
  if(failed) return {state: 'error', label: 'Error', currentVideo: '', lastError: failed.last_error || '', current: failed.video_file_name || '', error: failed.last_error || ''};
  return {state: 'idle', label: 'Idle', currentVideo: '', lastError: '', current: '', error: ''};
}
function _accountWorkspaceCounts(accountId){
  return _accountWorkspaceQueueItems(accountId).reduce((acc, item) => {
    const status = String(item.status || 'pending').toLowerCase();
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {pending: 0, scheduled: 0, uploading: 0, success: 0, failed: 0, held: 0, cancelled: 0});
}
function _findRunnableAccountQueueItem(accountId){
  return _accountWorkspaceQueueItems(accountId).find((item) => {
    const status = String(item.status || '').toLowerCase();
    if(!['pending', 'scheduled', 'held', 'failed'].includes(status)) return false;
    return !String(item.blocked_reason || '').trim();
  }) || null;
}
function _accountWorkspaceHint(account){
  if(!account) return 'Select an account to manage its upload flow.';
  const queueItems = _accountWorkspaceQueueItems(account.account_id);
  if(!queueItems.length) return 'This account is ready. Add a video to this account to create its next upload.';
  const activity = _accountWorkspaceActivity(account.account_id);
  if(activity.state === 'running') return `This account is uploading ${activity.currentVideo}.`;
  if(activity.state === 'error') return 'This account has a recent upload error. Review the failed item or retry.';
  return 'This account is ready for its next upload.';
}

// =============================================================================
// STUDIO HELPERS (account workspace context bridge)
// =============================================================================

function _studioSelectedAccount(){
  const id = _accountWorkspaceSelectedId();
  return uploadAccountManagerItems.find((item) => String(item.account_id || '') === String(id || '')) || null;
}
function _studioAccountQueues(accountId){
  return uploadQueueManagerItems.filter((item) => String(item.account_id || '') === String(accountId || ''));
}
function _studioRunReason(account){
  if(!account) return 'Select an account first';
  const status = String(account.status || '').toLowerCase();
  const loginState = String(account.login_state || '').toLowerCase();
  const queues = _studioAccountQueues(account.account_id);
  if(status === 'disabled' || status === 'banned') return 'Account disabled';
  if(['logged_out', 'challenge', 'expired'].includes(loginState)) return 'Account not logged in';
  if(queues.some((item) => String(item.blocked_reason || '') === 'daily limit')) return 'Daily limit reached';
  if(queues.some((item) => String(item.blocked_reason || '') === 'cooldown')) return 'Cooldown active';
  if(queues.some((item) => String(item.blocked_reason || '') === 'profile busy')) return 'Profile busy';
  if(!queues.length) return 'No videos assigned';
  return 'No eligible upload item for this account';
}
function _studioNextRunnable(account){
  if(!account) return null;
  return _studioAccountQueues(account.account_id).find((item) => {
    const status = String(item.status || '').toLowerCase();
    return ['pending', 'scheduled', 'held', 'failed'].includes(status) && !String(item.blocked_reason || '').trim();
  }) || null;
}
function _studioActivity(account){
  if(!account) return {label: 'Idle', error: '', current: ''};
  const queues = _studioAccountQueues(account.account_id);
  const uploading = queues.find((item) => String(item.status || '').toLowerCase() === 'uploading');
  if(uploading){
    return {
      label: 'Uploading', error: uploading.last_error || '',
      current: uploading.video_file_name || String(uploading.video_path || '').split(/[\\/]/).pop() || '',
      attempt: `${Number(uploading.attempt_count || 0)} / ${Number(uploading.max_attempts || 3)}`,
    };
  }
  const busy = queues.find((item) => String(item.blocked_reason || '') === 'profile busy');
  if(busy) return {label: 'Busy', error: busy.blocked_reason || '', current: ''};
  const cooldown = queues.find((item) => String(item.blocked_reason || '') === 'cooldown');
  if(cooldown) return {label: 'Cooldown', error: cooldown.blocked_reason || '', current: ''};
  const failed = queues.find((item) => String(item.status || '').toLowerCase() === 'failed');
  if(failed) return {label: 'Error', error: failed.last_error || '', current: failed.video_file_name || ''};
  return {label: 'Idle', error: '', current: ''};
}
function _studioAccountMetaLine(item){
  const platform = item.platform || 'TikTok';
  const login = String(item.login_state || 'unknown').replace(/_/g, ' ');
  const activity = (_studioActivity(item) || {}).label || 'Idle';
  return `${platform} · ${login} · ${activity}`;
}
function _defaultAccountTab(account){
  if(!account) return 'videos';
  const hasActionable = uploadQueueManagerItems.some((item) =>
    String(item.account_id || '') === String(account.account_id || '') &&
    ['pending', 'scheduled', 'uploading', 'failed'].includes(String(item.status || '').toLowerCase())
  );
  return hasActionable ? 'queue' : 'videos';
}
function _disabledRunReasonForAccount(account){
  if(!account) return 'Select an account first';
  const status = String(account.status || '').toLowerCase();
  const loginState = String(account.login_state || '').toLowerCase();
  const items = _accountWorkspaceQueueItems(account.account_id);
  if(status === 'disabled' || status === 'banned') return 'Account disabled';
  if(['logged_out', 'challenge', 'expired'].includes(loginState)) return 'Account not logged in';
  if(items.some((item) => String(item.blocked_reason || '') === 'profile busy')) return 'Profile busy';
  if(items.some((item) => String(item.blocked_reason || '') === 'daily limit')) return 'Daily limit reached';
  if(items.some((item) => String(item.blocked_reason || '') === 'cooldown')) return 'Cooldown active';
  if(!items.length) return 'No videos assigned';
  return 'No eligible upload item for this account';
}

// =============================================================================
// UI STATE + TAB MANAGEMENT
// =============================================================================

let uploadManagerActiveTab = 'videos';

function _setEditorOpen(id, open){
  const el = qs(id);
  if(el && typeof open === 'boolean') el.open = open;
}

function openUploadAccountModal(){
  const modal = document.getElementById('upload_account_form_modal');
  if(modal) modal.hidden = false;
}

function closeUploadAccountModal(){
  const modal = document.getElementById('upload_account_form_modal');
  if(modal) modal.hidden = true;
}

function closeUploadAccountEditor(){
  closeUploadAccountModal();
}

function openUploadEditor(type){
  if(type === 'account'){
    resetUploadAccountForm();
    openUploadAccountModal();
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
  uploadManagerActiveTab = ['videos', 'queue', 'settings', 'automation'].includes(tab) ? tab : 'videos';
  document.querySelectorAll('.uploadManagerTab').forEach((btn) => {
    btn.classList.toggle('active', btn.id === `upload_tab_${uploadManagerActiveTab}`);
  });
  document.querySelectorAll('.uploadManagerTabPanel').forEach((panel) => {
    panel.classList.toggle('active', panel.getAttribute('data-tab-panel') === uploadManagerActiveTab);
  });
}

// =============================================================================
// RENDER: ACCOUNT LIST (card layout — no table)
// =============================================================================

function renderUploadAccounts(items){
  const list = qs('upload_accounts_list') || qs('upload_accounts_tbody');
  const workspace = document.getElementById('upload_manager_workspace');
  if(workspace) workspace.dataset.uploadState = (items && items.length) ? 'has-accounts' : 'no-accounts';
  if(!list) return;
  if(!items || !items.length){
    list.innerHTML = '';
    return;
  }
  // Apply health filter
  const filtered = _uploadAccountHealthFilter === 'all'
    ? items
    : items.filter((item) => _computeAccountHealth(item).status === _uploadAccountHealthFilter);
  if(!filtered.length){
    list.innerHTML = `<div class="uamEmpty">No ${esc(_uploadAccountHealthFilter)} accounts.</div>`;
    return;
  }
  list.innerHTML = filtered.map((item) => {
    const health = _computeAccountHealth(item);
    const name = item.display_name || item.account_key || item.account_id;
    const disabled = String(item.status || '').toLowerCase() === 'disabled';
    const selected = _accountWorkspaceSelectedId() === String(item.account_id || '');
    const loginState = String(item.login_state || 'unknown').replace(/_/g, ' ');
    const metaLine = `${esc(item.platform || 'tiktok')} · ${esc(loginState)}`;
    const usageLine = `Today ${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '–'}`;
    const cooldownLine = `Cooldown ${Number(item.cooldown_minutes || 0)}m`;
    const loginDisabledTitle = disabled ? 'Account disabled' : 'Check current login state for this account';
    const disableTitle = disabled ? 'Account already disabled' : 'Soft-disable this account';
    return `
      <div class="uamAccountItem${selected ? ' isSelected' : ''}${disabled ? ' isDisabled' : ''}"
           data-health="${esc(health.status)}"
           onclick="_selectUploadEntity('account', '${esc(item.account_id)}')">
        <div class="uamAccountItemTop">
          <div class="uamAccountItemName" title="${esc(name)}">${esc(name)}</div>
          <div class="uamAccountItemBadges">
            ${_healthBadgeHtml(health)}
            ${_uamBadge(item.status, 'status')}
            ${_uamBadge(item.login_state, 'login')}
          </div>
        </div>
        <div class="uamAccountItemMeta">${metaLine}</div>
        <div class="uamAccountItemUsage">${esc(usageLine)} · ${esc(cooldownLine)}</div>
        ${item.profile_conflict ? `<div class="uamAccountItemWarn">${esc(_uamConflictText(item))}</div>` : ''}
        <div class="uamAccountItemActions">
          <button class="ghostButton" type="button" title="${esc(loginDisabledTitle)}"
                  onclick="event.stopPropagation(); checkUploadAccountLogin('${esc(item.account_id)}')"
                  ${disabled ? 'disabled' : ''}>Check</button>
          <button class="ghostButton" type="button" title="Edit account"
                  onclick="event.stopPropagation(); fillUploadAccountForm('${esc(item.account_id)}')">Edit</button>
          <button class="ghostButton" type="button" title="${esc(disableTitle)}"
                  onclick="event.stopPropagation(); disableUploadAccount('${esc(item.account_id)}')"
                  ${disabled ? 'disabled' : ''}>Disable</button>
        </div>
      </div>
    `;
  }).join('');
}

// =============================================================================
// RENDER: VIDEO LIBRARY (5 visible columns: Video / Status / Caption / Tags / Actions)
// =============================================================================

function renderUploadVideoLibrary(items){
  const tbody = qs('upload_videos_tbody');
  const panel = document.getElementById('upload_video_library');
  if(!tbody) return;
  const isEmpty = !items || !items.length;
  if(panel) panel.dataset.uploadVideos = isEmpty ? 'empty' : 'loaded';
  if(isEmpty){
    tbody.innerHTML = `
      <tr><td colspan="6">
        <div class="uamEmptyState">
          <h3>No videos yet</h3>
          <p>Add videos to start building your upload queue</p>
          <button class="primaryButton" type="button" onclick="openUploadEditor('video')">Add Video</button>
        </div>
      </td></tr>
    `;
    _updateBatchAssignButton();
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || '').toLowerCase();
    const disabled = status === 'disabled';
    const caption = String(item.caption || '').trim();
    const selected = _selectedUploadId('video') === String(item.video_id || '');
    const isBatchSelectable = status === 'ready' && !!item.video_path;
    const isBatchSelected = selectedUploadVideoIds.has(String(item.video_id || ''));
    const queueTitle = disabled ? 'Video disabled' : (status !== 'ready' ? `Video status is ${status}` : 'Select this video for the queue form');
    const chkTitle = isBatchSelectable ? 'Select for batch assign' : (disabled ? 'Video disabled' : (!item.video_path ? 'No video path' : `Status: ${status}`));
    const rowCls = [disabled ? 'isDisabled' : '', selected ? 'isSelected' : ''].filter(Boolean).join(' ');
    return `
      <tr class="${rowCls}" onclick="_selectUploadEntity('video', '${esc(item.video_id)}')">
        <td class="uvlColCheck" onclick="event.stopPropagation()">
          <input type="checkbox" class="uvlSelectChk"
            ${isBatchSelectable ? '' : 'disabled'}
            ${isBatchSelected ? 'checked' : ''}
            title="${esc(chkTitle)}"
            onchange="toggleUploadVideoSelection('${esc(item.video_id)}', this.checked)">
        </td>
        <td class="uvlColVideo">
          <div class="uvlFileName">${esc(item.file_name || item.video_path || '-')}</div>
          <div class="uvlSub" title="${esc(item.video_path || '')}">${esc(_uamShortPath(item.video_path || ''))}</div>
        </td>
        <td class="uvlColStatus">${_uamBadge(item.status, 'status')}</td>
        <td class="uvlColCaption"><div class="uvlClipText">${esc(caption || '–')}</div></td>
        <td class="uvlColTags"><div class="uvlClipText">${esc(_uvlHashtagText(item.hashtags || []) || '–')}</div></td>
        <td class="uvlColActions">
          <div class="uvlActions">
            <button class="ghostButton" type="button" title="${esc(queueTitle)}" onclick="event.stopPropagation(); selectVideoForQueue('${esc(item.video_id)}')" ${disabled || status !== 'ready' ? 'disabled' : ''}>Queue</button>
            <button class="ghostButton" type="button" title="Edit video metadata" onclick="event.stopPropagation(); fillUploadVideoForm('${esc(item.video_id)}')">Edit</button>
            <button class="ghostButton" type="button" title="${disabled ? 'Video already disabled' : 'Disable this video'}" onclick="event.stopPropagation(); disableUploadVideo('${esc(item.video_id)}')" ${disabled ? 'disabled' : ''}>Disable</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
  _updateBatchAssignButton();
  _syncSelectAllCheckbox();
}

// =============================================================================
// PHASE 5: FAILURE TIER HELPERS
// =============================================================================

function classifyQueueBlockReason(reason, status){
  if(!reason) return status === 'failed' ? 'wait' : null;
  const key = String(reason).toLowerCase().trim();
  return _QUEUE_TIER_MAP[key] || 'wait';
}

function _computeNextRetryAt(item){
  const attempt = Number(item.attempt_count || 0);
  const maxAttempts = Number(item.max_attempts || 3);
  if(attempt >= maxAttempts) return null;
  const delayMin = _RETRY_BACKOFF_MINUTES[Math.min(attempt, _RETRY_BACKOFF_MINUTES.length - 1)];
  const updatedAt = item.updated_at ? new Date(item.updated_at) : null;
  if(!updatedAt || isNaN(updatedAt.getTime())) return null;
  return new Date(updatedAt.getTime() + delayMin * 60 * 1000);
}

function _formatRetryIn(item){
  const nextAt = _computeNextRetryAt(item);
  if(!nextAt) return '';
  const diffMs = nextAt - Date.now();
  if(diffMs <= 0) return 'retry eligible';
  const diffMin = Math.ceil(diffMs / 60000);
  if(diffMin < 60) return `retry in ~${diffMin}m`;
  return `retry in ~${Math.ceil(diffMin / 60)}h`;
}

function _tierBadgeHtml(tier, label){
  if(!tier) return '';
  return `<span class="uqmTierBadge" data-tier="${esc(tier)}">${esc(label || tier)}</span>`;
}

// =============================================================================
// RENDER: QUEUE MANAGER (6 visible columns: Video / Account / Status / Scheduled / Attempts / Actions)
// Phase 0: global queue view; account-filtered view is Phase 1.
// =============================================================================

function renderUploadQueueManager(items){
  const tbody = qs('upload_queue_manager_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = `
      <tr><td colspan="6">
        <div class="uamEmptyState">
          <h3>No uploads yet</h3>
          <p>Assign videos to create your upload queue</p>
        </div>
      </td></tr>
    `;
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || 'pending').toLowerCase();
    const muted = ['held', 'cancelled'].includes(status);
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    const clipName = item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-';
    const selected = _selectedUploadId('queue') === String(item.queue_id || '');

    // Phase 5: failure tier + blocked reason
    const blockedReason = String(item.blocked_reason || '').trim();
    const tier = classifyQueueBlockReason(blockedReason || (status === 'failed' ? item.last_error : ''), status);
    const isFatal = status === 'failed' && tier === 'fatal';
    const retryIn = status === 'failed' ? _formatRetryIn(item) : '';

    const rowCls = [
      muted ? 'isMuted' : '',
      selected ? 'isSelected' : '',
      status === 'uploading' ? 'isRunning' : '',
      status === 'failed' ? 'isFailed' : '',
      status === 'success' ? 'isSuccess' : '',
    ].filter(Boolean).join(' ');
    const runDisabledReason =
      status === 'success' ? 'Successful items cannot run again' :
      status === 'cancelled' ? 'Cancelled items cannot run' :
      status === 'uploading' ? 'Item is already uploading' :
      'Run this queue item now';
    let runButton = '';
    if(['pending', 'scheduled', 'held'].includes(status)){
      runButton = `<button class="ghostButton" type="button" title="${esc(runDisabledReason)}" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Run</button>`;
    } else if(status === 'failed'){
      if(isFatal){
        runButton = `<button class="ghostButton" type="button" disabled title="Attempts exhausted — cannot retry">Retry</button>`;
      } else {
        runButton = `<button class="ghostButton" type="button" title="Retry failed queue item" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Retry</button>`;
      }
    } else if(status === 'uploading'){
      runButton = '<button class="ghostButton" type="button" disabled>Uploading…</button>';
    } else if(status === 'success'){
      runButton = '<button class="ghostButton" type="button" disabled>Done</button>';
    } else {
      runButton = `<button class="ghostButton" type="button" title="${esc(runDisabledReason)}" disabled>Run</button>`;
    }

    // blocked_reason sub-line (show on pending/scheduled/failed when blocked)
    const showBlockedLine = blockedReason && ['pending', 'scheduled', 'failed'].includes(status);
    const tierBadge = (status === 'failed' && tier) ? _tierBadgeHtml(tier, tier === 'wait' ? 'wait' : tier === 'action' ? 'action req.' : 'fatal') : '';

    return `
      <tr class="${rowCls}" onclick="_selectUploadEntity('queue', '${esc(item.queue_id)}')">
        <td class="uqmColVideo">
          <div class="uqmClipName">${esc(clipName)}</div>
          ${item.last_error ? `<div class="uqmError">${esc(item.last_error)}</div>` : ''}
          ${showBlockedLine ? `<div class="uqmBlockedReason">${esc(blockedReason)}</div>` : ''}
          ${retryIn ? `<div class="uqmRetryIn">${esc(retryIn)}</div>` : ''}
        </td>
        <td class="uqmColAccount">${esc(accountName)}</td>
        <td class="uqmColStatus">${_uamBadge(status, 'status')}${tierBadge}</td>
        <td class="uqmColScheduled">${esc(item.scheduled_at || '–')}</td>
        <td class="uqmColAttempts">${Number(item.attempt_count || 0)} / ${Number(item.max_attempts || 3)}</td>
        <td class="uqmColActions">
          <div class="uqmActions">
            ${runButton}
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); fillUploadQueueForm('${esc(item.queue_id)}')" ${['cancelled', 'uploading', 'success'].includes(status) ? 'disabled' : ''}>Edit</button>
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); holdUploadQueueItem('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'failed'].includes(status) ? 'disabled' : ''}>Hold</button>
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); resumeUploadQueueItem('${esc(item.queue_id)}')" ${status !== 'held' ? 'disabled' : ''}>Resume</button>
            <button class="ghostButton" type="button" onclick="event.stopPropagation(); cancelUploadQueueItemUi('${esc(item.queue_id)}')" ${!['pending', 'scheduled', 'held', 'failed'].includes(status) ? 'disabled' : ''}>Cancel</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// =============================================================================
// RENDER: INSPECTOR
// =============================================================================

function renderUploadInspector(){
  const titleEl = qs('upload_detail_title');
  const hintEl = qs('upload_detail_hint');
  const bodyEl = qs('upload_detail_body');
  const breadcrumbEl = qs('upload_detail_breadcrumb');
  if(!titleEl || !hintEl || !bodyEl) return;
  const account = _selectedAccountWorkspaceItem();
  if(!selectedUploadEntity.type || !selectedUploadEntity.id){
    titleEl.textContent = account ? `${account.display_name || account.account_key || 'Account'} Details` : 'Selection Details';
    hintEl.textContent = account ? 'Account-level details and upload state.' : 'Select an account, video, or upload item to inspect details.';
    if(breadcrumbEl) breadcrumbEl.textContent = account ? `Selected Account -> ${account.display_name || account.account_key || account.account_id}` : 'Nothing selected';
    bodyEl.innerHTML = account
      ? `
        <div class="uploadDetailGrid">
          ${_detailSection('Status', String(account.status || 'unknown').replace(/_/g, ' '), false)}
          ${_detailSection('Login State', String(account.login_state || 'unknown').replace(/_/g, ' '), false)}
          ${_detailSection('Today Count', `${Number(account.today_count || 0)} / ${Number(account.daily_limit || 0) || '-'}`, false)}
          ${_detailSection('Cooldown', `${Number(account.cooldown_minutes || 0)} min`, false)}
        </div>
        ${_detailSection('Profile Path', account.profile_path || '-', false)}
        ${_detailSection('Proxy', account.proxy_id || '-', false)}
        ${_detailSection('Health', _prettyJson(account.health_json || {}), true)}
      `
      : '<div class="uploadInspectorPlaceholder">Select an account, video, or upload item to inspect details.</div>';
    return;
  }
  if(selectedUploadEntity.type === 'account'){
    const item = uploadAccountManagerItems.find((x) => String(x.account_id || '') === String(selectedUploadEntity.id || ''));
    if(!item) return;
    if(breadcrumbEl) breadcrumbEl.textContent = `Selected Account -> ${item.display_name || item.account_key || item.account_id}`;
    titleEl.textContent = item.display_name || item.account_key || item.account_id;
    hintEl.textContent = 'Account profile, health, and isolation details.';
    bodyEl.innerHTML = `
      <div class="uploadDetailGrid">
        ${_detailSection('Status', String(item.status || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Login State', String(item.login_state || 'unknown').replace(/_/g, ' '), false)}
        ${_detailSection('Profile Lock', String(item.profile_lock_state || 'idle').replace(/_/g, ' '), false)}
        ${_detailSection('Usage Today', `${Number(item.today_count || 0)} / ${Number(item.daily_limit || 0) || '-'}`, false)}
        ${_detailSection('Cooldown', `${Number(item.cooldown_minutes || 0)} min`, false)}
        ${_detailSection('Proxy ID', item.proxy_id || '-', false)}
      </div>
      ${_inspectorHealthPanelHtml(item)}
      ${_detailSection('Profile Path', item.profile_path || '-', false)}
      ${_detailSection('Profile', accountHasActiveUpload(item.account_id) ? 'Locked' : (item.profile_conflict ? 'Conflict' : 'Isolated'), false)}
      ${item.profile_conflict ? _detailSection('Profile Conflict', _uamConflictText(item), false) : ''}
      ${_detailSection('Health JSON', _prettyJson(item.health_json || {}), true)}
    `;
    return;
  }
  if(selectedUploadEntity.type === 'video'){
    const item = uploadVideoLibraryItems.find((x) => String(x.video_id || '') === String(selectedUploadEntity.id || ''));
    if(!item) return;
    if(breadcrumbEl) breadcrumbEl.textContent = `Selected Video -> ${item.file_name || item.video_id}`;
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
  if(selectedUploadEntity.type === 'queue'){
    const item = uploadQueueManagerItems.find((x) => String(x.queue_id || '') === String(selectedUploadEntity.id || ''));
    if(!item) return;
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    if(breadcrumbEl) breadcrumbEl.textContent = `Selected Queue Item -> ${item.video_file_name || item.queue_id} -> Account ${accountName}`;
    titleEl.textContent = item.video_file_name || item.queue_id;
    hintEl.textContent = `Upload item for ${accountName}.`;
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
      ${_detailSection('Blocked Reason', item.blocked_reason || '-', false)}
      ${_detailSection('Last Error', item.last_error || '-', false)}
      ${_detailSection('Adapter Result', _historySummary(item.result_json || item.result || {}) || '-', false)}
    `;
  }
}

// =============================================================================
// RENDER: WORKSPACE PANELS
// =============================================================================

function _renderSettingsTab(account){
  const body = qs('upload_settings_body');
  if(!body) return;
  if(!account){
    body.innerHTML = '<div class="uploadInspectorPlaceholder">Select an account to view upload settings.</div>';
    return;
  }
  body.innerHTML = `
    <div class="uploadSettingsGrid">
      ${_detailSection('Profile Path', account.profile_path || '-', false)}
      ${_detailSection('Proxy ID', account.proxy_id || '-', false)}
      ${_detailSection('Daily Limit', String(Number(account.daily_limit || 0)), false)}
      ${_detailSection('Today Count', String(Number(account.today_count || 0)), false)}
      ${_detailSection('Cooldown', `${Number(account.cooldown_minutes || 0)} min`, false)}
      ${_detailSection('Login State', String(account.login_state || 'unknown').replace(/_/g, ' '), false)}
      ${_detailSection('Profile Lock', String(account.profile_lock_state || 'idle').replace(/_/g, ' '), false)}
      ${_detailSection('Last Upload', account.last_upload_at || '-', false)}
      ${_detailSection('Last Login Check', account.last_login_check_at || '-', false)}
    </div>
    ${_detailSection('Health', _prettyJson(account.health_json || {}), true)}
  `;
}

function _renderActiveUploadCard(account){
  const activity = _studioActivity(account);
  const items = _studioAccountQueues(account.account_id);
  const uploading = items.find((item) => String(item.status || '').toLowerCase() === 'uploading');
  if(uploading){
    return `
      <div class="accountWorkspaceStat accountWorkspaceStatWide">
        <div class="accountWorkspaceStatLabel">Uploading now</div>
        <div class="accountWorkspaceStatValue">${esc(uploading.video_file_name || String(uploading.video_path || '').split(/[\\/]/).pop() || '-')}</div>
        <div class="uamSub">Attempt ${Number(uploading.attempt_count || 0)} / ${Number(uploading.max_attempts || 3)}</div>
        <div class="uamSub">${esc(uploading.last_error || uploading.blocked_reason || 'Running')}</div>
      </div>
    `;
  }
  return `
    <div class="accountWorkspaceStat accountWorkspaceStatWide">
      <div class="accountWorkspaceStatLabel">Account idle</div>
      <div class="accountWorkspaceStatValue">Add videos to this account or run the scheduler.</div>
      <div class="uamSub">${esc(activity.error || 'No active upload right now.')}</div>
    </div>
  `;
}

function _renderWorkspaceHeader(){
  const account = _studioSelectedAccount();
  const titleEl = qs('upload_account_workspace_title');
  const hintEl = qs('upload_account_workspace_hint');
  const metaEl = qs('upload_account_workspace_meta');
  const videoBtn = qs('uvl_add_video_btn');
  const assignBtn = qs('uqm_add_to_account_btn');
  const runBtn = qs('upload_run_account_btn');
  const holdBtn = qs('upload_stop_account_btn');
  const checkBtn = qs('upload_check_login_btn');
  const uploadsTitle = qs('uqm_uploads_title');
  const videosHint = qs('uvl_account_workspace_hint');
  if(!account){
    if(titleEl) titleEl.textContent = 'Account Workspace: Select an account';
    if(hintEl) hintEl.textContent = 'Select an account to manage its upload flow.';
    if(metaEl) metaEl.innerHTML = '<div class="uploadWorkspaceEmptyState"><div class="uploadWorkspaceEmptyTitle">Select an account to manage uploads</div><div class="uploadWorkspaceEmptyCopy">Each account uses its own isolated browser profile.</div></div>';
    [videoBtn, assignBtn, runBtn, holdBtn, checkBtn].forEach((btn) => { if(btn) btn.disabled = true; });
    if(videoBtn) videoBtn.textContent = 'Add Video';
    if(assignBtn) assignBtn.textContent = 'Assign to Account';
    if(runBtn){ runBtn.textContent = 'Start Upload'; runBtn.title = 'Select an account first'; }
    if(holdBtn) holdBtn.title = 'Select an account first';
    if(checkBtn) checkBtn.title = 'Select an account first';
    if(uploadsTitle) uploadsTitle.textContent = 'Uploads for this account';
    if(videosHint) videosHint.textContent = 'Upload-ready files you can assign to the selected account.';
    _renderSettingsTab(null);
    return;
  }
  const activity = _studioActivity(account);
  const nextItem = _studioNextRunnable(account);
  const queues = _studioAccountQueues(account.account_id);
  if(titleEl) titleEl.textContent = `Account Workspace: ${account.display_name || account.account_key || account.account_id}`;
  if(hintEl) hintEl.textContent = `${account.platform || 'TikTok'} · ${String(account.login_state || 'unknown').replace(/_/g, ' ')} · Today ${Number(account.today_count || 0)}/${Number(account.daily_limit || 0) || '-'} · Cooldown ${Number(account.cooldown_minutes || 0)}m`;
  if(uploadsTitle) uploadsTitle.textContent = `Uploads for ${account.display_name || account.account_key || 'this account'}`;
  if(videosHint) videosHint.textContent = `Upload-ready files you can assign to ${account.display_name || account.account_key || 'this account'}.`;
  if(videoBtn){ videoBtn.disabled = false; videoBtn.textContent = `Add Video to ${account.display_name || account.account_key || 'this account'}`; }
  if(assignBtn){ assignBtn.disabled = false; assignBtn.textContent = `Add Video to ${account.display_name || account.account_key || 'this account'}`; }
  if(runBtn){
    runBtn.disabled = !nextItem;
    runBtn.textContent = 'Start Upload';
    runBtn.title = nextItem ? `Start upload for ${account.display_name || account.account_key || 'this account'}` : _studioRunReason(account);
  }
  if(holdBtn){
    const hasHoldable = queues.some((item) => ['pending', 'scheduled', 'failed'].includes(String(item.status || '').toLowerCase()));
    holdBtn.disabled = !hasHoldable;
    holdBtn.title = hasHoldable ? 'Hold pending uploads for this account' : 'No pending uploads assigned';
  }
  if(checkBtn){ checkBtn.disabled = ['disabled', 'banned'].includes(String(account.status || '').toLowerCase()); }
  if(metaEl){
    metaEl.innerHTML = `
      <div class="accountWorkspaceStats">
        <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Current activity</div><div class="accountWorkspaceStatValue">${esc(activity.label)}</div></div>
        <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Assigned uploads</div><div class="accountWorkspaceStatValue">${queues.length}</div></div>
        <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Login</div><div class="accountWorkspaceStatValue">${esc(String(account.login_state || 'unknown').replace(/_/g, ' '))}</div></div>
        <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Status</div><div class="accountWorkspaceStatValue">${esc(String(account.status || 'active').replace(/_/g, ' '))}</div></div>
        <div class="accountWorkspaceStat accountWorkspaceStatWide">
          <div class="accountWorkspaceStatLabel">${activity.label === 'Uploading' ? 'Uploading now' : 'Account idle'}</div>
          <div class="accountWorkspaceStatValue">${esc(activity.current || (activity.label === 'Uploading' ? '-' : 'Assign videos or start scheduler.'))}</div>
          <div class="uamSub">${esc(activity.error || (activity.label === 'Uploading' ? `Attempt ${activity.attempt || '-'}` : 'Ready for the next upload.'))}</div>
        </div>
      </div>
    `;
  }
  _renderSettingsTab(account);
}

function _renderAccountWorkspaceSummary(){
  const account = _selectedAccountWorkspaceItem();
  const titleEl = qs('upload_account_workspace_title');
  const hintEl = qs('upload_account_workspace_hint');
  const metaEl = qs('upload_account_workspace_meta');
  const addBtn = qs('uqm_add_to_account_btn');
  const runBtn = qs('upload_run_account_btn');
  const stopBtn = qs('upload_stop_account_btn');
  const checkBtn = qs('upload_check_login_btn');
  const queueHint = qs('uqm_account_workspace_hint');
  const formHint = qs('uqm_form_hint');
  const videosBtn = qs('uvl_add_video_btn');

  // CASE 1: No accounts exist at all — show Get Started
  if(!uploadAccountManagerItems.length){
    if(titleEl) titleEl.textContent = 'Account Workspace: Get Started';
    if(hintEl) hintEl.textContent = 'Create your first account to begin uploading.';
    if(queueHint) queueHint.textContent = 'Create an account to manage uploads.';
    if(formHint) formHint.textContent = 'Create an account first.';
    [addBtn, runBtn, stopBtn, checkBtn].forEach((btn) => { if(btn) btn.disabled = true; });
    if(addBtn) { addBtn.textContent = 'Select Account First'; addBtn.title = 'Create an account first'; }
    if(videosBtn) { videosBtn.textContent = 'Add Video'; }
    if(runBtn) { runBtn.textContent = 'Start Upload'; runBtn.title = 'Create an account first'; }
    if(stopBtn) stopBtn.title = 'Create an account first';
    if(checkBtn) checkBtn.title = 'Create an account first';
    if(metaEl) metaEl.innerHTML = `
      <div class="uamGetStarted">
        <div class="uamGetStartedTitle">🚀 Get Started with Upload</div>
        <div class="uamGetStartedSteps">
          <div class="uamGetStartedStep">Step 1: Create your first account</div>
          <div class="uamGetStartedStep uamGetStartedStepMuted">Step 2: Add videos</div>
          <div class="uamGetStartedStep uamGetStartedStepMuted">Step 3: Assign and upload</div>
        </div>
        <button class="primaryButton" type="button" onclick="openUploadEditor('account')">+ Create First Account</button>
      </div>
    `;
    _renderSettingsTab(null);
    return;
  }

  const accountName = account ? (account.display_name || account.account_key || 'this account') : 'Select an account';
  const items = account ? _accountWorkspaceQueueItems(account.account_id) : [];
  const nextItem = account ? _findRunnableAccountQueueItem(account.account_id) : null;
  const counts = account ? _accountWorkspaceCounts(account.account_id) : {pending:0,scheduled:0,uploading:0,success:0,failed:0};
  if(titleEl) titleEl.textContent = `Account Workspace: ${accountName}`;
  if(hintEl) hintEl.textContent = account ? `${account.platform || 'tiktok'} · ${String(account.login_state || 'unknown').replace(/_/g, ' ')} · Today ${Number(account.today_count || 0)}/${Number(account.daily_limit || 0) || '-'}` : 'Select an account to manage its upload flow.';
  if(queueHint) queueHint.textContent = account ? `Uploads for ${accountName}` : 'Select an account to see its upload items and run them safely.';
  if(addBtn){
    addBtn.textContent = account ? `Add Video to ${accountName}` : 'Select Account First';
    addBtn.disabled = !account;
    addBtn.title = account ? `Assign a video to ${accountName}` : 'Select an account first';
  }
  if(videosBtn) videosBtn.textContent = account ? `Add Video to ${accountName}` : 'Add Video';
  if(runBtn){
    runBtn.disabled = !account || !nextItem;
    runBtn.textContent = 'Start Upload';
    runBtn.title = nextItem ? `Start the next eligible upload for ${accountName}` : _disabledRunReasonForAccount(account);
  }
  if(stopBtn){
    const stoppable = items.some((item) => ['pending', 'scheduled', 'failed'].includes(String(item.status || '').toLowerCase()));
    stopBtn.disabled = !account || !stoppable;
    stopBtn.title = !account ? 'Select an account first' : (stoppable ? `Hold pending uploads for ${accountName}` : 'No pending uploads to hold');
  }
  if(checkBtn) checkBtn.disabled = !account || ['disabled', 'banned'].includes(String(account?.status || '').toLowerCase());
  if(formHint) formHint.textContent = account ? `Selected account: ${accountName}. Choose the next video for it.` : 'Select an account, then choose the next video for it.';
  if(qs('uqm_account_id') && account && !qs('uqm_queue_id')?.value) qs('uqm_account_id').value = account.account_id || '';
  if(!metaEl) return;
  if(!account){
    metaEl.innerHTML = `
      <div class="uploadWorkspaceEmptyState">
        <div class="uploadWorkspaceEmptyTitle">Select an account to manage uploads</div>
        <div class="uploadWorkspaceEmptyCopy">Accounts are isolated with their own browser profile.</div>
      </div>
    `;
    _renderSettingsTab(null);
    return;
  }
  metaEl.innerHTML = `
    <div class="accountWorkspaceStats">
      <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Current activity</div><div class="accountWorkspaceStatValue">${esc(_accountWorkspaceActivity(account.account_id).label)}</div></div>
      <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Assigned uploads</div><div class="accountWorkspaceStatValue">${items.length}</div></div>
      <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Pending uploads</div><div class="accountWorkspaceStatValue">${counts.pending + counts.scheduled}</div></div>
      <div class="accountWorkspaceStat"><div class="accountWorkspaceStatLabel">Login state</div><div class="accountWorkspaceStatValue">${esc(String(account.login_state || 'unknown').replace(/_/g, ' '))}</div></div>
      ${_renderActiveUploadCard(account)}
    </div>
  `;
  _renderSettingsTab(account);
}

// =============================================================================
// WORKFLOW GUIDE
// =============================================================================

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
  if(!_uqmValue('uqm_account_id') || !String(qs('uqm_video_id')?.value || '').trim()) return 'Select account + video first.';
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
  const selected = _selectedAccountWorkspaceItem();
  const hasVideos = uploadVideoLibraryItems.length > 0;
  const selectedUploads = selected ? _accountWorkspaceQueueItems(selected.account_id) : [];
  let step = 1;
  let hint = '1. Select an account.';
  if(selected && !hasVideos){
    step = 2; hint = '2. Add a video file.';
  } else if(selected && hasVideos && !selectedUploads.length){
    step = 3; hint = '3. Assign a video to this account.';
  } else if(selected && selectedUploads.some((item) => ['pending', 'scheduled', 'uploading', 'failed'].includes(String(item.status || '').toLowerCase()))){
    step = 4; hint = '4. Start upload for this account.';
  }
  currentUploadWorkflowStep = step;
  [1,2,3,4].forEach((idx) => {
    const el = qs(`upload_workflow_step_${idx}`);
    if(!el) return;
    el.classList.toggle('isActive', idx === step);
    el.classList.toggle('isComplete', idx < step);
  });
  if(qs('upload_workflow_hint')) qs('upload_workflow_hint').textContent = hint;
  const queueHint = qs('uqm_form_hint');
  if(queueHint) queueHint.textContent = getQueueCreateHint();
}

// =============================================================================
// SELECT ENTITY (central coordination)
// =============================================================================

function _selectUploadEntity(type, id){
  selectedUploadEntity = {type: String(type || ''), id: String(id || '')};
  if(type === 'account'){
    selectedUploadAccountWorkspaceId = String(id || '');
    UploadStore.setSelectedAccountId(id);
    const account = _selectedAccountWorkspaceItem();
    setUploadManagerTab(_defaultAccountTab(account));
  } else if(type === 'video'){
    setUploadManagerTab('videos');
  } else if(type === 'queue'){
    selectedUploadQueueId = String(id || '');
    UploadStore.setSelectedQueueItemId(id);
    const row = uploadQueueManagerItems.find((item) => String(item.queue_id || '') === selectedUploadQueueId);
    if(row && row.account_id) selectedUploadAccountWorkspaceId = String(row.account_id || '');
    setUploadManagerTab('queue');
    loadUploadQueueHistory(selectedUploadQueueId);
  }
  renderUploadAccounts(uploadAccountManagerItems);
  renderUploadVideoLibrary(uploadVideoLibraryItems);
  renderUploadQueueManager(uploadQueueManagerItems);
  _renderAccountWorkspaceSummary();
  renderUploadInspector();
  renderUploadWorkflowGuide();
  loadSelectedAccountHistory();
}

function _selectedUploadId(type){
  return selectedUploadEntity.type === type ? selectedUploadEntity.id : '';
}

// =============================================================================
// PROFILE ISOLATION SAFETY — Feature 4.6
// =============================================================================

function normalizeProfilePath(rawPath) {
  const raw = String(rawPath || '').trim();
  if (!raw) return '';
  let normalized = raw.replace(/\//g, '\\').replace(/[/\\]+$/, '');
  if (/^[a-zA-Z]:\\/.test(normalized)) normalized = normalized.toLowerCase();
  return normalized;
}

function findProfilePathConflict(profilePath, editingAccountId) {
  const target = normalizeProfilePath(profilePath);
  if (!target) return null;
  return uploadAccountManagerItems.find((acc) => {
    if (String(acc.account_id) === String(editingAccountId)) return false;
    const accPath = normalizeProfilePath(acc.profile_path || acc.user_data_dir || '');
    return accPath && accPath === target;
  }) || null;
}

function accountHasActiveUpload(accountId) {
  return uploadQueueManagerItems.some(
    (item) =>
      String(item.account_id) === String(accountId) &&
      ['running', 'uploading', 'processing'].includes(String(item.status || '').toLowerCase())
  );
}

function validateAccountProfilePathBeforeSave(formData, editingAccountId) {
  const errors = [];
  const warnings = [];
  const profilePath = normalizeProfilePath(formData.profile_path || '');

  if (!profilePath) {
    errors.push('Profile folder is required.');
    return { ok: false, errors, warnings };
  }

  const conflict = findProfilePathConflict(profilePath, editingAccountId);
  if (conflict) {
    const name = conflict.display_name || conflict.account_key || conflict.account_id;
    errors.push(`Profile folder is already used by account: ${name}.`);
  }

  if (editingAccountId && accountHasActiveUpload(editingAccountId)) {
    const existing = uploadAccountManagerItems.find((a) => a.account_id === editingAccountId);
    const existingPath = normalizeProfilePath(existing?.profile_path || '');
    if (existingPath && existingPath !== profilePath) {
      errors.push('Profile folder cannot be changed while an upload is running for this account.');
    }
  }

  return { ok: errors.length === 0, errors, warnings };
}

async function updateProfilePathStatus() {
  const statusEl = qs('uam_profile_path_status');
  if (!statusEl) return;

  const rawPath = _uamValue('uam_profile_path');
  const editingAccountId = _uamValue('uam_account_id');

  if (!rawPath) {
    statusEl.textContent = '⚠ Profile path is required';
    statusEl.className = 'uamProfileStatus isError';
    return;
  }

  const profilePath = normalizeProfilePath(rawPath);
  const conflict = findProfilePathConflict(profilePath, editingAccountId);
  if (conflict) {
    const name = conflict.display_name || conflict.account_key || conflict.account_id;
    statusEl.textContent = `🔴 Already used by account: ${name}`;
    statusEl.className = 'uamProfileStatus isError';
    return;
  }

  if (window.electronAPI?.pathExists) {
    try {
      const exists = await window.electronAPI.pathExists(rawPath);
      if (exists) {
        statusEl.textContent = '🟡 Existing browser profile folder';
        statusEl.className = 'uamProfileStatus isWarn';
      } else {
        statusEl.textContent = '🟢 New profile folder';
        statusEl.className = 'uamProfileStatus isOk';
      }
    } catch (_) {
      statusEl.textContent = '🟢 Profile folder set';
      statusEl.className = 'uamProfileStatus isOk';
    }
  } else {
    statusEl.textContent = '🟢 Profile folder set';
    statusEl.className = 'uamProfileStatus isOk';
  }
}

function _setProfileFolderLocked(locked) {
  const profileInput = qs('uam_profile_path');
  const chooseBtn = qs('uam_choose_folder_btn');
  const autoCreateBtn = qs('uam_auto_create_btn');
  if (profileInput) profileInput.disabled = locked;
  if (chooseBtn) chooseBtn.disabled = locked;
  if (autoCreateBtn) autoCreateBtn.disabled = locked;
}

// =============================================================================
// FORM: ACCOUNT — helpers
// =============================================================================

function _genAccountKey(displayName, platform) {
  const base = (displayName || platform || 'account')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40) || 'account';
  return base;
}

function _genChannelCode(platform, accountKey) {
  const p = (platform || 'tiktok').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return `${p}_${accountKey}`.slice(0, 50);
}

function _buildProxyConfig() {
  const type = _uamValue('uam_proxy_type');
  const host = _uamValue('uam_proxy_host');
  const port = _uamValue('uam_proxy_port');
  const username = _uamValue('uam_proxy_username');
  const password = _uamValue('uam_proxy_password');
  if (!type || !host) return {};
  const portPart = port ? `:${port}` : '';
  const cfg = { network_mode: 'proxy', proxy_server: `${type}://${host}${portPart}` };
  if (username) cfg.proxy_username = username;
  if (password) cfg.proxy_password = password;
  return cfg;
}

function _parseProxyConfig(cfg) {
  const clearIds = ['uam_proxy_host', 'uam_proxy_port', 'uam_proxy_username', 'uam_proxy_password'];
  if (!cfg || typeof cfg !== 'object' || !cfg.proxy_server) {
    if (qs('uam_proxy_type')) qs('uam_proxy_type').value = '';
    clearIds.forEach((id) => { if (qs(id)) qs(id).value = ''; });
    return;
  }
  const m = String(cfg.proxy_server).match(/^(https?|socks5?):\/\/([^:/]+)(?::(\d+))?/);
  const type = m ? (m[1].startsWith('http') ? 'http' : 'socks5') : '';
  if (qs('uam_proxy_type')) qs('uam_proxy_type').value = type;
  if (qs('uam_proxy_host')) qs('uam_proxy_host').value = m ? (m[2] || '') : '';
  if (qs('uam_proxy_port')) qs('uam_proxy_port').value = m ? (m[3] || '') : '';
  if (qs('uam_proxy_username')) qs('uam_proxy_username').value = cfg.proxy_username || '';
  if (qs('uam_proxy_password')) qs('uam_proxy_password').value = cfg.proxy_password || '';
}

async function testProxyConfig() {
  const host = _uamValue('uam_proxy_host');
  const resultEl = qs('uam_proxy_test_result');
  const btn = qs('uam_proxy_test_btn');
  if (!host) {
    if (resultEl) { resultEl.textContent = '⚠ Enter host first'; resultEl.className = 'uamProxyTestResult warn'; }
    return;
  }
  if (btn) btn.disabled = true;
  if (resultEl) { resultEl.textContent = 'Testing…'; resultEl.className = 'uamProxyTestResult'; }
  try {
    const res = await fetch('/api/upload/accounts/test-proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: _uamValue('uam_proxy_type') || 'http',
        host,
        port: _uamInt('uam_proxy_port') || null,
        username: _uamValue('uam_proxy_username') || null,
        password: _uamValue('uam_proxy_password') || null,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      const parts = ['✓ OK'];
      if (data.latency_ms) parts.push(`${data.latency_ms}ms`);
      if (data.ip) parts.push(`IP: ${data.ip}`);
      if (resultEl) { resultEl.textContent = parts.join(' · '); resultEl.className = 'uamProxyTestResult ok'; }
    } else {
      if (resultEl) { resultEl.textContent = `✗ ${data.error || 'Failed'}`; resultEl.className = 'uamProxyTestResult fail'; }
    }
  } catch (err) {
    if (resultEl) { resultEl.textContent = `✗ ${err.message}`; resultEl.className = 'uamProxyTestResult fail'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function pickProfileFolder() {
  if (!window.electronAPI?.openFolderPicker) {
    if (qs('uam_profile_path')) qs('uam_profile_path').focus();
    return;
  }
  const btn = qs('uam_choose_folder_btn');
  if (btn) btn.disabled = true;
  document.body.style.cursor = 'wait';
  try {
    const folder = await window.electronAPI.openFolderPicker();
    if (folder) {
      if (qs('uam_profile_path')) qs('uam_profile_path').value = folder;
      await updateProfilePathStatus();
    }
  } catch (err) {
    console.warn('[FolderPicker] failed:', err);
  } finally {
    document.body.style.cursor = '';
    if (btn) btn.disabled = false;
  }
}

async function autoCreateProfilePath() {
  const platform = _uamValue('uam_platform') || 'tiktok';
  const displayName = _uamValue('uam_display_name');
  let accountKey = _uamValue('uam_account_key');
  if (!accountKey) accountKey = _genAccountKey(displayName, platform);
  let channelCode = _uamValue('uam_channel_code');
  if (!channelCode) channelCode = _genChannelCode(platform, accountKey);
  const path = `D:\\channels\\${channelCode}\\profiles\\${accountKey}`;
  if (qs('uam_profile_path')) qs('uam_profile_path').value = path;
  await updateProfilePathStatus();
}

// =============================================================================
// FORM: ACCOUNT
// =============================================================================

function collectUploadAccountForm(){
  const platform = _uamValue('uam_platform') || 'tiktok';
  const displayName = _uamValue('uam_display_name');
  const isCreate = !_uamValue('uam_account_id');

  let accountKey = _uamValue('uam_account_key');
  if (!accountKey) accountKey = _genAccountKey(displayName, platform);

  let channelCode = _uamValue('uam_channel_code');
  if (!channelCode) channelCode = _genChannelCode(platform, accountKey);

  const payload = {
    platform,
    channel_code: channelCode,
    account_key: accountKey,
    display_name: displayName,
    status: isCreate ? 'active' : (_uamValue('uam_status') || 'active'),
    login_state: isCreate ? 'unknown' : (_uamValue('uam_login_state') || 'unknown'),
    daily_limit: _uamInt('uam_daily_limit') ?? 5,
    cooldown_minutes: _uamInt('uam_cooldown_minutes') ?? 30,
    profile_path: _uamValue('uam_profile_path'),
    proxy_id: _uamValue('uam_proxy_id'),
    proxy_config: _buildProxyConfig(),
    health_json: {},
    metadata_json: {},
  };
  if (!isCreate) payload.today_count = _uamInt('uam_today_count') ?? 0;
  return payload;
}

function resetUploadAccountForm(){
  ['uam_account_id', 'uam_channel_code', 'uam_display_name', 'uam_profile_path',
   'uam_proxy_id', 'uam_proxy_host', 'uam_proxy_port', 'uam_proxy_username', 'uam_proxy_password'].forEach((id) => {
    if (qs(id)) qs(id).value = '';
  });
  if (qs('uam_platform')) qs('uam_platform').value = 'tiktok';
  if (qs('uam_account_key')) qs('uam_account_key').value = '';
  if (qs('uam_proxy_type')) qs('uam_proxy_type').value = '';
  if (qs('uam_status')) qs('uam_status').value = 'active';
  if (qs('uam_login_state')) qs('uam_login_state').value = 'unknown';
  if (qs('uam_daily_limit')) qs('uam_daily_limit').value = '5';
  if (qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = '30';
  if (qs('uam_today_count')) qs('uam_today_count').value = '0';
  if (qs('uam_proxy_test_result')) { qs('uam_proxy_test_result').textContent = ''; qs('uam_proxy_test_result').className = 'uamProxyTestResult'; }
  const statusEl = qs('uam_profile_path_status');
  if (statusEl) { statusEl.textContent = ''; statusEl.className = 'uamProfileStatus'; }
  _setProfileFolderLocked(false);
  const diagSection = qs('uam_diagnostics_section');
  if (diagSection) diagSection.hidden = true;
  if (qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Create Account';
  if (qs('uam_modal_title')) qs('uam_modal_title').textContent = 'New Account';
}

function fillUploadAccountForm(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if (!item) return;
  _selectUploadEntity('account', accountId);
  openUploadAccountModal();
  if (qs('uam_account_id')) qs('uam_account_id').value = item.account_id || '';
  if (qs('uam_platform')) qs('uam_platform').value = item.platform || 'tiktok';
  if (qs('uam_channel_code')) qs('uam_channel_code').value = item.channel_code || '';
  if (qs('uam_account_key')) qs('uam_account_key').value = item.account_key || '';
  if (qs('uam_display_name')) qs('uam_display_name').value = item.display_name || '';
  if (qs('uam_status')) qs('uam_status').value = item.status || 'active';
  if (qs('uam_login_state')) qs('uam_login_state').value = item.login_state || 'unknown';
  if (qs('uam_daily_limit')) qs('uam_daily_limit').value = Number(item.daily_limit ?? 5);
  if (qs('uam_cooldown_minutes')) qs('uam_cooldown_minutes').value = Number(item.cooldown_minutes ?? 30);
  if (qs('uam_today_count')) qs('uam_today_count').value = Number(item.today_count || 0);
  if (qs('uam_profile_path')) qs('uam_profile_path').value = item.profile_path || '';
  if (qs('uam_proxy_id')) qs('uam_proxy_id').value = item.proxy_id || '';
  _parseProxyConfig(item.proxy_config);
  if (qs('uam_proxy_test_result')) { qs('uam_proxy_test_result').textContent = ''; qs('uam_proxy_test_result').className = 'uamProxyTestResult'; }
  // Active-upload lock: disable profile folder controls if account has running uploads
  const isLocked = accountHasActiveUpload(item.account_id);
  _setProfileFolderLocked(isLocked);
  const statusEl = qs('uam_profile_path_status');
  if (isLocked && statusEl) {
    statusEl.textContent = '🔒 Profile folder is locked while uploads are running.';
    statusEl.className = 'uamProfileStatus isWarn';
  } else {
    updateProfilePathStatus();
  }
  const diagSection = qs('uam_diagnostics_section');
  if (diagSection) diagSection.hidden = false;
  if (qs('uam_save_btn')) qs('uam_save_btn').textContent = 'Save Changes';
  if (qs('uam_modal_title')) qs('uam_modal_title').textContent = `Edit: ${item.display_name || item.account_key || item.account_id}`;
}

// =============================================================================
// FORM: VIDEO
// =============================================================================

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
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => { if(qs(id)) qs(id).disabled = false; });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Add Video';
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
  ['uvl_video_path', 'uvl_platform', 'uvl_source_type'].forEach((id) => { if(qs(id)) qs(id).disabled = true; });
  if(qs('uvl_save_btn')) qs('uvl_save_btn').textContent = 'Save Video';
}

// =============================================================================
// FORM: QUEUE
// =============================================================================

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
  ['uqm_queue_id', 'uqm_caption', 'uqm_hashtags', 'uqm_scheduled_at'].forEach((id) => { if(qs(id)) qs(id).value = ''; });
  if(qs('uqm_video_id')) qs('uqm_video_id').value = '';
  if(qs('uqm_account_id')) qs('uqm_account_id').value = '';
  if(qs('uqm_priority')) qs('uqm_priority').value = '0';
  if(qs('uqm_status')) qs('uqm_status').value = 'pending';
  if(qs('uqm_video_id')) qs('uqm_video_id').disabled = false;
  if(qs('uqm_save_btn')) qs('uqm_save_btn').textContent = 'Add to Queue';
  renderUploadQueueHistory([]);
  if(qs('uqm_history_hint')) qs('uqm_history_hint').textContent = 'Select a queue item to view attempts.';
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

// =============================================================================
// ACCOUNT WORKSPACE ACTIONS
// =============================================================================

async function runSelectedAccountQueue(){
  const account = _selectedAccountWorkspaceItem();
  if(!account){ showToast('Select an account first', 'info'); return; }
  const nextItem = _findRunnableAccountQueueItem(account.account_id);
  if(!nextItem){
    const blocked = _accountWorkspaceQueueItems(account.account_id).find((item) => ['pending', 'scheduled', 'held', 'failed'].includes(String(item.status || '').toLowerCase()));
    showToast(blocked && blocked.blocked_reason ? blocked.blocked_reason : 'No eligible upload item for this account', 'info');
    return;
  }
  _selectUploadEntity('queue', nextItem.queue_id);
  await runUploadQueueItem(nextItem.queue_id);
}

async function stopSelectedAccountQueue(){
  const account = _selectedAccountWorkspaceItem();
  if(!account){ showToast('Select an account first', 'info'); return; }
  const stoppable = _accountWorkspaceQueueItems(account.account_id).filter((item) => ['pending', 'scheduled', 'failed'].includes(String(item.status || '').toLowerCase()));
  if(!stoppable.length){ showToast('No pending uploads to stop for this account', 'info'); return; }
  let changed = 0;
  for(const item of stoppable){
    try{
      const res = await fetch(`/api/upload/queue/${encodeURIComponent(item.queue_id)}/hold`, {method: 'POST'});
      if(res.ok) changed += 1;
    }catch(_e){}
  }
  await loadUploadQueueManager();
  showToast(changed ? `Held ${changed} upload item${changed === 1 ? '' : 's'} for this account` : 'Nothing changed', changed ? 'success' : 'info');
}

function checkSelectedAccountLogin(){
  const account = _selectedAccountWorkspaceItem();
  if(!account){ showToast('Select an account first', 'info'); return; }
  checkUploadAccountLogin(account.account_id);
}

function openSelectedAccountQueueFlow(){
  const account = _selectedAccountWorkspaceItem();
  if(!account){ showToast('Select an account first', 'info'); return; }
  setUploadManagerTab('videos');
  if(qs('uqm_account_id')) qs('uqm_account_id').value = account.account_id || '';
  _setEditorOpen('uvl_editor', true);
  showToast(`Add or select a video for ${account.display_name || account.account_key || 'this account'}`, 'info');
}

function selectVideoForQueue(videoId){
  const account = _selectedAccountWorkspaceItem();
  const item = uploadVideoLibraryItems.find((x) => String(x.video_id || '') === String(videoId || ''));
  if(!account){ showToast('Select an account first', 'info'); return; }
  if(!item) return;
  if(String(item.status || '').toLowerCase() === 'disabled'){ showToast('Disabled video cannot be queued', 'error'); return; }
  _selectUploadEntity('video', videoId);
  resetUploadQueueForm();
  if(qs('uqm_account_id')) qs('uqm_account_id').value = account.account_id || '';
  if(qs('uqm_video_id')) qs('uqm_video_id').value = item.video_id || '';
  if(qs('uqm_caption')) qs('uqm_caption').value = item.caption || '';
  if(qs('uqm_hashtags')) qs('uqm_hashtags').value = _uvlHashtagText(item.hashtags || []);
  _setEditorOpen('uqm_editor', true);
  setUploadManagerTab('queue');
  showToast(`Ready to assign ${item.file_name || 'video'} to ${account.display_name || account.account_key || 'this account'}`, 'success');
}

// =============================================================================
// HISTORY
// =============================================================================

async function loadSelectedAccountHistory(){
  const account = _selectedAccountWorkspaceItem();
  const list = qs('upload_queue_history_list');
  const hint = qs('uqm_history_hint');
  if(!account){
    currentSelectedAccountHistoryItems = [];
    if(hint) hint.textContent = 'Select an account to view its recent upload attempts.';
    renderUploadQueueHistory([]);
    renderSelectedAccountLog();
    return;
  }
  if(hint) hint.textContent = `Recent upload attempts for ${account.display_name || account.account_key || 'this account'}.`;
  if(list) list.innerHTML = '<div class="uqmEmpty">Loading account history...</div>';
  try{
    const res = await fetch('/api/upload/history?limit=100');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    currentSelectedAccountHistoryItems = (Array.isArray(data.items) ? data.items : []).filter((item) => String(item.account_id || '') === String(account.account_id || ''));
    renderUploadQueueHistory(currentSelectedAccountHistoryItems);
    renderSelectedAccountLog();
  }catch(e){
    currentSelectedAccountHistoryItems = [];
    if(list) list.innerHTML = `<div class="uqmEmpty">History load failed: ${esc(e.message || e)}</div>`;
    renderSelectedAccountLog();
  }
}

function renderSelectedAccountLog(){
  const box = qs('event_log_upload');
  const account = _selectedAccountWorkspaceItem();
  if(!box) return;
  if(!account){
    box.innerHTML = '<div class="uqmEmpty">Select an account to view its recent upload log.</div>';
    return;
  }
  const activity = _accountWorkspaceActivity(account.account_id);
  const queueItems = _accountWorkspaceQueueItems(account.account_id).slice(0, 6);
  const historyItems = currentSelectedAccountHistoryItems.slice(0, 8);
  box.innerHTML = `
    <div class="accountLogPanel">
      <div class="accountLogHeaderRow">
        <span class="accountWorkspaceChip">${esc(activity.label)}</span>
        <span class="accountLogMuted">${esc(account.display_name || account.account_key || account.account_id)}</span>
      </div>
      ${queueItems.map((item) => `
        <div class="accountLogItem">
          <div class="accountLogTop">
            <span>${esc(item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-')}</span>
            <span>${esc(String(item.status || 'pending').replace(/_/g, ' '))}</span>
          </div>
          <div class="accountLogSub">${esc(item.last_error || item.blocked_reason || item.scheduled_at || 'Ready')}</div>
        </div>
      `).join('') || '<div class="uqmEmpty">No upload items for this account yet.</div>'}
      ${historyItems.length ? '<div class="accountLogDivider"></div>' : ''}
      ${historyItems.map((item) => `
        <div class="accountLogItem">
          <div class="accountLogTop">
            <span>Attempt ${Number(item.attempt_no || 0)}</span>
            <span>${esc(String(item.status || '').replace(/_/g, ' '))}</span>
          </div>
          <div class="accountLogSub">${esc(item.error || _historySummary(item.adapter_result) || item.finished_at || item.started_at || '-')}</div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderUploadQueueHistory(items){
  currentUploadQueueHistoryItems = Array.isArray(items) ? items : [];
  const list = qs('upload_queue_history_list');
  const account = _selectedAccountWorkspaceItem();
  if(!list) return;
  if(!account && !selectedUploadQueueId){
    list.innerHTML = '<div class="uqmEmpty">Select an account or queue item to view attempts.</div>';
    return;
  }
  if(!items || !items.length){
    list.innerHTML = '<div class="uqmEmpty">No attempts recorded yet.</div>';
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
      <div class="uqmSub">${esc(item.video_path ? String(item.video_path).split(/[\\/]/).pop() : (item.queue_id || '-'))}</div>
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

function loadSelectedUploadQueueHistory(){
  if(!selectedUploadQueueId){ renderUploadQueueHistory([]); return; }
  loadUploadQueueHistory(selectedUploadQueueId);
}

// =============================================================================
// LOAD FUNCTIONS
// =============================================================================

async function loadUploadAccounts(){
  const list = qs('upload_accounts_list') || qs('upload_accounts_tbody');
  if(list) list.innerHTML = '<div class="uamEmpty">Loading accounts…</div>';
  try{
    const res = await fetch('/api/upload/accounts');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadAccountManagerItems = Array.isArray(data.items) ? data.items : [];
    UploadStore.setAccounts(uploadAccountManagerItems);
    if(!_accountWorkspaceSelectedId() && uploadAccountManagerItems.length){
      selectedUploadAccountWorkspaceId = String(uploadAccountManagerItems[0].account_id || '');
    }
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueSelectors();
    _renderAccountWorkspaceSummary();
    renderUploadInspector();
    loadSelectedAccountHistory();
    renderUploadWorkflowGuide();
    refreshUploadWorkspace('accounts_loaded');
  }catch(e){
    if(list) list.innerHTML = `<div class="uamEmpty">Load failed: ${esc(e.message || e)}</div>`;
    addEvent(`Upload account load failed: ${e.message || e}`, 'upload');
  }
}

async function loadUploadVideoLibrary(){
  const tbody = qs('upload_videos_tbody');
  if(tbody) tbody.innerHTML = '<tr><td colspan="6" class="uvlEmpty">Loading videos...</td></tr>';
  const params = new URLSearchParams();
  const status = _uvlValue('uvl_filter_status');
  if(status) params.set('status', status);
  params.set('limit', '100');
  try{
    const res = await fetch(`/api/upload/videos?${params.toString()}`);
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    uploadVideoLibraryItems = Array.isArray(data.items) ? data.items : [];
    // Prune stale batch selections: remove IDs that are no longer ready+valid after refresh
    const _readyIds = new Set(uploadVideoLibraryItems.filter((v) => String(v.status || '').toLowerCase() === 'ready' && !!v.video_path).map((v) => String(v.video_id)));
    for(const id of [...selectedUploadVideoIds]){ if(!_readyIds.has(id)) selectedUploadVideoIds.delete(id); }
    renderUploadVideoLibrary(uploadVideoLibraryItems);
    renderUploadQueueSelectors();
    renderUploadInspector();
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" class="uvlEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
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
    UploadStore.setQueueItems(uploadQueueManagerItems);
    renderUploadQueueManager(uploadQueueManagerItems);
    renderUploadInspector();
    renderSelectedAccountLog();
    renderUploadWorkflowGuide();
    loadUploadSchedulerStatus();
    if(selectedUploadQueueId) loadSelectedUploadQueueHistory();
    refreshUploadWorkspace('queue_loaded');
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" class="uqmEmpty">Load failed: ${esc(e.message || e)}</td></tr>`;
    addEvent(`Upload queue load failed: ${e.message || e}`, 'upload');
  }
}

function refreshUploadWorkspace(reason = 'manual'){
  if(__uploadRefreshing) return;
  __uploadRefreshing = true;
  try{
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadQueueManager(uploadQueueManagerItems);
    _renderAccountWorkspaceSummary();
    renderUploadSchedulerStatus(_cachedSchedulerData);
    renderAutomationDashboard();
  }finally{
    __uploadRefreshing = false;
  }
}

// =============================================================================
// SAVE FUNCTIONS
// =============================================================================

async function saveUploadAccount(event){
  if(event) event.preventDefault();
  const accountId = _uamValue('uam_account_id');
  const payload = collectUploadAccountForm();

  const profileValidation = validateAccountProfilePathBeforeSave(payload, accountId);
  if (!profileValidation.ok) {
    showToast(profileValidation.errors[0], 'error');
    await updateProfilePathStatus();
    return;
  }

  try{
    const res = await fetch(accountId ? `/api/upload/accounts/${encodeURIComponent(accountId)}` : '/api/upload/accounts', {
      method: accountId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    resetUploadAccountForm();
    closeUploadAccountModal();
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
  if(!videoId && !payload.video_path){ showToast('Video path is required', 'error'); return; }
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
  if(!queueId && !payload.video_id){ showToast('Select a video first', 'error'); return; }
  if(!payload.account_id){ showToast('Select an account first', 'error'); return; }
  const body = queueId ? {account_id: payload.account_id, caption: payload.caption, hashtags: payload.hashtags, priority: payload.priority, scheduled_at: payload.scheduled_at, status: payload.status} : payload;
  try{
    const res = await fetch(queueId ? `/api/upload/queue/${encodeURIComponent(queueId)}` : '/api/upload/queue/add', {
      method: queueId ? 'PATCH' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    selectedUploadQueueId = queueId || data.queue_id || data.item?.queue_id || '';
    resetUploadQueueForm();
    _setEditorOpen('uqm_editor', false);
    setUploadManagerTab('queue');
    await loadUploadQueueManager();
    await loadSelectedAccountHistory();
    showToast(queueId ? 'Upload updated' : 'Assigned to account', 'success');
  }catch(e){
    showToast(`Assign failed: ${e.message || e}`, 'error');
  }
}

// =============================================================================
// ACCOUNT / VIDEO / QUEUE ACTIONS
// =============================================================================

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
    const loginMsgs = {logged_in: 'Login OK', logged_out: 'Session Expired', challenge: 'Captcha Required', expired: 'Session Expired', unknown: 'Login state unknown'};
    const toastType = loginState === 'logged_in' ? 'success' : (loginState === 'unknown' ? 'info' : 'error');
    showToast(loginMsgs[loginState] || data.message || 'Login check completed', toastType);
  }catch(e){
    showToast(`Login check failed: ${e.message || e}`, 'error');
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

// =============================================================================
// SCHEDULER
// =============================================================================

function _schedulerBlockedSummary(blockedCounts){
  const entries = Object.entries(blockedCounts || {});
  if(!entries.length) return '';
  const tierFor = (label) => _QUEUE_TIER_MAP[String(label).toLowerCase().trim()] || 'wait';
  const chips = entries.map(([key, value]) =>
    `<span class="schedulerChip" data-tier="${esc(tierFor(key))}">${esc(key)}: ${Number(value)}</span>`
  ).join('');
  return `<div class="schedulerChips">${chips}</div>`;
}

function _schedulerStatRowHtml(data){
  const eligible = Number(data?.next_eligible_count || 0);
  const activeRuns = Number(data?.running_count || 0);
  const blockedEntries = Object.entries(data?.blocked_counts || {});
  const blockedTotal = blockedEntries.reduce((s, [, v]) => s + Number(v), 0);
  const failedItems = uploadQueueManagerItems.filter((x) => String(x.status || '').toLowerCase() === 'failed');
  const fatalCount = failedItems.filter((x) => {
    const tier = classifyQueueBlockReason(String(x.blocked_reason || ''), 'failed');
    return tier === 'fatal';
  }).length;
  const retryableCount = failedItems.length - fatalCount;
  const parts = [
    `<span class="schedulerStatChip"><strong>${eligible}</strong> ready</span>`,
    `<span class="schedulerStatChip"><strong>${activeRuns}</strong> running</span>`,
    blockedTotal > 0 ? `<span class="schedulerStatChip"><strong>${blockedTotal}</strong> blocked</span>` : '',
    retryableCount > 0 ? `<span class="schedulerStatChip" style="color:#fca5a5"><strong>${retryableCount}</strong> retryable</span>` : '',
    fatalCount > 0 ? `<span class="schedulerStatChip" style="color:#94a3b8"><strong>${fatalCount}</strong> fatal</span>` : '',
  ].filter(Boolean);
  return `<div class="schedulerStatRow">${parts.join('')}</div>`;
}

function renderUploadSchedulerStatus(data){
  const running = !!(data && (data.running || data.scheduler_enabled || String(data?.scheduler_status || '').toLowerCase() === 'running'));
  const eligible = Number(data?.next_eligible_count || 0);
  const activeRuns = Number(data?.running_count || 0);
  const stateText = running ? 'running' : 'stopped';
  ['upload_scheduler_status_badge', 'upload_scheduler_status_badge_top'].forEach((id) => {
    const badge = qs(id);
    if(badge){ badge.textContent = stateText; badge.dataset.state = stateText; badge.setAttribute('data-state', stateText); }
  });
  ['upload_scheduler_meta', 'upload_scheduler_meta_top'].forEach((id) => {
    const meta = qs(id);
    if(meta) meta.textContent = `Eligible ${eligible} · Running ${activeRuns}`;
  });

  // Update Retry Failed button states
  const failedTotal = uploadQueueManagerItems.filter((x) => String(x.status || '').toLowerCase() === 'failed').length;
  const hasRetryable = uploadQueueManagerItems.some((x) => {
    if(String(x.status || '').toLowerCase() !== 'failed') return false;
    return classifyQueueBlockReason(String(x.blocked_reason || ''), 'failed') !== 'fatal';
  });
  ['retry_failed_btn', 'retry_failed_btn_top'].forEach((id) => {
    const btn = qs(id);
    if(btn){
      btn.disabled = !hasRetryable;
      btn.title = hasRetryable ? `Reset ${failedTotal} failed item(s) to pending` : 'No retryable failed items';
    }
  });

  const blocked = qs('upload_scheduler_blocked');
  if(blocked){
    const statRow = _schedulerStatRowHtml(data);
    const blockedCounts = data?.blocked_counts || {};
    const hasBlocked = Object.keys(blockedCounts).length > 0;
    if(!running && activeRuns === 0 && eligible === 0 && !hasBlocked){
      blocked.innerHTML = `${statRow}<span style="color:var(--text-muted);font-size:12px">No active uploads. Start scheduler to begin processing queue.</span>`;
    } else if(!running && eligible > 0){
      blocked.innerHTML = `${statRow}<span style="color:var(--text-muted);font-size:12px">${eligible} item${eligible === 1 ? '' : 's'} ready. Start scheduler to begin processing queue.</span>`;
    } else {
      blocked.innerHTML = statRow + _schedulerBlockedSummary(blockedCounts);
    }
  }
}

async function loadUploadSchedulerStatus(){
  try{
    const res = await fetch('/api/upload/scheduler/status');
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    _cachedSchedulerData = data;
    renderUploadSchedulerStatus(data);
  }catch(e){
    const blocked = qs('upload_scheduler_blocked');
    if(blocked) blocked.textContent = `Scheduler status unavailable: ${e.message || e}`;
  }
}

async function startUploadScheduler(){
  try{
    const res = await fetch('/api/upload/scheduler/start', {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    showToast('Scheduler started', 'success');
    await loadUploadSchedulerStatus();
    await loadUploadQueueManager();
  }catch(e){
    showToast(`Scheduler start failed: ${e.message || e}`, 'error');
  }
}

async function stopUploadScheduler(){
  try{
    const res = await fetch('/api/upload/scheduler/stop', {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    showToast('Scheduler stopped', 'success');
    await loadUploadSchedulerStatus();
  }catch(e){
    showToast(`Scheduler stop failed: ${e.message || e}`, 'error');
  }
}

async function retryFailedUploads(){
  ['retry_failed_btn', 'retry_failed_btn_top'].forEach((id) => {
    const btn = qs(id);
    if(btn){ btn.disabled = true; btn.textContent = 'Retrying…'; }
  });
  try{
    const res = await fetch('/api/upload/queue/retry-failed', {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    const count = Number(data.reset_count || 0);
    showToast(count > 0 ? `${count} failed item${count === 1 ? '' : 's'} reset to pending` : 'No retryable failed items found', count > 0 ? 'success' : 'info');
    await loadUploadQueueManager();
    await loadUploadSchedulerStatus();
  }catch(e){
    showToast(`Retry failed: ${e.message || e}`, 'error');
    // Restore button state since loadUploadSchedulerStatus (which normally does this) wasn't reached
    renderUploadSchedulerStatus(_cachedSchedulerData);
  }finally{
    ['retry_failed_btn', 'retry_failed_btn_top'].forEach((id) => {
      const btn = qs(id);
      if(btn) btn.textContent = 'Retry Failed';
    });
  }
}

async function runUploadSchedulerTick(){
  try{
    const res = await fetch('/api/upload/scheduler/tick', {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    showToast(data.picked_queue_ids?.length ? 'Scheduler tick dispatched uploads' : 'Scheduler tick found no eligible items', 'info');
    await loadUploadSchedulerStatus();
    await loadUploadQueueManager();
  }catch(e){
    showToast(`Scheduler tick failed: ${e.message || e}`, 'error');
  }
}

function initUploadSchedulerUi(){ loadUploadSchedulerStatus(); }
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', initUploadSchedulerUi);
}else{
  initUploadSchedulerUi();
}

// =============================================================================
// UX FLOW INIT
// =============================================================================

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

// =============================================================================
// BATCH ASSIGN — Phase 3
// =============================================================================

function _isBatchEligibleAccount(account){
  if(!account) return {eligible: false, reason: 'No account'};
  const status = String(account.status || '').toLowerCase();
  const loginState = String(account.login_state || '').toLowerCase();
  if(status === 'banned') return {eligible: false, reason: 'Banned'};
  if(status === 'disabled') return {eligible: false, reason: 'Disabled'};
  if(['logged_out', 'challenge', 'expired'].includes(loginState)) return {eligible: false, reason: 'Login required'};
  const dailyLimit = Number(account.daily_limit || 0);
  const todayCount = Number(account.today_count || 0);
  if(dailyLimit > 0 && todayCount >= dailyLimit) return {eligible: false, reason: 'Daily limit reached'};
  const health = _computeAccountHealth(account);
  if(health.status === 'risky' && !_batchIncludeRisky) return {eligible: false, reason: `Risky: ${health.reasons.join(', ')}`};
  return {eligible: true, reason: ''};
}

function toggleUploadVideoSelection(videoId, checked){
  if(checked){
    selectedUploadVideoIds.add(String(videoId));
  }else{
    selectedUploadVideoIds.delete(String(videoId));
  }
  _updateBatchAssignButton();
  _syncSelectAllCheckbox();
}

function toggleSelectAllVideos(checked){
  if(checked){
    uploadVideoLibraryItems.forEach((item) => {
      if(String(item.status || '').toLowerCase() === 'ready' && item.video_path){
        selectedUploadVideoIds.add(String(item.video_id));
      }
    });
  }else{
    selectedUploadVideoIds.clear();
  }
  renderUploadVideoLibrary(uploadVideoLibraryItems);
}

function _syncSelectAllCheckbox(){
  const allChk = qs('uvl_select_all');
  if(!allChk) return;
  const eligible = uploadVideoLibraryItems.filter(
    (item) => String(item.status || '').toLowerCase() === 'ready' && !!item.video_path
  );
  if(!eligible.length){ allChk.checked = false; allChk.indeterminate = false; return; }
  const selectedCount = eligible.filter((item) => selectedUploadVideoIds.has(String(item.video_id))).length;
  if(selectedCount === 0){ allChk.checked = false; allChk.indeterminate = false; }
  else if(selectedCount === eligible.length){ allChk.checked = true; allChk.indeterminate = false; }
  else { allChk.checked = false; allChk.indeterminate = true; }
}

function _updateBatchAssignButton(){
  const btn = qs('uvl_batch_assign_btn');
  const countEl = qs('uvl_batch_count');
  const hintEl = qs('uvl_select_hint');
  if(!btn) return;
  const count = selectedUploadVideoIds.size;
  btn.disabled = count === 0;
  if(countEl) countEl.textContent = count > 0 ? `(${count})` : '';
  if(hintEl) hintEl.hidden = count > 0 || !uploadVideoLibraryItems.length;
}

function openBatchAssignModal(){
  if(!selectedUploadVideoIds.size){ showToast('Select at least one ready video first', 'info'); return; }
  _batchModalStep = 'configure';
  _batchSelectedAccountIds = new Set();
  _batchMode = 'smart';
  _batchSpaceMinutes = 30;
  _batchPreviewData = null;
  const modal = document.getElementById('batch_assign_modal');
  if(modal) modal.hidden = false;
  _renderBatchModalContent();
}

function closeBatchAssignModal(){
  const modal = document.getElementById('batch_assign_modal');
  if(modal) modal.hidden = true;
  _batchPreviewData = null;
}

function _renderBatchModalContent(){
  const panel = qs('batch_assign_modal_panel');
  if(!panel) return;
  panel.innerHTML = _batchModalStep === 'configure'
    ? _buildBatchConfigHtml()
    : _buildBatchPreviewHtml(_batchPreviewData);
  if(_batchModalStep === 'configure'){
    _batchSelectedAccountIds.forEach((id) => {
      const chk = panel.querySelector(`[data-account-id="${CSS.escape(id)}"]`);
      if(chk) chk.checked = true;
    });
    const modeEl = panel.querySelector(`input[name="batch_mode"][value="${_batchMode}"]`);
    if(modeEl) modeEl.checked = true;
    const spaceEl = qs('batch_space_minutes');
    if(spaceEl) spaceEl.value = _batchSpaceMinutes;
  }
}

function _buildBatchConfigHtml(){
  const videoCount = selectedUploadVideoIds.size;
  const accountRows = uploadAccountManagerItems.map((acc) => {
    const health = _computeAccountHealth(acc);
    const {eligible, reason} = _isBatchEligibleAccount(acc);
    const dailyLimit = Number(acc.daily_limit || 0);
    const todayCount = Number(acc.today_count || 0);
    const usageLine = dailyLimit > 0 ? `Today ${todayCount}/${dailyLimit}` : 'No daily limit';
    const cooldownMin = Number(acc.cooldown_minutes || 0);
    const cooldownLine = cooldownMin > 0 ? `Cooldown ${cooldownMin}m` : 'No cooldown';
    const name = esc(acc.display_name || acc.account_key || acc.account_id);
    return `
      <label class="batchAccountRow${eligible ? '' : ' batchAccountRowDisabled'}" title="${eligible ? '' : esc(reason)}">
        <input type="checkbox" class="batchAccountChk" data-account-id="${esc(acc.account_id)}"
          ${eligible ? '' : 'disabled'}
          onchange="_onBatchAccountToggle(this)">
        <div class="batchAccountInfo">
          <div class="batchAccountName">${name} ${_healthBadgeHtml(health)}</div>
          <div class="batchAccountMeta">${esc(usageLine)} · ${esc(cooldownLine)}</div>
          ${!eligible ? `<div class="batchAccountDisabledReason">${esc(reason)}</div>` : ''}
        </div>
      </label>
    `;
  }).join('');

  return `
    <div class="uploadModalHeader">
      <div class="uploadModalTitle">Batch Assign Videos</div>
      <button class="ghostButton uploadModalClose" type="button" onclick="closeBatchAssignModal()">×</button>
    </div>
    <div class="batchModalBody">
      <div class="batchSelectedCount">Selected: <strong>${videoCount}</strong> video${videoCount !== 1 ? 's' : ''}</div>
      <div class="batchSection">
        <div class="batchSectionTitle">Accounts
          <label class="batchRiskyToggle" title="Risky accounts are excluded by default">
            <input type="checkbox" id="batch_include_risky" ${_batchIncludeRisky ? 'checked' : ''}
              onchange="_onBatchIncludeRiskyToggle(this.checked)">
            Include risky accounts
          </label>
        </div>
        <div class="batchAccountList" id="batch_account_list">
          ${accountRows || '<div class="batchNoAccounts">No accounts available. Create an account first.</div>'}
        </div>
      </div>
      <div class="batchSection">
        <div class="batchSectionTitle">Distribution Mode</div>
        <label class="batchRadioRow"><input type="radio" name="batch_mode" value="smart" checked> Smart distribute across selected accounts</label>
        <label class="batchRadioRow"><input type="radio" name="batch_mode" value="all_to_one"> All videos to first selected account</label>
      </div>
      <div class="batchSection">
        <div class="batchSectionTitle">Schedule</div>
        <label class="batchRadioRow">
          <input type="radio" name="batch_schedule" value="auto_space" checked>
          Auto-space every <input type="number" class="batchInlineInput" id="batch_space_minutes" value="30" min="1" max="480"> minutes
        </label>
        <label class="batchRadioRow"><input type="radio" name="batch_schedule" value="next_available"> Next available (no spacing)</label>
      </div>
    </div>
    <div class="batchModalFooter">
      <button class="ghostButton" type="button" onclick="closeBatchAssignModal()">Cancel</button>
      <button class="primaryButton" type="button" onclick="previewBatchAssign()">Preview</button>
    </div>
  `;
}

function _onBatchIncludeRiskyToggle(checked){
  _batchIncludeRisky = !!checked;
  _renderBatchModalContent();
}

function _onBatchAccountToggle(chk){
  const id = chk.dataset.accountId;
  if(!id) return;
  if(chk.checked){ _batchSelectedAccountIds.add(id); }else{ _batchSelectedAccountIds.delete(id); }
}

function previewBatchAssign(){
  const panel = qs('batch_assign_modal_panel');
  if(!panel) return;
  _batchSelectedAccountIds = new Set();
  panel.querySelectorAll('.batchAccountChk:checked').forEach((chk) => {
    if(chk.dataset.accountId) _batchSelectedAccountIds.add(chk.dataset.accountId);
  });
  const modeEl = panel.querySelector('input[name="batch_mode"]:checked');
  _batchMode = modeEl ? modeEl.value : 'smart';
  const scheduleEl = panel.querySelector('input[name="batch_schedule"]:checked');
  const useSpacing = !scheduleEl || scheduleEl.value === 'auto_space';
  const spaceEl = qs('batch_space_minutes');
  _batchSpaceMinutes = useSpacing ? (parseInt(spaceEl ? spaceEl.value : '30', 10) || 30) : 0;
  if(!_batchSelectedAccountIds.size){ showToast('Select at least one account', 'info'); return; }
  const result = computeBatchAssignments(
    Array.from(selectedUploadVideoIds),
    Array.from(_batchSelectedAccountIds),
    {mode: _batchMode, spaceMinutes: _batchSpaceMinutes}
  );
  _batchPreviewData = result;
  _batchModalStep = 'preview';
  _renderBatchModalContent();
}

function goBackBatchConfig(){
  _batchModalStep = 'configure';
  _renderBatchModalContent();
}

function computeBatchAssignments(videoIds, accountIds, options){
  const mode = options.mode || 'smart';
  const spaceMinutes = Number(options.spaceMinutes) || 0;
  const assignments = [];
  const skipped = [];
  const warnings = [];
  const now = Date.now();

  const videos = videoIds
    .map((id) => uploadVideoLibraryItems.find((v) => String(v.video_id) === String(id)))
    .filter(Boolean);
  const accounts = accountIds
    .map((id) => uploadAccountManagerItems.find((a) => String(a.account_id) === String(id)))
    .filter(Boolean);

  if(!accounts.length){
    videos.forEach((v) => skipped.push({video_id: v.video_id, reason: 'no eligible account'}));
    return {assignments, skipped, warnings};
  }

  const accountState = {};
  for(const acc of accounts){
    const dailyLimit = Number(acc.daily_limit || 0);
    const todayCount = Number(acc.today_count || 0);
    const remaining = dailyLimit > 0 ? Math.max(0, dailyLimit - todayCount) : Infinity;
    const cooldownMs = Number(acc.cooldown_minutes || 0) * 60 * 1000;
    accountState[acc.account_id] = {
      remaining,
      nextMs: now + cooldownMs,
      assigned: 0,
    };
  }

  const existingPairs = new Set(
    uploadQueueManagerItems
      .filter((q) => !['cancelled', 'success'].includes(String(q.status || '').toLowerCase()))
      .map((q) => `${q.video_id}|${q.account_id}`)
  );

  function tryAssign(video, acc){
    const state = accountState[acc.account_id];
    if(existingPairs.has(`${video.video_id}|${acc.account_id}`)) return 'duplicate';
    if(state.remaining !== Infinity && state.assigned >= state.remaining) return 'quota';
    const scheduledAt = new Date(state.nextMs).toISOString();
    if(spaceMinutes > 0) state.nextMs += spaceMinutes * 60 * 1000;
    state.assigned++;
    assignments.push({video_id: video.video_id, account_id: acc.account_id, scheduled_at: scheduledAt, priority: 0, reason: 'assigned'});
    return 'ok';
  }

  if(mode === 'all_to_one'){
    const acc = accounts[0];
    for(const video of videos){
      const r = tryAssign(video, acc);
      if(r === 'duplicate') skipped.push({video_id: video.video_id, reason: 'already queued'});
      else if(r === 'quota') skipped.push({video_id: video.video_id, reason: 'daily limit reached'});
    }
  }else{
    const sorted = [...accounts].sort((a, b) => {
      const rA = accountState[a.account_id].remaining === Infinity ? 9999 : accountState[a.account_id].remaining;
      const rB = accountState[b.account_id].remaining === Infinity ? 9999 : accountState[b.account_id].remaining;
      return rB - rA;
    });
    let idx = 0;
    for(const video of videos){
      let assigned = false;
      for(let attempt = 0; attempt < sorted.length; attempt++){
        const acc = sorted[(idx + attempt) % sorted.length];
        if(tryAssign(video, acc) === 'ok'){ idx = (idx + 1) % sorted.length; assigned = true; break; }
      }
      if(!assigned){
        const allDup = accounts.every((a) => existingPairs.has(`${video.video_id}|${a.account_id}`));
        const allFull = accounts.every((a) => {
          const s = accountState[a.account_id];
          return s.remaining !== Infinity && s.assigned >= s.remaining;
        });
        skipped.push({video_id: video.video_id, reason: allDup ? 'already queued' : (allFull ? 'no remaining quota' : 'no eligible account')});
      }
    }
  }

  for(const acc of accounts){
    const s = accountState[acc.account_id];
    if(s.remaining !== Infinity && s.remaining - s.assigned <= 1 && s.assigned > 0){
      warnings.push(`${acc.display_name || acc.account_key} is near daily limit`);
    }
  }
  return {assignments, skipped, warnings};
}

function _buildBatchPreviewHtml(result){
  if(!result) return '<div class="batchModalBody"><div class="batchNoAccounts">No preview data.</div></div>';
  const {assignments, skipped, warnings} = result;

  const byAccount = {};
  for(const a of assignments){
    if(!byAccount[a.account_id]) byAccount[a.account_id] = [];
    byAccount[a.account_id].push(a);
  }

  const groupHtml = Object.entries(byAccount).map(([accountId, items]) => {
    const acc = uploadAccountManagerItems.find((a) => String(a.account_id) === String(accountId));
    const accName = acc ? (acc.display_name || acc.account_key || accountId) : accountId;
    const rows = items.map((item) => {
      const video = uploadVideoLibraryItems.find((v) => String(v.video_id) === String(item.video_id));
      const videoName = video ? (video.file_name || String(video.video_path || '').split(/[\\/]/).pop() || item.video_id) : item.video_id;
      const timeStr = item.scheduled_at ? item.scheduled_at.replace('T', ' ').slice(0, 16) : 'ASAP';
      return `<div class="batchPreviewItem"><span class="batchPreviewItemName">${esc(videoName)}</span><span class="batchPreviewItemTime">${esc(timeStr)}</span></div>`;
    }).join('');
    return `<div class="batchPreviewGroup"><div class="batchPreviewGroupTitle">${esc(accName)}</div>${rows}</div>`;
  }).join('');

  const skippedHtml = skipped.length ? `
    <div class="batchSection">
      <div class="batchSectionTitle batchSectionTitleWarn">Skipped (${skipped.length})</div>
      <div class="batchSkippedList">
        ${skipped.map((s) => {
          const video = uploadVideoLibraryItems.find((v) => String(v.video_id) === String(s.video_id));
          const name = video ? (video.file_name || String(video.video_path || '').split(/[\\/]/).pop() || s.video_id) : s.video_id;
          return `<div class="batchSkippedItem"><span>${esc(name)}</span><span class="batchSkipReason">${esc(s.reason)}</span></div>`;
        }).join('')}
      </div>
    </div>` : '';

  const warningsHtml = warnings.length ? `
    <div class="batchSection">
      <div class="batchSectionTitle batchSectionTitleWarn">Warnings (${warnings.length})</div>
      ${warnings.map((w) => `<div class="batchWarningItem">${esc(w)}</div>`).join('')}
    </div>` : '';

  return `
    <div class="uploadModalHeader">
      <div class="uploadModalTitle">Batch Assign — Preview</div>
      <button class="ghostButton uploadModalClose" type="button" onclick="closeBatchAssignModal()">×</button>
    </div>
    <div class="batchModalBody">
      <div class="batchPreviewSummary">
        <div class="batchPreviewStat batchPreviewStatOk">Ready to enqueue: <strong>${assignments.length}</strong></div>
        ${skipped.length ? `<div class="batchPreviewStat batchPreviewStatSkip">Skipped: <strong>${skipped.length}</strong></div>` : ''}
        ${warnings.length ? `<div class="batchPreviewStat batchPreviewStatWarn">Warnings: <strong>${warnings.length}</strong></div>` : ''}
      </div>
      ${assignments.length ? `
        <div class="batchSection">
          <div class="batchSectionTitle">Assignments by Account</div>
          <div class="batchPreviewGroups">${groupHtml}</div>
        </div>` : '<div class="batchNoAccounts">No valid assignments. Check accounts and quotas.</div>'}
      ${skippedHtml}
      ${warningsHtml}
    </div>
    <div class="batchModalFooter">
      <button class="ghostButton" type="button" onclick="goBackBatchConfig()">Back</button>
      <button class="primaryButton" type="button" id="batch_enqueue_btn"
        onclick="executeBatchEnqueue()" ${assignments.length === 0 ? 'disabled' : ''}>
        Enqueue ${assignments.length} Video${assignments.length !== 1 ? 's' : ''}
      </button>
    </div>
  `;
}

async function createQueueItemFromAssignment(assignment){
  const video = uploadVideoLibraryItems.find((v) => String(v.video_id) === String(assignment.video_id));
  const payload = {
    video_id: String(assignment.video_id),
    account_id: String(assignment.account_id),
    scheduled_at: assignment.scheduled_at || '',
    priority: Number(assignment.priority) || 0,
    status: 'scheduled',
    caption: video ? (video.caption || '') : '',
    hashtags: video ? (video.hashtags || []) : [],
  };
  const res = await fetch('/api/upload/queue/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if(!res.ok) throw new Error(_formatApiError(data.detail));
  return data;
}

function _batchAggressiveWarning(assignments){
  const warnings = [];
  const byAccount = {};
  for(const a of assignments){
    const key = String(a.account_id || '');
    if(!byAccount[key]) byAccount[key] = [];
    byAccount[key].push(a);
  }
  for(const [accountId, items] of Object.entries(byAccount)){
    // Check if any 3 items are scheduled within a 2-hour window
    const times = items
      .map((x) => x.scheduled_at ? new Date(x.scheduled_at).getTime() : null)
      .filter((t) => t && !isNaN(t))
      .sort((a, b) => a - b);
    for(let i = 0; i + 2 < times.length; i++){
      if(times[i + 2] - times[i] < 2 * 60 * 60 * 1000){
        const account = uploadAccountManagerItems.find((x) => String(x.account_id || '') === accountId);
        const name = (account && (account.display_name || account.account_key)) || accountId;
        warnings.push(`Account "${name}" has 3+ uploads scheduled within 2 hours — may trigger rate limits.`);
        break;
      }
    }
    // Check daily limit proximity
    const account = uploadAccountManagerItems.find((x) => String(x.account_id || '') === accountId);
    if(account){
      const dailyLimit = Number(account.daily_limit || 0);
      const todayCount = Number(account.today_count || 0);
      if(dailyLimit > 0 && (todayCount + items.length) > dailyLimit * 0.8){
        const name = account.display_name || account.account_key || accountId;
        warnings.push(`Account "${name}" will exceed 80% of its daily upload limit (${dailyLimit}).`);
      }
    }
  }
  return warnings;
}

async function executeBatchEnqueue(){
  const btn = qs('batch_enqueue_btn');
  if(btn){ btn.disabled = true; btn.textContent = 'Enqueuing…'; }
  if(!_batchPreviewData || !_batchPreviewData.assignments.length){
    showToast('Nothing to enqueue', 'info');
    if(btn){ btn.disabled = false; }
    return;
  }
  const {assignments, skipped} = _batchPreviewData;

  // Phase 5: aggressive schedule warning
  const aggressiveWarns = _batchAggressiveWarning(assignments);
  if(aggressiveWarns.length > 0){
    const msg = `Schedule concern:\n\n${aggressiveWarns.join('\n')}\n\nProceed anyway?`;
    if(!window.confirm(msg)){
      if(btn){ btn.disabled = false; btn.textContent = `Enqueue ${assignments.length} Video${assignments.length !== 1 ? 's' : ''}`; }
      return;
    }
  }
  const results = [];
  for(const assignment of assignments){
    try{
      await createQueueItemFromAssignment(assignment);
      results.push({ok: true, assignment});
    }catch(err){
      results.push({ok: false, assignment, error: err.message || String(err)});
    }
  }
  const succeeded = results.filter((r) => r.ok).length;
  const failed = results.filter((r) => !r.ok).length;
  const totalSkipped = skipped.length;
  closeBatchAssignModal();
  selectedUploadVideoIds.clear();
  _updateBatchAssignButton();
  await loadUploadVideoLibrary();
  await loadUploadQueueManager();
  refreshUploadWorkspace('batch_enqueued');
  setUploadManagerTab('queue');
  if(failed === 0){
    showToast(`${succeeded} video${succeeded !== 1 ? 's' : ''} added to queue.${totalSkipped > 0 ? ` ${totalSkipped} skipped.` : ''}`, 'success');
  }else{
    showToast(`${succeeded} queued, ${failed} failed. See console for details.`, 'error');
    console.warn('[BatchAssign] Failed items:', results.filter((r) => !r.ok));
  }
}

// =============================================================================
// PHASE 6: AUTOMATION LAYER
// =============================================================================

// --- AUTOMATION SETTINGS ---
const _AUTO_DEFAULTS = {
  autoStartScheduler: false,
  excludeRisky: true,
  respectDailyLimit: true,
  respectCooldown: true,
  jitterEnabled: true,
  baseSpacingMinutes: 30,
  jitterMinutes: 5,
  maxPerAccountPerDay: 5,
  acceptRenderOutputs: false,
};
let _autoSettings = {..._AUTO_DEFAULTS};
let _autoPlanData = null;
let _autoPlanExcluded = new Set();

function loadAutomationSettings(){
  try{
    const raw = localStorage.getItem('uploadAutomationSettings');
    if(raw) _autoSettings = {..._AUTO_DEFAULTS, ...JSON.parse(raw)};
  }catch(_){}
  _applyAutoSettingsToUi();
}

function saveAutomationSettings(){
  _readAutoSettingsFromUi();
  try{ localStorage.setItem('uploadAutomationSettings', JSON.stringify(_autoSettings)); }catch(_){}
  renderAutomationDashboard();
}

function _applyAutoSettingsToUi(){
  _setChk('auto_set_exclude_risky',     _autoSettings.excludeRisky);
  _setChk('auto_set_respect_limit',     _autoSettings.respectDailyLimit);
  _setChk('auto_set_respect_cooldown',  _autoSettings.respectCooldown);
  _setChk('auto_set_jitter',            _autoSettings.jitterEnabled);
  _setChk('auto_set_auto_start',        _autoSettings.autoStartScheduler);
  _setChk('auto_set_accept_render',     _autoSettings.acceptRenderOutputs);
  _setVal('auto_set_base_spacing',      _autoSettings.baseSpacingMinutes);
  _setVal('auto_set_jitter_min',        _autoSettings.jitterMinutes);
  _setVal('auto_set_max_per_day',       _autoSettings.maxPerAccountPerDay);
}

function _readAutoSettingsFromUi(){
  _autoSettings.excludeRisky          = _getChk('auto_set_exclude_risky');
  _autoSettings.respectDailyLimit     = _getChk('auto_set_respect_limit');
  _autoSettings.respectCooldown       = _getChk('auto_set_respect_cooldown');
  _autoSettings.jitterEnabled         = _getChk('auto_set_jitter');
  _autoSettings.autoStartScheduler    = _getChk('auto_set_auto_start');
  _autoSettings.acceptRenderOutputs   = _getChk('auto_set_accept_render');
  _autoSettings.baseSpacingMinutes    = Math.max(1,  parseInt(_getVal('auto_set_base_spacing'), 10) || 30);
  _autoSettings.jitterMinutes         = Math.max(0,  parseInt(_getVal('auto_set_jitter_min'),   10) || 5);
  _autoSettings.maxPerAccountPerDay   = Math.max(1,  parseInt(_getVal('auto_set_max_per_day'),  10) || 5);
}

function _getChk(id){ const el = qs(id); return el ? el.checked : false; }
function _setChk(id, val){ const el = qs(id); if(el) el.checked = !!val; }
function _getVal(id){ return String(qs(id)?.value || ''); }
function _setVal(id, val){ const el = qs(id); if(el) el.value = val; }
function _setEl(id, text, state){
  const el = qs(id);
  if(!el) return;
  el.textContent = text;
  if(state !== undefined) el.setAttribute('data-state', state);
}

// --- FEATURE 3: ACCOUNT SCORING ---

function scoreUploadAccount(account){
  if(!account) return {score: -999, reasons: ['No account']};
  const health = _computeAccountHealth(account);
  let score = 0;
  const reasons = [];

  if(health.status === 'healthy')     { score += 50;  reasons.push('+50 healthy'); }
  else if(health.status === 'warning'){ score += 20;  reasons.push('+20 warning'); }
  else if(health.status === 'risky')  { score -= 100; reasons.push('-100 risky'); }

  const dailyLimit = Number(account.daily_limit || 0);
  const todayCount = Number(account.today_count || 0);
  if(dailyLimit > 0){
    const remaining = Math.max(0, dailyLimit - todayCount);
    const quotaScore = Math.min(20, Math.round((remaining / dailyLimit) * 20));
    score += quotaScore;
    if(quotaScore > 0) reasons.push(`+${quotaScore} quota`);
  }else{
    score += 10; reasons.push('+10 unlimited');
  }

  const cooldownMin = Number(account.cooldown_minutes || 0);
  if(cooldownMin > 0){ score -= 20; reasons.push('-20 cooldown active'); }
  else               { score += 10; reasons.push('+10 ready'); }

  if(health.fail_count_24h > 0){
    const p = health.fail_count_24h * 10;
    score -= p; reasons.push(`-${p} failures`);
  }
  if(health.proxy_status === 'failed'){ score -= 50; reasons.push('-50 proxy failed'); }

  const pp = normalizeProfilePath(String(account.profile_path || ''));
  if(pp){
    const hasConflict = uploadAccountManagerItems.some((a) =>
      String(a.account_id) !== String(account.account_id) &&
      normalizeProfilePath(String(a.profile_path || '')) === pp
    );
    if(hasConflict){ score -= 100; reasons.push('-100 profile conflict'); }
  }

  return {score, reasons};
}

function _autoScoreTier(score){
  if(score >= 60) return 'high';
  if(score >= 30) return 'mid';
  if(score >= 0)  return 'low';
  return 'neg';
}

// --- FEATURE 2 SUPPORT: ELIGIBLE ACCOUNTS + READY VIDEOS ---

function _autoEligibleAccounts(){
  return uploadAccountManagerItems.filter((acc) => {
    const status = String(acc.status || '').toLowerCase();
    if(['banned', 'disabled'].includes(status)) return false;
    const loginState = String(acc.login_state || '').toLowerCase();
    if(['logged_out', 'challenge', 'expired'].includes(loginState)) return false;
    if(_autoSettings.excludeRisky && _computeAccountHealth(acc).status === 'risky') return false;
    if(_autoSettings.respectDailyLimit){
      const dl = Number(acc.daily_limit || 0);
      const tc = Number(acc.today_count || 0);
      const cap = dl > 0 ? Math.min(_autoSettings.maxPerAccountPerDay, dl) : _autoSettings.maxPerAccountPerDay;
      if(tc >= cap) return false;
    }
    return true;
  });
}

function _autoReadyVideos(){
  const statuses = new Set(['ready']);
  if(_autoSettings.acceptRenderOutputs) statuses.add('render_ready');
  return uploadVideoLibraryItems.filter((v) => statuses.has(String(v.status || '').toLowerCase()) && !!v.video_path);
}

// --- FEATURE 4: SAFE SCHEDULING + SCORING ---

function computeAutoAssignments(){
  const accounts = _autoEligibleAccounts();
  const videos = _autoReadyVideos();

  if(!accounts.length || !videos.length){
    const reason = !accounts.length ? 'no eligible accounts' : 'no ready videos';
    return {
      assignments: [],
      skipped: videos.map((v) => ({video_id: v.video_id, reason})),
      warnings: [!accounts.length ? 'No eligible accounts found.' : 'No ready videos found.'],
      scores: {},
    };
  }

  const scores = {};
  accounts.forEach((acc) => { scores[acc.account_id] = scoreUploadAccount(acc); });
  const sortedIds = [...accounts]
    .sort((a, b) => scores[b.account_id].score - scores[a.account_id].score)
    .map((a) => a.account_id);

  const videoIds = videos.map((v) => v.video_id);
  const result = computeBatchAssignments(videoIds, sortedIds, {mode: 'smart', spaceMinutes: _autoSettings.baseSpacingMinutes});

  if(_autoSettings.jitterEnabled && _autoSettings.jitterMinutes > 0){
    const jMs = _autoSettings.jitterMinutes * 60 * 1000;
    result.assignments.forEach((a) => {
      if(a.scheduled_at){
        const t = new Date(a.scheduled_at).getTime();
        const offset = Math.round((Math.random() * 2 - 1) * jMs);
        a.scheduled_at = new Date(Math.max(Date.now() + 30000, t + offset)).toISOString();
      }
    });
  }

  return {...result, scores};
}

// --- FEATURE 7: SAFETY WARNINGS ---

function _autoSafetyWarnings(assignments, accounts){
  const warnings = [];
  if(!accounts.length) return ['No eligible accounts — check account status and automation settings.'];

  const healthyCount = accounts.filter((a) => _computeAccountHealth(a).status === 'healthy').length;
  if(healthyCount === 0) warnings.push('No healthy accounts in plan — all eligible accounts are in warning or risky state.');

  if(_autoSettings.baseSpacingMinutes < 15) warnings.push(`Schedule spacing is ${_autoSettings.baseSpacingMinutes}m — below the 15-minute safe minimum may trigger rate limits.`);

  if(!_autoSettings.excludeRisky){
    const riskyCount = accounts.filter((a) => _computeAccountHealth(a).status === 'risky').length;
    if(riskyCount > 0) warnings.push(`${riskyCount} risky account(s) included in this plan. Review carefully before confirming.`);
  }

  const proxyFailed = accounts.filter((a) => _computeAccountHealth(a).proxy_status === 'failed');
  if(proxyFailed.length) warnings.push(`${proxyFailed.length} account(s) have proxy failures — uploads may fail.`);

  const conflicts = accounts.filter((a) => {
    const norm = normalizeProfilePath(String(a.profile_path || ''));
    if(!norm) return false;
    return uploadAccountManagerItems.some((b) =>
      String(b.account_id) !== String(a.account_id) && normalizeProfilePath(String(b.profile_path || '')) === norm
    );
  });
  if(conflicts.length) warnings.push(`${conflicts.length} account(s) have profile path conflicts — isolation may be broken.`);

  const totalQuota = accounts.reduce((s, acc) => {
    const dl = Number(acc.daily_limit || 0);
    const tc = Number(acc.today_count || 0);
    return s + (dl > 0 ? Math.max(0, dl - tc) : _autoSettings.maxPerAccountPerDay);
  }, 0);
  const readyCount = _autoReadyVideos().length;
  if(readyCount > totalQuota * 1.5) warnings.push(`${readyCount} ready videos but only ~${totalQuota} quota slots — many will be skipped.`);

  warnings.push(..._batchAggressiveWarning(assignments));
  return warnings;
}

// --- FEATURE 6: AUTOMATION DASHBOARD ---

function renderAutomationDashboard(){
  const eligible = _autoEligibleAccounts();
  const ready = _autoReadyVideos();
  const allAccounts = uploadAccountManagerItems;

  const riskyAll = allAccounts.filter((a) => _computeAccountHealth(a).status === 'risky');
  const riskyExcluded = _autoSettings.excludeRisky ? riskyAll.length : 0;

  const totalQuota = eligible.reduce((sum, acc) => {
    const dl = Number(acc.daily_limit || 0);
    const tc = Number(acc.today_count || 0);
    const cap = dl > 0 ? Math.max(0, Math.min(_autoSettings.maxPerAccountPerDay, dl - tc)) : _autoSettings.maxPerAccountPerDay;
    return sum + cap;
  }, 0);

  const estUploads = Math.min(ready.length, totalQuota);

  const minCooldownMs = eligible.reduce((min, acc) => {
    const cm = Number(acc.cooldown_minutes || 0) * 60000;
    return Math.min(min, cm);
  }, Infinity);
  const nextSlotMs = Date.now() + (isFinite(minCooldownMs) ? minCooldownMs : 0) + _autoSettings.baseSpacingMinutes * 60000;
  const nextSlotStr = eligible.length > 0
    ? new Date(nextSlotMs).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    : '–';

  _setEl('auto_dash_ready',    String(ready.length),    ready.length > 0 ? 'ok' : 'none');
  _setEl('auto_dash_accounts', String(eligible.length), eligible.length > 0 ? 'ok' : 'none');
  _setEl('auto_dash_est',      String(estUploads),      estUploads > 0 ? 'ok' : 'none');
  _setEl('auto_dash_risky',    String(riskyExcluded),   riskyExcluded > 0 ? 'warn' : 'ok');
  _setEl('auto_dash_next',     nextSlotStr,             eligible.length > 0 ? 'ok' : 'none');
  _setEl('auto_dash_quota',    String(isFinite(totalQuota) ? totalQuota : '∞'), totalQuota > 0 ? 'ok' : 'none');
}

// --- FEATURE 2: AUTO PLAN READY VIDEOS ---

function autoPlanReadyVideos(){
  _readAutoSettingsFromUi();
  const accounts = _autoEligibleAccounts();
  const videos = _autoReadyVideos();

  if(!videos.length){
    showToast('No ready videos found. Add videos to the library first.', 'info');
    return;
  }
  if(!accounts.length){
    showToast('No eligible accounts found. Check account status or adjust automation settings.', 'info');
    return;
  }

  const result = computeAutoAssignments();
  const warnings = _autoSafetyWarnings(result.assignments, accounts);
  _autoPlanData = {...result, safetyWarnings: warnings};
  _autoPlanExcluded = new Set();

  const modal = document.getElementById('auto_plan_modal');
  if(modal){ modal.hidden = false; _renderAutoPlanModal(); }
}

function closeAutoPlanModal(){
  const modal = document.getElementById('auto_plan_modal');
  if(modal) modal.hidden = true;
  _autoPlanData = null;
  _autoPlanExcluded = new Set();
}

function toggleAutoPlanExclude(key, included){
  if(included){ _autoPlanExcluded.delete(key); }else{ _autoPlanExcluded.add(key); }
  _renderAutoPlanModal();
}

function _renderAutoPlanModal(){
  const panel = qs('auto_plan_modal_panel');
  if(!panel) return;
  panel.innerHTML = _buildAutoPlanPreviewHtml(_autoPlanData);
}

// --- FEATURE 8: MANUAL OVERRIDE (EXCLUDE) + PREVIEW ---

function _buildAutoPlanPreviewHtml(result){
  if(!result) return '';
  const {assignments = [], skipped = [], safetyWarnings = [], scores = {}} = result;

  const activeAssignments = assignments.filter((a) => !_autoPlanExcluded.has(`${a.video_id}|${a.account_id}`));

  const byAccount = {};
  for(const a of assignments){
    if(!byAccount[a.account_id]) byAccount[a.account_id] = [];
    byAccount[a.account_id].push(a);
  }

  const groupHtml = Object.entries(byAccount).map(([accountId, items]) => {
    const acc = uploadAccountManagerItems.find((a) => String(a.account_id) === String(accountId));
    const accName = acc ? (acc.display_name || acc.account_key || accountId) : accountId;
    const scoreData = scores[accountId];
    const scoreTier = scoreData ? _autoScoreTier(scoreData.score) : 'low';
    const scoreTooltip = scoreData ? scoreData.reasons.join(', ') : '';
    const scoreNum = scoreData ? scoreData.score : '?';
    const dl = acc ? Number(acc.daily_limit || 0) : 0;
    const tc = acc ? Number(acc.today_count || 0) : 0;
    const slotsLeft = dl > 0 ? Math.max(0, dl - tc) : '∞';

    const rows = items.map((item) => {
      const video = uploadVideoLibraryItems.find((v) => String(v.video_id) === String(item.video_id));
      const vname = video ? (video.file_name || String(video.video_path || '').split(/[\\/]/).pop() || item.video_id) : item.video_id;
      const tStr = item.scheduled_at ? item.scheduled_at.replace('T', ' ').slice(0, 16) : 'ASAP';
      const key = `${item.video_id}|${item.account_id}`;
      const excluded = _autoPlanExcluded.has(key);
      return `
        <div class="autoPlanExcludeRow${excluded ? ' autoPlanExcluded' : ''}">
          <input type="checkbox" class="autoPlanExcludeChk" title="Include in enqueue"
            ${excluded ? '' : 'checked'}
            onchange="toggleAutoPlanExclude('${esc(key)}', this.checked)">
          <span class="batchPreviewItemName">${esc(vname)}</span>
          <span class="batchPreviewItemTime">${esc(tStr)}</span>
        </div>`;
    }).join('');

    return `
      <div class="batchPreviewGroup">
        <div class="batchPreviewGroupTitle">
          ${esc(accName)}
          <span class="autoScoreBadge" data-tier="${esc(scoreTier)}" title="${esc(scoreTooltip)}">Score ${esc(String(scoreNum))}</span>
          <span style="color:var(--text-muted);font-size:11px;font-weight:400;margin-left:6px">${slotsLeft === '∞' ? 'unlimited' : `${slotsLeft} slot${slotsLeft !== 1 ? 's' : ''} left`}</span>
        </div>
        ${rows}
      </div>`;
  }).join('');

  const safeWarnHtml = safetyWarnings.length ? `
    <div class="batchSection">
      <div class="batchSectionTitle batchSectionTitleWarn">Safety Warnings (${safetyWarnings.length})</div>
      ${safetyWarnings.map((w) => `<div class="batchWarningItem">${esc(w)}</div>`).join('')}
    </div>` : '';

  const skippedHtml = skipped.length ? `
    <div class="batchSection">
      <div class="batchSectionTitle batchSectionTitleWarn">Skipped (${skipped.length})</div>
      <div class="batchSkippedList">
        ${skipped.map((s) => {
          const video = uploadVideoLibraryItems.find((v) => String(v.video_id) === String(s.video_id));
          const name = video ? (video.file_name || String(video.video_path || '').split(/[\\/]/).pop() || s.video_id) : s.video_id;
          return `<div class="batchSkippedItem"><span>${esc(name)}</span><span class="batchSkipReason">${esc(s.reason)}</span></div>`;
        }).join('')}
      </div>
    </div>` : '';

  const confirmCount = activeAssignments.length;
  return `
    <div class="uploadModalHeader">
      <div class="uploadModalTitle">Auto Plan — Review &amp; Confirm</div>
      <button class="ghostButton uploadModalClose" type="button" onclick="closeAutoPlanModal()">×</button>
    </div>
    <div class="batchModalBody">
      <div class="autoPlanPreviewNote">Review the auto-generated plan. Uncheck any item to exclude it from the queue. Click Confirm to enqueue.</div>
      <div class="batchPreviewSummary" style="margin-top:8px">
        <div class="batchPreviewStat batchPreviewStatOk">To enqueue: <strong>${confirmCount}</strong></div>
        ${skipped.length ? `<div class="batchPreviewStat batchPreviewStatSkip">Skipped: <strong>${skipped.length}</strong></div>` : ''}
        ${safetyWarnings.length ? `<div class="batchPreviewStat batchPreviewStatWarn">Warnings: <strong>${safetyWarnings.length}</strong></div>` : ''}
      </div>
      ${safeWarnHtml}
      ${assignments.length ? `
        <div class="batchSection">
          <div class="batchSectionTitle">Assignments by Account</div>
          <div class="batchPreviewGroups">${groupHtml}</div>
        </div>` : '<div class="batchNoAccounts">No assignments computed. Check accounts, video library, and settings.</div>'}
      ${skippedHtml}
    </div>
    <div class="batchModalFooter">
      <button class="ghostButton" type="button" onclick="closeAutoPlanModal()">Cancel</button>
      <button class="primaryButton" type="button" id="auto_plan_confirm_btn"
        onclick="executeAutoPlanEnqueue()" ${confirmCount === 0 ? 'disabled' : ''}>
        Confirm &amp; Enqueue ${confirmCount}
      </button>
    </div>`;
}

// --- FEATURE 2 + 4: EXECUTE AUTO PLAN ENQUEUE ---

async function executeAutoPlanEnqueue(){
  if(!_autoPlanData) return;
  const btn = qs('auto_plan_confirm_btn');
  if(btn){ btn.disabled = true; btn.textContent = 'Enqueuing…'; }

  const active = (_autoPlanData.assignments || []).filter((a) => !_autoPlanExcluded.has(`${a.video_id}|${a.account_id}`));
  const results = [];
  for(const assignment of active){
    try{
      await createQueueItemFromAssignment(assignment);
      results.push({ok: true});
    }catch(err){
      results.push({ok: false, error: err.message || String(err)});
    }
  }

  const succeeded = results.filter((r) => r.ok).length;
  const failed = results.filter((r) => !r.ok).length;
  closeAutoPlanModal();

  await loadUploadVideoLibrary();
  await loadUploadQueueManager();
  refreshUploadWorkspace('auto_plan_enqueued');
  setUploadManagerTab('queue');

  if(_autoSettings.autoStartScheduler){
    try{ await fetch('/api/upload/scheduler/start', {method: 'POST'}); await loadUploadSchedulerStatus(); }catch(_){}
  }

  const msg = failed === 0
    ? `Auto plan: ${succeeded} video${succeeded !== 1 ? 's' : ''} queued.`
    : `Auto plan: ${succeeded} queued, ${failed} failed.`;
  showToast(msg, failed === 0 ? 'success' : 'error');
  renderAutomationDashboard();
}

// --- INIT ---

function initAutomationPanel(){
  loadAutomationSettings();
  renderAutomationDashboard();
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', initAutomationPanel);
}else{
  initAutomationPanel();
}
