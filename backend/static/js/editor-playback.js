/* =========================================================
   editor-playback.js  —  P1-B: Playback Engine
   RAF-based playback loop, keyboard shortcuts, rate control.
   Wraps the existing <video id="evVideo"> element.
   Integrates with EditorState (state store).
   ========================================================= */
'use strict';

window.EditorPlayback = (() => {

  let _video   = null;
  let _rafId   = null;
  let _running = false;
  let _kbBound = false;

  // ── RAF loop — pushes currentTime into state ──────────────
  function _loop() {
    if (!_video || !_running) return;
    const t = _video.currentTime;
    if (t !== EditorState.getState().currentTime) {
      EditorState.setEditorState({ currentTime: t });
    }
    _rafId = requestAnimationFrame(_loop);
  }

  function _startLoop() {
    if (_rafId) return;
    _rafId = requestAnimationFrame(_loop);
  }

  function _stopLoop() {
    if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
    // One final sync
    if (_video) EditorState.setEditorState({ currentTime: _video.currentTime, isPlaying: false });
  }

  // ── Attach to video element ──────────────────────────────
  function attach(videoEl) {
    if (_video === videoEl) {
      _running = true;
      // Only start own loop if PlaybackRuntime isn't handling the clock
      if (typeof PlaybackRuntime === 'undefined' || !PlaybackRuntime.isRunning()) {
        _startLoop();
      }
      return;
    }
    if (_video) _detachListeners();

    _video   = videoEl;
    _running = true;

    _video.addEventListener('play',     _onPlay);
    _video.addEventListener('pause',    _onPause);
    _video.addEventListener('seeking',  _onSeeking);
    _video.addEventListener('ended',    _onEnded);
    _video.addEventListener('ratechange', _onRate);

    // Sync initial muted state
    EditorState.setEditorState({ isMuted: !!_video.muted });

    // Only start own RAF loop if PlaybackRuntime isn't providing the clock
    if (typeof PlaybackRuntime === 'undefined' || !PlaybackRuntime.isRunning()) {
      _startLoop();
    }

    if (!_kbBound) {
      document.addEventListener('keydown', _onKeydown, { capture: false });
      _kbBound = true;
    }
  }

  function detach() {
    _running = false;
    _stopLoop();
    _detachListeners();
    _video = null;
  }

  function _detachListeners() {
    if (!_video) return;
    _video.removeEventListener('play',      _onPlay);
    _video.removeEventListener('pause',     _onPause);
    _video.removeEventListener('seeking',   _onSeeking);
    _video.removeEventListener('ended',     _onEnded);
    _video.removeEventListener('ratechange', _onRate);
  }

  // ── Video event handlers ─────────────────────────────────
  function _onPlay() {
    _startLoop();
    EditorState.setEditorState({ isPlaying: true });
    _syncPlayBtn(false);
    EditorState.emit('playback:play');
  }

  function _onPause() {
    _stopLoop();
    _syncPlayBtn(true);
    EditorState.emit('playback:pause');
  }

  function _onSeeking() {
    if (_video) EditorState.setEditorState({ currentTime: _video.currentTime });
    EditorState.emit('playback:seek', _video ? _video.currentTime : 0);
  }

  function _onEnded() {
    _stopLoop();
    _syncPlayBtn(true);
    EditorState.emit('playback:ended');
  }

  function _onRate() {
    if (_video) EditorState.setEditorState({ playbackRate: _video.playbackRate });
  }

  function _syncPlayBtn(paused) {
    const btn = document.getElementById('evPlayBtn');
    if (btn) btn.textContent = paused ? '▶' : '⏸';
  }

  // ── Public controls ──────────────────────────────────────
  function play() {
    if (_video && _video.paused) _video.play().catch(() => {});
  }

  function pause() {
    if (_video && !_video.paused) _video.pause();
  }

  function toggle() {
    if (!_video) return;
    if (_video.paused) play(); else pause();
  }

  function seekTo(t) {
    // Delegate to PlaybackRuntime seek queue when available (prevents flooding)
    if (typeof PlaybackRuntime !== 'undefined' && PlaybackRuntime.isRunning()) {
      PlaybackRuntime.seekTo(t);
      return;
    }
    if (!_video) return;
    const dur = _video.duration || EditorState.getState().duration || 0;
    _video.currentTime = Math.max(0, Math.min(dur, t));
  }

  function seekBy(delta) {
    seekTo((_video ? _video.currentTime : 0) + delta);
  }

  function setRate(rate) {
    if (_video) { _video.playbackRate = rate; }
    EditorState.setEditorState({ playbackRate: rate });
  }

  function setMuted(muted) {
    if (_video) { _video.muted = muted; }
    EditorState.setEditorState({ isMuted: muted });
  }

  function getCurrentTime() { return _video ? _video.currentTime : 0; }
  function getDuration()    { return _video ? (_video.duration || 0) : 0; }

  // RAF-throttled seek for scrub preview (writes video.currentTime ≤ once/frame)
  let _previewT   = null;
  let _previewRaf = null;
  function seekPreview(t) {
    _previewT = t;
    if (!_previewRaf) _previewRaf = requestAnimationFrame(_flushPreview);
  }
  function _flushPreview() {
    _previewRaf = null;
    if (_previewT !== null && _video) {
      const dur = _video.duration || 0;
      _video.currentTime = Math.max(0, dur > 0 ? Math.min(dur, _previewT) : _previewT);
      _previewT = null;
    }
  }

  // ── Keyboard shortcuts ───────────────────────────────────
  function _onKeydown(e) {
    if (!_video || !_running) return;

    // Don't steal from text inputs
    const tag = (document.activeElement || {}).tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    // Only active in editor view
    const ev = document.getElementById('view_editor');
    if (!ev || ev.classList.contains('hiddenView')) return;

    switch (e.key) {
      case ' ':
        e.preventDefault();
        toggle();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        seekBy(e.shiftKey ? -5 : -1);
        break;
      case 'ArrowRight':
        e.preventDefault();
        seekBy(e.shiftKey ? 5 : 1);
        break;
      case 'j': case 'J': seekBy(-10); break;
      case 'l': case 'L': seekBy(10);  break;
      case 'k': case 'K': toggle();    break;
      case 'm': case 'M':
        setMuted(!(_video ? _video.muted : false));
        break;
      case 'Home':
        e.preventDefault();
        seekTo(0);
        break;
      case 'End':
        e.preventDefault();
        seekTo(getDuration());
        break;
    }
  }

  return {
    attach,
    detach,
    play,
    pause,
    toggle,
    seekTo,
    seekBy,
    seekPreview,
    setRate,
    setMuted,
    getCurrentTime,
    getDuration,
  };

})();
