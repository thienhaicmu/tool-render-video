/* =========================================================
   editor-interactions.js  —  P1.5: Timeline Interaction Layer
   Handles all pointer events: playhead drag, clip select/move,
   trim handles, hover tooltip, and Ctrl+Wheel zoom.

   Architecture:
   - During drag → direct DOM mutation (60fps, no re-renders)
   - On pointer-up → commit to EditorState → EditorTimeline.renderClips()
   - RAF-throttled seeks (video.currentTime written ≤1/frame)

   Dependencies: EditorState, EditorTimeline, EditorPlayback,
                 EditorCoordinates.
   ========================================================= */
'use strict';

window.EditorInteractions = (() => {

  // ── Module state ─────────────────────────────────────────────
  let _root    = null;   // #evRichTimeline
  let _scroll  = null;   // #evTLScrollBody
  let _ph      = null;   // #evTLPlayhead
  let _tooltip = null;   // floating time tooltip
  let _op      = null;   // active pointer operation

  // RAF-throttled seek queue
  let _seekT   = null;
  let _seekRaf = null;

  // ── Operation type constants ─────────────────────────────────
  const OP = {
    SCRUB:     'SCRUB',
    TRIM:      'TRIM',
    CLIP_MOVE: 'CLIP_MOVE',
  };

  // ── Init / Destroy ───────────────────────────────────────────
  function init(rootId) {
    destroy();

    _root   = document.getElementById(rootId || 'evRichTimeline');
    _scroll = document.getElementById('evTLScrollBody');
    _ph     = document.getElementById('evTLPlayhead');
    if (!_root) return;

    _ensureTooltip();

    _root.addEventListener('pointerdown',  _onDown,  { passive: false });
    _root.addEventListener('pointermove',  _onHover, { passive: true  });
    _root.addEventListener('pointerleave', _onLeave, { passive: true  });
    _root.addEventListener('wheel',        _onWheel, { passive: false });

    document.addEventListener('pointermove',   _onMove,   { passive: false });
    document.addEventListener('pointerup',     _onUp,     { passive: true  });
    document.addEventListener('pointercancel', _onUp,     { passive: true  });
  }

  function destroy() {
    if (_root) {
      _root.removeEventListener('pointerdown',  _onDown);
      _root.removeEventListener('pointermove',  _onHover);
      _root.removeEventListener('pointerleave', _onLeave);
      _root.removeEventListener('wheel',        _onWheel);
    }
    document.removeEventListener('pointermove',   _onMove);
    document.removeEventListener('pointerup',     _onUp);
    document.removeEventListener('pointercancel', _onUp);

    if (_tooltip) { _tooltip.style.display = 'none'; }
    if (_seekRaf) { cancelAnimationFrame(_seekRaf); _seekRaf = null; }
    _op = null; _root = null; _scroll = null; _ph = null;
  }

  // ── Tooltip ──────────────────────────────────────────────────
  function _ensureTooltip() {
    if (document.getElementById('evTLTooltip')) {
      _tooltip = document.getElementById('evTLTooltip');
      return;
    }
    _tooltip = document.createElement('div');
    _tooltip.id = 'evTLTooltip';
    _tooltip.className = 'evTLTooltip';
    _tooltip.style.cssText = 'display:none';
    document.body.appendChild(_tooltip);
  }

  function _showTooltip(clientX, clientY, text) {
    if (!_tooltip) return;
    _tooltip.textContent = text;
    _tooltip.style.display  = 'block';
    _tooltip.style.left     = (clientX + 12) + 'px';
    _tooltip.style.top      = (clientY - 28) + 'px';
  }

  function _hideTooltip() {
    if (_tooltip) _tooltip.style.display = 'none';
  }

  // ── RAF-throttled seek ────────────────────────────────────────
  function _queueSeek(t) {
    _seekT = t;
    if (!_seekRaf) _seekRaf = requestAnimationFrame(_flushSeek);
  }

  function _flushSeek() {
    _seekRaf = null;
    if (_seekT !== null) {
      // Prefer PlaybackRuntime's queue (better seek stability)
      if (typeof PlaybackRuntime !== 'undefined' && PlaybackRuntime.isRunning()) {
        PlaybackRuntime.seekTo(_seekT);
      } else if (typeof EditorPlayback !== 'undefined') {
        EditorPlayback.seekTo(_seekT);
      }
      _seekT = null;
    }
  }

  // ── Playhead direct update (bypasses EditorState for 60fps) ──
  function _movePH(t) {
    if (!_ph) return;
    const pps = EditorTimeline.getPxPerSec();
    _ph.style.setProperty('--ph-x', Math.round(t * pps) + 'px');
  }

  // ── Pointer down ─────────────────────────────────────────────
  function _onDown(e) {
    const tgt = e.target;

    // ── 1. Trim handle ─────────────────────────────
    if (tgt.classList.contains('evTLClipResize')) {
      e.preventDefault();
      const clipId = tgt.dataset.clipId;
      const side   = tgt.dataset.resize; // 'start' | 'end'
      const clip   = EditorState.getState().clips.find(c => c.id === clipId);
      if (!clip) return;

      const clipEl = tgt.closest('.evTLClip');
      const pps    = EditorTimeline.getPxPerSec();
      const dur    = EditorState.getState().duration;

      clipEl.classList.add('is-trim-active');
      _op = {
        type:       OP.TRIM,
        clipId,
        side,
        clipEl,
        origStart:  clip.start,
        origEnd:    clip.end,
        origLeft:   clip.start * pps,
        origWidth:  (clip.end - clip.start) * pps,
        startX:     e.clientX,
        pps,
        dur,
      };
      try { _root.setPointerCapture(e.pointerId); } catch (_) {}
      _root.classList.add('is-trimming');
      return;
    }

    // ── 2. Clip body — select + drag-move prep ─────
    const clipEl = tgt.classList.contains('evTLClip')
      ? tgt
      : tgt.closest?.('.evTLClip');
    if (clipEl) {
      const clipId = clipEl.dataset.clipId;
      const clip   = EditorState.getState().clips.find(c => c.id === clipId);
      if (!clip) return;
      e.preventDefault();

      EditorState.selectClip(clipId);
      _queueSeek(clip.start);

      const pps = EditorTimeline.getPxPerSec();
      const dur = EditorState.getState().duration;
      clipEl.classList.add('is-dragging');

      _op = {
        type:       OP.CLIP_MOVE,
        clipId,
        clipEl,
        origStart:  clip.start,
        origEnd:    clip.end,
        startX:     e.clientX,
        pps,
        dur,
        moved:      false,
        _liveStart: clip.start,
        _liveEnd:   clip.end,
      };
      try { _root.setPointerCapture(e.pointerId); } catch (_) {}
      _root.classList.add('is-clip-dragging');
      return;
    }

    // ── 3. Subtitle segment — seek to start ───────
    const subEl = tgt.classList.contains('evTLSub')
      ? tgt
      : tgt.closest?.('.evTLSub');
    if (subEl) {
      const idx  = parseInt(subEl.dataset.subIdx, 10);
      const segs = EditorState.getState().subtitles;
      if (!isNaN(idx) && segs[idx]) _queueSeek(segs[idx].start);
      return;
    }

    // ── 4. Ruler / playhead / track body — scrub ──
    const inRuler = tgt.id === 'evTLPlayhead'
                 || tgt.classList.contains('evTLTick')
                 || tgt.id === 'evTLRulerContent'
                 || !!tgt.closest?.('#evTLRulerContent');
    const inTrack = ['evTLTrackSource','evTLTrackClips','evTLTrackSubs','evTLTrackText']
                    .includes(tgt.id)
                 || tgt.classList.contains('evTLSourceBar')
                 || !!tgt.closest?.('[data-track]');

    if (inRuler || inTrack) {
      e.preventDefault();
      const t = EditorCoordinates.clientXToTime(e.clientX, _scroll, EditorTimeline.getPxPerSec());
      if (t >= 0) {
        _movePH(t);
        _queueSeek(t);
      }
      _op = { type: OP.SCRUB, startX: e.clientX };
      _root.classList.add('is-scrubbing');
      try { _root.setPointerCapture(e.pointerId); } catch (_) {}
    }
  }

  // ── Pointer move (document, active drag) ────────────────────
  function _onMove(e) {
    if (!_op) return;
    e.preventDefault();

    const pps = _op.pps || EditorTimeline.getPxPerSec();

    // ── SCRUB ───────────────────────────────────
    if (_op.type === OP.SCRUB) {
      const t = EditorCoordinates.clientXToTime(e.clientX, _scroll, pps);
      if (t >= 0) {
        _movePH(t);
        _queueSeek(Math.max(0, t));
      }
      return;
    }

    const dx   = e.clientX - _op.startX;
    const dSec = dx / pps;
    const C    = EditorCoordinates;

    // Snap points for magnetic editing (exclude this clip's own edges)
    const _snapPts = C.getSnapPoints(EditorState.getState())
      .filter(p => p !== _op.origStart && p !== _op.origEnd);

    // ── TRIM ────────────────────────────────────
    if (_op.type === OP.TRIM) {
      const clipEl = _op.clipEl;
      if (!clipEl) return;

      if (_op.side === 'start') {
        const rawStart = C.clampTime(
          _op.origStart + dSec, 0, _op.origEnd - C.MIN_CLIP_DUR
        );
        const newStart = C.magneticTime(rawStart, _snapPts, pps);
        const newLeft  = Math.round(newStart * pps);
        const newWidth = Math.max(3, Math.round((_op.origEnd - newStart) * pps));
        clipEl.style.left  = newLeft  + 'px';
        clipEl.style.width = newWidth + 'px';
        _movePH(newStart);
        _queueSeek(newStart);
        _op._liveStart = newStart;

      } else {
        const rawEnd = C.clampTime(
          _op.origEnd + dSec, _op.origStart + C.MIN_CLIP_DUR, _op.dur || 999999
        );
        const newEnd   = C.magneticTime(rawEnd, _snapPts, pps);
        const newWidth = Math.max(3, Math.round((newEnd - _op.origStart) * pps));
        clipEl.style.width = newWidth + 'px';
        _movePH(newEnd);
        _queueSeek(newEnd);
        _op._liveEnd = newEnd;
      }
      return;
    }

    // ── CLIP MOVE ───────────────────────────────
    if (_op.type === OP.CLIP_MOVE) {
      if (Math.abs(dx) < 2) return; // deadzone
      _op.moved = true;
      const clipDur  = _op.origEnd - _op.origStart;
      const rawStart = C.clampTime(
        _op.origStart + dSec, 0, (_op.dur || 999999) - clipDur
      );
      const newStart = C.magneticTime(rawStart, _snapPts, pps);
      const newEnd   = newStart + clipDur;
      const movePx   = Math.round((newStart - _op.origStart) * pps);
      _op.clipEl.style.transform = 'translateX(' + movePx + 'px)';
      _op._liveStart = newStart;
      _op._liveEnd   = newEnd;
      _movePH(newStart);
    }
  }

  // ── Pointer up ───────────────────────────────────────────────
  function _onUp() {
    if (!_op) return;

    const type   = _op.type;
    const clipId = _op.clipId;

    // Commit operations to state
    if (type === OP.TRIM) {
      _op.clipEl?.classList.remove('is-trim-active');
      _root?.classList.remove('is-trimming');
      const liveStart = _op.side === 'start' ? (_op._liveStart ?? _op.origStart) : _op.origStart;
      const liveEnd   = _op.side === 'end'   ? (_op._liveEnd   ?? _op.origEnd)   : _op.origEnd;
      EditorState.patchClip(clipId, { start: liveStart, end: liveEnd });
      EditorTimeline.renderClips(EditorState.getState().clips);

    } else if (type === OP.CLIP_MOVE && _op.moved) {
      _op.clipEl?.classList.remove('is-dragging');
      _op.clipEl.style.transform = '';
      _root?.classList.remove('is-clip-dragging');
      EditorState.patchClip(clipId, {
        start: _op._liveStart ?? _op.origStart,
        end:   _op._liveEnd   ?? _op.origEnd,
      });
      EditorTimeline.renderClips(EditorState.getState().clips);

    } else if (type === OP.CLIP_MOVE) {
      // No movement — just clean up classes
      _op.clipEl?.classList.remove('is-dragging');
      _root?.classList.remove('is-clip-dragging');

    } else if (type === OP.SCRUB) {
      _root?.classList.remove('is-scrubbing');
    }

    _op = null;
  }

  // ── Hover (no drag) — tooltip + hovered clip state ───────────
  function _onHover(e) {
    if (_op) return;

    // Hover clip state
    const clipEl = e.target.closest?.('.evTLClip');
    const id     = clipEl ? clipEl.dataset.clipId : null;
    if (id !== EditorState.getState().hoveredClipId) {
      EditorState.setEditorState({ hoveredClipId: id });
    }

    // Time tooltip
    const pps = EditorTimeline.getPxPerSec();
    const t   = EditorCoordinates.clientXToTime(e.clientX, _scroll, pps);
    if (t >= 0) {
      const m    = Math.floor(t / 60);
      const sRaw = t % 60;
      const s    = sRaw.toFixed(2);
      const lbl  = m + ':' + (sRaw < 10 ? '0' : '') + s;
      _showTooltip(e.clientX, e.clientY, lbl);
    }
  }

  function _onLeave() {
    if (EditorState.getState().hoveredClipId !== null) {
      EditorState.setEditorState({ hoveredClipId: null });
    }
    _hideTooltip();
  }

  // ── Ctrl+Wheel zoom ──────────────────────────────────────────
  function _onWheel(e) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    e.stopPropagation();

    const scroll = _scroll;
    if (!scroll) return;

    const pps       = EditorTimeline.getPxPerSec();
    const factor    = e.deltaY < 0 ? 1.25 : (1 / 1.25);
    const newPps    = Math.max(2, Math.min(4000, pps * factor));
    if (newPps === pps) return;

    // Anchor zoom at cursor position
    const anchorT   = EditorCoordinates.clientXToTime(e.clientX, scroll, pps);
    const newScroll = EditorCoordinates.zoomScrollLeft(anchorT, e.clientX, scroll, newPps);

    EditorTimeline.setZoom(newPps);
    requestAnimationFrame(() => { if (scroll) scroll.scrollLeft = newScroll; });
  }

  return { init, destroy };

})();
