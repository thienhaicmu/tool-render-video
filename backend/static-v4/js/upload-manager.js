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
function _collapsedDetailSection(label, value){
  const raw = _prettyJson(value);
  if(!raw || raw === '{}' || raw === 'null' || raw === '') return '';
  return `<details class="rawDebugDetails"><summary>${esc(label)}</summary><pre>${esc(raw)}</pre></details>`;
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
  const rotateElig = canRotateProxyForAccount(account);
  const rotateBtn = `<button class="ghostButton" style="font-size:11px;padding:2px 8px;min-height:0" type="button"
    onclick="openProxyRotateModal('${id}')"
    ${rotateElig.ok ? '' : `disabled title="${esc(rotateElig.reason || 'Cannot rotate')}"`}>Rotate Proxy</button>`;
  const hasProfile = !!(account.profile_path || '').trim();
  const hasElectron = typeof window !== 'undefined' && !!window.electronAPI?.openBrowserProfile;
  const openProfileDisabled = !hasProfile;
  const openProfileTitle = !hasProfile ? 'Profile path required — set in Account Settings' :
                           !hasElectron ? 'Desktop app required' : '';

  return `
    <div class="uploadHealthPanel">
      <div class="uploadHealthPanelTitle">Account Health</div>
      ${_healthRowHtml('Login', loginLabel, loginState)}
      <div class="uploadHealthRow">
        <span class="uploadHealthRowLabel">Login Actions</span>
        <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
          <button class="ghostButton" style="font-size:11px;padding:2px 8px;min-height:0" type="button"
            data-open-profile="${id}"
            ${openProfileDisabled ? `disabled title="${esc(openProfileTitle)}"` : `title="${esc(openProfileTitle)}"`}
            onclick="openAccountProfile('${id}')">Open Profile</button>
          <button class="ghostButton" style="font-size:11px;padding:2px 8px;min-height:0" type="button"
            onclick="checkUploadAccountLogin('${id}')">Check Login</button>
          <button class="ghostButton" style="font-size:11px;padding:2px 8px;min-height:0" type="button"
            onclick="markAccountLoggedIn('${id}')">Mark Logged In</button>
        </div>
      </div>
      ${_healthRowHtml('Proxy', proxyLabel, proxyState)}
      <div class="uploadHealthRow">
        <span class="uploadHealthRowLabel">Proxy Actions</span>
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          <button class="ghostButton" style="font-size:11px;padding:2px 8px;min-height:0" type="button"
            onclick="testUploadAccountProxy('${id}')">Test Proxy</button>
          ${rotateBtn}
        </div>
      </div>
      ${proxyResultHtml}
      ${_healthRowHtml('Last Upload', lastLabel, lastState)}
      ${_healthRowHtml('Failures (24h)', String(h.fail_count_24h), failState)}
      ${h.proxy_status === 'failed' && isProxyRelatedFailure(h.reasons.join(' ')) ? '<div class="proxyIssueHint">⚠ Proxy failure detected — rotate proxy to recover.</div>' : ''}
      ${h.status === 'risky' ? '<div class="uploadHealthWarning">⚠ This account may fail uploads</div>' : ''}
    </div>
    ${_profileLoginGuideHtml(account)}
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

function isProxyRelatedFailure(reasonOrError){
  const s = String(reasonOrError || '').toLowerCase();
  return ['proxy','timeout','connection','network','tunnel','socks','dns','econn','etimedout']
    .some((token) => s.includes(token));
}

// =============================================================================
// PHASE 10: BROWSER RUNTIME + LOGIN FLOW
// =============================================================================

function _resolveProxyServerForAccount(account){
  // Prefer manual proxy_config.proxy_server; fall back to pool proxy
  const cfg = account.proxy_config;
  if(cfg && cfg.proxy_server) return String(cfg.proxy_server);
  if(account.proxy_id){
    const p = _proxyPool.find((px) => px.id === String(account.proxy_id));
    if(p && p.host){
      const proto = p.type || 'http';
      const port  = p.port ? `:${p.port}` : '';
      return `${proto}://${p.host}${port}`;
    }
  }
  return '';
}

function _warnIfProfilePathConflict(profilePath, excludeAccountId){
  const norm = normalizeProfilePath(profilePath);
  if(!norm) return null;
  const conflict = uploadAccountManagerItems.find((a) =>
    String(a.account_id) !== String(excludeAccountId) &&
    normalizeProfilePath(String(a.profile_path || '')) === norm
  );
  return conflict ? (conflict.display_name || conflict.account_key || conflict.account_id) : null;
}

async function openAccountProfile(accountId){
  const acc = uploadAccountManagerItems.find((a) => String(a.account_id) === String(accountId));
  if(!acc){ showToast('Account not found', 'error'); return; }
  if(!guardRapidAction()) return;

  const profilePath = String(acc.profile_path || '').trim();
  if(!profilePath){
    showToast('Profile path is required. Set it in Account Settings.', 'error');
    return;
  }

  const conflict = _warnIfProfilePathConflict(profilePath, accountId);
  if(conflict){
    if(!confirm(`Warning: profile path is also used by "${conflict}".\n\nSharing profiles breaks account isolation. Continue anyway?`)) return;
  }

  if(!window.electronAPI?.openBrowserProfile){
    // Web / non-Electron fallback: try to open the profile folder
    if(window.electronAPI?.openPath){
      await window.electronAPI.openPath(profilePath);
      showToast('Desktop runtime required to open browser with profile. Opened profile folder instead.', 'info');
    }else{
      showToast('Open Profile requires the desktop app. Run the Electron shell.', 'error');
    }
    return;
  }

  const proxyServer = _resolveProxyServerForAccount(acc);
  const env = resolveAccountRuntimeEnv(acc);
  const btn = document.querySelector(`button[data-open-profile="${esc(accountId)}"]`);
  if(btn){ btn.disabled = true; btn.textContent = 'Opening…'; }

  try{
    await randomizeBehaviorDelay();
    const result = await window.electronAPI.openBrowserProfile({
      profilePath,
      proxyServer,
      timezone: env.timezone,
      locale: env.locale,
    });
    if(!result || !result.ok){
      showToast(`Failed to open browser: ${result?.error || 'unknown error'}`, 'error');
      return;
    }
    const browserName = result.browser || 'Browser';
    showToast(`${browserName} opened with profile for "${acc.display_name || acc.account_key}". Log in, then click Check Login.`, 'success');
    _auditLog('profile_opened', `Opened profile for ${acc.display_name || acc.account_key || accountId}`);
  }catch(e){
    showToast(`Profile open failed: ${e.message || e}`, 'error');
  }finally{
    if(btn){ btn.disabled = false; btn.textContent = 'Open Profile'; }
  }
}

async function markAccountLoggedIn(accountId){
  const acc = uploadAccountManagerItems.find((a) => String(a.account_id) === String(accountId));
  if(!acc){ showToast('Account not found', 'error'); return; }
  const name = acc.display_name || acc.account_key || accountId;

  if(!confirm(`Mark "${name}" as Logged In?\n\nOnly confirm if you have already signed in inside the browser profile.`)){
    return;
  }

  try{
    const res = await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({login_state: 'logged_in'}),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    await loadUploadAccounts();
    showToast(`"${name}" marked as Logged In.`, 'success');
    _auditLog('login_checked', `Login marked for ${name}`);
  }catch(e){
    showToast(`Mark failed: ${e.message || e}`, 'error');
  }
}

