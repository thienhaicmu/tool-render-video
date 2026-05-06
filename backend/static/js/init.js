function init() {
bindNav();
applyEnglishLabels();
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
renderYoutubeUrlBatch();
setView('render');
resetRenderSessionUi();
renderRenderHistory();
if (typeof renderDownloadQueue === 'function') renderDownloadQueue();
if (typeof renderHistoryView === 'function') renderHistoryView();
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
