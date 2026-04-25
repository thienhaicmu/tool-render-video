function qs(id){ return document.getElementById(id); }

function _setBtnLoading(btnId, loadingText) {
  const btn = qs(btnId);
  if (!btn) return () => {};
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = loadingText;
  return () => { btn.disabled = false; btn.textContent = orig; };
}
function esc(v){ return String(v ?? '').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function setPageHeader(title, subtitle){
  const t = qs('page_title_text');
  const s = qs('page_subtitle_text');
  if(t) t.textContent = title;
  if(s) s.textContent = subtitle;
}

function applyEnglishLabels(){
  const set = (selector, text) => { const el = document.querySelector(selector); if (el) el.textContent = text; };
  const setNavLabel = (view, text) => {
    const el = document.querySelector(`.navItem[data-view="${view}"]`);
    if (el) el.textContent = text;
  };
  const setLabel = (id, text) => {
    const el = qs(id);
    const holder = el?.closest('label')?.querySelector('.fieldLabel');
    if (holder) holder.textContent = text;
  };
  const setToggle = (id, text) => {
    const el = qs(id);
    const holder = el?.closest('label')?.querySelector('span');
    if (holder) holder.textContent = text;
  };

  set('.brandSub', 'Local AI video platform');
  setNavLabel('download', 'Download');
  setNavLabel('render', 'Render');
  setNavLabel('upload', 'Upload');
  setNavLabel('history', 'History');
  set('#job_chip', 'No active job');

  set('#card_render_setup .sectionTitle', 'Render Setup');
  set('#card_render_setup .sectionSubtitle', 'Minimal mode: select source + channel, then run.');
  set('#card_render_setup .ghostButton', 'Refresh Jobs');
  set('#start_render_btn', 'Open Editor');
  const resumeBtn = document.querySelector('#card_render_setup .secondaryButton');
  if (resumeBtn) resumeBtn.textContent = 'Resume by Job ID';
  const resumeInput = qs('resume_job_id'); if (resumeInput) resumeInput.placeholder = 'Enter job id to resume';

  setLabel('youtube_url', 'YouTube URL');
  setLabel('youtube_urls', 'YouTube Queue (added links)');
  setLabel('source_mode', 'Source Mode');
  setLabel('output_mode', 'Output Mode');
  setLabel('render_channels_root', 'Render Channels Root Folder');
  setLabel('source_video_path', 'Local Video');
  setLabel('channel_code', 'Channel');
  setLabel('render_output_dir', 'Render Output Folder');
  setLabel('manual_output_dir', 'Manual Output Folder');
  const pickBtn = qs('pick_local_video_btn');
  if (pickBtn) pickBtn.textContent = 'Choose Video';
  const addYtBtn = qs('add_youtube_url_btn');
  if (addYtBtn) addYtBtn.textContent = 'Add';
  const healthBtn = qs('youtube_health_btn');
  if (healthBtn) healthBtn.textContent = 'Download Health';
  setLabel('aspect_ratio', 'Aspect Ratio');
  setLabel('render_profile', 'Render Profile');
  setLabel('render_device', 'Render Device');
  setLabel('output_fps', 'Output FPS');
  setLabel('min_part_sec', 'Min Part Duration (sec)');
  setLabel('max_part_sec', 'Max Part Duration (sec)');
  setLabel('max_export_parts', 'Max Export Parts');
  setLabel('frame_scale_x', 'Frame Scale X (%)');
  setLabel('frame_scale_y', 'Frame Scale Y (%)');
  setLabel('subtitle_style', 'Subtitle Style');
  setLabel('transform_preset', 'Transform Preset');

  setToggle('motion_aware_crop', 'Motion-aware crop');
  setToggle('add_subtitle', 'Add subtitles');
  setToggle('reup_mode', 'Reup Mode (color + audio enhance)');
  setToggle('cleanup_temp_files', 'Clean temp files after render');
  setToggle('reup_bgm_enable', 'Background Music (BGM)');

  set('#card_upload .sectionTitle', 'Upload');
  set('#card_upload .sectionSubtitle', 'Main flow: Create Channel -> Login -> Upload.');
  setLabel('upload_channel', 'Upload Channel');
  setLabel('upload_channels_root', 'Channels Root Folder');
  setLabel('channel_name_prefix', 'Channel Prefix Filter');
  setLabel('upload_action_mode', 'Action');
  setLabel('upload_mode', 'Upload Mode');
  setLabel('upload_ui_level', 'UI Level');
  setLabel('upload_account_key', 'Account Key');
  setLabel('upload_profile_path', 'Resolved Profile Path');
  setLabel('upload_credential_line', 'Credential Line');
  setLabel('upload_tiktok_username', 'TikTok Username');
  setLabel('upload_tiktok_password', 'TikTok Password');
  setLabel('upload_mail_username', 'Mail Username (OTP)');
  setLabel('upload_mail_password', 'Mail Password (OTP)');
  setLabel('upload_login_username', 'Login Username (legacy)');
  setLabel('upload_login_password', 'Login Password (legacy)');
  setLabel('upload_config_mode', 'Config Mode');
  setLabel('upload_browser_preference', 'Browser Preference');
  setLabel('upload_video_input_dir', 'Upload Source Folder (Auto by channel)');
  setLabel('upload_schedule_slots', 'Daily Schedule Slots (HH:MM, comma separated)');
  setLabel('upload_browser_executable', 'Browser Executable (optional)');
  setLabel('upload_max_items', 'Max Items');
  setLabel('upload_caption_prefix', 'Caption Prefix');
  setLabel('upload_network_mode', 'Network Mode');
  setLabel('upload_proxy_server', 'Proxy Server');
  setLabel('upload_proxy_username', 'Proxy Username');
  setLabel('upload_proxy_password', 'Proxy Password');
  setToggle('upload_dry_run', 'Dry run (no publish)');
  setToggle('upload_include_hashtags', 'Include hashtags');
  setToggle('upload_headless', 'Run in background (headless)');
  set('#ensure_upload_btn', 'Prepare Profile');
  set('#check_upload_btn', 'Check Login Status');
  set('#start_upload_login_btn', 'Login Flow (Email -> TikTok)');
  set('#run_upload_btn', 'Run Upload Plan');

  set('#card_logs .sectionTitle', 'Render Live Log');
  set('#card_logs .sectionSubtitle', 'Render runtime events and errors.');

  set('#card_channels .sectionTitle', 'Channel Management');
  set('#card_channels .sectionSubtitle', 'Create channel scaffold + JSON config from UI.');
  setLabel('new_channel_code', 'New Channel Code');
  setLabel('new_channel_channels_root', 'Channels Root Folder');
  setLabel('new_channel_path', 'Channel Folder (auto)');
  setLabel('new_channel_video_output_subdir', 'Video Output Folder (for render/upload)');
  setLabel('new_channel_default_hashtags', 'Default Hashtags');
  set('#new_channel_pick_root_btn', 'Choose Folder');
  set('#create_channel_btn', 'Create Channel + Config');

  set('#card_reports .sectionTitle', 'Reports');
  set('#card_reports .sectionSubtitle', 'Render and upload summary output.');
  set('#card_settings .sectionTitle', 'System Settings');
  set('#card_settings .sectionSubtitle', 'Maintenance and runtime settings.');
  setLabel('cleanup_keep_last', 'Keep latest logs per channel');
  setLabel('cleanup_older_days', 'Delete logs older than (days)');
  const cleanBtn = document.querySelector('#card_settings .secondaryButton');
  if (cleanBtn) cleanBtn.textContent = 'Clean old job logs';

  set('#card_progress .sectionTitle', 'Render Progress');
  set('#card_progress .sectionSubtitle', 'Track pipeline and parts in real time.');
  set('#job_stage_pill', 'Idle');
  set('#job_title', 'No active job');
  set('#job_meta_1', 'Channel - | Source -');
  set('#job_meta_2', '0/0 parts done | 0 scenes');
  set('#job_message', 'Initializing');
  set('#action_title', 'Waiting for job');
  set('#action_hint', 'Live action updates after you click Render.');
  set('#action_state', 'idle');
  set('#action_message', 'No active processing task.');
  set('#action_meta', 'Elapsed 00:00 | Updated -');
  set('#card_parts .sectionTitle', 'Rendered Parts');
  set('#card_parts .sectionSubtitle', 'Part status, progress, and viral score.');
  set('#card_jobs .sectionTitle', 'Recent Jobs');
  set('#card_jobs .sectionSubtitle', 'Latest job overview.');
}


function _fmtTime(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function _formatApiError(detail) {
  if (!detail) return 'unknown error';
  // Pydantic 422: detail is an array of {loc, msg, type} objects
  if (Array.isArray(detail)) {
    return detail.map(e => {
      const field = Array.isArray(e.loc) ? e.loc.filter(x => x !== 'body').join('.') : '';
      return field ? `${field}: ${e.msg}` : (e.msg || JSON.stringify(e));
    }).join(' | ');
  }
  // HTTPException 400/500: detail is a plain string
  return typeof detail === 'string' ? detail : JSON.stringify(detail);
}