function _profileLoginGuideHtml(account){
  const hasProfile = !!(account.profile_path || '').trim();
  const loginState = String(account.login_state || 'unknown').toLowerCase();
  const isLoggedIn  = loginState === 'logged_in';
  const id = esc(String(account.account_id));

  const step1Done = hasProfile;
  const step3Done = isLoggedIn;

  return `
    <div class="profileLoginGuide">
      <div class="profileLoginGuideTitle">Login Flow</div>
      <ol class="profileLoginGuideSteps">
        <li class="${step1Done ? 'stepDone' : 'stepPending'}">
          Set a <strong>Profile Path</strong> in Account Settings
          ${!hasProfile ? '<span class="stepNote">— required before opening browser</span>' : ''}
        </li>
        <li class="${step1Done ? 'stepPending' : 'stepLocked'}">
          Click <strong>Open Profile</strong> — browser opens with isolated profile + proxy
        </li>
        <li class="${step1Done ? 'stepPending' : 'stepLocked'}">
          Log in to <strong>${esc(account.platform || 'TikTok')}</strong> inside the browser window
        </li>
        <li class="${step3Done ? 'stepDone' : (step1Done ? 'stepPending' : 'stepLocked')}">
          Return here and click <strong>Check Login</strong> to verify session
        </li>
      </ol>
      ${isLoggedIn ? '<div class="profileLoginGuideOk">✓ Session active — scheduler can use this account.</div>' : ''}
    </div>`;
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
  _populateProxyPoolSelect();
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
      <div class="uamAccountCard${selected ? ' active' : ''}${disabled ? ' isDisabled' : ''}"
           data-id="${esc(item.account_id)}"
           data-health="${esc(health.status)}"
           onclick="_selectUploadEntity('account', '${esc(item.account_id)}')">
        <div class="uamCardTop">
          <div class="uamCardName" title="${esc(name)}">${esc(name)}</div>
          <div class="uamHealthBadge ${esc(health.status)}">${esc(health.status)}</div>
        </div>
        <div class="uamCardMeta">${metaLine}</div>
        ${item.profile_conflict ? `<div class="uamAccountItemWarn">${esc(_uamConflictText(item))}</div>` : ''}
        <div class="uamCardActions">
          <button class="uamBtnPrimary" type="button"
                  onclick="event.stopPropagation(); openAccountProfile('${esc(item.account_id)}')">Open</button>
          <button class="uamBtn" type="button"
                  onclick="event.stopPropagation(); checkUploadAccountLogin('${esc(item.account_id)}')"
                  ${disabled ? 'disabled' : ''}>Login</button>
          <button class="uamBtn" type="button"
                  onclick="event.stopPropagation(); console.warn('queueUploadForAccount not implemented')">Upload</button>
        </div>
        <div class="uamCardStats">
          <span>${esc(usageLine)}</span>
          <span>${esc(cooldownLine)}</span>
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

function _queueStatusMeta(status){
  const map = {
    pending:   { icon: '⏳', label: 'Waiting',   cls: 'wait' },
    scheduled: { icon: '⏳', label: 'Scheduled',  cls: 'wait' },
    held:      { icon: '⏸', label: 'Held',        cls: 'wait' },
    running:   { icon: '▶',  label: 'Uploading',  cls: 'run'  },
    uploading: { icon: '▶',  label: 'Uploading',  cls: 'run'  },
    success:   { icon: '🟢', label: 'Done',        cls: 'ok'   },
    failed:    { icon: '🔴', label: 'Failed',      cls: 'fail' },
    cancelled: { icon: '⛔', label: 'Cancelled',   cls: 'fail' },
  };
  return map[status] || map.pending;
}

if(!window.__uqmRetryCountdownStarted){
  window.__uqmRetryCountdownStarted = true;
  setInterval(() => {
    document.querySelectorAll('.uqmRetry').forEach((el) => {
      const txt = el.textContent;
      if(!txt.includes('Retry in')) return;
      const match = txt.match(/(\d+)m (\d+)s/);
      if(!match) return;
      let m = parseInt(match[1], 10);
      let s = parseInt(match[2], 10);
      if(s > 0) s--;
      else if(m > 0){ m--; s = 59; }
      el.textContent = `Retry in ${m}m ${s}s`;
    });
  }, 1000);
}

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

    const qMeta = _queueStatusMeta(status);
    const qReason = String(item.blocked_reason || item.last_error || '').trim();
    const qRetryAt = item.next_retry_at;
    let qRetryText = '';
    if(qRetryAt){
      const qDiff = Math.max(0, new Date(qRetryAt).getTime() - Date.now());
      const qm = Math.floor(qDiff / 60000);
      const qs2 = Math.floor((qDiff % 60000) / 1000);
      qRetryText = `Retry in ${qm}m ${qs2}s`;
    }
    const statusHtml = `<div class="uqmStatusBlock ${qMeta.cls}"><div class="uqmStatusMain"><span class="uqmIcon">${qMeta.icon}</span><span>${qMeta.label}</span></div>${qReason ? `<div class="uqmReason">${esc(qReason)}</div>` : ''}${qRetryText ? `<div class="uqmRetry">${qRetryText}</div>` : ''}</div>`;

    return `
      <tr class="${rowCls}" onclick="_selectUploadEntity('queue', '${esc(item.queue_id)}')">
        <td class="uqmColVideo">
          <div class="uqmClipName">${esc(clipName)}</div>
          ${item.last_error ? `<div class="uqmError">${esc(item.last_error)}</div>` : ''}
          ${showBlockedLine ? `<div class="uqmBlockedReason">${esc(blockedReason)}</div>` : ''}
          ${retryIn ? `<div class="uqmRetryIn">${esc(retryIn)}</div>` : ''}
          ${status === 'failed' && isProxyRelatedFailure(item.last_error || blockedReason) ? `<div class="proxyIssueHint">Proxy issue — rotate proxy in account health</div>` : ''}
        </td>
        <td class="uqmColAccount">${esc(accountName)}</td>
        <td class="uqmStatusCell">${statusHtml}</td>
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
        ${_collapsedDetailSection('Health JSON', account.health_json || {})}
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
      ${_collapsedDetailSection('Health JSON', item.health_json || {})}
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
      _auditLog('Proxy test OK', `${host}${data.ip ? ` → ${data.ip}` : ''}`);
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
  const poolSel = qs('uam_pool_proxy_select');
  if(poolSel) poolSel.value = '';
  const poolBadge = qs('uam_pool_proxy_badge');
  if(poolBadge){ poolBadge.textContent = ''; poolBadge.removeAttribute('data-status'); poolBadge.removeAttribute('data-market'); }
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
  // Restore pool proxy selector if proxy_id matches a pool entry
  const _poolSel = qs('uam_pool_proxy_select');
  if(_poolSel){
    const _matchedProxy = _proxyPool.find((p) => p.id === String(item.proxy_id || ''));
    _poolSel.value = _matchedProxy ? _matchedProxy.id : '';
    _updateProxyPoolBadge(_matchedProxy ? _matchedProxy.id : '');
  }
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
    invalidateUploadAnalyticsCache();
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
    invalidateUploadAnalyticsCache();
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

function _getSelectedAccount(){
  const id = _accountWorkspaceSelectedId();
  return uploadAccountManagerItems.find((a) => String(a.account_id) === String(id || '')) || null;
}

function bindSimpleActions(){
  const acc = _getSelectedAccount();
  const sp = qs('spAddAccount');
  if(!sp) return; // panel not in DOM
  qs('spAddAccount').onclick = () => openUploadEditor('account');
  qs('spAddVideo').onclick   = () => openUploadEditor('video');
  qs('spOpenProfile').onclick = () => {
    if(!acc?.profile_path) return;
    openAccountProfile(acc.account_id);
  };
  qs('spCheckLogin').onclick = () => {
    if(!acc) return;
    checkUploadAccountLogin(acc.account_id);
  };
  qs('spAutoPlan').onclick   = () => autoPlanReadyVideos?.();
  qs('spStartUpload').onclick = () => startUploadScheduler?.();
}

function getUploadWizardState() {
  const acc = _getSelectedAccount?.();
  const readyVideos = (uploadVideoLibraryItems || []).filter(v =>
    String(v.status || '').toLowerCase() === 'ready' && (v.video_path || v.path)
  );
  const queued = (uploadQueueManagerItems || []).filter(i =>
    !['success', 'cancelled', 'failed'].includes(String(i.status || '').toLowerCase())
  );

  if (!acc) return { step: 'account' };
  if (!acc.profile_path || acc.login_state !== 'logged_in') return { step: 'login', acc };
  if (!readyVideos.length && !queued.length) return { step: 'video', acc };
  return { step: 'upload', acc, readyVideos, queued };
}

function renderUploadWizard() {
  const el = document.querySelector('#uploadWizardSteps');
  if (!el) return;

  const state = getUploadWizardState();
  const step = state.step;

  const steps = [
    { key: 'account', label: 'Account', help: 'Create or select a channel profile.' },
    { key: 'login', label: 'Login', help: 'Open profile and log in once.' },
    { key: 'video', label: 'Video', help: 'Add videos ready for upload.' },
    { key: 'upload', label: 'Upload', help: 'Plan or start uploading.' }
  ];

  const order = steps.map(s => s.key);
  const activeIndex = order.indexOf(step);

  el.innerHTML = steps.map((s, idx) => {
    const cls = idx < activeIndex ? 'done' : idx === activeIndex ? 'active' : 'locked';
    return `
      <div class="uploadWizardStep ${cls}">
        <div class="uploadWizardNum">${idx + 1}</div>
        <div>
          <div class="uploadWizardLabel">${s.label}</div>
          <div class="uploadWizardHelp">${s.help}</div>
        </div>
      </div>
    `;
  }).join('');
}

function renderUploadWizardCTA() {
  const el = document.querySelector('#uploadWizardCTA');
  if (!el) return;

  const state = getUploadWizardState();

  if (state.step === 'account') {
    el.innerHTML = `<button class="wizardPrimary" onclick="openUploadEditor('account')">+ Add Account</button>`;
    return;
  }

  if (state.step === 'login') {
    el.innerHTML = `
      <button class="wizardPrimary" onclick="openAccountProfile('${state.acc.account_id}')">Open Profile</button>
      <button class="wizardSecondary" onclick="checkUploadAccountLogin('${state.acc.account_id}')">Check Login</button>
      <button class="wizardSecondary" onclick="markAccountLoggedIn('${state.acc.account_id}')">Mark Logged In</button>
    `;
    return;
  }

  if (state.step === 'video') {
    el.innerHTML = `<button class="wizardPrimary" onclick="openUploadEditor('video')">+ Add Video</button>`;
    return;
  }

  el.innerHTML = `
    <button class="wizardPrimary" onclick="autoPlanReadyVideos()">Auto Plan</button>
    <button class="wizardSecondary" onclick="startUploadScheduler()">Start Upload</button>
  `;
}

function renderSimpleSummary(){
  const acc  = _getSelectedAccount();
  const el   = qs('spSummary');
  const next = qs('spNextStep');
  if(!el || !next) return;
  if(!uploadAccountManagerItems.length){
    el.innerHTML   = 'No account yet.';
    next.innerHTML = 'Add or select an account.';
    return;
  }
  if(!acc){
    el.innerHTML   = 'Select an account to begin.';
    next.innerHTML = 'Add or select an account.';
    return;
  }
  const _loginLabels = {logged_in:'Logged in', logged_out:'Need login', expired:'Expired', challenge:'Action required', unknown:'Need login'};
  const loginLabel = _loginLabels[acc.login_state] || 'Need login';
  const platform = acc.platform || 'tiktok';
  const todayCount = Number(acc.today_count || 0);
  const dailyLimit = Number(acc.daily_limit || 0) || '-';
  el.innerHTML = `<b>${esc(acc.display_name || acc.account_key || acc.account_id)}</b> · ${esc(platform)} · ${esc(loginLabel)} · Today ${todayCount}/${dailyLimit}`;
  if(__loginCheckHint && __loginCheckHint.accountId === String(acc.account_id)){
    const _hintMsgs = {PLAYWRIGHT_BROWSER_MISSING:'Login check tool not installed.', PROFILE_IN_USE:'Close the browser profile, then check again.'};
    next.innerHTML = esc(_hintMsgs[__loginCheckHint.errorCode] || 'Login check unavailable.');
    return;
  }
  if(!acc.profile_path){
    next.innerHTML = 'Set profile folder.';
  }else if(acc.login_state !== 'logged_in'){
    next.innerHTML = 'Open Profile, log in, then Check Login.';
  }else if(!uploadVideoLibraryItems.length){
    next.innerHTML = 'Add a video.';
  }else{
    next.innerHTML = 'Auto Plan or Start Upload.';
  }
}

function renderSimpleStats(){
  const el = qs('spStats');
  if(!el) return;
  const ready   = uploadVideoLibraryItems.length;
  const queued  = uploadQueueManagerItems.length;
  const running = uploadQueueManagerItems.filter((i) => i.status === 'running' || i.status === 'uploading').length;
  const failed  = uploadQueueManagerItems.filter((i) => i.status === 'failed').length;
  el.innerHTML = `Ready: ${ready} | Queued: ${queued} | Running: ${running} | Failed: ${failed}`;
}

function _bindWorkspaceActions(){
  const acc = _getSelectedAccount();
  const openBtn  = qs('uwOpenProfileBtn');
  const loginBtn = qs('uwLoginCheckBtn');
  const addBtn   = qs('uwAddVideoBtn');
  const autoBtn  = qs('uwAutoPlanBtn');
  const startBtn = qs('uwStartBtn');
  if(openBtn)  openBtn.onclick  = acc ? () => openAccountProfile(acc.account_id) : null;
  if(loginBtn) loginBtn.onclick = acc ? () => checkUploadAccountLogin(acc.account_id) : null;
  if(addBtn)   addBtn.onclick   = () => openUploadEditor('video');
  if(autoBtn)  autoBtn.onclick  = () => autoPlanReadyVideos?.();
  if(startBtn) startBtn.onclick = () => startUploadScheduler?.();
}

function renderWorkspaceContext(){
  const acc = _getSelectedAccount();
  const el = qs('uwContextPanel');
  if(!el) return;

  // Show login-check hint for the current account if one is active
  if(__loginCheckHint && acc && __loginCheckHint.accountId === String(acc.account_id)){
    const isBrowserMissing = __loginCheckHint.errorCode === 'PLAYWRIGHT_BROWSER_MISSING';
    const isInUse          = __loginCheckHint.errorCode === 'PROFILE_IN_USE';
    let html = `<div class="loginCheckError">${esc(__loginCheckHint.message)}</div>`;
    if(isBrowserMissing){
      html += `<div class="loginCheckSetupHint">Setup: run <code>.venv\\Scripts\\playwright install chromium</code></div>`;
    }
    if(isBrowserMissing || isInUse){
      html += `<div class="loginCheckFallback"><b>Alternative manual flow:</b><ol>
        <li>Click <b>Open Profile</b></li>
        <li>Log in manually in the browser</li>
        <li>Close the browser window</li>
        <li>Click <b>Mark Logged In</b></li>
      </ol></div>`;
    }
    el.innerHTML = html;
    return;
  }

  if(!acc){
    el.innerHTML = '<div class="uwHint">Select an account to begin</div>';
    return;
  }
  if(!acc.profile_path){
    el.innerHTML = '<div class="uwWarning">Profile not set. Configure account first.</div>';
    return;
  }
  if(acc.login_state !== 'logged_in'){
    el.innerHTML = '<div class="uwWarning">Not logged in → Click <b>Open Profile</b> → login → then <b>Check Login</b></div>';
    return;
  }
  if(!uploadVideoLibraryItems.length){
    el.innerHTML = '<div class="uwHint">No videos → Click <b>Add Video</b> to continue</div>';
    return;
  }
  el.innerHTML = '<div class="uwSuccess">Ready to upload → Use Auto Plan or Start Scheduler</div>';
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
    _bindWorkspaceActions();
    renderWorkspaceContext();
    const _wsAcc = _getSelectedAccount();
    if(_wsAcc) detectEnvMismatch(_wsAcc);
    bindSimpleActions();
    renderSimpleSummary();
    renderSimpleStats();
    renderUploadWizard();
    renderUploadWizardCTA();
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
    _auditLog(accountId ? 'Account updated' : 'Account added', payload.account_key || payload.display_name || accountId || '');
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
    _auditLog(videoId ? 'Video updated' : 'Video added', payload.file_name || String(payload.video_path || '').split(/[\\/]/).pop() || videoId || '');
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

let __loginCheckHint = null; // { accountId, errorCode, message }

function _showLoginCheckHint(accountId, errorCode, message){
  __loginCheckHint = errorCode ? {accountId, errorCode, message} : null;
}

async function checkUploadAccountLogin(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  if(!guardRapidAction()) return;
  try{
    const res = await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}/login-check`, {method: 'POST'});
    const data = await res.json();

    // Structured error: backend returned error_code on a 200 response
    if(data?.error_code){
      const errorMsgs = {
        PLAYWRIGHT_BROWSER_MISSING: 'Login check tool is not installed. Run: playwright install chromium.',
        PROFILE_IN_USE:             'Close the browser profile, then check again.',
        LOGIN_CHECK_FAILED:         'Login check failed. You can still use Mark Logged In if you confirmed manually.',
      };
      const msg = errorMsgs[data.error_code] || data.message || 'Login check failed.';
      // Setup/config errors are not fatal — use info, not error toast
      const toastKind = data.error_code === 'LOGIN_CHECK_FAILED' ? 'error' : 'info';
      showToast(msg, toastKind);
      _showLoginCheckHint(accountId, data.error_code, msg);
      await loadUploadAccounts();
      return;
    }

    // HTTP error fallback (unexpected server error)
    if(!res.ok) throw new Error(_formatApiError(data.detail || data.message));

    await loadUploadAccounts();
    const loginState = data?.item?.login_state || (data?.result?.logged_in ? 'logged_in' : 'logged_out');
    const loginMsgs = {logged_in: 'Login OK', logged_out: 'Session Expired', challenge: 'Captcha Required', expired: 'Session Expired', unknown: 'Login state unknown'};
    const toastType = loginState === 'logged_in' ? 'success' : (loginState === 'unknown' ? 'info' : 'error');
    if(loginState === 'logged_in') _showLoginCheckHint(accountId, null, null); // clear hint on confirmed success
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
  if(!guardRapidAction()) return;
  try{
    const res = await fetch('/api/upload/scheduler/start', {method: 'POST'});
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data.detail));
    _auditLog('Scheduler started');
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
    _auditLog('Scheduler stopped');
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
    if(count > 0) _auditLog('Retry failed uploads', `${count} item${count === 1 ? '' : 's'} reset`);
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
    const cooldownMs = options.ignoreCooldown ? 0 : Number(acc.cooldown_minutes || 0) * 60 * 1000;
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
  await randomizeBehaviorDelay();
  const results = [];
  for(const assignment of assignments){
    const _sgAcc = uploadAccountManagerItems.find((a) => String(a.account_id) === String(assignment.account_id));
    if(_sgAcc && !safeAllowAssignment(assignment, _sgAcc)){
      skipped.push({video_id: assignment.video_id, reason: 'safety_filter'});
      continue;
    }
    if(_sgAcc && !allowByTrust(_sgAcc)){
      skipped.push({video_id: assignment.video_id, reason: 'low_trust'});
      continue;
    }
    if(_sgAcc && !isGoodPostingTime(_sgAcc)){
      skipped.push({video_id: assignment.video_id, reason: 'bad_time'});
      continue;
    }
    if(__workerMode){
      const sent = await dispatchToWorker(assignment);
      if(sent){ results.push({ok: true, assignment}); continue; }
    }
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
  _auditLog('Batch enqueue', `${succeeded} queued${totalSkipped > 0 ? `, ${totalSkipped} skipped` : ''}${failed > 0 ? `, ${failed} failed` : ''}`);
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
  postingWindowEnabled: false,
  postingWindowStart: '08:00',
  postingWindowEnd: '23:00',
  marketStrategy: 'custom',
  marketTimezone: '',
  rotationMode: 'balanced',
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
  _refreshTimezoneNote();
}

function saveAutomationSettings(){
  _readAutoSettingsFromUi();
  try{ localStorage.setItem('uploadAutomationSettings', JSON.stringify(_autoSettings)); }catch(_){}
  renderAutomationDashboard();
}

function _applyAutoSettingsToUi(){
  _setChk('auto_set_exclude_risky',      _autoSettings.excludeRisky);
  _setChk('auto_set_respect_limit',      _autoSettings.respectDailyLimit);
  _setChk('auto_set_respect_cooldown',   _autoSettings.respectCooldown);
  _setChk('auto_set_jitter',             _autoSettings.jitterEnabled);
  _setChk('auto_set_posting_window',     _autoSettings.postingWindowEnabled);
  _setChk('auto_set_auto_start',         _autoSettings.autoStartScheduler);
  _setChk('auto_set_accept_render',      _autoSettings.acceptRenderOutputs);
  _setVal('auto_set_base_spacing',       _autoSettings.baseSpacingMinutes);
  _setVal('auto_set_jitter_min',         _autoSettings.jitterMinutes);
  _setVal('auto_set_max_per_day',        _autoSettings.maxPerAccountPerDay);
  _setVal('auto_set_window_start',       _autoSettings.postingWindowStart);
  _setVal('auto_set_window_end',         _autoSettings.postingWindowEnd);
  _setVal('auto_set_market',             _autoSettings.marketStrategy || 'custom');
  const rotMode = _autoSettings.rotationMode || 'balanced';
  const rotRadio = document.querySelector(`input[name="auto_rotation_mode"][value="${rotMode}"]`);
  if(rotRadio) rotRadio.checked = true;
}

