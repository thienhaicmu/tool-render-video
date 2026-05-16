/* =========================================================
   creator-memory.js  —  P3.1: Creator Memory
   Persists editor preference signals across sessions.
   Bridges session-only aiPreferenceProfile → localStorage
   → backend /api/creator/preferences.

   Designed to be safe: influences AI copy only after
   MIN_SIGNALS_FOR_INFLUENCE accepted/rejected actions.
   ========================================================= */
'use strict';

window.CreatorMemory = (() => {

  const LS_KEY  = 'cm_prefs_v1';
  const MIN_SIG = 5;   // signals required before influencing AI copy
  const SYNC_MS = 2000; // debounce backend sync

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
  // Call once on editor load — pulls persisted prefs from backend,
  // merges with localStorage (whichever has more signals wins),
  // seeds EditorState.aiPreferenceProfile if we have enough data.
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
      accepted:     Object.assign({}, _profile.accepted),
      rejected:     Object.assign({}, _profile.rejected),
      aggressiveness: _profile.aggressiveness || 0.5,
      sessionTotal: _profile.totalSignals || 0,
    };
  }

  // ── Public: recordSignal ──────────────────────────────────
  // Called by _trackPreference after every accept/reject.
  // Mirrors the aggressiveness update logic in editor-ai-actions.js
  // so both surfaces stay in sync.
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
  // Returns a digest used by _buildReasoning to inject memory-aware copy.
  // `confident` is false until MIN_SIG signals — never influences AI before that.
  function getDerivedPreferences() {
    const total     = _profile.totalSignals || 0;
    const confident = total >= MIN_SIG;
    const accepted  = _profile.accepted || {};
    const rejected  = _profile.rejected || {};
    const favored   = Object.entries(accepted)
      .filter(([k, v]) => v > (rejected[k] || 0))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([k]) => k);
    const avoided = Object.entries(rejected)
      .filter(([k, v]) => v > (accepted[k] || 0))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2)
      .map(([k]) => k);
    return {
      confident,
      totalSignals:   total,
      aggressiveness: _profile.aggressiveness || 0.5,
      favored,
      avoided,
    };
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
    const pct      = Math.min(100, Math.round((n / MIN_SIG) * 100));
    const remaining = MIN_SIG - n;
    return '<div class="cmPanelLearn">' +
      '<div class="cmPanelTitle">AI is learning your style</div>' +
      '<div class="cmLearnBar"><div class="cmLearnFill" style="width:' + pct + '%"></div></div>' +
      '<div class="cmPanelHint">Accept or discard ' + remaining + ' more suggestion' + (remaining !== 1 ? 's' : '') + ' to unlock preference memory.</div>' +
      '</div>';
  }

  function _renderKnown(prefs) {
    const aggLabel = prefs.aggressiveness > 0.65 ? 'Bold' : prefs.aggressiveness < 0.4 ? 'Conservative' : 'Balanced';
    let html = '<div class="cmPanelKnown">' +
      '<div class="cmPanelTitle">Creator Memory <span class="cmPanelReset" onclick="CreatorMemory.reset()">Reset</span></div>' +
      '<div class="cmPrefRow"><span class="cmPrefLabel">Editing style</span><span class="cmPrefVal">' + aggLabel + '</span></div>';
    if (prefs.favored.length) {
      html += '<div class="cmPrefRow"><span class="cmPrefLabel">Prefers</span>' +
        '<span class="cmPrefVal cmFavored">' + prefs.favored.map(_label).join(', ') + '</span></div>';
    }
    if (prefs.avoided.length) {
      html += '<div class="cmPrefRow"><span class="cmPrefLabel">Avoids</span>' +
        '<span class="cmPrefVal cmAvoided">' + prefs.avoided.map(_label).join(', ') + '</span></div>';
    }
    html += '<div class="cmPrefRow"><span class="cmPrefLabel">Total signals</span>' +
      '<span class="cmPrefVal">' + prefs.totalSignals + '</span></div>';
    html += '</div>';
    return html;
  }

  return { init, recordSignal, getProfile, getDerivedPreferences, reset };

})();
