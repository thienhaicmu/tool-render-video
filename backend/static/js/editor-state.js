/* =========================================================
   editor-state.js  —  P1-A: Editor State Engine
   Central pub/sub store for the editor workspace.
   Extends the existing _ev object with clip/playback state.
   ========================================================= */
'use strict';

window.EditorState = (() => {

  // ── State ────────────────────────────────────────────────────
  let _state = {
    sessionId:       null,
    sourceVideo:     null,
    duration:        0,
    currentTime:     0,
    isPlaying:       false,
    isMuted:         false,
    playbackRate:    1,
    zoom:            0,          // px/sec — 0 means auto-fit
    viewportStart:   0,          // seconds from start (scroll offset)
    selectedClipId:  null,
    hoveredClipId:   null,
    clips:           [],         // [{id, start, end, score, label, color, tags, locked}]
    subtitles:       [],         // [{text, start, end}]
    textLayers:      [],         // mirror of _ev.textLayers
    activeInspectorTab: 'mode',
    renderSelection: null,       // null = all clips
    audioTracks: null,           // set by EditorAudioRuntime
    qualityHoverPreview: true,   // set by EditorPerformanceRuntime
    qualityFilmstrip:    true,
    qualityWaveform:     true,
    // P2: AI intelligence
    sceneGraph:    [],           // [{id, start, end, energyScore, speechDensity, clipCount}]
    aiMarkers:     [],           // [{type, time, label}]
    aiSuggestions: [],           // [{id, label, action, confidence}]
    aiPatchGraph:      [],           // [{actionName, patches, ts}] — current preview graph
    aiPreferenceProfile: null,       // {accepted:{}, rejected:{}, aggressiveness:0.5, sessionTotal:0}
  };

  const _subs = new Set();
  let _batching = false;

  // ── Notify (microtask-batched) ───────────────────────────────
  function _notify() {
    if (_batching) return;
    _batching = true;
    Promise.resolve().then(() => {
      _batching = false;
      const snap = Object.freeze(Object.assign({}, _state));
      _subs.forEach(fn => { try { fn(snap); } catch (e) { console.error('[EditorState]', e); } });
    });
  }

  // ── Core API ────────────────────────────────────────────────
  function getState() { return Object.assign({}, _state); }

  function setEditorState(patch) {
    let changed = false;
    for (const k in patch) {
      if (Object.prototype.hasOwnProperty.call(patch, k) && _state[k] !== patch[k]) {
        _state[k] = patch[k];
        changed = true;
      }
    }
    if (changed) _notify();
  }

  const patchEditorState = setEditorState;

  function subscribeEditorState(fn) {
    _subs.add(fn);
    try { fn(Object.freeze(Object.assign({}, _state))); } catch (e) {}
    return function unsubscribe() { _subs.delete(fn); };
  }

  // ── Clip helpers ─────────────────────────────────────────────
  function setClips(rawClips) {
    const clips = (rawClips || []).map((c, i) => ({
      id:     c.id   || ('clip_' + i),
      start:  Number(c.start) || 0,
      end:    Number(c.end)   || 0,
      score:  Number(c.score) || 0,
      label:  c.label || ('Clip ' + (i + 1)),
      color:  _scoreColor(Number(c.score) || 0),
      tags:   c.tags  || [],
      locked: false,
    }));
    _state.clips = clips;
    _notify();
  }

  function setSubtitles(segs) {
    _state.subtitles = Array.isArray(segs) ? segs : [];
    _notify();
  }

  function setTextLayers(layers) {
    _state.textLayers = Array.isArray(layers) ? layers : [];
    _notify();
  }

  function selectClip(id) {
    if (_state.selectedClipId === id) return;
    _state.selectedClipId = id;
    _notify();
  }

  function patchClip(id, patch) {
    const clips = _state.clips.map(c => (c.id === id ? Object.assign({}, c, patch) : c));
    _state.clips = clips;
    _notify();
  }

  function _scoreColor(score) {
    if (score >= 0.8) return 'var(--success)';
    if (score >= 0.6) return 'var(--warning)';
    return 'var(--fg-400)';
  }

  // ── Event bus (for loose coupling between engines) ──────────
  const _evtMap = {};

  function on(event, fn) {
    (_evtMap[event] = _evtMap[event] || new Set()).add(fn);
  }
  function off(event, fn) {
    if (_evtMap[event]) _evtMap[event].delete(fn);
  }
  function emit(event, data) {
    if (_evtMap[event]) _evtMap[event].forEach(fn => { try { fn(data); } catch (e) {} });
  }

  // ── Reset (called when editor closes) ────────────────────────
  function reset() {
    _state.sessionId      = null;
    _state.sourceVideo    = null;
    _state.duration       = 0;
    _state.currentTime    = 0;
    _state.isPlaying      = false;
    _state.selectedClipId = null;
    _state.hoveredClipId  = null;
    _state.clips             = [];
    _state.subtitles         = [];
    _state.textLayers        = [];
    _state.audioTracks       = null;
    _state.qualityHoverPreview = true;
    _state.qualityFilmstrip    = true;
    _state.qualityWaveform     = true;
    _state.sceneGraph          = [];
    _state.aiMarkers           = [];
    _state.aiSuggestions       = [];
    _state.aiPatchGraph        = [];
    _state.aiPreferenceProfile = null;
    _notify();
  }

  return {
    getState,
    setEditorState,
    patchEditorState,
    subscribeEditorState,
    setClips,
    setSubtitles,
    setTextLayers,
    selectClip,
    patchClip,
    on, off, emit,
    reset,
  };

})();