function _readAutoSettingsFromUi(){
  _autoSettings.excludeRisky          = _getChk('auto_set_exclude_risky');
  _autoSettings.respectDailyLimit     = _getChk('auto_set_respect_limit');
  _autoSettings.respectCooldown       = _getChk('auto_set_respect_cooldown');
  _autoSettings.jitterEnabled         = _getChk('auto_set_jitter');
  _autoSettings.postingWindowEnabled  = _getChk('auto_set_posting_window');
  _autoSettings.autoStartScheduler    = _getChk('auto_set_auto_start');
  _autoSettings.acceptRenderOutputs   = _getChk('auto_set_accept_render');
  _autoSettings.baseSpacingMinutes    = Math.max(1,  parseInt(_getVal('auto_set_base_spacing'), 10) || 30);
  _autoSettings.jitterMinutes         = Math.max(0,  parseInt(_getVal('auto_set_jitter_min'),   10) || 5);
  _autoSettings.maxPerAccountPerDay   = Math.max(1,  parseInt(_getVal('auto_set_max_per_day'),  10) || 5);
  _autoSettings.postingWindowStart    = _getVal('auto_set_window_start') || '08:00';
  _autoSettings.postingWindowEnd      = _getVal('auto_set_window_end')   || '23:00';
  _autoSettings.marketStrategy        = _getVal('auto_set_market')       || 'custom';
  const rotSelected = document.querySelector('input[name="auto_rotation_mode"]:checked');
  _autoSettings.rotationMode          = rotSelected ? rotSelected.value : 'balanced';
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

  const activeMarket = String(_autoSettings.marketStrategy || '').toUpperCase();
  if(activeMarket && activeMarket !== 'CUSTOM'){
    const poolEntry = _proxyPool.find((p) => p.id === String(account.proxy_id || ''));
    const proxyMarket = poolEntry ? String(poolEntry.market || '').toUpperCase() : '';
    if(proxyMarket === activeMarket)       { score += 20; reasons.push(`+20 proxy market match (${activeMarket})`); }
    else if(proxyMarket && proxyMarket !== activeMarket){ score -= 15; reasons.push(`-15 proxy market mismatch`); }
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

// --- PHASE 9 FEATURE 5: ROTATION-AWARE ACCOUNT PICKER ---

function pickAccountForAutoAssignment(video, candidates, context){
  const {rotationMode, baseScores, assignedCounts, previousAccountId, accountState, existingPairs} = context;

  const scored = [];
  for(const acc of candidates){
    const aid = String(acc.account_id);
    const state = accountState[aid];

    // Hard gates: quota exhausted or already queued for this video
    if(existingPairs.has(`${video.video_id}|${aid}`)) continue;
    if(state.remaining !== Infinity && state.assigned >= state.remaining) continue;

    const base = baseScores[aid] || {score: 0, reasons: []};
    let adj = base.score;
    const adjReasons = [];

    // --- Rotation penalties ---
    const inPlanCount = assignedCounts[aid] || 0;

    // Assigned-count penalty — balanced applies strongly, score_first weakly
    if(inPlanCount > 0){
      const p = rotationMode === 'score_first' ? inPlanCount * 4 :
                rotationMode === 'conservative' ? inPlanCount * 12 :
                inPlanCount * 8;
      adj -= p;
      adjReasons.push(`-${p} already assigned ${inPlanCount} in plan`);
    }

    // Consecutive same-account penalty
    if(previousAccountId === aid){
      const p = rotationMode === 'score_first' ? 3 : 10;
      adj -= p;
      adjReasons.push(`-${p} consecutive slot`);
    }

    // Recently used account (last upload within 2 hours)
    const lastUpAt = acc.last_upload_at;
    if(lastUpAt){
      const minsAgo = (Date.now() - new Date(lastUpAt).getTime()) / 60000;
      if(minsAgo >= 0 && minsAgo < 120){
        adj -= 15;
        adjReasons.push('-15 recently used');
      }
    }

    // High today_count penalty (>50% of daily limit used)
    const dl = Number(acc.daily_limit || 0);
    const tc = Number(acc.today_count || 0);
    if(dl > 0 && tc > dl * 0.5){
      const p = rotationMode === 'conservative' ? 20 : rotationMode === 'score_first' ? 5 : 10;
      adj -= p;
      adjReasons.push(`-${p} high usage today`);
    }

    // Conservative: extra penalty for warning-health accounts when healthy ones exist
    if(rotationMode === 'conservative'){
      const health = _computeAccountHealth(acc);
      if(health.status === 'warning'){
        adj -= 30;
        adjReasons.push('-30 warning account (conservative)');
      }
    }

    // Analytics integration: use cached failure data if available
    if(__uploadAnalyticsCache && Array.isArray(__uploadAnalyticsCache.accounts)){
      const aData = __uploadAnalyticsCache.accounts.find((a) => String(a.account_id) === aid);
      if(aData && aData.failed > 0){
        const p = Math.min(20, aData.failed * 5);
        adj -= p;
        adjReasons.push(`-${p} recent failures (analytics)`);
      }
    }

    scored.push({acc, aid, score: adj, reasons: [...base.reasons, ...adjReasons]});
  }

  if(!scored.length) return null;
  scored.sort((a, b) => b.score - a.score);
  const w = scored[0];
  return {account: w.acc, score: w.score, reasons: w.reasons};
}

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

  const rotationMode = _autoSettings.rotationMode || 'balanced';

  // Precompute base scores once (without rotation adjustments)
  const baseScores = {};
  accounts.forEach((acc) => { baseScores[acc.account_id] = scoreUploadAccount(acc); });

  // Per-account state: quota remaining and next available time slot
  const now = Date.now();
  const accountState = {};
  for(const acc of accounts){
    const dl = Number(acc.daily_limit || 0);
    const tc = Number(acc.today_count || 0);
    const cooldownMs = _autoSettings.respectCooldown ? Number(acc.cooldown_minutes || 0) * 60 * 1000 : 0;
    accountState[acc.account_id] = {
      remaining: dl > 0 ? Math.max(0, dl - tc) : Infinity,
      nextMs:    now + cooldownMs,
      assigned:  0,
    };
  }

  // Pairs already in queue (de-duplicate check)
  const existingPairs = new Set(
    uploadQueueManagerItems
      .filter((q) => !['cancelled', 'success'].includes(String(q.status || '').toLowerCase()))
      .map((q) => `${q.video_id}|${q.account_id}`)
  );

  const assignments = [];
  const skipped     = [];
  const warnings    = [];
  const assignedCounts    = {};   // account_id → count assigned in this plan
  const assignmentReasons = {};   // `video_id|account_id` → {score, reasons, rotationMode}
  let previousAccountId   = null;

  const context = {
    rotationMode, baseScores, assignedCounts,
    get previousAccountId(){ return previousAccountId; },
    accountState, existingPairs,
  };

  const spaceMs = _autoSettings.baseSpacingMinutes * 60 * 1000;

  for(const video of videos){
    const pick = pickAccountForAutoAssignment(video, accounts, context);

    if(!pick){
      const allDup  = accounts.every((a) => existingPairs.has(`${video.video_id}|${a.account_id}`));
      const allFull = accounts.every((a) => {
        const s = accountState[a.account_id];
        return s.remaining !== Infinity && s.assigned >= s.remaining;
      });
      skipped.push({video_id: video.video_id,
        reason: allDup ? 'already queued' : allFull ? 'no remaining quota' : 'no eligible account'});
      continue;
    }

    const {account: acc, score, reasons} = pick;
    const state  = accountState[acc.account_id];
    const schedAt = new Date(state.nextMs).toISOString();

    state.nextMs += spaceMs;
    state.assigned++;
    assignedCounts[acc.account_id] = (assignedCounts[acc.account_id] || 0) + 1;
    existingPairs.add(`${video.video_id}|${acc.account_id}`);
    previousAccountId = acc.account_id;

    const key = `${video.video_id}|${acc.account_id}`;
    assignmentReasons[key] = {score, reasons, rotationMode};

    assignments.push({
      video_id:     video.video_id,
      account_id:   acc.account_id,
      scheduled_at: schedAt,
      priority:     0,
      reason:       'rotation_assigned',
    });
  }

  // Near-limit warnings
  for(const acc of accounts){
    const s = accountState[acc.account_id];
    if(s.remaining !== Infinity && s.remaining - s.assigned <= 1 && s.assigned > 0){
      warnings.push(`${acc.display_name || acc.account_key} is near daily limit`);
    }
  }

  // Jitter
  if(_autoSettings.jitterEnabled && _autoSettings.jitterMinutes > 0){
    const jMs = _autoSettings.jitterMinutes * 60 * 1000;
    assignments.forEach((a) => {
      if(a.scheduled_at){
        const t = new Date(a.scheduled_at).getTime();
        const offset = Math.round((Math.random() * 2 - 1) * jMs);
        a.scheduled_at = new Date(Math.max(Date.now() + 30000, t + offset)).toISOString();
      }
    });
  }

  // Posting window
  if(_autoSettings.postingWindowEnabled){
    const tzWarnings = new Set();
    assignments.forEach((a) => {
      if(a.scheduled_at){
        const {date, warning} = applyPostingWindowForTimezone(
          new Date(a.scheduled_at),
          _autoSettings.postingWindowStart,
          _autoSettings.postingWindowEnd,
          _autoSettings.marketTimezone,
        );
        a.scheduled_at = date.toISOString();
        if(warning) tzWarnings.add(warning);
      }
    });
    tzWarnings.forEach((w) => warnings.push(w));
    if(_autoSettings.marketTimezone && _isValidTimezone(_autoSettings.marketTimezone)){
      _auditLog('timezone_schedule_applied', _autoSettings.marketTimezone);
    }
  }

  // Cooldown bypass notices
  if(!_autoSettings.respectCooldown){
    accounts.filter((a) => Number(a.cooldown_minutes || 0) > 0).forEach((a) => {
      warnings.push(`Cooldown ignored for @${a.display_name || a.account_key || a.account_id}`);
    });
  }

  // scores kept for backward-compatible preview (base scores, not rotation-adjusted)
  return {assignments, skipped, warnings, scores: baseScores, assignedCounts, assignmentReasons, rotationMode};
}

// --- FEATURE 7: SAFETY WARNINGS ---

function _autoSafetyWarnings(assignments, accounts){
  const critical = [];
  const warnings = [];
  if(!accounts.length){
    critical.push('No eligible accounts — check account status and automation settings.');
    return {critical, warnings};
  }

  const healthyCount = accounts.filter((a) => _computeAccountHealth(a).status === 'healthy').length;
  if(healthyCount === 0) critical.push('No healthy accounts in plan — all eligible accounts are in warning or risky state.');

  const proxyFailed = accounts.filter((a) => _computeAccountHealth(a).proxy_status === 'failed');
  if(proxyFailed.length) critical.push(`${proxyFailed.length} account(s) have proxy failures — uploads may fail.`);

  const conflicts = accounts.filter((a) => {
    const norm = normalizeProfilePath(String(a.profile_path || ''));
    if(!norm) return false;
    return uploadAccountManagerItems.some((b) =>
      String(b.account_id) !== String(a.account_id) && normalizeProfilePath(String(b.profile_path || '')) === norm
    );
  });
  if(conflicts.length) critical.push(`${conflicts.length} account(s) have profile path conflicts — isolation may be broken.`);

  if(_autoSettings.baseSpacingMinutes < 15) warnings.push(`Schedule spacing is ${_autoSettings.baseSpacingMinutes}m — below the 15-minute safe minimum may trigger rate limits.`);

  if(!_autoSettings.excludeRisky){
    const riskyCount = accounts.filter((a) => _computeAccountHealth(a).status === 'risky').length;
    if(riskyCount > 0) warnings.push(`${riskyCount} risky account(s) included in this plan. Review carefully before confirming.`);
  }

  const totalQuota = accounts.reduce((s, acc) => {
    const dl = Number(acc.daily_limit || 0);
    const tc = Number(acc.today_count || 0);
    return s + (dl > 0 ? Math.max(0, dl - tc) : _autoSettings.maxPerAccountPerDay);
  }, 0);
  const readyCount = _autoReadyVideos().length;
  if(readyCount > totalQuota * 1.5) warnings.push(`${readyCount} ready videos but only ~${totalQuota} quota slots — many will be skipped.`);

  if(!_autoSettings.respectCooldown){
    const cooldownAccts = accounts.filter((a) => Number(a.cooldown_minutes || 0) > 0);
    if(cooldownAccts.length) warnings.push(`Cooldown bypassed for ${cooldownAccts.length} account(s) — may hit platform rate limits.`);
  }

  if(!_autoSettings.postingWindowEnabled) warnings.push('Posting window is disabled — uploads may be scheduled outside safe hours.');

  // Timezone-aware scheduling checks
  if(_autoSettings.postingWindowEnabled){
    const tz = String(_autoSettings.marketTimezone || '').trim();
    if(tz && !_isValidTimezone(tz)){
      warnings.push(`Timezone "${tz}" is invalid — scheduling will fall back to local machine time.`);
    } else if(!tz){
      warnings.push('No market timezone set — posting window uses local machine time. Select a market preset for accurate scheduling.');
    }
    const [sH, sM] = String(_autoSettings.postingWindowStart || '08:00').split(':').map(Number);
    const [eH, eM] = String(_autoSettings.postingWindowEnd   || '23:00').split(':').map(Number);
    if(sH * 60 + sM >= eH * 60 + eM){
      warnings.push('Posting window end is before or equal to start — crossing-midnight windows are not yet supported. Scheduling will not adjust.');
    }
  }

  // Phase 8: proxy pool + market safety checks
  const activeMarket = String(_autoSettings.marketStrategy || '').toUpperCase();

  const failedPoolProxyAccounts = accounts.filter((a) => {
    const p = _proxyPool.find((px) => px.id === String(a.proxy_id || ''));
    return p && p.status === 'failed';
  });
  if(failedPoolProxyAccounts.length) critical.push(`${failedPoolProxyAccounts.length} account(s) have a failed pool proxy — uploads will likely fail.`);

  const proxyCounts = {};
  accounts.forEach((a) => { const pid = String(a.proxy_id || ''); if(pid) proxyCounts[pid] = (proxyCounts[pid] || 0) + 1; });
  const overusedEntries = Object.entries(proxyCounts).filter(([, c]) => c > 3);
  if(overusedEntries.length){
    overusedEntries.forEach(([pid, count]) => {
      const p = _proxyPool.find((px) => px.id === pid);
      const name = p ? p.name : pid;
      critical.push(`Proxy "${name}" shared by ${count} accounts — IP conflict risk.`);
    });
  }

  if(activeMarket && activeMarket !== 'CUSTOM'){
    const noProxyAccounts = accounts.filter((a) => !String(a.proxy_host || '') && !String(a.proxy_id || ''));
    if(noProxyAccounts.length) critical.push(`Market strategy ${activeMarket} active but ${noProxyAccounts.length} account(s) have no proxy assigned.`);
  }

  const untestedPoolProxyAccounts = accounts.filter((a) => {
    const p = _proxyPool.find((px) => px.id === String(a.proxy_id || ''));
    return p && (!p.status || p.status === 'untested');
  });
  if(untestedPoolProxyAccounts.length) warnings.push(`${untestedPoolProxyAccounts.length} account(s) have untested pool proxies — test before running.`);

  if(activeMarket && activeMarket !== 'CUSTOM'){
    const mismatchAccounts = accounts.filter((a) => {
      const p = _proxyPool.find((px) => px.id === String(a.proxy_id || ''));
      const pm = p ? String(p.market || '').toUpperCase() : '';
      return pm && pm !== activeMarket;
    });
    if(mismatchAccounts.length) warnings.push(`${mismatchAccounts.length} account(s) proxy market does not match strategy (${activeMarket}).`);
  }

  const highLatencyAccounts = accounts.filter((a) => {
    const p = _proxyPool.find((px) => px.id === String(a.proxy_id || ''));
    return p && Number(p.latency_ms || 0) > 1000;
  });
  if(highLatencyAccounts.length) warnings.push(`${highLatencyAccounts.length} account(s) have high-latency proxies (>1000ms).`);

  warnings.push(..._batchAggressiveWarning(assignments));

  // --- Rotation-mode safety checks ---
  const rotationMode = _autoSettings.rotationMode || 'balanced';
  if(assignments.length > 0){
    // >50% concentration in one account
    const byAcct = {};
    assignments.forEach((a) => { byAcct[a.account_id] = (byAcct[a.account_id] || 0) + 1; });
    const top = Math.max(...Object.values(byAcct));
    const pct = Math.round((top / assignments.length) * 100);
    if(pct > 50){
      const topAcc = uploadAccountManagerItems.find((a) =>
        String(a.account_id) === String(Object.keys(byAcct).find((k) => byAcct[k] === top) || ''));
      const name = topAcc ? (topAcc.display_name || topAcc.account_key) : 'one account';
      warnings.push(`${pct}% of planned uploads assigned to "${name}" — consider Balanced mode to spread load.`);
    }

    // Conservative: warn if no healthy accounts in plan
    if(rotationMode === 'conservative'){
      const planAcctIds = new Set(assignments.map((a) => String(a.account_id)));
      const planAccts = accounts.filter((a) => planAcctIds.has(String(a.account_id)));
      const healthyInPlan = planAccts.filter((a) => _computeAccountHealth(a).status === 'healthy').length;
      if(healthyInPlan === 0) critical.push('Conservative mode: no healthy accounts in plan — all eligible accounts are warning/risky.');
    }

    // Balanced: warn if consecutive same-account assignments were unavoidable
    if(rotationMode === 'balanced'){
      let consecutiveSame = 0;
      for(let i = 1; i < assignments.length; i++){
        if(assignments[i].account_id === assignments[i - 1].account_id) consecutiveSame++;
      }
      if(consecutiveSame > 0) warnings.push(`Balanced mode: ${consecutiveSame} consecutive same-account slot${consecutiveSame > 1 ? 's' : ''} — add more eligible accounts to improve spread.`);
    }

    // Score-first: inform that load concentration is intentional
    if(rotationMode === 'score_first' && pct > 40){
      warnings.push(`Score-first mode: load concentrated on highest-scoring accounts (${pct}% to one account) — this is intentional.`);
    }
  }

  return {critical, warnings};
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

  const eligibleIds = new Set(eligible.map((a) => String(a.account_id)));
  const latestQueuedMs = uploadQueueManagerItems
    .filter((q) => eligibleIds.has(String(q.account_id)) &&
      !['cancelled', 'success', 'failed'].includes(String(q.status || '').toLowerCase()) &&
      q.scheduled_at)
    .reduce((max, q) => Math.max(max, new Date(q.scheduled_at).getTime()), 0);
  const nextSlotMs = Math.max(latestQueuedMs, Date.now()) + _autoSettings.baseSpacingMinutes * 60000;
  const nextSlotStr = eligible.length > 0
    ? new Date(nextSlotMs).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    : '–';

  _setEl('auto_dash_ready',    String(ready.length),    ready.length > 0 ? 'ok' : 'none');
  _setEl('auto_dash_accounts', String(eligible.length), eligible.length > 0 ? 'ok' : 'none');
  _setEl('auto_dash_est',      String(estUploads),      estUploads > 0 ? 'ok' : 'none');
  _setEl('auto_dash_risky',    String(riskyExcluded),   riskyExcluded > 0 ? 'warn' : 'ok');
  _setEl('auto_dash_next',     nextSlotStr,             eligible.length > 0 ? 'ok' : 'none');
  _setEl('auto_dash_quota',    String(isFinite(totalQuota) ? totalQuota : '∞'), totalQuota > 0 ? 'ok' : 'none');

  const rotMode = _autoSettings.rotationMode || 'balanced';
  const rotLabel = rotMode === 'score_first' ? 'Score-first' : rotMode === 'conservative' ? 'Conservative' : 'Balanced';
  _setEl('auto_dash_rotation', rotLabel, 'ok');

  // Last-plan load distribution (if a plan exists)
  if(_autoPlanData && _autoPlanData.assignedCounts){
    const counts = Object.values(_autoPlanData.assignedCounts);
    const topLoad = counts.length ? Math.max(...counts) : 0;
    const accsUsed = counts.filter((c) => c > 0).length;
    _setEl('auto_dash_topload',  String(topLoad),   topLoad > 0  ? 'ok'  : 'none');
    _setEl('auto_dash_accs_used', String(accsUsed), accsUsed > 0 ? 'ok'  : 'none');
  }
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
  _auditLog('Auto plan generated', `${result.assignments.length} assignments, ${videos.length} videos, ${accounts.length} accounts`);

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
  const {assignments = [], skipped = [], safetyWarnings = [], scores = {},
         assignmentReasons = {}, rotationMode = 'balanced', assignedCounts = {}} = result;

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
    const poolEntry = acc ? _proxyPool.find((p) => p.id === String(acc.proxy_id || '')) : null;
    const proxyLabel = poolEntry
      ? `${esc(poolEntry.name)} · ${esc((poolEntry.market || 'custom').toUpperCase())} · ${esc(poolEntry.status || 'untested')}`
      : (acc && acc.proxy_host ? 'Manual proxy' : 'No proxy');
    const activeMarket = String(_autoSettings.marketStrategy || '').toUpperCase();
    const proxyMarket = poolEntry ? String(poolEntry.market || '').toUpperCase() : '';
    const marketMatch = activeMarket && activeMarket !== 'CUSTOM' && proxyMarket === activeMarket;
    const marketMismatch = activeMarket && activeMarket !== 'CUSTOM' && proxyMarket && proxyMarket !== activeMarket;

    const inPlanCount = assignedCounts[accountId] || items.length;
    const rotModeLabel = rotationMode === 'score_first' ? 'Score-first' : rotationMode === 'conservative' ? 'Conservative' : 'Balanced';

    // Collect rotation reasons from the first assignment for this account
    const firstKey = items.length ? `${items[0].video_id}|${items[0].account_id}` : null;
    const firstReason = firstKey && assignmentReasons[firstKey] ? assignmentReasons[firstKey] : null;
    const rotReasonText = firstReason
      ? firstReason.reasons.filter((r) => r.startsWith('-')).slice(0, 3).join('; ')
      : '';

    const rows = items.map((item) => {
      const video = uploadVideoLibraryItems.find((v) => String(v.video_id) === String(item.video_id));
      const vname = video ? (video.file_name || String(video.video_path || '').split(/[\\/]/).pop() || item.video_id) : item.video_id;
      const tStr = item.scheduled_at ? item.scheduled_at.replace('T', ' ').slice(0, 16) : 'ASAP';
      const key = `${item.video_id}|${item.account_id}`;
      const excluded = _autoPlanExcluded.has(key);
      const itemReason = assignmentReasons[key];
      const itemScore = itemReason ? itemReason.score : null;
      return `
        <div class="autoPlanExcludeRow${excluded ? ' autoPlanExcluded' : ''}">
          <input type="checkbox" class="autoPlanExcludeChk" title="Include in enqueue"
            ${excluded ? '' : 'checked'}
            onchange="toggleAutoPlanExclude('${esc(key)}', this.checked)">
          <span class="batchPreviewItemName">${esc(vname)}</span>
          <span class="batchPreviewItemTime">${esc(tStr)}</span>
          ${itemScore !== null ? `<span class="autoPlanItemScore" title="${esc(itemReason.reasons.join(', '))}">adj.${itemScore}</span>` : ''}
        </div>`;
    }).join('');

    return `
      <div class="batchPreviewGroup">
        <div class="batchPreviewGroupTitle">
          ${esc(accName)}
          <span class="autoScoreBadge" data-tier="${esc(scoreTier)}" title="${esc(scoreTooltip)}">Score ${esc(String(scoreNum))}</span>
          <span class="autoPlanRotBadge">${esc(rotModeLabel)}</span>
          <span style="color:var(--text-muted);font-size:11px;font-weight:400;margin-left:4px">${inPlanCount} assigned</span>
          <span style="color:var(--text-muted);font-size:11px;font-weight:400;margin-left:6px">${slotsLeft === '∞' ? 'unlimited' : `${slotsLeft} slot${slotsLeft !== 1 ? 's' : ''} left`}</span>
          ${marketMatch ? `<span style="color:#6ee7b7;font-size:10px;font-weight:700;margin-left:6px">${esc(activeMarket)} match</span>` : ''}
          ${marketMismatch ? `<span style="color:#fcd34d;font-size:10px;font-weight:700;margin-left:6px">market mismatch</span>` : ''}
          <span style="color:var(--text-muted);font-size:10px;margin-left:6px">${proxyLabel}</span>
        </div>
        ${rotReasonText ? `<div class="autoPlanRotPenalty">Penalty: ${esc(rotReasonText)}</div>` : ''}
        ${rows}
      </div>`;
  }).join('');

  const swCritical = Array.isArray(safetyWarnings) ? [] : (safetyWarnings.critical || []);
  const swWarnings = Array.isArray(safetyWarnings) ? safetyWarnings : (safetyWarnings.warnings || []);
  const totalWarnCount = swCritical.length + swWarnings.length;
  const safeWarnHtml = totalWarnCount > 0 ? `
    <div class="batchSection">
      <div class="batchSectionTitle batchSectionTitleWarn">Safety Warnings (${totalWarnCount})</div>
      ${swCritical.length ? `<div class="autoWarnGroup"><div class="autoWarnGroupLabel critical">Critical (${swCritical.length})</div>${swCritical.map((w) => `<div class="batchWarningItem">${esc(w)}</div>`).join('')}</div>` : ''}
      ${swWarnings.length ? `<div class="autoWarnGroup"><div class="autoWarnGroupLabel warnings">Warnings (${swWarnings.length})</div>${swWarnings.map((w) => `<div class="batchWarningItem">${esc(w)}</div>`).join('')}</div>` : ''}
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
        <div class="batchPreviewStat" style="color:var(--text-muted)">Rotation: <strong>${esc(rotationMode === 'score_first' ? 'Score-first' : rotationMode === 'conservative' ? 'Conservative' : 'Balanced')}</strong></div>
        ${skipped.length ? `<div class="batchPreviewStat batchPreviewStatSkip">Skipped: <strong>${skipped.length}</strong></div>` : ''}
        ${totalWarnCount ? `<div class="batchPreviewStat batchPreviewStatWarn">Warnings: <strong>${totalWarnCount}</strong>${swCritical.length ? ` (${swCritical.length} critical)` : ''}</div>` : ''}
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
    const _sgAcc = uploadAccountManagerItems.find((a) => String(a.account_id) === String(assignment.account_id));
    if(_sgAcc && !safeAllowAssignment(assignment, _sgAcc)){
      results.push({ok: false, error: 'safety_filter'});
      continue;
    }
    if(_sgAcc && !allowByTrust(_sgAcc)){
      results.push({ok: false, error: 'low_trust'});
      continue;
    }
    if(_sgAcc && !isGoodPostingTime(_sgAcc)){
      results.push({ok: false, error: 'bad_time'});
      continue;
    }
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

  _auditLog('Auto plan enqueued', `${succeeded} queued${failed > 0 ? `, ${failed} failed` : ''}`);
  const msg = failed === 0
    ? `Auto plan: ${succeeded} video${succeeded !== 1 ? 's' : ''} queued.`
    : `Auto plan: ${succeeded} queued, ${failed} failed.`;
  showToast(msg, failed === 0 ? 'success' : 'error');
  renderAutomationDashboard();
}

// --- FEATURE 4: TIMEZONE-AWARE POSTING WINDOW ---

function _isValidTimezone(tz){
  if(!tz) return false;
  try{ new Intl.DateTimeFormat('en-US', {timeZone: tz}).format(new Date()); return true; }
  catch(_){ return false; }
}

function _getZonedParts(date, timezone){
  const dtf = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
  const parts = Object.fromEntries(dtf.formatToParts(date).map((p) => [p.type, p.value]));
  return {
    year:   Number(parts.year),
    month:  Number(parts.month),
    day:    Number(parts.day),
    hour:   Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
  };
}

function _zonedDateTimeToUtc(year, month, day, hour, minute, timezone){
  // Iteratively converge: start with naive UTC estimate, measure how far off
  // the zoned representation is, and correct. Two iterations always suffice for
  // offsets within ±14h (all real IANA zones).
  let probe = new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
  for(let i = 0; i < 3; i++){
    const p = _getZonedParts(probe, timezone);
    let delta = (hour * 60 + minute) - (p.hour * 60 + p.minute);
    // Clamp to ±720 min to avoid day-wrap confusion
    if(delta >  720) delta -= 1440;
    if(delta < -720) delta += 1440;
    if(delta === 0) break;
    probe = new Date(probe.getTime() + delta * 60000);
  }
  return probe;
}

/**
 * Clamp a candidate Date into a posting window defined in a specific IANA timezone.
 * Returns {date: Date, applied: boolean, warning: string|null}
 */
function applyPostingWindowForTimezone(date, windowStart, windowEnd, timezone){
  if(!_autoSettings.postingWindowEnabled) return {date, applied: false, warning: null};

  // Resolve effective timezone — fallback to local machine timezone when unset
  let tz = String(timezone || '').trim();
  let warning = null;
  if(tz && !_isValidTimezone(tz)){
    warning = `Invalid timezone "${tz}"; using local machine time for scheduling.`;
    tz = '';
  }
  const effectiveTz = tz || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const [sH, sM] = String(windowStart || '08:00').split(':').map(Number);
  const [eH, eM] = String(windowEnd   || '23:00').split(':').map(Number);
  const startMin = sH * 60 + sM;
  const endMin   = eH * 60 + eM;

  if(startMin >= endMin){
    return {date, applied: false, warning: 'Posting window crossing midnight is not supported yet.'};
  }

  const parts  = _getZonedParts(date, effectiveTz);
  const curMin = parts.hour * 60 + parts.minute;

  if(curMin >= startMin && curMin < endMin){
    // Inside window — keep as-is
    return {date, applied: false, warning};
  }

  let resultDate;
  if(curMin < startMin){
    // Before window — move to same-day window start in target timezone
    resultDate = _zonedDateTimeToUtc(parts.year, parts.month, parts.day, sH, sM, effectiveTz);
  }else{
    // After window — next calendar day in target timezone at window start.
    // Pass day+1 directly; _zonedDateTimeToUtc's initial Date.UTC probe handles
    // month/year overflow correctly and the iteration converges to the right UTC.
    resultDate = _zonedDateTimeToUtc(parts.year, parts.month, parts.day + 1, sH, sM, effectiveTz);
  }

  return {date: resultDate, applied: true, warning};
}

// Thin wrapper kept for any external callers — warnings are silently dropped here.
function _applyPostingWindow(isoStr){
  if(!_autoSettings.postingWindowEnabled) return isoStr;
  const {date} = applyPostingWindowForTimezone(
    new Date(isoStr),
    _autoSettings.postingWindowStart,
    _autoSettings.postingWindowEnd,
    _autoSettings.marketTimezone,
  );
  return date.toISOString();
}

// =============================================================================
// PHASE 8: PROXY POOL + MARKET STRATEGY
// =============================================================================

const _PROXY_POOL_KEY = 'uploadProxyPool';
let _proxyPool = [];
let _proxyPoolEditId = null;

const _MARKET_PRESETS = {
  US: {timezone: 'America/New_York', postingWindowEnabled: true, postingWindowStart: '18:00', postingWindowEnd: '22:00', baseSpacingMinutes: 30, jitterMinutes: 5},
  JP: {timezone: 'Asia/Tokyo',       postingWindowEnabled: true, postingWindowStart: '19:00', postingWindowEnd: '23:00', baseSpacingMinutes: 30, jitterMinutes: 5},
  EU: {timezone: 'Europe/Berlin',    postingWindowEnabled: true, postingWindowStart: '18:00', postingWindowEnd: '22:00', baseSpacingMinutes: 35, jitterMinutes: 7},
};

// --- PROXY POOL STORE ---

function _normalizeProxyFromBackend(item){
  return {
    id:             item.proxy_id || item.id || '',
    name:           item.name     || '',
    type:           item.type     || 'http',
    host:           item.host     || '',
    port:           item.port     || null,
    username:       item.username || '',
    password:       item.password || '',
    market:         item.market   || 'custom',
    status:         item.status   || 'untested',
    latency_ms:     item.latency_ms || null,
    last_tested_at: item.last_tested_at || null,
  };
}

async function _loadProxyPool(){
  try{
    const res = await fetch('/api/upload/proxies');
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _proxyPool = (data.items || []).map(_normalizeProxyFromBackend);
    invalidateUploadAnalyticsCache();
    // If backend is empty but localStorage has data, prompt migration
    if(_proxyPool.length === 0){
      try{
        const local = JSON.parse(localStorage.getItem(_PROXY_POOL_KEY) || '[]');
        if(local.length > 0) console.info('[ProxyPool] localStorage has proxies not yet in backend — run importProxyPoolFromLocalStorage()');
      }catch(_){}
    }
  }catch(err){
    console.warn('[ProxyPool] Backend unavailable, using localStorage fallback:', err);
    try{
      _proxyPool = JSON.parse(localStorage.getItem(_PROXY_POOL_KEY) || '[]');
    }catch(_){ _proxyPool = []; }
  }
}

function _saveProxyPool(){
  // no-op: proxy pool is now persisted in the backend DB
}

async function importProxyPoolFromLocalStorage(){
  const raw = localStorage.getItem(_PROXY_POOL_KEY);
  if(!raw){ showToast('No local proxy data found', 'info'); return; }
  let items;
  try{ items = JSON.parse(raw); }catch(_){ showToast('Invalid local proxy data', 'error'); return; }
  if(!items.length){ showToast('Local proxy list is empty', 'info'); return; }
  let imported = 0;
  let failed = 0;
  for(const proxy of items){
    try{
      const res = await fetch('/api/upload/proxies', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name:     proxy.name     || 'Imported',
          type:     proxy.type     || 'http',
          host:     proxy.host     || '',
          port:     proxy.port     || null,
          username: proxy.username || '',
          password: proxy.password || '',
          market:   proxy.market   || '',
        }),
      });
      if(res.ok) imported++; else failed++;
    }catch(_){ failed++; }
  }
  await _loadProxyPool();
  renderProxyPool();
  renderProxyPoolDashboard();
  _populateProxyPoolSelect();
  _auditLog('proxy_imported', `${imported} proxies from localStorage`);
  showToast(`Imported ${imported} proxies${failed ? `, ${failed} failed` : ''}`, imported > 0 ? 'success' : 'error');
}

function _proxyPoolId(){
  return `pp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

