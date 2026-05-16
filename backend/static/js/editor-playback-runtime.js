/* =========================================================
   editor-playback-runtime.js  —  P1.6-A: Playback Stability
   Single RAF clock: seek queue, dropped-frame detection, FPS
   counter, dev overlay.  Replaces EditorPlayback's inner loop.

   Integration:
   - Boot: PlaybackRuntime.attach(video) before EditorPlayback.attach()
   - EditorPlayback.attach() checks window.PlaybackRuntime and skips its
     own RAF loop if this module is present.
   - EditorPlayback.seekTo() delegates here for seek-queue benefit.
   - Dev overlay: Ctrl+Shift+D to toggle.
   ========================================================= */
'use strict';

window.PlaybackRuntime = (() => {

  let _video   = null;
  let _rafId   = null;
  let _running = false;
  let _clockT  = -1;    // last time value pushed to EditorState

  // ── Seek queue ─ latest value wins, flushed once per frame ──
  let _seekT  = null;

  // ── Diagnostics ──────────────────────────────────────────────
  const _diag = {
    fps: 0, frameCount: 0, fpsWindowStart: 0,
    droppedFrames: 0, lastFrameTs: 0,
  };

  // ── Dev overlay ──────────────────────────────────────────────
  let _overlay    = null;
  let _overlayVis = false;

  function _initDevOverlay() {
    if (document.getElementById('editorDevOverlay')) {
      _overlay = document.getElementById('editorDevOverlay');
      return;
    }
    _overlay = document.createElement('div');
    _overlay.id = 'editorDevOverlay';
    _overlay.style.cssText = [
      'position:fixed', 'bottom:10px', 'right:10px', 'z-index:999999',
      'display:none', 'background:rgba(0,0,0,.75)', 'color:#0f0',
      'font:11px/1.5 monospace', 'padding:5px 10px', 'border-radius:5px',
      'pointer-events:none', 'border:1px solid rgba(0,255,0,.2)',
      'white-space:pre', 'min-width:160px',
    ].join(';');
    document.body.appendChild(_overlay);

    document.addEventListener('keydown', e => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        _overlayVis = !_overlayVis;
        _overlay.style.display = _overlayVis ? 'block' : 'none';
      }
    });

    setInterval(_updateOverlay, 800);
  }

  function _updateOverlay() {
    if (!_overlay || !_overlayVis) return;
    const tlNodes = document.querySelectorAll('#evRichTimeline *').length;
    const cardVids = document.querySelectorAll('.clipCardThumbVid').length;
    const clipsDom = document.querySelectorAll('.evTLClip').length;
    const subsDom  = document.querySelectorAll('.evTLSub').length;
    _overlay.textContent = [
      'FPS:      ' + _diag.fps,
      'Dropped:  ' + _diag.droppedFrames,
      'TL nodes: ' + tlNodes,
      'Clips:    ' + clipsDom,
      'Subs:     ' + subsDom,
      'CardVids: ' + cardVids,
    ].join('\n');
  }

  // ── RAF loop ─────────────────────────────────────────────────
  function _loop(ts) {
    if (!_running || !_video) return;
    _rafId = requestAnimationFrame(_loop);

    // Dropped-frame detection (>50 ms between frames while playing)
    if (_diag.lastFrameTs && (ts - _diag.lastFrameTs) > 50 && !_video.paused) {
      _diag.droppedFrames++;
    }
    _diag.lastFrameTs = ts;

    // FPS counter (reset every second)
    _diag.frameCount++;
    if (ts - _diag.fpsWindowStart >= 1000) {
      _diag.fps = _diag.frameCount;
      _diag.frameCount = 0;
      _diag.fpsWindowStart = ts;
    }

    // Flush seek queue — latest wins, prevents flooding
    if (_seekT !== null) {
      const dur = _video.duration;
      const t   = dur > 0 ? Math.max(0, Math.min(dur, _seekT)) : Math.max(0, _seekT);
      if (Math.abs(_video.currentTime - t) > 0.016) {
        _video.currentTime = t;
      }
      _seekT = null;
    }

    // Sync currentTime → EditorState (guard: only when changed)
    const now = _video.currentTime;
    if (now !== _clockT) {
      _clockT = now;
      if (typeof EditorState !== 'undefined') {
        EditorState.setEditorState({ currentTime: now });
      }
    }
  }

  // ── Public API ───────────────────────────────────────────────
  function attach(videoEl) {
    detach();
    _video = videoEl;
    _running = true;
    _clockT = -1;
    _diag.fpsWindowStart = performance.now();
    _diag.lastFrameTs    = _diag.fpsWindowStart;
    _rafId = requestAnimationFrame(_loop);
    _initDevOverlay();
  }

  function detach() {
    _running = false;
    if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
    _video  = null;
    _seekT  = null;
    _clockT = -1;
  }

  // Queue a seek — latest value wins (safe to call on every pointermove)
  function seekTo(t) {
    _seekT = t;
  }

  // Immediate seek bypasses queue (for committed navigations)
  function seekImmediate(t) {
    _seekT = null;
    if (!_video) return;
    const dur = _video.duration;
    _video.currentTime = dur > 0 ? Math.max(0, Math.min(dur, t)) : Math.max(0, t);
  }

  function getFps()          { return _diag.fps; }
  function getDroppedFrames(){ return _diag.droppedFrames; }
  function isRunning()       { return _running; }
  function getDiag()         { return Object.assign({}, _diag); }

  return { attach, detach, seekTo, seekImmediate, getFps, getDroppedFrames, isRunning, getDiag };

})();
