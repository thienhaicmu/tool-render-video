/* =========================================================
   creator-memory.js  —  P3.1/P3.3: Creator Memory + Taste Model
   Persists editor preference signals across sessions.
   P3.3 adds getTasteModel() — weighted multi-dimensional inference
   from the same accepted/rejected signal data. No ML, no archetypes.
   ========================================================= */
'use strict';

window.CreatorMemory = (() => {

  const LS_KEY       = 'cm_prefs_v1';
  const MIN_SIG      = 5;   // signals required for basic preference confidence
  const MIN_TASTE_SIG = 8;  // signals required for taste model confidence
  const SYNC_MS      = 2000;

  let _profile   = _loadLS();
  let _syncTimer = null;

  // ── Profile shape ─────────────────────────────────────────
  function _empty() {
    return { accepted: {}, rejected: {}, aggressiveness: 0.5, totalSignals: 0, lastUpdated: null };
  }

  function _loadLS() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) return Object.assign(_empty(), JSON.parse(raw));
    } catch (e) {}
    return _empty();
  }

  function _saveLS(p) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(p)); } catch (e) {}
  }

  // ── Backend sync ──────────────────────────────────────────
  function _scheduleSync() {
    if (_syncTimer) clearTimeout(_syncTimer);
    _syncTimer = setTimeout(_pushToBackend, SYNC_MS);
  }

  function _pushToBackend() {
    fetch('/api/creator/preferences', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefs: _profile }),
    }).catch(() => {});
  }

  // ── Public: init ──────────────────────────────────────────
  function init() {
    fetch('/api/creator/preferences')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !data.prefs) return;
        const remote = data.prefs;
        if ((remote.totalSignals || 0) > (_profile.totalSignals || 0)) {
          _profile = Object.assign(_empty(), remote);
          _saveLS(_profile);
        }
        if (_profile.totalSignals > 0 && typeof EditorState !== 'undefined') {
          EditorState.setEditorState({ aiPreferenceProfile: _toEditorProfile() });
        }
        _refreshPanel();
      })
      .catch(() => {});
  }

  function _toEditorProfile() {
    return {
      accepted:       Object.assign({}, _profile.accepted),
      rejected:       Object.assign({}, _profile.rejected),
      aggressiveness: _profile.aggressiveness || 0.5,
      sessionTotal:   _profile.totalSignals || 0,
    };
  }

  // ── Public: recordSignal ──────────────────────────────────
  function recordSignal(actionName, accepted) {
    if (!actionName) return;
    const next = Object.assign({}, _profile, {
      accepted: Object.assign({}, _profile.accepted),
      rejected: Object.assign({}, _profile.rejected),
    });
    if (accepted) {
      next.accepted[actionName] = (next.accepted[actionName] || 0) + 1;
    } else {
      next.rejected[actionName] = (next.rejected[actionName] || 0) + 1;
    }
    const totalAcc = Object.values(next.accepted).reduce((s, v) => s + v, 0);
    const totalRej = Object.values(next.rejected).reduce((s, v) => s + v, 0);
    const total    = totalAcc + totalRej;
    if (total >= 2) {
      next.aggressiveness = Math.max(0.25, Math.min(0.88, 0.5 + (totalAcc - totalRej) / (total * 5)));
    }
    next.totalSignals = total;
    next.lastUpdated  = new Date().toISOString();
    _profile = next;
    _saveLS(_profile);
    _scheduleSync();
    _refreshPanel();
  }

  // ── Public: getProfile ────────────────────────────────────
  function getProfile() {
    return Object.assign({}, _profile);
  }

  // ── Public: getDerivedPreferences ─────────────────────────
  function getDerivedPreferences() {
    const total     = _profile.totalSignals || 0;
    const confident = total >= MIN_SIG;
    const acc       = _profile.accepted || {};
    const rej       = _profile.rejected || {};
    const favored   = Object.entries(acc)
      .filter(([k, v]) => v > (rej[k] || 0))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([k]) => k);
    const avoided = Object.entries(rej)
      .filter(([k, v]) => v > (acc[k] || 0))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2)
      .map(([k]) => k);
    return { confident, totalSignals: total, aggressiveness: _profile.aggressiveness || 0.5, favored, avoided };
  }

  // ── Public: getTasteModel ─────────────────────────────────
  // P3.3: Multi-dimensional taste inference from preference signals.
  // Returns soft dimensional scores — NOT hardcoded creator archetypes.
  // Requires MIN_TASTE_SIG signals for confidence.
  function getTasteModel() {
    const total = _profile.totalSignals || 0;
    const confident = total >= MIN_TASTE_SIG;
    const acc = _profile.accepted || {};
    const rej = _profile.rejected || {};

    // ── Pace dimension ────────────────────────────────────────
    // Fast signals: fasterPacing + removeDeadSpace accepted, cinematicMode rejected
    // Cinematic signals: cinematicMode accepted, fasterPacing + removeDeadSpace rejected
    const fastAcc = (acc.fasterPacing || 0) + (acc.removeDeadSpace || 0);
    const fastRej = (rej.fasterPacing || 0) + (rej.removeDeadSpace || 0);
    const slowAcc = (acc.cinematicMode || 0);
    const slowRej = (rej.cinematicMode || 0);
    const paceObs = fastAcc + fastRej + slowAcc + slowRej;
    // paceRaw: -1 (cinematic) to +1 (fast)
    const paceRaw  = paceObs > 0 ? (fastAcc + slowRej - fastRej - slowAcc) / paceObs : 0;
    const pace     = paceRaw > 0.2 ? 'fast' : paceRaw < -0.2 ? 'cinematic' : 'balanced';
    const paceConf = Math.min(1, paceObs / 4);

    // ── Hook dimension ────────────────────────────────────────
    // Aggressive: strongerHook + viralMode accepted
    // Soft: those rejected
    const hookAcc  = (acc.strongerHook || 0) + (acc.viralMode || 0);
    const hookRej  = (rej.strongerHook || 0) + (rej.viralMode || 0);
    const hookObs  = hookAcc + hookRej;
    const hookRaw  = hookObs > 0 ? (hookAcc - hookRej) / hookObs : 0;
    const hook     = hookRaw > 0.3 ? 'aggressive' : hookRaw < -0.3 ? 'soft' : 'moderate';
    const hookConf = Math.min(1, hookObs / 4);

    // ── Edit style (composite) ────────────────────────────────
    const eduAcc = (acc.subtitleCleanup || 0) + (acc.smartClipPrioritization || 0);
    const eduRej = (rej.subtitleCleanup || 0) + (rej.smartClipPrioritization || 0);
    const eduNet = eduAcc - eduRej;
    let editStyle;
    if (paceRaw > 0.2 && hookRaw > 0.2)          editStyle = 'viral';
    else if (paceRaw < -0.2 && hookRaw <= 0.1)   editStyle = 'cinematic';
    else if (eduNet >= 2 && paceRaw >= -0.1)      editStyle = 'educational';
    else                                           editStyle = 'balanced';

    return { confident, pace, paceRaw, paceConf, hook, hookRaw, hookConf, editStyle };
  }

  // ── Public: reset ─────────────────────────────────────────
  function reset() {
    _profile = _empty();
    _saveLS(_profile);
    _pushToBackend();
    if (typeof EditorState !== 'undefined') {
      EditorState.setEditorState({ aiPreferenceProfile: null });
    }
    _refreshPanel();
  }

  // ── Inspector panel render ────────────────────────────────
  const _LABELS = {
    removeDeadSpace:         'Tighten Cuts',
    strongerHook:            'Stronger Hook',
    fasterPacing:            'Faster Pacing',
    viralMode:               'Viral Mode',
    cinematicMode:           'Cinematic Mode',
    subtitleCleanup:         'Subtitle Cleanup',
    smartClipPrioritization: 'Smart Prioritization',
  };
  function _label(k) { return _LABELS[k] || k; }

  function _refreshPanel() {
    const panel = document.getElementById('cmPrefsPanel');
    if (!panel) return;
    const prefs = getDerivedPreferences();
    panel.innerHTML = prefs.confident ? _renderKnown(prefs) : _renderLearning(prefs.totalSignals);
  }

  function _renderLearning(n) {
    const pct       = Math.min(100, Math.round((n / MIN_SIG) * 100));
    const remaining = MIN_SIG - n;
    return '<div class="cmPanelLearn">' +
      '<div class="cmPanelTitle">AI is learning your style</div>' +
      '<div class="cmLearnBar"><div class="cmLearnFill" style="width:' + pct + '%"></div></div>' +
      '<div class="cmPanelHint">Accept or discard ' + remaining + ' more suggestion' + (remaining !== 1 ? 's' : '') + ' to unlock preference memory.</div>' +
      '</div>';
  }

  function _renderKnown(prefs) {
    const taste    = getTasteModel();
    const aggLabel = prefs.aggressiveness > 0.65 ? 'Bold' : prefs.aggressiveness < 0.4 ? 'Conservative' : 'Balanced';

    let html = '<div class="cmPanelKnown">' +
      '<div class="cmPanelTitle">Creator Memory <span class="cmPanelReset" onclick="CreatorMemory.reset()">Reset</span></div>' +
      '<div class="cmPrefRow"><span class="cmPrefLabel">Editing style</span><span class="cmPrefVal">' + aggLabel + '</span></div>';

    // P3.3: taste dimensions — shown only when taste model is confident
    if (taste.confident) {
      const PACE_LABELS  = { fast: 'Fast', balanced: 'Balanced', cinematic: 'Cinematic' };
      const HOOK_LABELS  = { aggressive: 'Aggressive', moderate: 'Moderate', soft: 'Soft' };
      const STYLE_LABELS = { viral: 'Viral / High-energy', cinematic: 'Cinematic / Story', educational: 'Educational / Clarity', balanced: 'Balanced' };
      html += '<div class="cmPrefRow"><span class="cmPrefLabel">Pace tendency</span><span class="cmPrefVal cmTasteVal">' + (PACE_LABELS[taste.pace] || taste.pace) + '</span></div>';
      html += '<div class="cmPrefRow"><span class="cmPrefLabel">Hook tendency</span><span class="cmPrefVal cmTasteVal">' + (HOOK_LABELS[taste.hook] || taste.hook) + '</span></div>';
      if (taste.editStyle !== 'balanced') {
        html += '<div class="cmPrefRow"><span class="cmPrefLabel">Edit tendency</span><span class="cmPrefVal cmTasteVal">' + (STYLE_LABELS[taste.editStyle] || taste.editStyle) + '</span></div>';
      }
    }

    if (prefs.favored.length) {
      html += '<div class="cmPrefRow"><span class="cmPrefLabel">Prefers</span>' +
        '<span class="cmPrefVal cmFavored">' + prefs.favored.map(_label).join(', ') + '</span></div>';
    }
    if (prefs.avoided.length) {
      html += '<div class="cmPrefRow"><span class="cmPrefLabel">Avoids</span>' +
        '<span class="cmPrefVal cmAvoided">' + prefs.avoided.map(_label).join(', ') + '</span></div>';
    }
    html += '<div class="cmPrefRow"><span class="cmPrefLabel">Total signals</span><span class="cmPrefVal">' + prefs.totalSignals + '</span></div>';
    html += '</div>';
    return html;
  }

  return { init, recordSignal, getProfile, getDerivedPreferences, getTasteModel, reset };

})();
