
// ── Upload Step Wizard ───────────────────────────────────────────────────────
// Maps each step to the DOM element IDs that belong to it.
// setUploadWizardStep() adds .stepGated (display:none !important) to all
// elements NOT in the active step, without touching the existing hiddenView
// logic that controls field-level visibility within each step.
const _UPLOAD_STEP_ELEMENTS = {
  1: ['upload_feature_launcher', 'upload_flow_box', 'upload_cluster_context',
      'upload_action_mode_field', 'upload_channels_root_field', 'channel_name_prefix_field',
      'upload_channel_field', 'upload_mode_field', 'upload_ui_level_field', 'upload_config_mode_field'],
  2: ['upload_cluster_account', 'upload_account_key_field', 'upload_profile_path_field',
      'upload_config_actions_field', 'upload_credential_line_field',
      'upload_tiktok_username_field', 'upload_tiktok_password_field',
      'upload_mail_username_field', 'upload_mail_password_field',
      'upload_login_username_field', 'upload_login_password_field',
      'upload_browser_preference_field', 'upload_browser_executable_field',
      'upload_login_actions_row'],
  3: ['upload_cluster_source', 'upload_video_input_dir_field', 'upload_json_panel',
      'upload_schedule_slots_wrap', 'upload_manual_select_wrap',
      'upload_max_items_field', 'upload_caption_prefix_field',
      'upload_cluster_caption_network', 'upload_caption_mode_field', 'upload_ollama_model_field',
      'upload_network_mode_field', 'upload_proxy_server_wrap',
      'upload_proxy_username_wrap', 'upload_proxy_password_wrap'],
  4: ['upload_cluster_run', 'upload_run_hint_field', 'upload_dry_run_field',
      'upload_include_hashtags_field', 'upload_headless_field',
      'upload_run_actions_row', 'upload_status_panel', 'upload_log_row'],
};
const _UPLOAD_STEP_HINTS = {
  1: 'Select action and channel to continue.',
  2: 'Enter credentials, then run Login Flow.',
  3: 'Configure upload source and caption options.',
  4: 'Review settings, then run the upload plan.',
};

function setUploadWizardStep(n) {
  uploadWizardStep = Math.max(1, Math.min(4, Number(n) || 1));

  // Update step indicator pills
  for (let i = 1; i <= 4; i++) {
    const el = qs(`upload_step_${i}`);
    if (!el) continue;
    el.classList.toggle('stepActive', i === uploadWizardStep);
    el.classList.toggle('stepDone', i < uploadWizardStep);
  }

  // Remove stepGated from every managed element
  const allIds = Object.values(_UPLOAD_STEP_ELEMENTS).flat();
  for (const id of allIds) {
    const el = qs(id);
    if (el) el.classList.remove('stepGated');
  }

  // Apply stepGated to all elements NOT in the active step
  for (const [stepStr, ids] of Object.entries(_UPLOAD_STEP_ELEMENTS)) {
    if (Number(stepStr) !== uploadWizardStep) {
      for (const id of ids) {
        const el = qs(id);
        if (el) el.classList.add('stepGated');
      }
    }
  }

  // Update nav buttons
  const backBtn = qs('upload_step_back');
  const nextBtn = qs('upload_step_next');
  const hint    = qs('upload_step_hint');
  if (backBtn) backBtn.style.visibility = uploadWizardStep > 1 ? 'visible' : 'hidden';
  if (nextBtn) nextBtn.style.display    = uploadWizardStep < 4 ? '' : 'none';
  if (hint)    hint.textContent         = _UPLOAD_STEP_HINTS[uploadWizardStep] || '';
}

function advanceUploadStep() {
  // Gate step 1 → 2: require channel selection
  if (uploadWizardStep === 1) {
    const hasRoot    = !!String(qs('upload_channels_root')?.value || '').trim();
    const hasChannel = !!String(qs('upload_channel')?.value || '').trim();
    if (!hasRoot) { showToast('Choose Channels Root Folder first', 'error'); return; }
    if (!hasChannel) { showToast('Select a channel before continuing', 'error'); return; }
  }
  // Gate step 2 → 3 (login mode): skip to step 4 (no source needed)
  if (uploadWizardStep === 2) {
    const isLogin = (qs('upload_action_mode')?.value || 'upload') === 'login';
    if (isLogin) { setUploadWizardStep(4); return; }
  }
  setUploadWizardStep(uploadWizardStep + 1);
}

function backUploadStep() {
  // Reverse of the skip: login mode at step 4 goes back to step 2
  if (uploadWizardStep === 4) {
    const isLogin = (qs('upload_action_mode')?.value || 'upload') === 'login';
    if (isLogin) { setUploadWizardStep(2); return; }
  }
  setUploadWizardStep(uploadWizardStep - 1);
}
// ── End Upload Step Wizard ───────────────────────────────────────────────────

