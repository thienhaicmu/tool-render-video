/* score-preference.js — Phase 69: Learn clip type preference from Keep/Avoid/Download signals */
'use strict';

window.ScorePreference = (() => {
  const LS_KEY      = 'score_pref_v1';
  const MAX_SIGNALS = 30;
  const TTL_MS      = 30 * 24 * 60 * 60 * 1000; // 30 days
  const MIN_TOTAL   = 5;
  const MIN_SCORE   = 3.0;
  const MIN_RATIO   = 1.5;
  const HIGH_THRESH = 65;
  const DUR_THRESH  = 70;

  const _DIMS = ['hook', 'speech', 'retention', 'duration', 'market'];
  const _LABELS = {
    hook:      'Preference: Hook clips',
    speech:    'Preference: Speech clips',
    retention: 'Preference: Smooth pacing',
    duration:  'Preference: Duration fit',
    market:    'Preference: Market-fit clips',
  };
  const _WEIGHTS = { download: 2, keep: 1, avoid: -1 };

  function _empty() {
    return { signals: [], total: 0, dim_scores: { hook: 0, speech: 0, retention: 0, duration: 0, market: 0 } };
  }

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? Object.assign(_empty(), JSON.parse(raw)) : _empty();
    } catch (_) { return _empty(); }
  }

  function _save(d) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(d)); } catch (_) { console.warn('[preference:score] localStorage write failed'); }
  }

  function _prune(d) {
    const now = Date.now();
    d.signals = d.signals
      .filter(function(s) { return (now - (s.ts || 0)) < TTL_MS; })
      .slice(-MAX_SIGNALS);
    return d;
  }

  function _isHigh(components, dim) {
    const thresh = dim === 'duration' ? DUR_THRESH : HIGH_THRESH;
    const key = dim === 'hook'      ? 'hook_score'
              : dim === 'speech'    ? 'speech_density_score'
              : dim === 'retention' ? 'retention_score'
              : dim === 'duration'  ? 'duration_fit_score'
              : dim === 'market'    ? 'market_score'
              : null;
    if (!key) return false;
    const val = Number(components[key] || 0);
    if (dim === 'market' && val === 50.0) return false;
    return val > thresh;
  }

  function recordSignal(action, components) {
    if (!Object.prototype.hasOwnProperty.call(_WEIGHTS, action)) return;
    if (!components || typeof components !== 'object') return;
    const w = _WEIGHTS[action];
    const d = _prune(_load());
    const sig = { action: action, ts: Date.now() };
    _DIMS.forEach(function(dim) {
      const high = _isHigh(components, dim);
      sig[dim + '_high'] = high;
      d.dim_scores[dim] = (d.dim_scores[dim] || 0) + (high ? w : 0);
    });
    d.signals.push(sig);
    d.total = (d.total || 0) + 1;
    _save(d);
  }

  function getPreference() {
    const d = _prune(_load());
    if ((d.total || 0) < MIN_TOTAL) return null;
    const entries = _DIMS
      .map(function(dim) { return [dim, d.dim_scores[dim] || 0]; })
      .filter(function(e) { return e[1] > 0; })
      .sort(function(a, b) { return b[1] - a[1]; });
    if (!entries.length || entries[0][1] < MIN_SCORE) return null;
    if (entries.length > 1 && entries[0][1] < entries[1][1] * MIN_RATIO) return null;
    const dim = entries[0][0];
    return { confident: true, dimension: dim, label: _LABELS[dim] };
  }

  function getCount() { return { total: _load().total || 0 }; }
  function reset() { _save(_empty()); }

  return { recordSignal: recordSignal, getPreference: getPreference, getCount: getCount, reset: reset };
})();
