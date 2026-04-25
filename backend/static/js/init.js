function init() {
bindNav();
applyEnglishLabels();
bindUploadRealtimeValidation();
if (qs('source_mode')) qs('source_mode').addEventListener('change', syncSourceModeUI);
if (qs('output_mode')) qs('output_mode').addEventListener('change', syncOutputModeUI);
if (qs('render_channels_root')) qs('render_channels_root').addEventListener('change', function(){
  const v = (this.value || '').trim();
  if(v){ renderChannelsRootPath = v; loadRenderChannels(); }
});
if (qs('render_channels_root')) qs('render_channels_root').addEventListener('keydown', function(e){
  if(e.key === 'Enter'){ e.preventDefault(); const v = (this.value || '').trim(); if(v){ renderChannelsRootPath = v; loadRenderChannels(); } }
});
if (qs('youtube_url')) qs('youtube_url').addEventListener('input', () => setYoutubeHealthState('idle', 'Health status: not checked.'));
if (qs('local_video_file_picker')) qs('local_video_file_picker').addEventListener('change', onLocalVideoPicked);
// bgm_fields moved to editor view — handled by evToggleBgmFields()
if (qs('bgm_file_picker')) qs('bgm_file_picker').addEventListener('change', onBgmFilePicked);
if (qs('channel_code')) qs('channel_code').addEventListener('change', syncRenderOutputByChannel);
if (qs('upload_channel')) qs('upload_channel').addEventListener('change', async () => {
  uploadLoginValid = false;
  selectedUploadVideos = [];
  setUploadConfigEditMode(false);
  await syncUploadSourceDirByChannel();
  await loadUploadChannelConfig(true);
  await loadUploadVideos();
  syncUploadJsonModeUI();
});
if (qs('upload_action_mode')) qs('upload_action_mode').addEventListener('change', syncUploadJsonModeUI);
if (qs('upload_ui_level')) qs('upload_ui_level').addEventListener('change', syncUploadJsonModeUI);
if (qs('upload_account_key')) qs('upload_account_key').addEventListener('input', () => { uploadLoginValid = false; syncUploadJsonModeUI(); });
if (qs('upload_credential_line')) qs('upload_credential_line').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_tiktok_username')) qs('upload_tiktok_username').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_tiktok_password')) qs('upload_tiktok_password').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_mail_username')) qs('upload_mail_username').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_mail_password')) qs('upload_mail_password').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_login_username')) qs('upload_login_username').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_login_password')) qs('upload_login_password').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_mode')) qs('upload_mode').addEventListener('change', syncUploadJsonModeUI);
if (qs('upload_config_mode')) qs('upload_config_mode').addEventListener('change', syncUploadJsonModeUI);
if (qs('upload_network_mode')) qs('upload_network_mode').addEventListener('change', syncUploadJsonModeUI);
if (qs('upload_browser_preference')) qs('upload_browser_preference').addEventListener('change', syncUploadJsonModeUI);
if (qs('upload_browser_executable')) qs('upload_browser_executable').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_proxy_server')) qs('upload_proxy_server').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_proxy_username')) qs('upload_proxy_username').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_proxy_password')) qs('upload_proxy_password').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_schedule_slots')) qs('upload_schedule_slots').addEventListener('input', syncUploadJsonModeUI);
if (qs('upload_channels_root')) qs('upload_channels_root').addEventListener('change', function(){
  const v = (this.value || '').trim();
  if(v){ uploadChannelsRootPath = v; loadChannels(); }
});
if (qs('upload_channels_root')) qs('upload_channels_root').addEventListener('keydown', function(e){
  if(e.key === 'Enter'){ e.preventDefault(); const v = (this.value || '').trim(); if(v){ uploadChannelsRootPath = v; loadChannels(); } }
});
if (qs('new_channel_channels_root')) qs('new_channel_channels_root').addEventListener('change', function(){
  const v = (this.value || '').trim();
  if(v){ createChannelsRootPath = v; syncNewChannelPathUI(); addEvent(`Create Channel root set: ${v}`, 'channels'); }
});
if (qs('new_channel_channels_root')) qs('new_channel_channels_root').addEventListener('keydown', function(e){
  if(e.key === 'Enter'){ e.preventDefault(); const v = (this.value || '').trim(); if(v){ createChannelsRootPath = v; syncNewChannelPathUI(); addEvent(`Create Channel root set: ${v}`, 'channels'); } }
});
if (qs('channel_name_prefix')) qs('channel_name_prefix').addEventListener('input', () => { loadChannels({ silentIfNoRoot: true }); });
if (qs('new_channel_network_mode')) qs('new_channel_network_mode').addEventListener('change', syncNewChannelNetworkModeUI);
if (qs('new_channel_code')) qs('new_channel_code').addEventListener('input', syncNewChannelPathUI);
// Manual output folder — Choose button
(function(){
  const btn = qs('btn_pick_output_dir');
  if(!btn) return;
  btn.addEventListener('click', async function(){
    let picked = '';
    if(window.electronAPI && typeof window.electronAPI.pickDirectory === 'function'){
      try { picked = String(await window.electronAPI.pickDirectory()).trim(); } catch(_){}
    } else {
      picked = (prompt('Paste folder path:') || '').trim();
    }
    if(picked){
      const inp = qs('manual_output_dir');
      if(inp){ inp.value = picked; inp.dispatchEvent(new Event('input')); }
    }
  });
})();
syncSourceModeUI();
syncOutputModeUI();
syncUploadJsonModeUI();
syncNewChannelNetworkModeUI();
renderYoutubeUrlBatch();
setView('render');
resetRenderSessionUi();
renderRenderHistory();
if (typeof renderDownloadQueue === 'function') renderDownloadQueue();
if (typeof renderHistoryView === 'function') renderHistoryView();
renderUploadRun(null);
initChannelsRoot();
syncNewChannelPathUI();
loadJobs();
initWarmup();
addEvent('Dashboard ready');

// ── Editor keyboard shortcuts ──────────────────────────────────────────────
// Single centralized keydown handler. All guards run before any action fires.
// IIFE keeps _isTyping private (not a global utility).
(function () {
  function _isTyping(el) {
    if (!el) return false;
    const t = el.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT' || !!el.isContentEditable;
  }

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return; // never steal modifier combos
    if (_isTyping(e.target)) return;                 // focus is in a text field → ignore
    if (currentView !== 'editor') return;            // editor must be the active view

    switch (e.code) {
      case 'Space':  e.preventDefault(); evTogglePlay();          break; // prevents page scroll
      case 'KeyI':                        evSetTrimIn();           break;
      case 'KeyO':                        evSetTrimOut();          break;
      case 'Escape':                      cancelEditorView();      break;
      case 'Enter':  e.preventDefault(); startRenderFromEditor(); break; // prevents button re-click
    }
  });
})();

// No resize listener needed — overlay uses % inside fixed-aspect frame
}

(async function () {
  try {
    if (typeof loadPartials === 'function') {
      await loadPartials();
    }
    init();
  } catch (e) {
    console.error('Init failed', e);
  }
})();
