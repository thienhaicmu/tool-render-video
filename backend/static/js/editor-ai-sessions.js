/* =========================================================
   editor-ai-sessions.js  —  P2-D: AI Editing Sessions
   Non-destructive snapshot stack + four named variant slots
   (aggressive / balanced / cinematic / viral).
   Snapshots are created automatically by EditorAiActions._snap().
   Variants are one-click presets that call into EditorAiActions.
   ========================================================= */
'use strict';

window.EditorAiSessions = (() => {

  const VARIANTS  = ['viral', 'cinematic', 'aggressive', 'balanced'];
  let   _variants = {};
  let   _snaps    = [];
  const MAX_SNAPS = 12;

  // ── Variant → action mapping ─────────────────────────────
  const _VARIANT_ACTION = {
    aggressive: 'viralMode',
    balanced:   null,           // restore to last balanced state
    cinematic:  'cinematicMode',
    viral:      'viralMode',
  };

  // ── Snapshots ────────────────────────────────────────────
  function createSnapshot(label) {
    if (typeof EditorState === 'undefined') return null;
    const s = EditorState.getState();
    const snap = {
      id:    'snap_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6),
      label: String(label || 'Snapshot'),
      clips: s.clips.map(c => Object.assign({}, c)),
      ts:    Date.now(),
    };
    _snaps.unshift(snap);
    if (_snaps.length > MAX_SNAPS) _snaps.pop();
    _renderSnaps();
    return snap;
  }

  function restoreSnapshot(snapId) {
    const snap = _snaps.find(s => s.id === snapId);
    if (!snap) return false;
    EditorState.setEditorState({ clips: snap.clips.map(c => Object.assign({}, c)) });
    if (typeof EditorTimeline !== 'undefined') EditorTimeline.renderClips(EditorState.getState().clips);
    if (typeof EditorSceneIntelligence !== 'undefined') EditorSceneIntelligence.runAnalysis(EditorState.getState());
    return true;
  }

  // ── Variants ─────────────────────────────────────────────
  // Saves current state as the variant, then applies its action.
  function applyVariant(name) {
    if (!VARIANTS.includes(name)) return;
    if (typeof EditorState === 'undefined') return;
    const s = EditorState.getState();
    _variants[name] = { clips: s.clips.map(c => Object.assign({}, c)), savedAt: Date.now() };
    _renderVariantBtns();
    const action = _VARIANT_ACTION[name];
    if (action && typeof EditorAiActions !== 'undefined') EditorAiActions.runAction(action);
  }

  // Restores a previously saved variant (no action applied).
  function loadVariant(name) {
    const v = _variants[name];
    if (!v) return false;
    EditorState.setEditorState({ clips: v.clips.map(c => Object.assign({}, c)) });
    if (typeof EditorTimeline !== 'undefined') EditorTimeline.renderClips(EditorState.getState().clips);
    if (typeof EditorSceneIntelligence !== 'undefined') EditorSceneIntelligence.runAnalysis(EditorState.getState());
    return true;
  }

  // ── DOM helpers ──────────────────────────────────────────
  function _fmt(ts) {
    const d = new Date(ts);
    return d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  function _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function _renderSnaps() {
    const el = document.getElementById('aiSnapshotList');
    if (!el) return;
    if (!_snaps.length) {
      el.innerHTML = '<div class="aiSnapshotEmpty">No snapshots yet</div>';
      return;
    }
    el.innerHTML = _snaps.map(s =>
      `<div class="aiSnapshotItem" onclick="EditorAiSessions.restoreSnapshot('${s.id}')" title="Restore snapshot">` +
      `<span class="aiSnapshotLabel">${_esc(s.label)}</span>` +
      `<span class="aiSnapshotTime">${_fmt(s.ts)}</span>` +
      `</div>`
    ).join('');
  }

  function _renderVariantBtns() {
    VARIANTS.forEach(name => {
      const btn = document.getElementById('aiVariant_' + name);
      if (btn) btn.classList.toggle('has-save', !!_variants[name]);
    });
  }

  // ── State accessors ──────────────────────────────────────
  function getSnapshots() { return _snaps.slice(); }
  function getVariants()  { return Object.assign({}, _variants); }

  function reset() {
    _variants = {};
    _snaps    = [];
    _renderSnaps();
    _renderVariantBtns();
  }

  return {
    createSnapshot, restoreSnapshot,
    applyVariant, loadVariant,
    getSnapshots, getVariants,
    reset,
  };

})();