function setUploadConfigEditMode(enabled){
  uploadConfigEditMode = !!enabled;
  const canProceed = !!String(qs('upload_channels_root')?.value || '').trim() && !!String(qs('upload_channel')?.value || '').trim();
  for(const id of uploadConfigEditableIds){
    const el = qs(id);
    if(!el) continue;
    el.disabled = !canProceed || !uploadConfigEditMode;
  }
  if(qs('upload_edit_cfg_btn')){
    qs('upload_edit_cfg_btn').textContent = uploadConfigEditMode ? 'Cancel Edit' : 'Edit Config';
    qs('upload_edit_cfg_btn').disabled = !canProceed;
  }
  if(qs('upload_save_cfg_btn')){
    qs('upload_save_cfg_btn').classList.toggle('hiddenView', !uploadConfigEditMode);
    qs('upload_save_cfg_btn').disabled = !canProceed || !uploadConfigEditMode;
  }
}

function toggleUploadConfigEdit(){
  setUploadConfigEditMode(!uploadConfigEditMode);
}

async function loadUploadChannelConfig(verbose = false){
  const channel = (qs('upload_channel')?.value || '').trim();
  if(!channel){
    if(verbose) addEvent('Please choose Channel first.');
    return;
  }
  const accountKey = _safeAccountKeyUi((qs('upload_account_key')?.value || '').trim() || 'default');
  try{
    const rootParam = uploadChannelsRootPath ? `&root_path=${encodeURIComponent(uploadChannelsRootPath)}` : '';
    const res = await fetch(`/api/channels/${encodeURIComponent(channel)}/config?account_key=${encodeURIComponent(accountKey)}${rootParam}`);
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'load channel config failed');
    const settings = data.settings || {};
    const profile = data.profile || {};
    if(qs('upload_account_key')) qs('upload_account_key').value = String(profile.account_key || accountKey || 'default');
    if(qs('upload_browser_preference')) qs('upload_browser_preference').value = String(settings.browser_preference || profile.browser_preference || 'chromeportable').toLowerCase();
    if(qs('upload_browser_executable')) qs('upload_browser_executable').value = String(settings.browser_executable || profile.browser_executable || '').trim();
    if(qs('upload_network_mode')) qs('upload_network_mode').value = String(settings.network_mode || profile.network_mode || 'direct').toLowerCase();
    if(qs('upload_proxy_server')) qs('upload_proxy_server').value = String(settings.proxy_server || profile.proxy_server || '').trim();
    if(qs('upload_proxy_username')) qs('upload_proxy_username').value = String(settings.proxy_username || profile.proxy_username || '').trim();
    if(qs('upload_proxy_password')) qs('upload_proxy_password').value = String(settings.proxy_password || profile.proxy_password || '').trim();
    const slots = Array.isArray(settings.schedule_slots) ? settings.schedule_slots : [];
    if(qs('upload_schedule_slots')) qs('upload_schedule_slots').value = slots.length ? slots.join(',') : '07:00,17:00';
    let channelInputDir = '';
    try{
      const rootInfoParam = uploadChannelsRootPath ? `?root_path=${encodeURIComponent(uploadChannelsRootPath)}` : '';
      const chInfoRes = await fetch(`/api/channels/${encodeURIComponent(channel)}${rootInfoParam}`);
      const chInfo = await chInfoRes.json();
      if(chInfoRes.ok){
        channelInputDir = String(chInfo.input_dir || '').trim();
      }
    }catch(_){}
    if(qs('upload_video_input_dir')) qs('upload_video_input_dir').value = channelInputDir || String(profile.video_input_dir || '').trim();
    if(qs('upload_tiktok_username')) qs('upload_tiktok_username').value = String(profile.tiktok_username || profile.login_username || '').trim();
    if(qs('upload_tiktok_password')) qs('upload_tiktok_password').value = String(profile.tiktok_password || profile.login_password || '').trim();
    if(qs('upload_mail_username')) qs('upload_mail_username').value = String(profile.mail_username || '').trim();
    if(qs('upload_mail_password')) qs('upload_mail_password').value = String(profile.mail_password || '').trim();
    const tiktokUser = String(profile.tiktok_username || profile.login_username || '').trim();
    const tiktokPass = String(profile.tiktok_password || profile.login_password || '').trim();
    const mailUser = String(profile.mail_username || '').trim();
    const mailPass = String(profile.mail_password || '').trim();
    const profileCredLine = String(profile.credential_line || '').trim();
    if(qs('upload_credential_line')){
      if(profileCredLine){
        qs('upload_credential_line').value = profileCredLine;
      } else if(tiktokUser && tiktokPass && mailUser && mailPass){
        qs('upload_credential_line').value = `${tiktokUser}|${tiktokPass}|${mailUser}|${mailPass}`;
      }
    }
    if(qs('upload_profile_path')) qs('upload_profile_path').value = String(profile.user_data_dir || '').trim();
    syncUploadJsonModeUI();
    setUploadConfigEditMode(false);
    if(verbose) addEvent(`Loaded channel config: ${channel} / ${String(profile.account_key || accountKey)}`);
  }catch(e){
    if(verbose) addEvent(`Load channel config failed: ${e.message || e}`);
  }
}

