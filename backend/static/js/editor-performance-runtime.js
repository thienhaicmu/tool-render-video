/* =========================================================
   editor-performance-runtime.js  —  P1.8-K: Performance Tab Runtime
   Live diagnostics, adaptive quality controls, cache management.
   Polls PlaybackRuntime._diag and DOM counters when tab is active.
   ========================================================= */
'use strict';

window.EditorPerformanceRuntime = (() => {

  let _pollTimer  = null;
  let _isActive   = false;

  // ── Adaptive quality flags ────────────────────────────────
  // These are checked by EditorTimeline + render-ui at render time.
  const _quality = {
    hoverPreview: true,
    filmstrip:    true,
    waveform:     true,
  };

  // ── Poll loop ─────────────────────────────────────────────
  function _startPoll() {
    if (_pollTimer) return;
    _poll();
    _pollTimer = setInterval(_poll, 1200);
  }

  function _stopPoll() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  function _poll() {
    if (!_isActive) return;
    refresh();
  }

  // ── Collect metrics ───────────────────────────────────────
  function _getMetrics() {
    const diag = (typeof PlaybackRuntime !== 'undefined' && PlaybackRuntime.getDiag)
      ? PlaybackRuntime.getDiag()
      : null;
    const tl = document.getElementById('evTLInner');
    const tlNodes = tl ? tl.querySelectorAll('*').length : 0;
    const clipsDom  = document.querySelectorAll('.evTLClip').length;
    const subsDom   = document.querySelectorAll('.evTLSub').length;
    const thumbCacheSz = (typeof ThumbnailCache !== 'undefined' && ThumbnailCache._cacheSize)
      ? ThumbnailCache._cacheSize() : '—';
    const waveCacheSz = (typeof EditorWaveform !== 'undefined' && EditorWaveform._cacheSize)
      ? EditorWaveform._cacheSize() : '—';
    const hoverVids = document.querySelectorAll('.clipCard.is-preview-playing').length;
    return {
      fps:        diag?.fps          ?? '—',
      dropped:    diag?.droppedFrames ?? '—',
      tlNodes,
      clipsDom,
      subsDom,
      thumbCacheSz,
      waveCacheSz,
      hoverVids,
    };
  }

  // ── Update DOM ────────────────────────────────────────────
  function refresh() {
    const m = _getMetrics();
    const g = (id) => document.getElementById(id);
    const fmt = (v) => (v === '—' || v === null || v === undefined) ? '—' : String(v);
    if (g('edPerfFps'))       g('edPerfFps').textContent       = typeof m.fps === 'number' ? m.fps.toFixed(1) : fmt(m.fps);
    if (g('edPerfDropped'))   g('edPerfDropped').textContent   = fmt(m.dropped);
    if (g('edPerfNodes'))     g('edPerfNodes').textContent     = fmt(m.tlNodes);
    if (g('edPerfClipsDom'))  g('edPerfClipsDom').textContent  = fmt(m.clipsDom);
    if (g('edPerfSubsDom'))   g('edPerfSubsDom').textContent   = fmt(m.subsDom);
    if (g('edPerfThumbCache'))g('edPerfThumbCache').textContent= fmt(m.thumbCacheSz);
    if (g('edPerfWaveCache')) g('edPerfWaveCache').textContent = fmt(m.waveCacheSz);
    if (g('edPerfHoverVids')) g('edPerfHoverVids').textContent = fmt(m.hoverVids);

    // Health warning if too many TL nodes
    const section = document.getElementById('edPerfDiagSection');
    if (section) {
      const heavy = m.tlNodes > 2000 || m.clipsDom > 150 || m.subsDom > 300;
      section.classList.toggle('edPerfWarning', heavy);
    }
  }

  // ── Cache tools ───────────────────────────────────────────
  function clearThumbCache() {
    if (typeof ThumbnailCache !== 'undefined') ThumbnailCache.clear();
    refresh();
  }

  function clearWaveCache() {
    if (typeof EditorWaveform !== 'undefined') EditorWaveform.clear();
    refresh();
  }

  function toggleDevOverlay() {
    // Dispatch Ctrl+Shift+D keyboard event to trigger PlaybackRuntime overlay
    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'D', code: 'KeyD', ctrlKey: true, shiftKey: true, bubbles: true,
    }));
  }

  // ── Adaptive quality toggles ──────────────────────────────
  function onHoverPreviewToggle(on) {
    _quality.hoverPreview = !!on;
    // Immediately pause active hover preview if disabled
    if (!on && typeof _stopCardHoverVideo === 'function') _stopCardHoverVideo();
    EditorState?.setEditorState?.({ qualityHoverPreview: _quality.hoverPreview });
  }

  function onFilmstripToggle(on) {
    _quality.filmstrip = !!on;
    EditorState?.setEditorState?.({ qualityFilmstrip: _quality.filmstrip });
    // Re-render clips (filmstrip will be skipped if toggle is off)
    if (typeof EditorTimeline !== 'undefined') {
      const state = EditorState.getState();
      EditorTimeline.renderClips(state.clips);
    }
  }

  function onWaveformToggle(on) {
    _quality.waveform = !!on;
    EditorState?.setEditorState?.({ qualityWaveform: _quality.waveform });
    const waveTrack = document.getElementById('evTLTrackWave');
    const waveRow   = waveTrack?.closest?.('.evTLRow.is-wave');
    if (waveRow) waveRow.style.display = on ? '' : 'none';
    if (!on && waveTrack) waveTrack.innerHTML = '';
  }

  function getQuality() { return Object.assign({}, _quality); }

  // ── Tab activation / deactivation ─────────────────────────
  function onTabActivate() {
    _isActive = true;
    refresh();
    _startPoll();
  }

  function onTabDeactivate() {
    _isActive = false;
    _stopPoll();
  }

  // ── Reset ─────────────────────────────────────────────────
  function reset() {
    _quality.hoverPreview = true;
    _quality.filmstrip    = true;
    _quality.waveform     = true;
    const g = (id) => document.getElementById(id);
    if (g('edPerfHoverPreview')) g('edPerfHoverPreview').checked = true;
    if (g('edPerfFilmstrip'))    g('edPerfFilmstrip').checked    = true;
    if (g('edPerfWaveform'))     g('edPerfWaveform').checked     = true;
  }

  return {
    refresh,
    clearThumbCache,
    clearWaveCache,
    toggleDevOverlay,
    onHoverPreviewToggle,
    onFilmstripToggle,
    onWaveformToggle,
    getQuality,
    onTabActivate,
    onTabDeactivate,
    reset,
  };

})();