// --- PROXY POOL CRUD ---

function openAddProxyModal(){
  _proxyPoolEditId = null;
  ['ppm_proxy_id','ppm_name','ppm_host','ppm_port','ppm_username','ppm_password'].forEach((id) => { const el = qs(id); if(el) el.value = ''; });
  if(qs('ppm_type'))   qs('ppm_type').value   = 'http';
  if(qs('ppm_market')) qs('ppm_market').value  = 'custom';
  if(qs('proxy_pool_modal_title')) qs('proxy_pool_modal_title').textContent = 'Add Proxy';
  const modal = qs('proxy_pool_modal');
  if(modal) modal.hidden = false;
}

function openEditProxyModal(id){
  const proxy = _proxyPool.find((p) => p.id === id);
  if(!proxy) return;
  _proxyPoolEditId = id;
  if(qs('ppm_proxy_id')) qs('ppm_proxy_id').value  = proxy.id;
  if(qs('ppm_name'))     qs('ppm_name').value       = proxy.name     || '';
  if(qs('ppm_type'))     qs('ppm_type').value        = proxy.type     || 'http';
  if(qs('ppm_host'))     qs('ppm_host').value        = proxy.host     || '';
  if(qs('ppm_port'))     qs('ppm_port').value        = proxy.port     || '';
  if(qs('ppm_username')) qs('ppm_username').value    = proxy.username || '';
  if(qs('ppm_password')) qs('ppm_password').value    = proxy.password || '';
  if(qs('ppm_market'))   qs('ppm_market').value      = proxy.market   || 'custom';
  if(qs('proxy_pool_modal_title')) qs('proxy_pool_modal_title').textContent = 'Edit Proxy';
  const modal = qs('proxy_pool_modal');
  if(modal) modal.hidden = false;
}

