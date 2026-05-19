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
if (typeof mountRenderRuntimePanel === 'function') mountRenderRuntimePanel();
renderYoutubeUrlBatch();
setView('workspace');
resetRenderSessionUi();
renderRenderHistory();
if (typeof renderDownloadQueue === 'function') renderDownloadQueue();
if (typeof renderHistoryView === 'function') renderHistoryView();
loadJobs();
(function _reconnectLastJob() {
  let savedId;
  try { savedId = sessionStorage.getItem('rc_last_job_id'); } catch(_) {}
  if (!savedId || currentJobId) return;
  fetch(`/api/jobs/${encodeURIComponent(savedId)}`)
    .then((r) => r.ok ? r.json() : null)
    .then((job) => {
      if (job && !isTerminalRenderStatus(job.status)) {
        currentJobId = savedId;
        startPolling(currentJobId);
        addEvent(`Reconnected to job ${savedId.slice(0, 8)}…`, 'render');
      }
    })
    .catch(() => {});
})();
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

    if (currentView === 'editor') {
      switch (e.code) {
        case 'Space':  e.preventDefault(); evTogglePlay();          break; // prevents page scroll
        case 'KeyI':                        evSetTrimIn();           break;
        case 'KeyO':                        evSetTrimOut();          break;
        case 'Escape':                      cancelEditorView();      break;
        case 'Enter':  e.preventDefault(); startRenderFromEditor(); break; // prevents button re-click
      }
      return;
    }

    if (currentView === 'render') {
      var card = document.activeElement;
      if (!card || !card.classList.contains('clipCard') || !card.classList.contains('isDone')) return;
      var startSec = Number(card.dataset.startSec);
      var endSec   = Number(card.dataset.endSec);
      var label    = String((card.querySelector('.clipCardTitle') || {}).textContent || '').trim();
      var partNo   = Number(card.dataset.partNo) || 0;
      switch (e.code) {
        case 'KeyK':
          if (_r72KbActionLock) return;
          _r72KbActionLock = true;
          setTimeout(function() { _r72KbActionLock = false; }, 150);
          if (typeof csKeepClip === 'function') csKeepClip(startSec, endSec, label, partNo);
          break;
        case 'KeyA':
          if (_r72KbActionLock) return;
          _r72KbActionLock = true;
          setTimeout(function() { _r72KbActionLock = false; }, 150);
          if (typeof csAvoidClip === 'function') csAvoidClip(startSec, endSec, label, partNo);
          break;
        case 'KeyD': {
          var dlBtn = card.querySelector('a.renderClipActionLink[download]');
          if (dlBtn) dlBtn.click();
          break;
        }
      }
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
