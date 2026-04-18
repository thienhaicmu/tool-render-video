function setView(view){
  currentView = view;
  const isRender   = view === 'render';
  const isUpload   = view === 'upload';
  const isChannels = view === 'channels';
  const isReports  = view === 'reports';
  const isSettings = view === 'settings';
  const isEditor   = view === 'editor';

  // Editor view: take over mainArea entirely
  const mainArea = qs('mainArea');
  if (mainArea) mainArea.classList.toggle('editorMode', isEditor);
  qs('view_editor').classList.toggle('hiddenView', !isEditor);

  // Normal views: hide page header + grid when in editor mode
  const pageHeader = document.querySelector('.pageHeader');
  if (pageHeader) pageHeader.classList.toggle('hiddenView', isEditor);
  qs('layout_grid').classList.toggle('hiddenView', isEditor);
  if (!isEditor) {
    qs('layout_grid').classList.toggle('singleCol', !isRender);
  }
  qs('right_column').classList.toggle('hiddenView', !isRender || isEditor);

  qs('card_render_setup').classList.toggle('hiddenView', !isRender || isEditor);
  qs('card_upload').classList.toggle('hiddenView', !isUpload);
  qs('card_progress').classList.toggle('hiddenView', !isRender || isEditor);
  qs('card_parts').classList.toggle('hiddenView', !isRender || isEditor);
  qs('card_jobs').classList.toggle('hiddenView', !isRender || isEditor);
  qs('card_logs').classList.toggle('hiddenView', !isRender || isEditor);
  qs('card_channels').classList.toggle('hiddenView', !isChannels);
  qs('card_reports').classList.toggle('hiddenView', !isReports);
  qs('card_settings').classList.toggle('hiddenView', !isSettings);

  if (isRender) setPageHeader('Render Studio', 'Configure and run render jobs with full stage visibility.');
  if (isUpload) setPageHeader('Upload Studio', 'Choose Action -> Select Channel -> Login or Upload.');
  if (isChannels) setPageHeader('Channel Management', 'Choose Root Folder -> Enter Channel Code -> Configure -> Create.');
  if (isReports) setPageHeader('Reports', 'Review render and upload reporting output.');
  if (isSettings) setPageHeader('Settings', 'System maintenance and operational options.');
  if (isRender) {
    const progTitle = document.querySelector('#card_progress .sectionTitle');
    const progSub = document.querySelector('#card_progress .sectionSubtitle');
    const partTitle = document.querySelector('#card_parts .sectionTitle');
    const partSub = document.querySelector('#card_parts .sectionSubtitle');
    const hint = document.querySelector('#card_progress .actionHint');
    if (progTitle) progTitle.textContent = 'Render Progress';
    if (progSub) progSub.textContent = 'Track pipeline and parts in real time.';
    if (partTitle) partTitle.textContent = 'Rendered Parts';
    if (partSub) partSub.textContent = 'Part status, progress, and viral score.';
    if (hint) hint.textContent = 'Live action updates after you click Render.';
  }

  document.querySelectorAll('.navItem[data-view]').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-view') === view);
  });
}

function bindNav(){
  document.querySelectorAll('.navItem[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => setView(btn.getAttribute('data-view') || 'render'));
  });
}

function syncSourceModeUI(){
  const mode = (qs('source_mode')?.value || 'youtube').toLowerCase();
  const y = qs('field_youtube_url');
  const ym = qs('field_youtube_urls');
  const l = qs('field_source_video_path');
  if(y) y.classList.toggle('hiddenView', mode !== 'youtube');
  if(ym) ym.classList.toggle('hiddenView', mode !== 'youtube');
  if(l) l.classList.toggle('hiddenView', mode !== 'local');
  // Auto-clear the other source when switching modes
  if(mode === 'local'){
    if(qs('youtube_url')) qs('youtube_url').value = '';
    batchYoutubeUrls = [];
    renderYoutubeUrlBatch();
  } else {
    selectedLocalVideoPath = '';
    _pendingLocalFile = null;
    if(qs('source_video_path')) qs('source_video_path').value = '';
    if(qs('source_video_name')) qs('source_video_name').textContent = 'No local video selected.';
    const picker = qs('local_video_file_picker');
    if(picker) picker.value = '';
  }
  if(currentView === 'upload') syncUploadActionModeUI();
}

function quickOpenFeature(feature){
  const f = String(feature || '').toLowerCase();
  const createBtn = qs('feature_create_btn');
  const loginBtn = qs('feature_login_btn');
  const uploadBtn = qs('feature_upload_btn');
  [createBtn, loginBtn, uploadBtn].forEach((b) => b && b.classList.remove('active'));
  if(f === 'create'){
    if(createBtn) createBtn.classList.add('active');
    setView('channels');
    return;
  }
  setView('upload');
  if(f === 'login'){
    if(loginBtn) loginBtn.classList.add('active');
    if(qs('upload_action_mode')) qs('upload_action_mode').value = 'login';
  } else {
    if(uploadBtn) uploadBtn.classList.add('active');
    if(qs('upload_action_mode')) qs('upload_action_mode').value = 'upload';
  }
  syncUploadJsonModeUI();
  if(!String(qs('upload_channels_root')?.value || '').trim()){
    addEvent('Step 1: Choose Action. Step 2: Choose Root Folder, then select channel.');
  }
}

function syncOutputModeUI(){
  const mode = (qs('output_mode')?.value || 'channel').toLowerCase();
  const channelField = qs('field_channel_code');
  const renderRootField = qs('field_render_channels_root');
  const channelOutField = qs('field_render_output_dir');
  const manualOutField = qs('field_manual_output_dir');
  const channelSelect = qs('channel_code');
  const autoOutInput = qs('render_output_dir');
  const manualOutInput = qs('manual_output_dir');
  const autoOutHint = qs('render_output_dir_hint');
  const manualOutHint = qs('manual_output_dir_hint');

  const byChannel = mode === 'channel';
  if(renderRootField) renderRootField.classList.toggle('hiddenView', !byChannel);
  if(channelField) channelField.classList.toggle('hiddenView', !byChannel);
  if(channelOutField) channelOutField.classList.toggle('hiddenView', !byChannel);
  if(manualOutField) manualOutField.classList.toggle('hiddenView', byChannel);

  if(byChannel){
    if(manualOutInput) manualOutInput.value = '';
    if(!String(renderChannelsRootPath || '').trim() && String(defaultChannelsRootPath || '').trim()){
      renderChannelsRootPath = defaultChannelsRootPath;
      if(qs('render_channels_root')) qs('render_channels_root').value = renderChannelsRootPath;
    }
    loadRenderChannels({ silentIfNoRoot: true });
    syncRenderOutputByChannel();
  } else {
    selectedRenderOutputDir = '';
    if(autoOutInput) autoOutInput.value = '';
    if(autoOutHint) autoOutHint.textContent = 'Channel output is disabled in Manual Folder mode.';
    if(manualOutHint) manualOutHint.textContent = 'All outputs (parts, kept source copy, report) will be saved in this folder. Not restricted to channels/.';
    if(channelSelect) channelSelect.value = '';
  }
}

