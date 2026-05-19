/* duration-preference.js — Phase 70: Learn clip length preference from Keep/Avoid/Download */
'use strict';

window.DurationPreference = (() => {
  const LS_KEY      = 'dur_pref_v1';
  const MAX_SIGNALS = 30;
  const TTL_MS      = 30 * 24 * 60 * 60 * 1000; // 30 days
  const MIN_TOTAL   = 5;
  const MIN_SCORE   = 3.0;
  const MIN_RATIO   = 1.5;
  const TIGHT_MAX   = 70;   // < 70s = tight (aligns with Phase 67 neutral zone lower bound)
  const LONG_MIN    = 120;  // > 120s = long (aligns with Phase 67 neutral zone upper bound)

  const _WEIGHTS = { download: 2, keep: 1, avoid: -1 };

  const _SUGGEST = {
    tight: { label: 'shorter clips', applyMin: 45, applyMax: 90  },
    long:  { label: 'longer clips',  applyMin: 90, applyMax: 180 },
  };

  function _empty() {
    return { signals: [], total: 0, bucket_scores: { tight: 0, mid: 0, long: 0 } };
  }

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? Object.assign(_empty(), JSON.parse(raw)) : _empty();
    } catch (_) { return _empty(); }
  }

  function _save(d) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(d)); } catch (_) {}
  }

  function _prune(d) {
    const now = Date.now();
    d.signals = d.signals
      .filter(function(s) { return (now - (s.ts || 0)) < TTL_MS; })
      .slice(-MAX_SIGNALS);
    return d;
  }

  function _bucket(dur) {
    if (dur < TIGHT_MAX) return 'tight';
    if (dur > LONG_MIN)  return 'long';
    return 'mid';
  }

  function recordSignal(action, durationSec) {
    if (!Object.prototype.hasOwnProperty.call(_WEIGHTS, action)) return;
    const dur = Number(durationSec) || 0;
    if (dur <= 0) return;
    const w = _WEIGHTS[action];
    const d = _prune(_load());
    const b = _bucket(dur);
    const sig = { action: action, dur_sec: dur, bucket: b, ts: Date.now() };
    d.bucket_scores[b] = (d.bucket_scores[b] || 0) + w;
    d.signals.push(sig);
    d.total = (d.total || 0) + 1;
    _save(d);
  }

  function getPreference() {
    const d = _prune(_load());
    if ((d.total || 0) < MIN_TOTAL) return null;
    // Only tight and long can be surfaced — mid is the default range
    const candidates = ['tight', 'long']
      .map(function(b) { return [b, d.bucket_scores[b] || 0]; })
      .filter(function(e) { return e[1] >= MIN_SCORE; })
      .sort(function(a, b) { return b[1] - a[1]; });
    if (!candidates.length) return null;
    const top = candidates[0];
    // Ratio check against ALL buckets (including mid) so mid dominance suppresses tight/long
    const allScores = Object.values(d.bucket_scores).filter(function(v) { return v > 0; });
    const secondMax = Math.max.apply(null, allScores.filter(function(v) { return v < top[1]; }).concat([0]));
    if (secondMax > 0 && top[1] < secondMax * MIN_RATIO) return null;
    const s = _SUGGEST[top[0]];
    return { confident: true, bucket: top[0], label: s.label, applyMin: s.applyMin, applyMax: s.applyMax };
  }

  function getCount() { return { total: _load().total || 0 }; }
  function reset() { _save(_empty()); }

  return { recordSignal: recordSignal, getPreference: getPreference, getCount: getCount, reset: reset };
})();