async function saveUploadChannelConfig(){
  const payload = collectUploadPayload();
  if(!payload.channel_code){
    addEvent('Save config failed: choose upload channel first.');
    return;
  }
  try{
    const res = await fetch('/api/upload/config/save', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'save failed');
    setUploadConfigEditMode(false);
    addEvent(`Config saved for ${payload.channel_code} / ${data.account_key || payload.account_key}.`);
    await loadUploadChannelConfig(false);
  }catch(e){
    addEvent(`Save config failed: ${e.message || e}`);
  }
}

function _safeAccountKeyUi(raw){
  const text = String(raw || 'default').trim().toLowerCase();
  const normalized = text.replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
  return normalized || 'default';
}

function _joinWinPath(...parts){
  return parts
    .map((p) => String(p || '').replace(/\//g, '\\').trim().replace(/^\\+|\\+$/g, ''))
    .filter(Boolean)
    .join('\\');
}

function _resolveUploadUserDataDir(channelCode, accountKey, browserPref){
  const root = String(uploadChannelsRootPath || '').trim();
  if(!root || !channelCode) return '';
  const browserKey = String(browserPref || 'chromeportable').toLowerCase().includes('firefox') ? 'firefoxportable' : 'chromeportable';
  return _joinWinPath(root, channelCode, 'account', 'profiles', accountKey, 'browser-profile', `${browserKey}_${accountKey}`);
}

function _resolveUploadBrowserExecutable(channelCode, browserPref){
  const root = String(uploadChannelsRootPath || '').trim();
  if(!root || !channelCode) return '';
  const base = _joinWinPath(root, channelCode, 'browser-profile');
  const pref = String(browserPref || 'chromeportable').toLowerCase();
  if(pref.includes('firefox')){
    return _joinWinPath(base, 'firefoxportable', 'App', 'Firefox64', 'firefox.exe');
  }
  return _joinWinPath(base, 'chromeportable', 'App', 'Chrome-bin', 'chrome.exe');
}

function parseUploadScheduleSlots(){
  const raw = (qs('upload_schedule_slots')?.value || '07:00,17:00').trim();
  const parts = raw.split(',').map(x => x.trim()).filter(Boolean);
  const valid = [];
  for(const p of parts){
    if(/^\d{1,2}:\d{2}$/.test(p)){
      const [h, m] = p.split(':').map(Number);
      if(h >= 0 && h <= 23 && m >= 0 && m <= 59) valid.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
    }
  }
  return valid.length ? [...new Set(valid)] : ['07:00', '17:00'];
}

function parseUploadScheduleSlotsDetailed(){
  const raw = (qs('upload_schedule_slots')?.value || '').trim();
  const parts = raw ? raw.split(',').map(x => x.trim()).filter(Boolean) : [];
  const valid = [];
  for(const p of parts){
    if(/^\d{1,2}:\d{2}$/.test(p)){
      const [h, m] = p.split(':').map(Number);
      if(h >= 0 && h <= 23 && m >= 0 && m <= 59){
        valid.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
      }
    }
  }
  return {
    raw,
    tokens: parts,
    valid: [...new Set(valid)]
  };
}

function _parseCredentialLineRaw(raw){
  const text = String(raw || '').trim();
  if(!text) return null;
  const delim = text.includes('|') ? '|' : (text.includes('/') ? '/' : '|');
  const parts = text.split(delim).map(x => x.trim());
  if(parts.length !== 4 || parts.some(x => !x)) return null;
  const [tiktokUser, tiktokPass, mailUser, mailPass] = parts;
  return { tiktokUser, tiktokPass, mailUser, mailPass };
}

function parseCredentialLine(){
  const parsed = _parseCredentialLineRaw((qs('upload_credential_line')?.value || '').trim());
  if(!parsed){
    setUploadAction('profile', 'failed', 'Invalid credential format. Use: tiktok_user|tiktok_pass|mail_user|mail_pass');
    addEvent('Invalid credential line format. Expected: tiktok_user|tiktok_pass|mail_user|mail_pass');
    return;
  }
  const { tiktokUser, tiktokPass, mailUser, mailPass } = parsed;
  if(qs('upload_tiktok_username')) qs('upload_tiktok_username').value = tiktokUser;
  if(qs('upload_tiktok_password')) qs('upload_tiktok_password').value = tiktokPass;
  if(qs('upload_mail_username')) qs('upload_mail_username').value = mailUser;
  if(qs('upload_mail_password')) qs('upload_mail_password').value = mailPass;
  // Backward compatibility fields (used by existing login auto-fill path)
  if(qs('upload_login_username')) qs('upload_login_username').value = tiktokUser;
  if(qs('upload_login_password')) qs('upload_login_password').value = tiktokPass;
  if(qs('upload_account_key')){
    qs('upload_account_key').value = _safeAccountKeyUi(tiktokUser);
  }
  setUploadAction('profile', 'running', 'Credential parsed. Ready to ensure profile/login.', `Account key: ${_safeAccountKeyUi(tiktokUser)}`);
  addEvent('Credential line parsed successfully.');
  syncUploadJsonModeUI();
}

function syncUploadModeUI(){
  const mode = (qs('upload_mode')?.value || 'scheduled').toLowerCase();
  if(qs('upload_schedule_slots_wrap')) qs('upload_schedule_slots_wrap').classList.toggle('hiddenView', mode !== 'scheduled');
  if(qs('upload_manual_select_wrap')) qs('upload_manual_select_wrap').classList.toggle('hiddenView', mode !== 'manual');
  if(mode === 'manual' && qs('upload_video_select_box')?.children?.length <= 1){
    loadUploadVideos();
  }
}

function syncUploadActionModeUI(){
  const action = (qs('upload_action_mode')?.value || 'upload').toLowerCase();
  const isLogin = action === 'login';
  const isUpload = !isLogin;
  const show = (id, visible) => { const el = qs(id); if(el) el.classList.toggle('hiddenView', !visible); };
  const uploadChannelLabel = qs('#upload_channel_field .fieldLabel');
  if(uploadChannelLabel) uploadChannelLabel.textContent = isLogin ? 'Select Channel (Login)' : 'Select Channel (Upload)';

  // Upload-only clusters
  show('upload_cluster_source', isUpload);
  show('upload_video_input_dir_field', isUpload);
  show('upload_mode_field', isUpload);
  show('upload_max_items_field', isUpload);
  show('upload_caption_prefix_field', isUpload);
  show('upload_cluster_caption_network', isUpload);
  show('upload_caption_mode_field', isUpload);
  show('upload_ollama_model_field', isUpload);
  show('upload_cluster_run', isUpload);
  show('upload_run_hint_field', isUpload);
  show('upload_dry_run_field', isUpload);
  show('upload_include_hashtags_field', isUpload);
  show('upload_headless_field', isUpload);
  if (qs('run_upload_btn')) qs('run_upload_btn').classList.toggle('hiddenView', !isUpload);
  show('upload_config_actions_field', false);

  // Login-focused fields
  show('upload_login_username_field', false);
  show('upload_login_password_field', false);
  show('upload_credential_line_field', isLogin);
  show('upload_tiktok_username_field', false);
  show('upload_tiktok_password_field', false);
  show('upload_mail_username_field', false);
  show('upload_mail_password_field', false);
  show('upload_account_key_field', false);
  show('upload_profile_path_field', false);
  show('upload_browser_executable_field', false);
  show('upload_ui_level_field', false);
  if (qs('ensure_upload_btn')) qs('ensure_upload_btn').classList.toggle('hiddenView', !isLogin);

  // Buttons still useful in both modes
  if (qs('check_upload_btn')) qs('check_upload_btn').classList.toggle('hiddenView', false);
  if (qs('start_upload_login_btn')) qs('start_upload_login_btn').classList.toggle('hiddenView', false);

  // JSON panel is mostly for upload config; hide in login mode for simplicity.
  if (qs('upload_json_panel')) qs('upload_json_panel').classList.toggle('hiddenView', isLogin || ((qs('upload_config_mode')?.value || 'ui') === 'ui'));

  syncUploadModeUI();
  syncUploadUiLevel();

  const createBtn = qs('feature_create_btn');
  const loginBtn = qs('feature_login_btn');
  const uploadBtn = qs('feature_upload_btn');
  if(createBtn && currentView !== 'channels') createBtn.classList.remove('active');
  if(loginBtn) loginBtn.classList.toggle('active', isLogin && currentView === 'upload');
  if(uploadBtn) uploadBtn.classList.toggle('active', isUpload && currentView === 'upload');
}

function syncUploadUiLevel(){
  const action = (qs('upload_action_mode')?.value || 'upload').toLowerCase();
  const isLogin = action === 'login';
  const show = (id, visible) => { const el = qs(id); if(el) el.classList.toggle('hiddenView', !visible); };
  // Keep UI simple by default and hide technical controls.
  show('upload_ui_level_field', false);
  show('upload_config_mode_field', !isLogin && ((qs('upload_config_mode')?.value || 'ui') !== 'ui'));
  show('upload_json_panel', !isLogin && ((qs('upload_config_mode')?.value || 'ui') !== 'ui'));
  show('upload_account_key_field', false);
  show('upload_browser_executable_field', false);
  show('upload_tiktok_username_field', false);
  show('upload_tiktok_password_field', false);
  show('upload_mail_username_field', false);
  show('upload_mail_password_field', false);
  show('upload_login_username_field', false);
  show('upload_login_password_field', false);

  // Buttons simplified by mode
  if (qs('ensure_upload_btn')) qs('ensure_upload_btn').classList.toggle('hiddenView', !isLogin);
  if (qs('check_upload_btn')) qs('check_upload_btn').classList.toggle('hiddenView', false);
  if (qs('start_upload_login_btn')) qs('start_upload_login_btn').classList.toggle('hiddenView', false);
  if (qs('run_upload_btn')) qs('run_upload_btn').classList.toggle('hiddenView', isLogin);
}

function syncUploadNetworkModeUI(){
  const mode = (qs('upload_network_mode')?.value || 'direct').toLowerCase();
  const showProxy = mode === 'proxy';
  if(qs('upload_proxy_server_wrap')) qs('upload_proxy_server_wrap').classList.toggle('hiddenView', !showProxy);
  if(qs('upload_proxy_username_wrap')) qs('upload_proxy_username_wrap').classList.toggle('hiddenView', !showProxy);
  if(qs('upload_proxy_password_wrap')) qs('upload_proxy_password_wrap').classList.toggle('hiddenView', !showProxy);
}

function evaluateUploadValidation(payload = null){
  const p = payload || collectUploadPayload();
  const action = (qs('upload_action_mode')?.value || 'upload').toLowerCase();
  const isLogin = action === 'login';
  const errors = [];
  const warnings = [];
  const rootPath = String(qs('upload_channels_root')?.value || '').trim();
  if(!rootPath) errors.push('Please choose Channels Root Folder first.');
  if(!String(p.channel_code || '').trim()) errors.push('Choose Channel first.');
  if((p.network_mode || '').toLowerCase() === 'proxy' && !String(p.proxy_server || '').trim()){
    errors.push('Proxy Server is required when Network Mode = Proxy.');
  }
  if(isLogin){
    const parsed = _parseCredentialLineRaw((qs('upload_credential_line')?.value || '').trim());
    const hasTikTok = (!!String(p.tiktok_username || '').trim() && !!String(p.tiktok_password || '').trim()) || !!(parsed?.tiktokUser && parsed?.tiktokPass);
    const hasMail = (!!String(p.mail_username || '').trim() && !!String(p.mail_password || '').trim()) || !!(parsed?.mailUser && parsed?.mailPass);
    if(!hasTikTok || !hasMail){
      errors.push('Credential Line is required: tiktok_user|tiktok_pass|mail_user|mail_pass');
    }
    return { valid: errors.length === 0, errors, warnings };
  }
  if(!String(p.video_input_dir || '').trim()) errors.push('Upload Source Folder is empty (channel mapping missing).');
  if(p.use_schedule){
    const slotsInfo = parseUploadScheduleSlotsDetailed();
    if(!slotsInfo.valid.length){
      errors.push('Schedule slots invalid. Use format like 07:00,12:00,17:00.');
    } else if(slotsInfo.tokens.length && slotsInfo.valid.length < slotsInfo.tokens.length){
      warnings.push('Some schedule slots are invalid and will be ignored.');
    }
  } else {
    const count = Array.isArray(p.selected_files) ? p.selected_files.length : 0;
    if(count <= 0) errors.push('Manual mode requires selecting at least one video.');
  }
  return { valid: errors.length === 0, errors, warnings };
}

function applyUploadControlGating(state){
  const hasRoot = !!String(qs('upload_channels_root')?.value || '').trim();
  const hasChannel = !!String(qs('upload_channel')?.value || '').trim();
  const canProceed = hasRoot && hasChannel;
  const gatedIds = [
    'upload_action_mode','upload_mode','upload_config_mode','upload_account_key','upload_login_username','upload_login_password',
    'upload_credential_line','upload_tiktok_username','upload_tiktok_password','upload_mail_username','upload_mail_password',
    'upload_browser_preference','upload_browser_executable','upload_max_items','upload_caption_prefix',
    'upload_caption_mode','upload_ollama_model','upload_network_mode','upload_proxy_server','upload_proxy_username',
    'upload_proxy_password','upload_schedule_slots','upload_dry_run','upload_include_hashtags','upload_headless'
  ];
  for(const id of gatedIds){
    const el = qs(id);
    if(el) el.disabled = !canProceed;
  }
  const actionBtns = ['ensure_upload_btn','check_upload_btn','start_upload_login_btn','run_upload_btn'];
  for(const id of actionBtns){
    const btn = qs(id);
    if(btn) btn.disabled = !canProceed;
  }
  if(qs('run_upload_btn')) qs('run_upload_btn').disabled = !canProceed || !state.valid;
  if(qs('upload_reload_cfg_btn')) qs('upload_reload_cfg_btn').disabled = !canProceed;
  setUploadConfigEditMode(uploadConfigEditMode);
}

function renderUploadValidation(state){
  const action = (qs('upload_action_mode')?.value || 'upload').toLowerCase();
  const panel = qs('upload_validation_panel');
  const title = qs('upload_validation_title');
  const items = qs('upload_validation_items');
  if(!panel || !title || !items) return;
  panel.classList.remove('ok', 'warn');
  if(state.errors.length){
    title.textContent = `Validation (${action}): ${state.errors.length} issue(s) need fixing`;
    items.innerHTML = state.errors.map((x) => `<div class="validationItem">- ${esc(x)}</div>`).join('');
    panel.classList.add('warn');
    return;
  }
  if(state.warnings.length){
    title.textContent = `Validation (${action}): ready with warnings`;
    items.innerHTML = state.warnings.map((x) => `<div class="validationItem">- ${esc(x)}</div>`).join('');
    panel.classList.add('warn');
    return;
  }
  title.textContent = action === 'login' ? 'Validation (login): ready to open login flow' : 'Validation (upload): ready to run';
  items.innerHTML = action === 'login'
    ? '<div class="validationItem">Channel/account/network settings are valid for login.</div>'
    : '<div class="validationItem">All required upload fields are valid.</div>';
  panel.classList.add('ok');
}

function refreshUploadValidationState(payload = null){
  const state = evaluateUploadValidation(payload || collectUploadPayload());
  applyUploadControlGating(state);
  renderUploadValidation(state);
  return state;
}

function renderUploadVideoSelection(items){
  const box = qs('upload_video_select_box');
  if(!box) return;
  if(!items || !items.length){
    box.innerHTML = '<div class="emptyState">No videos found in channel upload folder.</div>';
    return;
  }
  box.innerHTML = items.map((name, idx) => `
    <label class="partRow" style="cursor:pointer">
      <div class="partLeft"><div class="rankBadge">${idx + 1}</div><div><div class="partName">${esc(name)}</div></div></div>
      <div class="partRight"><input type="checkbox" data-upload-video value="${esc(name)}" ${selectedUploadVideos.includes(name) ? 'checked' : ''}></div>
    </label>
  `).join('');
  _syncSelectedUploadVideosFromUI();
  box.querySelectorAll('input[data-upload-video]').forEach((el) => {
    el.addEventListener('change', _syncSelectedUploadVideosFromUI);
  });
  refreshUploadValidationState();
}

async function loadUploadVideos(){
  const channel = (qs('upload_channel')?.value || '').trim();
  if(!channel){
    setUploadAction('channel', 'failed', 'Please choose Channel first.');
    addEvent('Please choose Channel first.');
    return;
  }
  try{
    setUploadAction('channel', 'running', `Loading upload videos for channel ${channel}...`);
    const rootParam = uploadChannelsRootPath ? `?root_path=${encodeURIComponent(uploadChannelsRootPath)}&account_key=${encodeURIComponent(_safeAccountKeyUi((qs('upload_account_key')?.value || '').trim() || 'default') || 'default')}` : '';
    const res = await fetch(`/api/upload/videos/${encodeURIComponent(channel)}${rootParam}`);
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'load videos failed');
    const items = Array.isArray(data.items) ? data.items : [];
    const resolvedInputDir = String(data.input_dir || '').trim();
    if(resolvedInputDir && qs('upload_video_input_dir')) qs('upload_video_input_dir').value = resolvedInputDir;
    selectedUploadVideos = selectedUploadVideos.filter(x => items.includes(x));
    renderUploadVideoSelection(items);
    setUploadAction('channel', 'running', `Source ready: ${items.length} video(s) found.`, resolvedInputDir || '-');
    addEvent(`Loaded ${items.length} video(s) from: ${resolvedInputDir || 'channel folder'}.`);
  }catch(e){
    setUploadAction('channel', 'failed', `Load upload videos failed: ${e.message || e}`);
    addEvent(`Load upload videos failed: ${e.message || e}`);
  }
  refreshUploadValidationState();
}

function _syncSelectedUploadVideosFromUI(){
  const box = qs('upload_video_select_box');
  if(!box) return;
  selectedUploadVideos = Array.from(box.querySelectorAll('input[data-upload-video]:checked')).map(x => x.value);
}

function selectAllUploadVideos(){
  const box = qs('upload_video_select_box');
  if(!box) return;
  box.querySelectorAll('input[data-upload-video]').forEach((el) => { el.checked = true; });
  _syncSelectedUploadVideosFromUI();
  addEvent(`Manual selected: ${selectedUploadVideos.length} video(s).`);
  refreshUploadValidationState();
}

function clearUploadVideos(){
  const box = qs('upload_video_select_box');
  if(!box) return;
  box.querySelectorAll('input[data-upload-video]').forEach((el) => { el.checked = false; });
  _syncSelectedUploadVideosFromUI();
  addEvent('Manual selection cleared.');
  refreshUploadValidationState();
}

function buildUploadJsonTemplate(){
  const channel = (qs('upload_channel')?.value || 'T1').trim() || 'T1';
  const accountKey = _safeAccountKeyUi(qs('upload_account_key')?.value || 'default');
  const scheduleSlots = parseUploadScheduleSlots();
  const proxyMode = (qs('upload_network_mode')?.value || 'direct').trim().toLowerCase();
  const browserPreference = (qs('upload_browser_preference')?.value || 'chromeportable').trim().toLowerCase();
  const browserExecutable = (qs('upload_browser_executable')?.value || '').trim();
  const loginUsername = (qs('upload_login_username')?.value || '').trim();
  const loginPassword = (qs('upload_login_password')?.value || '').trim();
  const tiktokUsername = (qs('upload_tiktok_username')?.value || '').trim();
  const tiktokPassword = (qs('upload_tiktok_password')?.value || '').trim();
  const mailUsername = (qs('upload_mail_username')?.value || '').trim();
  const mailPassword = (qs('upload_mail_password')?.value || '').trim();
  const base = `channels/${channel}`;
  return {
    channel_code: channel,
    account_key: accountKey,
    platform: 'tiktok',
    user_data_dir: `${base}/account/profiles/${accountKey}/browser-profile`,
    video_input_dir: `${base}/video_out`,
    uploaded_dir: `${base}/upload/uploaded/${accountKey}`,
    failed_dir: `${base}/upload/failed/${accountKey}`,
    hashtags_file: `${base}/hashtag/hashtags.txt`,
    schedule_slots: scheduleSlots,
    timezone_schedule: 'LOCAL',
    upload_url: 'https://www.tiktok.com/upload',
    network_mode: proxyMode,
    proxy_server: (qs('upload_proxy_server')?.value || '').trim(),
    proxy_username: (qs('upload_proxy_username')?.value || '').trim(),
    proxy_password: (qs('upload_proxy_password')?.value || '').trim(),
    proxy_bypass: '',
    use_gpm: false,
    gpm_profile_id: '',
    gpm_browser_ws: '',
    browser_preference: browserPreference,
    browser_executable: browserExecutable,
    login_username: loginUsername,
    login_password: loginPassword,
    tiktok_username: tiktokUsername,
    tiktok_password: tiktokPassword,
    mail_username: mailUsername,
    mail_password: mailPassword
  };
}

function buildUploadSettingsJsonTemplate(){
  const channel = (qs('upload_channel')?.value || 'T1').trim() || 'T1';
  const scheduleSlots = parseUploadScheduleSlots();
  const proxyMode = (qs('upload_network_mode')?.value || 'direct').trim().toLowerCase();
  const browserPreference = (qs('upload_browser_preference')?.value || 'chromeportable').trim().toLowerCase();
  const browserExecutable = (qs('upload_browser_executable')?.value || '').trim();
  const loginUsername = (qs('upload_login_username')?.value || '').trim();
  const loginPassword = (qs('upload_login_password')?.value || '').trim();
  const tiktokUsername = (qs('upload_tiktok_username')?.value || '').trim();
  const tiktokPassword = (qs('upload_tiktok_password')?.value || '').trim();
  const mailUsername = (qs('upload_mail_username')?.value || '').trim();
  const mailPassword = (qs('upload_mail_password')?.value || '').trim();
  return {
    channel_code: channel,
    video_output_subdir: 'video_out',
    default_video_input_dir: 'video_out',
    timezone_schedule: 'LOCAL',
    schedule_slots: scheduleSlots,
    network_mode: proxyMode,
    proxy_server: (qs('upload_proxy_server')?.value || '').trim(),
    proxy_username: (qs('upload_proxy_username')?.value || '').trim(),
    proxy_password: (qs('upload_proxy_password')?.value || '').trim(),
    proxy_bypass: '',
    use_gpm: false,
    gpm_profile_id: '',
    gpm_browser_ws: '',
    browser_preference: browserPreference,
    browser_executable: browserExecutable,
    login_username: loginUsername,
    login_password: loginPassword,
    tiktok_username: tiktokUsername,
    tiktok_password: tiktokPassword,
    mail_username: mailUsername,
    mail_password: mailPassword,
    upload_url: 'https://www.tiktok.com/upload'
  };
}

function syncUploadJsonModeUI(){
  const mode = (qs('upload_config_mode')?.value || 'ui').trim().toLowerCase();
  const panel = qs('upload_json_panel');
  const isLogin = (qs('upload_action_mode')?.value || 'upload').toLowerCase() === 'login';
  if(panel) panel.classList.toggle('hiddenView', isLogin || mode === 'ui');
  syncUploadActionModeUI();
  syncUploadNetworkModeUI();
  const channel = (qs('upload_channel')?.value || 'T1').trim() || 'T1';
  const rawAccountKey = (qs('upload_account_key')?.value || '').trim();
  const rawTiktokUser = (qs('upload_tiktok_username')?.value || '').trim();
  const parsedCred = _parseCredentialLineRaw((qs('upload_credential_line')?.value || '').trim());
  const accountKey = _safeAccountKeyUi(
    rawAccountKey && rawAccountKey.toLowerCase() !== 'default'
      ? rawAccountKey
      : (rawTiktokUser || parsedCred?.tiktokUser || rawAccountKey || 'default')
  );
  const relativePath = `channels/${channel}/account/profiles/${accountKey}/account.json`;
  const settingsPath = `channels/${channel}/account/upload_settings.json`;
  const profilePath = _resolveUploadUserDataDir(channel, accountKey, (qs('upload_browser_preference')?.value || 'chromeportable').trim().toLowerCase())
    || `channels/${channel}/account/profiles/${accountKey}/browser-profile`;
  if(qs('upload_json_path')) qs('upload_json_path').value = relativePath;
  if(qs('upload_profile_path')) qs('upload_profile_path').value = profilePath;
  if(qs('upload_json_template')) qs('upload_json_template').value = JSON.stringify(buildUploadJsonTemplate(), null, 2);
  if(qs('upload_settings_json_path')) qs('upload_settings_json_path').value = settingsPath;
  if(qs('upload_settings_json_template')) qs('upload_settings_json_template').value = JSON.stringify(buildUploadSettingsJsonTemplate(), null, 2);
  refreshUploadValidationState();
}

async function copyUploadJsonPath(){
  const v = (qs('upload_json_path')?.value || '').trim();
  if(!v){ addEvent('JSON path is empty.'); return; }
  try{
    await navigator.clipboard.writeText(v);
    addEvent('Copied upload JSON path.');
  }catch(_){
    addEvent('Copy failed. Please copy JSON path manually.');
  }
}

async function copyUploadJsonTemplate(){
  const v = (qs('upload_json_template')?.value || '').trim();
  if(!v){ addEvent('JSON template is empty.'); return; }
  try{
    await navigator.clipboard.writeText(v);
    addEvent('Copied upload JSON template.');
  }catch(_){
    addEvent('Copy failed. Please copy JSON template manually.');
  }
}

async function copyUploadSettingsJsonPath(){
  const v = (qs('upload_settings_json_path')?.value || '').trim();
  if(!v){ addEvent('upload_settings.json path is empty.'); return; }
  try{
    await navigator.clipboard.writeText(v);
    addEvent('Copied upload_settings.json path.');
  }catch(_){
    addEvent('Copy failed. Please copy upload_settings.json path manually.');
  }
}

async function copyUploadSettingsJsonTemplate(){
  const v = (qs('upload_settings_json_template')?.value || '').trim();
  if(!v){ addEvent('upload_settings.json template is empty.'); return; }
  try{
    await navigator.clipboard.writeText(v);
    addEvent('Copied upload_settings.json template.');
  }catch(_){
    addEvent('Copy failed. Please copy upload_settings.json template manually.');
  }
}