function closeProxyPoolModal(){
  const modal = qs('proxy_pool_modal');
  if(modal) modal.hidden = true;
  _proxyPoolEditId = null;
}

async function saveProxyFromModal(){
  const name = String(qs('ppm_name')?.value || '').trim();
  const host = String(qs('ppm_host')?.value || '').trim();
  if(!name){ showToast('Proxy name is required', 'error'); return; }
  if(!host){ showToast('Proxy host is required', 'error'); return; }
  const port = parseInt(String(qs('ppm_port')?.value || ''), 10) || null;
  const editId = _proxyPoolEditId;
  const payload = {
    name, host, port,
    type:     qs('ppm_type')?.value     || 'http',
    username: qs('ppm_username')?.value || '',
    password: qs('ppm_password')?.value || '',
    market:   qs('ppm_market')?.value   || 'custom',
  };
  closeProxyPoolModal();
  try{
    let res;
    if(editId){
      res = await fetch(`/api/upload/proxies/${encodeURIComponent(editId)}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
    }else{
      res = await fetch('/api/upload/proxies', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
    }
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data));
    const normalized = _normalizeProxyFromBackend(data.item);
    if(editId){
      const idx = _proxyPool.findIndex((p) => p.id === editId);
      if(idx >= 0) _proxyPool[idx] = normalized; else _proxyPool.push(normalized);
      _auditLog('proxy_pool_updated', name);
    }else{
      _proxyPool.push(normalized);
      _auditLog('proxy_pool_added', name);
    }
    renderProxyPool();
    renderProxyPoolDashboard();
    _populateProxyPoolSelect();
    showToast(editId ? 'Proxy updated' : 'Proxy saved', 'success');
  }catch(err){
    showToast(String(err?.message || err), 'error');
  }
}

async function deleteProxyFromPool(id){
  const proxy = _proxyPool.find((p) => p.id === id);
  if(!proxy) return;
  if(!window.confirm(`Delete proxy "${proxy.name}"?`)) return;
  const name = proxy.name;
  try{
    const res = await fetch(`/api/upload/proxies/${encodeURIComponent(id)}`, {method: 'DELETE'});
    if(!res.ok){ const d = await res.json(); throw new Error(_formatApiError(d)); }
    _proxyPool = _proxyPool.filter((p) => p.id !== id);
    _auditLog('proxy_pool_deleted', name);
    renderProxyPool();
    renderProxyPoolDashboard();
    _populateProxyPoolSelect();
    showToast('Proxy deleted', 'info');
  }catch(err){
    showToast(String(err?.message || err), 'error');
  }
}

// --- PROXY TEST FROM POOL ---

async function testProxyFromPool(id){
  const proxy = _proxyPool.find((p) => p.id === id);
  if(!proxy) return;
  const row = document.querySelector(`[data-proxy-id="${CSS.escape(id)}"]`);
  const statusEl = row ? row.querySelector('.proxyStatusBadge') : null;
  if(statusEl){ statusEl.textContent = 'Testing…'; statusEl.removeAttribute('data-status'); }
  try{
    const res = await fetch(`/api/upload/proxies/${encodeURIComponent(id)}/test`, {method: 'POST'});
    const data = await res.json();
    proxy.last_tested_at = new Date().toISOString();
    if(data.ok){
      proxy.status     = 'ok';
      proxy.latency_ms = data.latency_ms || null;
      _auditLog('proxy_pool_tested', `${proxy.name} — OK${data.latency_ms ? ` ${data.latency_ms}ms` : ''}`);
    }else{
      proxy.status     = 'failed';
      proxy.latency_ms = null;
      _auditLog('proxy_pool_tested', `${proxy.name} — Failed: ${data.error || 'no detail'}`);
    }
  }catch(err){
    proxy.status         = 'failed';
    proxy.latency_ms     = null;
    proxy.last_tested_at = new Date().toISOString();
    _auditLog('proxy_pool_tested', `${proxy.name} — Error: ${err.message || err}`);
  }
  renderProxyPool();
  renderProxyPoolDashboard();
  _populateProxyPoolSelect();
}

// --- PROXY POOL RENDER ---

function renderProxyPool(){
  const container = qs('proxy_pool_table_container');
  if(!container) return;
  if(!_proxyPool.length){
    container.innerHTML = '<div class="autoProxyPlaceholder">No proxies yet. Click + Add Proxy to add one.</div>';
    return;
  }
  const assignCounts = getProxyAssignmentCounts();
  const rows = _proxyPool.map((p) => {
    const statusText = p.status === 'ok'
      ? `OK${p.latency_ms ? ' · ' + p.latency_ms + 'ms' : ''}`
      : (p.status === 'failed' ? 'Failed' : 'Untested');
    const used = assignCounts[p.id] || 0;
    const usedBadge = used > 0 ? `<span class="proxyUsedBadge" title="${used} account(s) using this proxy">${used} acct</span>` : '';
    return `
      <div class="proxyPoolRow" data-proxy-id="${esc(p.id)}">
        <span class="proxyPoolName" title="${esc(p.name)}">${esc(p.name)}</span>
        <span class="proxyTypeBadge">${esc((p.type || 'http').toUpperCase())}</span>
        <span class="proxyPoolHost">${esc(p.host)}${p.port ? ':' + p.port : ''}</span>
        <span class="proxyMarketBadge" data-market="${esc(p.market || 'custom')}">${esc((p.market || 'custom').toUpperCase())}</span>
        <span class="proxyStatusBadge" data-status="${esc(p.status || 'untested')}">${esc(statusText)}</span>
        <span class="proxyPoolActions">
          ${usedBadge}
          <button class="ghostButton" type="button" onclick="testProxyFromPool('${esc(p.id)}')">Test</button>
          <button class="ghostButton" type="button" onclick="openEditProxyModal('${esc(p.id)}')">Edit</button>
          <button class="ghostButton" type="button" onclick="deleteProxyFromPool('${esc(p.id)}')">Delete</button>
        </span>
      </div>`;
  }).join('');

  container.innerHTML = `
    <div class="proxyPoolTable">
      <div class="proxyPoolHeaderRow">
        <span>Name</span><span>Type</span><span>Host:Port</span><span>Market</span><span>Status</span><span>Actions</span>
      </div>
      ${rows}
    </div>`;
}

// --- PROXY POOL DASHBOARD ---

function renderProxyPoolDashboard(){
  const total     = _proxyPool.length;
  const ok        = _proxyPool.filter((p) => p.status === 'ok').length;
  const failed    = _proxyPool.filter((p) => p.status === 'failed').length;
  const untested  = _proxyPool.filter((p) => !p.status || p.status === 'untested').length;
  const mktCounts = {};
  _proxyPool.forEach((p) => { const m = (p.market || 'custom').toUpperCase(); mktCounts[m] = (mktCounts[m] || 0) + 1; });
  const mktStr = total === 0 ? '–' : Object.entries(mktCounts).map(([m, c]) => `${m} ${c}`).join(' / ');

  _setEl('pp_dash_total',    String(total),  total    > 0 ? 'ok'   : 'none');
  _setEl('pp_dash_ok',       String(ok),     ok       > 0 ? 'ok'   : 'none');
  _setEl('pp_dash_failed',   String(failed), failed   > 0 ? 'warn' : 'ok');
  _setEl('pp_dash_untested', String(untested),untested > 0 ? 'warn' : 'ok');
  _setEl('pp_dash_markets',  mktStr,         total    > 0 ? 'ok'   : 'none');
}

// --- ACCOUNT PROXY POOL SELECTOR ---

function _populateProxyPoolSelect(){
  const sel = qs('uam_pool_proxy_select');
  if(!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">-- Manual entry --</option>' +
    _proxyPool.map((p) => {
      const statusText = p.status === 'ok' ? `OK${p.latency_ms ? ' ' + p.latency_ms + 'ms' : ''}` : (p.status === 'failed' ? 'Failed' : 'Untested');
      return `<option value="${esc(p.id)}">${esc(p.name)} — ${esc((p.market || 'custom').toUpperCase())} · ${esc(statusText)}</option>`;
    }).join('');
  if(_proxyPool.find((p) => p.id === current)) sel.value = current;
}

function _updateProxyPoolBadge(proxyId){
  const badge = qs('uam_pool_proxy_badge');
  if(!badge) return;
  if(!proxyId){ badge.textContent = ''; badge.removeAttribute('data-status'); badge.removeAttribute('data-market'); return; }
  const proxy = _proxyPool.find((p) => p.id === proxyId);
  if(!proxy){ badge.textContent = ''; badge.removeAttribute('data-status'); badge.removeAttribute('data-market'); return; }
  const statusText = proxy.status === 'ok' ? `OK${proxy.latency_ms ? ' · ' + proxy.latency_ms + 'ms' : ''}` : (proxy.status === 'failed' ? 'Failed' : 'Untested');
  badge.textContent = `${proxy.name} · ${(proxy.market || 'custom').toUpperCase()} · ${statusText}`;
  badge.setAttribute('data-status', proxy.status || 'untested');
  badge.setAttribute('data-market', proxy.market || 'custom');
}

function assignPoolProxyToAccount(){
  const id = qs('uam_pool_proxy_select')?.value;
  if(!id){ _updateProxyPoolBadge(''); return; }
  const proxy = _proxyPool.find((p) => p.id === id);
  if(!proxy) return;
  if(qs('uam_proxy_type'))     qs('uam_proxy_type').value     = proxy.type     || 'http';
  if(qs('uam_proxy_host'))     qs('uam_proxy_host').value     = proxy.host     || '';
  if(qs('uam_proxy_port'))     qs('uam_proxy_port').value     = proxy.port     || '';
  if(qs('uam_proxy_username')) qs('uam_proxy_username').value = proxy.username || '';
  if(qs('uam_proxy_password')) qs('uam_proxy_password').value = proxy.password || '';
  if(qs('uam_proxy_id'))       qs('uam_proxy_id').value       = proxy.id;
  _updateProxyPoolBadge(proxy.id);
  _auditLog('account_proxy_assigned', proxy.name);
  showToast(`Proxy "${proxy.name}" applied to form`, 'info');
}

// --- MARKET STRATEGY ---

function _refreshTimezoneNote(){
  const noteEl   = qs('market_preset_note');
  const windowEl = qs('tz_window_note');
  const market     = String(_autoSettings.marketStrategy || '').toUpperCase();
  const tz         = String(_autoSettings.marketTimezone || '').trim();
  const winEnabled = _autoSettings.postingWindowEnabled;

  if(!tz){
    if(noteEl)   noteEl.textContent   = 'No market timezone set. Posting window uses local machine time.';
    if(windowEl) windowEl.textContent = 'Uses local machine time';
    return;
  }
  if(!_isValidTimezone(tz)){
    if(noteEl)   noteEl.textContent   = `⚠ Invalid timezone "${tz}" — local machine time will be used for scheduling.`;
    if(windowEl) windowEl.textContent = 'Invalid timezone — using local time';
    return;
  }
  const windowRange = winEnabled
    ? `${_autoSettings.postingWindowStart}–${_autoSettings.postingWindowEnd} ${tz}`
    : 'window disabled';
  if(noteEl){
    noteEl.textContent = `Scheduling timezone: ${tz}${market && market !== 'CUSTOM' ? ' (' + market + ')' : ''}`
      + ` · Window ${windowRange}`
      + ` · Spacing ${_autoSettings.baseSpacingMinutes}m · Jitter ±${_autoSettings.jitterMinutes}m`;
  }
  if(windowEl) windowEl.textContent = `Market timezone: ${tz}`;
}

function applyMarketPreset(){
  _readAutoSettingsFromUi();
  const market = String(_autoSettings.marketStrategy || '').toUpperCase();
  const preset = _MARKET_PRESETS[market];
  if(preset){
    _autoSettings.postingWindowEnabled = preset.postingWindowEnabled;
    _autoSettings.postingWindowStart   = preset.postingWindowStart;
    _autoSettings.postingWindowEnd     = preset.postingWindowEnd;
    _autoSettings.baseSpacingMinutes   = preset.baseSpacingMinutes;
    _autoSettings.jitterMinutes        = preset.jitterMinutes;
    _autoSettings.marketTimezone       = preset.timezone;
    _applyAutoSettingsToUi();
  }else{
    _autoSettings.marketTimezone = '';
  }
  _refreshTimezoneNote();
  try{ localStorage.setItem('uploadAutomationSettings', JSON.stringify(_autoSettings)); }catch(_){}
  renderAutomationDashboard();
  _auditLog('market_strategy_changed', market || 'custom');
  if(preset) showToast(`Market preset applied: ${market}`, 'info');
}

// =============================================================================
// PHASE 9: PROXY ROTATION
// =============================================================================

// FEATURE 7: Count how many accounts are currently assigned each proxy
function getProxyAssignmentCounts(){
  const counts = {};
  uploadAccountManagerItems.forEach((acc) => {
    const pid = String(acc.proxy_id || '').trim();
    if(pid) counts[pid] = (counts[pid] || 0) + 1;
  });
  return counts;
}

// FEATURE 2: Rotation eligibility check
function canRotateProxyForAccount(account){
  if(!account) return {ok: false, reason: 'Account not found.'};
  const status = String(account.status || 'active').toLowerCase();
  if(['disabled','banned'].includes(status)) return {ok: false, reason: `Account is ${status}.`};
  if(accountHasActiveUpload(account.account_id)) return {ok: false, reason: 'Upload is running — wait for it to finish.'};
  if(!_proxyPool.length) return {ok: false, reason: 'Proxy pool is empty — add proxies first.'};
  const currentId = String(account.proxy_id || '').trim();
  const candidates = _proxyPool.filter((p) => p.id !== currentId);
  if(!candidates.length) return {ok: false, reason: 'No alternative proxies in pool.'};
  return {ok: true, reason: null};
}

// FEATURE 3: Score and rank replacement proxy candidates
function findBestReplacementProxy(account){
  if(!account) return {proxy: null, candidates: [], reason: 'No account.'};
  const currentId = String(account.proxy_id || '').trim();
  const counts = getProxyAssignmentCounts();
  const activeMarket = String(_autoSettings.marketStrategy || '').toUpperCase();
  const currentPoolProxy = _proxyPool.find((p) => p.id === currentId);
  const targetMarket = (currentPoolProxy ? String(currentPoolProxy.market || '').toUpperCase() : '')
    || (activeMarket && activeMarket !== 'CUSTOM' ? activeMarket : '');

  const scored = _proxyPool
    .filter((p) => p.id !== currentId)
    .map((p) => {
      let score = 0;
      const reasons = [];
      const pMarket = String(p.market || '').toUpperCase();
      if(targetMarket && pMarket === targetMarket){ score += 40; reasons.push('+40 market'); }
      const st = String(p.status || 'untested');
      if(st === 'ok')       { score += 50; reasons.push('+50 ok'); }
      else if(st === 'untested'){ score += 10; reasons.push('+10 untested'); }
      else if(st === 'failed')  { score -= 100; reasons.push('-100 failed'); }
      const lat = Number(p.latency_ms || 0);
      if(lat > 0 && lat < 500) { score += 10; reasons.push('+10 low lat'); }
      if(lat > 1500)            { score -= 10; reasons.push('-10 high lat'); }
      const used = counts[p.id] || 0;
      if(used > 0){ score -= used * 10; reasons.push(`-${used*10} shared`); }
      return {proxy: p, score, reasons};
    })
    .sort((a, b) => b.score - a.score);

  if(!scored.length) return {proxy: null, candidates: [], reason: 'No alternative proxies in pool.'};
  return {proxy: scored[0].proxy, candidates: scored, reason: null};
}

// FEATURE 4: Rotation modal
let _proxyRotateAccountId = null;

function openProxyRotateModal(accountId){
  const account = uploadAccountManagerItems.find((a) => String(a.account_id) === String(accountId));
  const {ok, reason} = canRotateProxyForAccount(account);
  if(!ok){ showToast(reason || 'Cannot rotate proxy for this account', 'error'); return; }
  _proxyRotateAccountId = accountId;
  const modal = qs('proxy_rotate_modal');
  if(!modal) return;
  const bodyEl = qs('proxy_rotate_modal_body');
  const titleEl = qs('proxy_rotate_modal_title');
  if(titleEl) titleEl.textContent = `Rotate Proxy — @${esc(account.display_name || account.account_key || accountId)}`;
  if(bodyEl) bodyEl.innerHTML = _buildProxyRotateModalHtml(account);
  modal.hidden = false;
}

function closeProxyRotateModal(){
  const modal = qs('proxy_rotate_modal');
  if(modal) modal.hidden = true;
  _proxyRotateAccountId = null;
}

function _buildProxyRotateModalHtml(account){
  const currentId = String(account.proxy_id || '').trim();
  const currentProxy = _proxyPool.find((p) => p.id === currentId) || null;
  const {proxy: recommended, candidates} = findBestReplacementProxy(account);

  const _proxyBadge = (p) => {
    if(!p) return '<span class="proxyRotateNone">No proxy assigned</span>';
    const lat = Number(p.latency_ms || 0);
    const latText = lat > 0 ? ` · ${lat}ms` : '';
    const market = String(p.market || '').toUpperCase() || 'CUSTOM';
    const st = String(p.status || 'untested');
    return `<span class="proxyMarketBadge" data-market="${esc(market.toLowerCase())}">${esc(market)}</span>`
      + ` <strong>${esc(p.name || p.host || p.id)}</strong>`
      + ` · <span class="proxyStatusBadge" data-status="${esc(st)}">${esc(st)}</span>${esc(latText)}`;
  };

  const currentHtml = `
    <div class="proxyRotateSection">
      <div class="proxyRotateSectionLabel">Current Proxy</div>
      <div class="proxyRotateCurrent">${_proxyBadge(currentProxy)}</div>
    </div>`;

  if(!recommended){
    return `${currentHtml}<div class="proxyRotateNone" style="margin-top:12px;padding:10px 0">No replacement proxies available in pool.</div>`;
  }

  const firstCandidate = candidates[0];
  const recHtml = `
    <div class="proxyRotateSection">
      <div class="proxyRotateSectionLabel">Recommended</div>
      <div class="proxyCandidateItem isRecommended selected" data-pid="${esc(recommended.id)}"
        onclick="_selectRotateCandidate(this,'${esc(recommended.id)}')">
        <div>${_proxyBadge(recommended)}</div>
        <span class="proxyCandidateScore">Score ${firstCandidate.score}</span>
      </div>
    </div>`;

  const others = candidates.slice(1);
  const othersHtml = others.length ? `
    <div class="proxyRotateSection">
      <div class="proxyRotateSectionLabel">Other Candidates</div>
      <div class="proxyCandidateList">
        ${others.map((c) => `
          <div class="proxyCandidateItem" data-pid="${esc(c.proxy.id)}"
            onclick="_selectRotateCandidate(this,'${esc(c.proxy.id)}')">
            <div>${_proxyBadge(c.proxy)}</div>
            <span class="proxyCandidateScore">Score ${c.score}</span>
          </div>
        `).join('')}
      </div>
    </div>` : '';

  return `
    ${currentHtml}
    ${recHtml}
    ${othersHtml}
    <input type="hidden" id="proxy_rotate_select_id" value="${esc(recommended.id)}">
    <div class="proxyRotateActions">
      <button class="ghostButton" type="button" onclick="closeProxyRotateModal()">Cancel</button>
      <button class="primaryButton" type="button" onclick="applyProxyRotation('${esc(account.account_id)}')">Rotate to Selected</button>
    </div>
  `;
}

function _selectRotateCandidate(el, proxyId){
  const list = el.closest('.uploadModalPanel');
  if(list) list.querySelectorAll('.proxyCandidateItem').forEach((e) => e.classList.remove('selected'));
  el.classList.add('selected');
  const sel = qs('proxy_rotate_select_id');
  if(sel) sel.value = proxyId;
}

// FEATURE 5: Apply rotation
async function applyProxyRotation(accountId){
  const selectEl = qs('proxy_rotate_select_id');
  const newProxyId = selectEl ? String(selectEl.value || '').trim() : '';
  if(!newProxyId){ showToast('No proxy selected', 'error'); return; }
  const account = uploadAccountManagerItems.find((a) => String(a.account_id) === String(accountId));
  const newProxy = _proxyPool.find((p) => p.id === newProxyId);
  if(!account){ showToast('Account not found', 'error'); return; }
  if(!newProxy){ showToast('Selected proxy not found in pool', 'error'); return; }

  const fromProxyId = String(account.proxy_id || '');
  const market = String(newProxy.market || '').toUpperCase();
  const proxy_config = {
    type:     String(newProxy.type     || 'http'),
    host:     String(newProxy.host     || ''),
    port:     newProxy.port || null,
    username: String(newProxy.username || ''),
    password: String(newProxy.password || ''),
  };

  closeProxyRotateModal();
  try{
    const res = await fetch(`/api/upload/accounts/${encodeURIComponent(accountId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({proxy_id: newProxyId, proxy_config}),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(_formatApiError(data));
    const idx = uploadAccountManagerItems.findIndex((a) => String(a.account_id) === String(accountId));
    if(idx >= 0){
      uploadAccountManagerItems[idx] = {
        ...uploadAccountManagerItems[idx],
        ...(data.item || {}),
        proxy_id:     newProxyId,
        proxy_config,
      };
    }
    UploadStore.setAccounts([...uploadAccountManagerItems]);
    renderUploadAccounts(uploadAccountManagerItems);
    renderUploadInspector();
    _auditLog('proxy_rotated',
      `${account.display_name || account.account_key || accountId}: ${fromProxyId || 'none'} → ${newProxyId}${market ? ' (' + market + ')' : ''}`);
    showToast(`Proxy rotated to ${esc(newProxy.name || newProxy.host)}`, 'success');
  }catch(err){
    showToast(String(err?.message || err), 'error');
  }
}

// --- PHASE 7: AUDIT LOG ---

const _AUDIT_LOG_KEY = 'uploadAuditLog';
const _AUDIT_MAX_ENTRIES = 100;

function _auditLog(action, detail){
  const entry = {ts: new Date().toISOString(), action, detail: detail || ''};
  try{
    const raw = localStorage.getItem(_AUDIT_LOG_KEY);
    const entries = raw ? JSON.parse(raw) : [];
    entries.unshift(entry);
    if(entries.length > _AUDIT_MAX_ENTRIES) entries.length = _AUDIT_MAX_ENTRIES;
    localStorage.setItem(_AUDIT_LOG_KEY, JSON.stringify(entries));
  }catch(_){}
}

function _auditGetEntries(){
  try{
    const raw = localStorage.getItem(_AUDIT_LOG_KEY);
    return raw ? JSON.parse(raw) : [];
  }catch(_){ return []; }
}

function renderAuditLog(){
  const panel = qs('audit_log_list');
  if(!panel) return;
  const entries = _auditGetEntries();
  if(!entries.length){
    panel.innerHTML = '<div class="auditLogEntry"><span class="auditLogTime">–</span><span class="auditLogAction">No activity yet.</span></div>';
    return;
  }
  panel.innerHTML = entries.slice(0, 30).map((e) => {
    const d = new Date(e.ts);
    const t = d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    const dateStr = d.toLocaleDateString([], {month: 'short', day: 'numeric'});
    return `<div class="auditLogEntry"><span class="auditLogTime">${esc(dateStr)} ${esc(t)}</span><span class="auditLogAction">${esc(e.action)}${e.detail ? ` — ${esc(e.detail)}` : ''}</span></div>`;
  }).join('');
}

function toggleAuditLogPanel(btn){
  const list = document.getElementById('audit_log_list');
  if(!list) return;
  const expanded = btn.getAttribute('aria-expanded') === 'true';
  btn.setAttribute('aria-expanded', String(!expanded));
  list.hidden = expanded;
  if(!expanded) renderAuditLog();
}

function clearAuditLog(){
  try{ localStorage.removeItem(_AUDIT_LOG_KEY); }catch(_){}
  renderAuditLog();
  showToast('Activity log cleared', 'info');
}

// =============================================================================
// =============================================================================
// PHASE 9: UPLOAD ANALYTICS
// =============================================================================

let __uploadAnalyticsCache = null;
let __uploadAnalyticsCacheTs = 0;
function invalidateUploadAnalyticsCache(){ __uploadAnalyticsCache = null; __uploadAnalyticsCacheTs = 0; }

window.__disableAnalytics = false;
let __isRenderingAnalytics = false;
let __analyticsRenderTimer = null;

const _MAX_ANALYTICS_ITEMS = 500;

function isTodayIso(ts){
  if(!ts) return false;
  try{
    const d = new Date(ts);
    const n = new Date();
    return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
  }catch(_){ return false; }
}

function normalizeFailureReason(item){
  const br = String(item.blocked_reason || '').toLowerCase().trim();
  const le = String(item.last_error || '').toLowerCase().trim();
  const combined = br || le;
  if(!combined) return 'unknown';
  if(br === 'login_required' || le.includes('login') || le.includes('logged_out') || le.includes('session expired')) return 'login_required';
  if(br === 'daily limit' || le.includes('daily limit') || le.includes('quota')) return 'daily_limit';
  if(br === 'cooldown' || le.includes('cooldown')) return 'cooldown';
  if(br === 'profile busy' || le.includes('profile busy')) return 'profile_busy';
  if(isProxyRelatedFailure(combined)) return 'proxy_failed';
  if((le.includes('file') || le.includes('video')) && (le.includes('missing') || le.includes('not found'))) return 'file_missing';
  if(le.includes('rate') || le.includes('throttl')) return 'rate_limited';
  if(le.includes('captcha') || le.includes('challenge')) return 'captcha_challenge';
  if(le.includes('upload') && le.includes('fail')) return 'upload_failed';
  // Return truncated combined reason for anything else
  return combined.slice(0, 36).trim() || 'unknown';
}

function computeUploadAnalytics(){
  const now = Date.now();
  if(__uploadAnalyticsCache && (now - __uploadAnalyticsCacheTs) < 15000) return __uploadAnalyticsCache;

  // Cap input to avoid long blocking on huge datasets
  const queueItems = uploadQueueManagerItems.slice(0, _MAX_ANALYTICS_ITEMS);

  // -- Single pass over queue: today stats + account map + retry + failure reasons --
  const today = {queued: 0, uploaded: 0, failed: 0, retry: 0};
  const acctMap = {};       // account_id → {uploaded, failed, retry}
  const failsByAcct = {};   // account_id → fail count (for proxy section, O(1) lookup)
  const reasonCounts = {};  // failure reason → count
  let retryableFailed = 0, retriedCount = 0, stillFailed = 0, recovered = 0;

  queueItems.forEach((item) => {
    const status = String(item.status || '').toLowerCase();
    const att    = Number(item.attempt_count || 0);
    const maxAtt = Number(item.max_attempts || 3);
    const aid    = String(item.account_id || '');
    const ts     = item.updated_at || item.created_at;

    // today counters
    if(isTodayIso(ts)){
      if(status === 'success')                              today.uploaded++;
      else if(status === 'failed')                          today.failed++;
      else if(['pending', 'scheduled', 'held'].includes(status)) today.queued++;
    }
    if(att > 1) today.retry++;

    // account map
    if(aid){
      if(!acctMap[aid]) acctMap[aid] = {uploaded: 0, failed: 0, retry: 0};
      if(status === 'success') acctMap[aid].uploaded++;
      if(status === 'failed')  acctMap[aid].failed++;
      if(att > 1)              acctMap[aid].retry++;
    }

    // fail counts by account (for proxy section)
    if(status === 'failed' && aid){
      failsByAcct[aid] = (failsByAcct[aid] || 0) + 1;
    }

    // retry effectiveness — single pass
    if(status === 'failed'){
      if(att < maxAtt) retryableFailed++;
      if(att > 1)      stillFailed++;
    }
    if(status === 'success' && att > 1) recovered++;
    if(att > 1) retriedCount++;

    // failure reasons
    if(status === 'failed'){
      const r = normalizeFailureReason(item);
      reasonCounts[r] = (reasonCounts[r] || 0) + 1;
    }
  });

  const totalDone  = today.uploaded + today.failed;
  const successRate = totalDone > 0 ? Math.round((today.uploaded / totalDone) * 100) : null;

  const failureReasons = Object.entries(reasonCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([reason, count]) => ({reason, count}));

  const retry = {retryableFailed, retried: retriedCount, stillFailed, recovered};

  // -- Account analytics (O(accounts)) --
  const accounts = uploadAccountManagerItems.map((acc) => {
    const aid = String(acc.account_id || '');
    const s   = acctMap[aid] || {uploaded: 0, failed: 0, retry: 0};
    const tot = s.uploaded + s.failed;
    return {
      account_id:   aid,
      name:         acc.display_name || acc.account_key || aid,
      uploaded:     s.uploaded,
      failed:       s.failed,
      retry:        s.retry,
      successRate:  tot > 0 ? Math.round((s.uploaded / tot) * 100) : null,
      health:       _computeAccountHealth(acc).status,
      lastUploadAt: acc.last_upload_at || null,
    };
  }).sort((a, b) => b.uploaded - a.uploaded || a.failed - b.failed);

  // -- Proxy analytics: O(accounts) using precomputed failsByAcct map --
  const proxyAcctMap = {};
  uploadAccountManagerItems.forEach((acc) => {
    const pid = String(acc.proxy_id || '').trim();
    if(!pid) return;
    if(!proxyAcctMap[pid]) proxyAcctMap[pid] = {count: 0, failures: 0};
    proxyAcctMap[pid].count++;
    proxyAcctMap[pid].failures += failsByAcct[String(acc.account_id || '')] || 0;
  });

  const proxies = _proxyPool.map((p) => {
    const u = proxyAcctMap[p.id] || {count: 0, failures: 0};
    return {
      proxy_id:        p.id,
      name:            p.name || p.host || p.id,
      market:          String(p.market || 'custom').toUpperCase(),
      usedBy:          u.count,
      status:          p.status || 'untested',
      latency_ms:      p.latency_ms || null,
      accountFailures: u.failures,
    };
  }).sort((a, b) => b.accountFailures - a.accountFailures || b.usedBy - a.usedBy);

  const result = {today, successRate, accounts, proxies, failureReasons, retry};
  __uploadAnalyticsCache = result;
  __uploadAnalyticsCacheTs = Date.now();
  return result;
}

// ── Render helpers ────────────────────────────────────────────────────────────

function _analyticsCard(label, value, state){
  return `<div class="uploadAnalyticsCard" data-state="${esc(state || 'none')}">
    <div class="analyticsCardLabel">${esc(label)}</div>
    <div class="analyticsCardValue">${esc(String(value ?? '—'))}</div>
  </div>`;
}

function _renderAccountAnalyticsTable(accounts){
  if(!accounts.length) return '<div class="analyticsEmpty">No accounts loaded.</div>';
  const rows = accounts.map((a) => {
    const sr   = a.successRate !== null ? `${a.successRate}%` : '—';
    const last = a.lastUploadAt ? new Date(a.lastUploadAt).toLocaleDateString([], {month: 'short', day: 'numeric'}) : '—';
    return `<tr>
      <td class="analyticsNameCell">${esc(a.name)}</td>
      <td>${a.uploaded}</td>
      <td>${a.failed > 0 ? `<span class="analyticsFailCount">${a.failed}</span>` : '0'}</td>
      <td>${a.retry}</td>
      <td>${esc(sr)}</td>
      <td><span class="uamHealthBadge" data-health="${esc(a.health)}">${esc(a.health)}</span></td>
      <td class="analyticsDateCell">${esc(last)}</td>
    </tr>`;
  }).join('');
  return `<div class="analyticsSection">
    <div class="analyticsSectionTitle">Account Performance</div>
    <div class="analyticsTableWrap">
      <table class="uploadAnalyticsTable">
        <thead><tr><th>Account</th><th>Uploaded</th><th>Failed</th><th>Retry</th><th>Rate</th><th>Health</th><th>Last Upload</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
}

function _renderProxyAnalyticsTable(proxies){
  if(!proxies.length) return '<div class="analyticsEmpty">No proxies in pool.</div>';
  const rows = proxies.map((p) => {
    const lat = p.latency_ms ? `${p.latency_ms}ms` : '—';
    return `<tr>
      <td class="analyticsNameCell">${esc(p.name)}</td>
      <td><span class="proxyMarketBadge" data-market="${esc(p.market.toLowerCase())}">${esc(p.market)}</span></td>
      <td>${p.usedBy}</td>
      <td><span class="proxyStatusBadge" data-status="${esc(p.status)}">${esc(p.status)}</span></td>
      <td>${esc(lat)}</td>
      <td>${p.accountFailures > 0 ? `<span class="analyticsFailCount">${p.accountFailures}</span>` : '0'}</td>
    </tr>`;
  }).join('');
  return `<div class="analyticsSection">
    <div class="analyticsSectionTitle">Proxy Performance</div>
    <div class="analyticsTableWrap">
      <table class="uploadAnalyticsTable">
        <thead><tr><th>Proxy</th><th>Market</th><th>Used By</th><th>Status</th><th>Latency</th><th>Failures</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
}

function _renderFailureReasonList(reasons){
  if(!reasons.length){
    return `<div class="analyticsSection">
      <div class="analyticsSectionTitle">Failure Reasons</div>
      <div class="analyticsEmpty">No failed items.</div>
    </div>`;
  }
  const items = reasons.map((r) =>
    `<li class="uploadAnalyticsReasonItem">
      <span class="analyticsReasonLabel">${esc(r.reason)}</span>
      <span class="analyticsReasonCount">×${r.count}</span>
    </li>`
  ).join('');
  return `<div class="analyticsSection">
    <div class="analyticsSectionTitle">Failure Reasons</div>
    <ul class="uploadAnalyticsReasonList">${items}</ul>
  </div>`;
}

function _renderRetryEffectiveness(retry){
  return `<div class="analyticsSection">
    <div class="analyticsSectionTitle">Retry Effectiveness <span class="analyticsApprox">approx.</span></div>
    <ul class="analyticsRetryList">
      <li>Retryable failed <strong>${retry.retryableFailed}</strong></li>
      <li>Total retried <strong>${retry.retried}</strong></li>
      <li>Still failed <strong>${retry.stillFailed}</strong></li>
      <li>Recovered <strong>${retry.recovered}</strong></li>
    </ul>
  </div>`;
}

function _renderRecentAuditSnapshot(count){
  const entries = _auditGetEntries().slice(0, count);
  if(!entries.length) return '';
  const items = entries.map((e) => {
    const d  = new Date(e.ts);
    const ts = d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    return `<li class="auditSnapshotEntry">
      <span class="auditSnapshotTime">${esc(ts)}</span>
      <span class="auditSnapshotAction">${esc(e.action)}${e.detail ? ` — ${esc(e.detail.slice(0, 60))}` : ''}</span>
    </li>`;
  }).join('');
  return `<div class="analyticsSection">
    <div class="analyticsSectionTitle">Recent Activity <span class="analyticsApprox">(last ${count})</span></div>
    <ul class="auditSnapshotList">${items}</ul>
  </div>`;
}

// ── Main render ───────────────────────────────────────────────────────────────

function renderAnalyticsDashboard(){
  if(window.__disableAnalytics) return;
  if(__isRenderingAnalytics) return;

  // Skip work while the panel is collapsed — it will render on open
  const container = qs('analytics_dashboard_container');
  if(container && container.hidden) return;

  const body = qs('analytics_body');
  if(!body) return;

  __isRenderingAnalytics = true;
  try{
    _renderAnalyticsDashboardInternal(body);
  }catch(e){
    console.warn('[Analytics] render error:', e);
  }finally{
    __isRenderingAnalytics = false;
  }
}

function _renderAnalyticsDashboardInternal(body){
  const d = computeUploadAnalytics();

  const srText  = d.successRate !== null ? `${d.successRate}%` : '—';
  const srState = d.successRate === null ? 'none' : d.successRate >= 80 ? 'ok' : d.successRate >= 50 ? 'warn' : 'risky';

  const hc = {healthy: 0, warning: 0, risky: 0};
  d.accounts.forEach((a) => { hc[a.health] = (hc[a.health] || 0) + 1; });

  const pc = {ok: 0, failed: 0, untested: 0};
  d.proxies.forEach((p) => { pc[p.status] = (pc[p.status] || 0) + 1; });

  const newHtml = `
    <div class="uploadAnalyticsGrid">
      ${_analyticsCard('Queued Today',   d.today.queued,    d.today.queued    > 0 ? 'ok'   : 'none')}
      ${_analyticsCard('Uploaded Today', d.today.uploaded,  d.today.uploaded  > 0 ? 'ok'   : 'none')}
      ${_analyticsCard('Failed Today',   d.today.failed,    d.today.failed    > 0 ? 'warn' : 'ok')}
      ${_analyticsCard('Retries',        d.today.retry,     d.today.retry     > 0 ? 'warn' : 'ok')}
      ${_analyticsCard('Success Rate',   srText,            srState)}
    </div>
    <div class="uploadAnalyticsSubGrid">
      ${_analyticsCard('Healthy Accts',  hc.healthy,        hc.healthy  > 0 ? 'ok'   : 'none')}
      ${_analyticsCard('Warning Accts',  hc.warning,        hc.warning  > 0 ? 'warn' : 'ok')}
      ${_analyticsCard('Risky Accts',    hc.risky,          hc.risky    > 0 ? 'risky': 'ok')}
      ${_analyticsCard('Proxy OK',       pc.ok,             pc.ok       > 0 ? 'ok'   : 'none')}
      ${_analyticsCard('Proxy Failed',   pc.failed,         pc.failed   > 0 ? 'warn' : 'ok')}
    </div>
    ${_renderAccountAnalyticsTable(d.accounts)}
    ${_renderProxyAnalyticsTable(d.proxies)}
    <div class="analyticsBottomRow">
      ${_renderFailureReasonList(d.failureReasons)}
      ${_renderRetryEffectiveness(d.retry)}
    </div>
    ${_renderRecentAuditSnapshot(5)}
  `;
  if(body.innerHTML !== newHtml) body.innerHTML = newHtml;
}

function scheduleRenderUploadAnalytics(){
  if(__analyticsRenderTimer) return;
  __analyticsRenderTimer = setTimeout(() => {
    __analyticsRenderTimer = null;
    renderAnalyticsDashboard();
  }, 80);
}

function safeRenderUploadAnalytics(){
  try{ scheduleRenderUploadAnalytics(); }catch(e){ console.warn('[Analytics] schedule failed:', e); }
}

async function refreshAnalytics(){
  const btn = qs('analytics_refresh_btn');
  if(btn){ btn.disabled = true; btn.textContent = 'Refreshing…'; }
  try{
    await Promise.all([loadUploadAccounts(), loadUploadQueueManager(), _loadProxyPool()]);
  }catch(e){ console.warn('[Analytics] refresh partial error:', e); }
  renderAnalyticsDashboard();
  _auditLog('analytics_refreshed', `${uploadQueueManagerItems.length} queue items`);
  if(btn){ btn.disabled = false; btn.textContent = 'Refresh'; }
}

function toggleAnalyticsPanel(btn){
  const panel = qs('analytics_dashboard_container');
  if(!panel) return;
  const expanded = btn.getAttribute('aria-expanded') === 'true';
  btn.setAttribute('aria-expanded', String(!expanded));
  panel.hidden = expanded;
  const arrow = btn.querySelector('.auditLogToggleArrow');
  if(arrow) arrow.textContent = expanded ? '▶' : '▼';
  if(!expanded) renderAnalyticsDashboard();
}

// --- INIT ---

async function initAutomationPanel(){
  await _loadProxyPool();
  loadAutomationSettings();
  renderAutomationDashboard();
  renderProxyPool();
  renderProxyPoolDashboard();
  _populateProxyPoolSelect();
  // Defer analytics: panel is collapsed by default; render after layout settles
  setTimeout(safeRenderUploadAnalytics, 0);
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', initAutomationPanel);
}else{
  initAutomationPanel();
}

// --- MARKET BEHAVIOR ENGINE ---

const __MARKET_WINDOWS = {
  US: [{ start: 17, end: 22 }],
  JP: [{ start: 18, end: 23 }],
  EU: [{ start: 17, end: 21 }],
};

function isWithinMarketWindow(acc){
  const market = acc.market || 'US';
  const hour = new Date().getHours();
  const windows = __MARKET_WINDOWS[market] || [];
  return windows.some((w) => hour >= w.start && hour <= w.end);
}

function pickLeastLoadedAccount(accounts){
  return [...accounts].sort((a, b) => {
    const qa = (uploadQueueManagerItems || []).filter((i) => i.account_id === a.account_id).length;
    const qb = (uploadQueueManagerItems || []).filter((i) => i.account_id === b.account_id).length;
    return qa - qb;
  })[0];
}

function detectProxyMarketMismatch(acc){
  if(!acc.proxy_id) return false;
  const proxy = (_proxyPool || []).find((p) => p.id === acc.proxy_id);
  if(!proxy) return false;
  if(!proxy.market || !acc.market) return false;
  if(proxy.market !== acc.market){
    console.warn('Proxy-market mismatch:', acc.display_name);
    return true;
  }
  return false;
}

function randomizeBehaviorDelay(){
  const delay = Math.random() * 2000 + 500; // 0.5–2.5s
  return new Promise((res) => setTimeout(res, delay));
}

function simulateHumanIdle(){
  const chance = Math.random();
  if(chance < 0.1){
    console.log('Simulating idle pause');
  }
}

if(!window.__marketBehaviorStarted){
  window.__marketBehaviorStarted = true;
  setInterval(simulateHumanIdle, 150000);
}

// --- PRODUCTION INTELLIGENCE ---

function computeAccountTrust(acc){
  let score = 100;
  if(acc.login_state !== 'logged_in') score -= 40;
  const fails = (uploadQueueManagerItems || []).filter((i) =>
    i.account_id === acc.account_id && i.status === 'failed'
  ).length;
  score -= Math.min(30, fails * 10);
  if(isProxyQuarantined?.(acc.proxy_id)) score -= 30;
  return Math.max(0, score);
}

function allowByTrust(acc){
  const score = computeAccountTrust(acc);
  if(score < 40){
    console.warn('Blocked by low trust:', acc.display_name, score);
    return false;
  }
  return true;
}

function maybeRotateProxy(acc){
  if(!acc.proxy_id) return;
  const fails = (uploadQueueManagerItems || []).filter((i) =>
    i.account_id === acc.account_id &&
    i.status === 'failed' &&
    (i.error || '').toLowerCase().includes('proxy')
  ).length;
  if(fails >= 2){
    console.warn('Suggest proxy rotation for:', acc.display_name);
  }
}

function shouldRetry(item){
  if(item.status !== 'failed') return false;
  const attempts = item.attempt_count || 0;
  if(attempts >= (item.max_attempts || 3)) return false;
  const delayMap = [5, 15, 45]; // minutes
  const suggested = delayMap[Math.min(attempts, delayMap.length - 1)];
  console.log('Retry allowed with delay suggestion:', suggested);
  return true;
}

function isGoodPostingTime(acc){
  const hour = new Date().getHours();
  if(hour >= 1 && hour <= 6){
    console.warn('Bad posting time (night):', acc.display_name);
    return false;
  }
  return true;
}

function detectSystemRisk(){
  const failed = (uploadQueueManagerItems || []).filter((i) => i.status === 'failed');
  if(failed.length >= 5){
    console.error('High failure rate detected — consider stopping scheduler');
  }
}

if(!window.__productionIntelStarted){
  window.__productionIntelStarted = true;
  setInterval(detectSystemRisk, 60000);
}

// --- ANTI-DETECT LITE ---

const __MARKET_TZ = {
  US: 'America/New_York',
  JP: 'Asia/Tokyo',
  EU: 'Europe/Berlin',
};

const __MARKET_LOCALE = {
  US: 'en-US',
  JP: 'ja-JP',
  EU: 'de-DE',
};

function resolveAccountRuntimeEnv(acc){
  const market = acc.market || acc.target_market || 'US';
  return {
    timezone: __MARKET_TZ[market] || Intl.DateTimeFormat().resolvedOptions().timeZone,
    locale:   __MARKET_LOCALE[market] || navigator.language,
  };
}

function applyHumanJitter(ts){
  const base = new Date(ts).getTime();
  const offset = (Math.random() * 6 + 1) * 60 * 1000; // 1–7 minutes
  const dir = Math.random() > 0.5 ? 1 : -1;
  return new Date(base + dir * offset).toISOString();
}

let __lastActionTs = 0;

function guardRapidAction(minGapMs = 3000){
  const now = Date.now();
  if(now - __lastActionTs < minGapMs){
    console.warn('Action too fast — blocked');
    return false;
  }
  __lastActionTs = now;
  return true;
}

function detectEnvMismatch(acc){
  const env = resolveAccountRuntimeEnv(acc);
  const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if(env.timezone !== localTz){
    console.warn('Timezone mismatch:', acc.display_name, env.timezone, localTz);
  }
}

function detectFastUploadPattern(){
  const now = Date.now();
  const recent = (uploadQueueManagerItems || []).filter((i) => {
    const t = new Date(i.created_at || 0).getTime();
    return now - t < 5 * 60 * 1000;
  });
  if(recent.length >= 3){
    console.warn('Rapid upload pattern detected:', recent.length);
  }
}

if(!window.__antiDetectStarted){
  window.__antiDetectStarted = true;
  setInterval(detectFastUploadPattern, 60000);
}

// --- STABILITY LAYER ---

const __proxyQuarantine = new Map(); // proxyId -> untilTs

function isProxyQuarantined(proxyId){
  const t = __proxyQuarantine.get(proxyId);
  return t && t > Date.now();
}

function quarantineProxy(proxyId, minutes = 30){
  if(!proxyId) return;
  const until = Date.now() + minutes * 60 * 1000;
  __proxyQuarantine.set(proxyId, until);
  console.warn('Proxy quarantined:', proxyId, 'until', new Date(until).toISOString());
}

function detectProxyFailuresAndQuarantine(){
  (uploadQueueManagerItems || []).forEach((i) => {
    if(i.status !== 'failed') return;
    const err = (i.error || i.blocked_reason || '').toLowerCase();
    if(!err) return;
    const isProxy = err.includes('proxy') || err.includes('timeout') ||
                    err.includes('connection') || err.includes('network') ||
                    err.includes('dns') || err.includes('tunnel');
    if(!isProxy) return;
    const acc = (uploadAccountManagerItems || []).find((a) => a.account_id === i.account_id);
    const proxyId = acc?.proxy_id;
    if(proxyId) quarantineProxy(proxyId, 30);
  });
}

function getWarmupLimit(acc){
  const created = new Date(acc.created_at || Date.now()).getTime();
  const ageDays = Math.floor((Date.now() - created) / (24 * 60 * 60 * 1000));
  if(ageDays < 1) return 1;
  if(ageDays < 3) return 2;
  if(ageDays < 7) return 3;
  return acc.daily_limit || 5;
}

function safeAllowAssignment(assignment, acc){
  if(isProxyQuarantined(acc.proxy_id)){
    console.warn('Skip (proxy quarantined):', acc.display_name);
    return false;
  }
  const warmLimit = getWarmupLimit(acc);
  if((acc.today_count || 0) >= warmLimit){
    console.warn('Skip (warm-up limit):', acc.display_name);
    return false;
  }
  const now = Date.now();
  const near = (uploadQueueManagerItems || []).some((i) => {
    if(i.account_id !== acc.account_id) return false;
    const t = new Date(i.scheduled_at || 0).getTime();
    return Math.abs(t - now) < (15 * 60 * 1000);
  });
  if(near){
    console.warn('Skip (too dense):', acc.display_name);
    return false;
  }
  if(!isWithinMarketWindow(acc)){
    console.warn('Skip (outside market window):', acc.display_name);
    return false;
  }
  if(detectProxyMarketMismatch(acc)){
    console.warn('Skip (proxy mismatch):', acc.display_name);
    return false;
  }
  return true;
}

function getSuggestedBackoff(attempt){
  const map = [5, 15, 45]; // minutes
  return map[Math.min(attempt || 0, map.length - 1)];
}

if(!window.__stabilityLayerStarted){
  window.__stabilityLayerStarted = true;
  setInterval(detectProxyFailuresAndQuarantine, 60000);
}

// --- SMART SYSTEM BEHAVIOR ---

async function autoDetectLoginState(){
  for(const acc of uploadAccountManagerItems || []){
    if(!acc.profile_path) continue;
    try{
      const res = await fetch(`/api/upload/accounts/${acc.account_id}/login-check`);
      const data = await res.json();
      if(data?.logged_in && acc.login_state !== 'logged_in'){
        acc.login_state = 'logged_in';
      }
      if(!data?.logged_in && acc.login_state === 'logged_in'){
        acc.login_state = 'expired';
      }
    }catch(e){
      console.warn('auto login detect failed', acc.account_id);
    }
  }
  UploadStore.setAccounts([...uploadAccountManagerItems]);
}

function smartRetryFailed(){
  const retryable = (uploadQueueManagerItems || []).filter((i) => shouldRetry(i));
  if(!retryable.length) return;
  retryable.forEach((i) => {
    const acc = uploadAccountManagerItems.find((a) => a.account_id === i.account_id);
    if(acc) maybeRotateProxy(acc);
  });
  console.log('Smart retry triggered:', retryable.length);
  retryFailedUploads?.();
}

function suggestProxyRotation(){
  const problematic = uploadQueueManagerItems.filter((i) =>
    i.status === 'failed' && (i.error || '').toLowerCase().includes('proxy')
  );
  if(!problematic.length) return;
  console.warn('Proxy issues detected, suggest rotation');
}

function detectAggressiveSchedule(){
  const now = Date.now();
  const near = uploadQueueManagerItems.filter((i) => {
    const t = new Date(i.scheduled_at || 0).getTime();
    return t > now && t < now + (2 * 60 * 60 * 1000);
  });
  if(near.length >= 5){
    console.warn('High density upload detected:', near.length);
  }
}

if(!window.__smartBehaviorStarted){
  window.__smartBehaviorStarted = true;
  setInterval(autoDetectLoginState,    60000);
  setInterval(smartRetryFailed,        45000);
  setInterval(suggestProxyRotation,    90000);
  setInterval(detectAggressiveSchedule, 60000);
}

// --- WORKER NODE ORCHESTRATION ---

let __workerMode = false;

function toggleWorkerMode(){
  __workerMode = !__workerMode;
  console.log('Worker mode:', __workerMode);
}

async function dispatchToWorker(job){
  if(!__workerMode) return false;
  try{
    await fetch('/api/upload/workers/dispatch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(job),
    });
    return true;
  }catch(e){
    console.warn('Dispatch failed');
    return false;
  }
}

// --- PHASE 7: DEBUG STATE HELPER ---

window.__uploadDebugState = function(){
  return {
    uploadAccountManagerItems,
    uploadVideoLibraryItems,
    uploadQueueManagerItems,
    _autoSettings,
    _autoPlanData,
    _autoPlanExcluded: [..._autoPlanExcluded],
    _cachedSchedulerData,
    selectedUploadVideoIds: [...selectedUploadVideoIds],
    _batchPreviewData,
    _proxyPool,
    auditLog: _auditGetEntries(),
  };
};
