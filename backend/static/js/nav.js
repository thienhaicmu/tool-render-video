function setView(view){
  currentView = view;
  const isRender   = view === 'render';
  const isDownload = view === 'download';
  const isHistory  = view === 'history';
  const isUpload   = view === 'upload';
  const isChannels = view === 'channels';
  const isReports  = view === 'reports';
  const isSettings = view === 'settings';
  const isEditor   = view === 'editor';
  // monitor view retired — bottom panel is always visible

  // Editor view: take over mainArea entirely (CSS :has rules + editorMode class)
  const mainArea = qs('mainArea');
  if (mainArea) mainArea.classList.toggle('editorMode', isEditor);
  qs('view_editor').classList.toggle('hiddenView', !isEditor);
  const downloadView = qs('view_download');
  if (downloadView) downloadView.classList.toggle('hiddenView', !isDownload);
  const historyView = qs('view_history');
  if (historyView) historyView.classList.toggle('hiddenView', !isHistory);
  const flowBar = qs('render_flow_bar');
  if (flowBar) flowBar.classList.toggle('hiddenView', !(isRender || isEditor));

  // pageHeader + layout_grid only visible for upload/channels/reports/settings
  const showMainContent = !isRender && !isEditor && !isDownload && !isHistory;
  const pageHeader = document.querySelector('.pageHeader');
  if (pageHeader) pageHeader.classList.toggle('hiddenView', !showMainContent);
  qs('layout_grid').classList.toggle('hiddenView', !showMainContent);
  if (showMainContent) {
    qs('layout_grid').classList.toggle('singleCol', true);
  }

  // Right column always hidden — content lives in appInspector
  qs('right_column').classList.toggle('hiddenView', true);

  // Sidebar setup cards only show for their workflow tabs.
  const renderSetup = qs('card_render_setup');
  if (renderSetup) renderSetup.classList.toggle('hiddenView', !(isRender || isEditor));
  const downloadSetup = qs('card_download_setup');
  if (downloadSetup) downloadSetup.classList.toggle('hiddenView', !isDownload);
  qs('card_upload').classList.toggle('hiddenView', !isUpload);
  qs('card_channels').classList.toggle('hiddenView', !isChannels);
  qs('card_reports').classList.toggle('hiddenView', !isReports);
  qs('card_settings').classList.toggle('hiddenView', !isSettings);

  if (isUpload)  setPageHeader('Upload Studio', 'Choose Action -> Select Channel -> Login or Upload.');
  if (isHistory) setPageHeader('History', 'Recent Download and Render activity');
  if (isChannels) setPageHeader('Channel Management', 'Choose Root Folder -> Enter Channel Code -> Configure -> Create.');
  if (isReports) setPageHeader('Reports', 'Review render and upload reporting output.');
  if (isSettings) setPageHeader('Settings', 'System maintenance and operational options.');

  document.querySelectorAll('.navItem[data-view]').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-view') === view);
  });

  // Inspector: only meaningful in editor view. Hide it everywhere else to
  // reclaim the 4fr right column for mainArea content.
  const appShell = document.querySelector('.appShell');
  if (appShell) appShell.classList.toggle('noInspector', !isEditor);

  // Render home panel: show idle dashboard only in render view.
  const rhp = qs('render_home_panel');
  if (rhp) rhp.classList.toggle('hiddenView', !isRender || !!currentJobId);
  if (typeof updateRenderMainState === 'function') {
    if (currentJobId && isRender) {
      const fallbackJob = { status: 'running', stage: 'queued', progress_percent: (typeof _jobDisplayPct !== 'undefined' ? _jobDisplayPct : 0) || 0 };
      updateRenderMainState(
        (typeof _renderMonitorLastJob !== 'undefined' && _renderMonitorLastJob) ? _renderMonitorLastJob : fallbackJob,
        (typeof _renderMonitorLastSummary !== 'undefined' && _renderMonitorLastSummary) ? _renderMonitorLastSummary : null,
        (typeof _renderMonitorLastParts !== 'undefined' && _renderMonitorLastParts) ? _renderMonitorLastParts : []
      );
    }
    if (!currentJobId) updateRenderMainState(null, null, []);
  }
  if (isRender && typeof renderRenderHistory === 'function') renderRenderHistory();
  if (isDownload && typeof renderDownloadQueue === 'function') renderDownloadQueue();
  if (isHistory && typeof loadHistoryView === 'function') loadHistoryView();
  if (!isRender && !isEditor && typeof hideRenderCompletionBar === 'function') hideRenderCompletionBar();

  // Bottom panel: auto-collapse when switching views with no active job.
  if (!currentJobId) _collapseBottomPanel(true);

  // Upload wizard: reset to step 1 when entering upload view.
  if (isUpload && typeof setUploadWizardStep === 'function') setUploadWizardStep(1);

  // Subtle enter animation: fade + lift the incoming content over 120ms.
  // Remove → reflow → re-add restarts the animation even on repeated calls.
  if (mainArea) {
    mainArea.classList.remove('viewEntering');
    void mainArea.offsetWidth; // force reflow so browser registers the removal
    mainArea.classList.add('viewEntering');
  }
}

// ── Bottom panel collapse helpers ──────────────────────────────────────────
function _collapseBottomPanel(collapsed) {
  const shell = document.querySelector('.appShell');
  if (!shell) return;
  shell.classList.toggle('abpCollapsed', !!collapsed);
  const btn = qs('abp_collapse_btn');
  if (btn) btn.textContent = collapsed ? '▴' : '▾';
}

function toggleBottomPanel() {
  const shell = document.querySelector('.appShell');
  if (!shell) return;
  _collapseBottomPanel(!shell.classList.contains('abpCollapsed'));
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


function toggleSourceSetup() {
  const panel = document.getElementById('abpSetupPanel');
  const btn   = document.getElementById('abpSetupToggle');
  if (!panel) return;
  const hidden = panel.classList.toggle('hiddenView');
  if (btn) btn.textContent = hidden ? '⚙ Source Setup' : '✕ Close Setup';
}
