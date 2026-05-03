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
  uploadManagerActiveTab = ['videos', 'queue', 'settings'].includes(tab) ? tab : 'videos';
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
  if(!list) return;
  if(!items || !items.length){
    list.innerHTML = '<div class="uamEmpty">No upload accounts yet. <button class="primaryButton" type="button" onclick="openUploadEditor(\'account\')">+ Create First Account</button></div>';
    return;
  }
  list.innerHTML = items.map((item) => {
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
           onclick="_selectUploadEntity('account', '${esc(item.account_id)}')">
        <div class="uamAccountItemTop">
          <div class="uamAccountItemName" title="${esc(name)}">${esc(name)}</div>
          <div class="uamAccountItemBadges">
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
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="5" class="uvlEmpty">No upload videos yet. Add a file to start building your library.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || '').toLowerCase();
    const disabled = status === 'disabled';
    const caption = String(item.caption || '').trim();
    const selected = _selectedUploadId('video') === String(item.video_id || '');
    const queueTitle = disabled ? 'Video disabled' : (status !== 'ready' ? `Video status is ${status}` : 'Select this video for the queue form');
    const rowCls = [disabled ? 'isDisabled' : '', selected ? 'isSelected' : ''].filter(Boolean).join(' ');
    return `
      <tr class="${rowCls}" onclick="_selectUploadEntity('video', '${esc(item.video_id)}')">
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
}

// =============================================================================
// RENDER: QUEUE MANAGER (6 visible columns: Video / Account / Status / Scheduled / Attempts / Actions)
// Phase 0: global queue view; account-filtered view is Phase 1.
// =============================================================================

function renderUploadQueueManager(items){
  const tbody = qs('upload_queue_manager_tbody');
  if(!tbody) return;
  if(!items || !items.length){
    tbody.innerHTML = '<tr><td colspan="6" class="uqmEmpty">No queue items yet. Select a video and account to create one.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const status = String(item.status || 'pending').toLowerCase();
    const muted = ['held', 'cancelled'].includes(status);
    const accountName = item.account_display_name || item.account_key || item.account_id || '-';
    const clipName = item.video_file_name || String(item.video_path || '').split(/[\\/]/).pop() || '-';
    const selected = _selectedUploadId('queue') === String(item.queue_id || '');
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
      runButton = `<button class="ghostButton" type="button" title="Retry failed queue item" onclick="event.stopPropagation(); runUploadQueueItem('${esc(item.queue_id)}')">Retry</button>`;
    } else if(status === 'uploading'){
      runButton = '<button class="ghostButton" type="button" disabled>Uploading…</button>';
    } else if(status === 'success'){
      runButton = '<button class="ghostButton" type="button" disabled>Done</button>';
    } else {
      runButton = `<button class="ghostButton" type="button" title="${esc(runDisabledReason)}" disabled>Run</button>`;
    }
    return `
      <tr class="${rowCls}" onclick="_selectUploadEntity('queue', '${esc(item.queue_id)}')">
        <td class="uqmColVideo">
          <div class="uqmClipName">${esc(clipName)}</div>
          ${item.last_error ? `<div class="uqmError">${esc(item.last_error)}</div>` : ''}
        </td>
        <td class="uqmColAccount">${esc(accountName)}</td>
        <td class="uqmColStatus">${_uamBadge(status, 'status')}</td>
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
      ${_detailSection('Profile Path', item.profile_path || '-', false)}
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
// FORM: ACCOUNT
// =============================================================================

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
  if(qs('uam_modal_title')) qs('uam_modal_title').textContent = 'New Account';
}
function fillUploadAccountForm(accountId){
  const item = uploadAccountManagerItems.find((x) => x.account_id === accountId);
  if(!item) return;
  _selectUploadEntity('account', accountId);
  openUploadAccountModal();
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
  if(qs('uam_modal_title')) qs('uam_modal_title').textContent = `Edit: ${item.display_name || item.account_key || item.account_id}`;
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
    showToast(loginState === 'logged_in' ? 'Login is valid' : (data.message || 'Login check completed'), loginState === 'logged_in' ? 'success' : 'info');
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
  if(!entries.length) return 'No blocked queue items.';
  return entries.map(([key, value]) => `${key}: ${value}`).join(' · ');
}

function renderUploadSchedulerStatus(data){
  const running = !!(data && (data.running || data.scheduler_enabled || String(data?.scheduler_status || '').toLowerCase() === 'running'));
  const stateText = running ? 'running' : 'stopped';
  ['upload_scheduler_status_badge', 'upload_scheduler_status_badge_top'].forEach((id) => {
    const badge = qs(id);
    if(badge){ badge.textContent = stateText; badge.dataset.state = stateText; badge.setAttribute('data-state', stateText); }
  });
  ['upload_scheduler_meta', 'upload_scheduler_meta_top'].forEach((id) => {
    const meta = qs(id);
    if(meta) meta.textContent = `Eligible ${Number(data?.next_eligible_count || 0)} · Running ${Number(data?.running_count || 0)}`;
  });
  if(qs('upload_scheduler_blocked')) qs('upload_scheduler_blocked').textContent = _schedulerBlockedSummary(data?.blocked_counts || {});
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
