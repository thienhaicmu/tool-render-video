/* =========================================================
   creator-series.js — UP31: Series Intelligence
   Soft series detection from render history signals.
   Builds a lightweight series fingerprint from:
     title similarity · repeated preset · asset pack · time window.
   Publishes continuity nudges — advisory only, never forced.

   Philosophy:
     - Local only. No ML. No cloud. No manual tagging.
     - Reuses existing: preset · DNA · assets · review queue · steering.
     - Gentle only. Creator always wins.
     - Confidence gate prevents noise from single divergent renders.

   Storage: creator_series_v1
   Hierarchy: manual > taste > feedback > DNA > series > platform > default
   ========================================================= */
'use strict';

window.CreatorSeries = (() => {

  const LS_KEY         = 'creator_series_v1';
  const MAX_RENDERS    = 50;
  const TIME_WINDOW_MS = 30 * 24 * 3600 * 1000;  // 30 days sliding window
  const EMA_ALPHA      = 0.82;                    // per-render decay (~18 renders to forget)
  const MIN_RENDERS    = 3;                       // window floor before any detection attempt
  const DETECT_GATE    = 0.35;                    // confidence floor: hint fires in steering panel
  const CHIP_GATE      = 0.55;                    // confidence floor: trust chip in output panel

  // ── Storage ────────────────────────────────────────────────────────
  function _emptyState() {
    return { renders: [], fingerprint: _nullFingerprint() };
  }

  function _nullFingerprint() {
    return {
      confidence:     0,
      series_detected:false,
      title_prefix:   null,
      preset_id:      null,
      logo_path:      null,
      subtitle_style: null,
      cta_type:       null,
      platform:       null,
      render_profile: null,
      structure_bias: null,
      last_seen:      0,
      last_computed:  0,
      window_size:    0,
    };
  }

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? Object.assign(_emptyState(), JSON.parse(raw)) : _emptyState();
    } catch (_) { return _emptyState(); }
  }

  function _save(state) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (_) { console.warn('[preference:series] localStorage write failed'); }
  }

  function _getFingerprint() {
    return _load().fingerprint || _nullFingerprint();
  }

  // ── Record a completed render ──────────────────────────────────────
  function recordRender(jobId, name, payload) {
    if (!jobId) return;
    const state = _load();
    if (state.renders.find(r => r.jobId === jobId)) return;  // dedup

    const p = payload || {};

    // Preset: try payload field first, fall back to active CreatorPresets
    let presetId = String(p.preset_name || p.preset_id || '').trim() || null;
    if (!presetId && typeof CreatorPresets !== 'undefined') {
      presetId = CreatorPresets.getActive()?.id || null;
    }

    // CTA: only record when CTA is actually on with an explicit type
    const ctaOn   = p.cta_enabled !== false;
    const ctaType = String(p.cta_type || '').trim();
    const effectiveCta = (ctaOn && ctaType && ctaType !== 'auto') ? ctaType : null;

    const record = {
      jobId,
      name:          String(name || jobId),
      preset_id:     presetId,
      subtitle_style:String(p.subtitle_style || '').trim() || null,
      cta_type:      effectiveCta,
      structure_bias:String(p.structure_bias || '').trim() || null,
      platform:      String(p.target_platform || '').trim() || null,
      render_profile:String(p.render_profile || '').trim() || null,
      logo_path:     String(p.asset_logo_path || '').trim() || null,
      intro_path:    String(p.asset_intro_path || '').trim() || null,
      ts:            Date.now(),
      review_action: null,
    };

    state.renders.unshift(record);
    if (state.renders.length > MAX_RENDERS) state.renders = state.renders.slice(0, MAX_RENDERS);
    state.fingerprint = _computeFingerprint(state.renders);
    _save(state);

    const fp = state.fingerprint;
    _log('series_confidence', `${Math.round(fp.confidence * 100)}% window=${fp.window_size}`);
    if (fp.series_detected) {
      _log('series_detected',
        `prefix="${fp.title_prefix || ''}" preset=${fp.preset_id || '-'} conf=${Math.round(fp.confidence * 100)}%`);
    }
    if (fp.window_size >= MIN_RENDERS && fp.confidence > 0 && fp.confidence < DETECT_GATE) {
      _log('series_suppressed', `below detect gate (${Math.round(fp.confidence * 100)}% < ${Math.round(DETECT_GATE * 100)}%)`);
    }
  }

  // ── Record a review queue action ───────────────────────────────────
  // keep / favorite reinforce series confidence; dismiss is neutral.
  function recordReviewAction(jobId, action) {
    if (!jobId) return;
    try {
      const state = _load();
      const record = state.renders.find(r => r.jobId === jobId);
      if (!record) return;
      record.review_action = action;
      state.fingerprint = _computeFingerprint(state.renders);
      _save(state);
    } catch (_) {}
  }

  // ── Fingerprint computation ────────────────────────────────────────
  function _computeFingerprint(renders) {
    const now    = Date.now();
    const window = renders.filter(r => (now - r.ts) < TIME_WINDOW_MS);

    if (window.length < MIN_RENDERS) return _nullFingerprint();

    // ── Signal scoring — max 9 points ──────────────────────────────
    let sig = 0;

    // Preset consistency (2 pts) — same preset in ≥ MIN_RENDERS of window
    const topPreset = _topValue(window.map(r => r.preset_id), MIN_RENDERS);
    if (topPreset) sig += 2;

    // Logo consistency (2 pts) — same logo file in ≥ MIN_RENDERS
    const topLogo = _topValue(window.map(r => r.logo_path), MIN_RENDERS);
    if (topLogo) sig += 2;

    // Intro consistency (1 pt) — same intro file in ≥ MIN_RENDERS
    const topIntro = _topValue(window.map(r => r.intro_path), MIN_RENDERS);
    if (topIntro) sig += 1;

    // Title prefix (2 pts) — ≥ MIN_RENDERS share a common word prefix
    const titlePrefix = _titlePrefix(window.map(r => r.name));
    if (titlePrefix) sig += 2;

    // Platform consistency (1 pt) — same platform in ≥ 60% of window renders
    const topPlatform = _topValue(
      window.map(r => r.platform),
      Math.max(MIN_RENDERS, Math.ceil(window.length * 0.6))
    );
    if (topPlatform) sig += 1;

    // Review reinforcement (1 pt) — ≥ 2 keep/favorite actions in window
    const positive = window.filter(
      r => r.review_action === 'keep' || r.review_action === 'favorite'
    ).length;
    if (positive >= 2) sig += 1;

    const confidence     = Math.min(1.0, Math.round((sig / 9) * 100) / 100);
    const series_detected = confidence >= 0.3;

    // ── Weighted fingerprint for style dimensions ──────────────────
    const sorted = [...window].sort((a, b) => b.ts - a.ts);

    return {
      confidence,
      series_detected,
      title_prefix:  titlePrefix,
      preset_id:     topPreset,
      logo_path:     topLogo,
      subtitle_style:_weightedTop(sorted, r => r.subtitle_style),
      cta_type:      _weightedTop(sorted, r => r.cta_type),
      structure_bias:_weightedTop(sorted, r => r.structure_bias),
      platform:      _weightedTop(sorted, r => r.platform),
      render_profile:_weightedTop(sorted, r => r.render_profile),
      last_seen:     sorted[0]?.ts || 0,
      last_computed: now,
      window_size:   window.length,
    };
  }

  // ── Helpers ────────────────────────────────────────────────────────

  // Most common non-null value — must appear at least minCount times.
  function _topValue(arr, minCount) {
    const counts = {};
    arr.forEach(v => { if (v) counts[v] = (counts[v] || 0) + 1; });
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    return (top && top[1] >= minCount) ? top[0] : null;
  }

  // Exponentially weighted top value — newer renders count more.
  // Returns null if no single value is clearly dominant.
  function _weightedTop(sorted, getter) {
    const weights = {};
    sorted.forEach((r, i) => {
      const v = getter(r);
      if (v) weights[v] = (weights[v] || 0) + Math.pow(EMA_ALPHA, i);
    });
    const entries = Object.entries(weights).sort((a, b) => b[1] - a[1]);
    if (!entries.length) return null;
    const [topKey, topScore] = entries[0];
    if (topScore < 0.8) return null;  // minimum weight threshold
    // Must be clearly more dominant than runner-up (1.35x ratio)
    if (entries.length > 1 && topScore < entries[1][1] * 1.35) return null;
    return topKey;
  }

  // Detect common word prefix across a list of clip names.
  // Tries lengths 3→2→1; returns longest match appearing in ≥ MIN_RENDERS names.
  function _titlePrefix(names) {
    const normalized = names.filter(Boolean).map(n =>
      String(n).toLowerCase().replace(/[^\w\s]/g, ' ').trim().split(/\s+/).filter(Boolean)
    );
    if (normalized.length < MIN_RENDERS) return null;
    for (let len = 3; len >= 1; len--) {
      const prefixCounts = {};
      for (const wl of normalized) {
        if (wl.length >= len) {
          const key = wl.slice(0, len).join(' ');
          prefixCounts[key] = (prefixCounts[key] || 0) + 1;
        }
      }
      for (const [p, count] of Object.entries(prefixCounts)) {
        if (count >= MIN_RENDERS) return p;
      }
    }
    return null;
  }

  // ── Public API ─────────────────────────────────────────────────────

  // Full fingerprint for payload annotation — always fast (LS read).
  function getSeriesContext() {
    return _getFingerprint();
  }

  // Advisory nudges — returns null if confidence < DETECT_GATE.
  function getNudges() {
    const fp = _getFingerprint();
    if (!fp || fp.confidence < DETECT_GATE) return null;
    const label = fp.title_prefix
      ? `Series: "${fp.title_prefix}"`
      : 'Series style active';
    if (fp.confidence >= DETECT_GATE && typeof addEvent === 'function') {
      // series_nudge fires when nudge context is first exposed this session
      // (guarded by caller to prevent per-render spam)
    }
    return {
      subtitle_style: fp.subtitle_style,
      cta_type:       fp.cta_type,
      platform:       fp.platform,
      render_profile: fp.render_profile,
      confidence:     fp.confidence,
      label,
    };
  }

  // Hint text for the steering panel element (cpSeriesHint).
  function getAppliedHint() {
    const nudges = getNudges();
    if (!nudges) return null;
    _log('series_nudge', nudges.label);
    return nudges.label;
  }

  // Short text for the output trust bar chip — null if below CHIP_GATE.
  function getAppliedChip() {
    const fp = _getFingerprint();
    if (!fp || fp.confidence < CHIP_GATE) return null;
    return fp.title_prefix ? `Series: ${fp.title_prefix}` : 'Series style';
  }

  // ── Logging ────────────────────────────────────────────────────────
  function _log(event, detail) {
    try {
      if (typeof addEvent === 'function') addEvent(`${event}: ${detail}`, 'render');
    } catch (_) {}
  }

  // ── Lifecycle ──────────────────────────────────────────────────────
  function init() {
    try {
      const state = _load();
      // Recompute fingerprint on init — evicts expired window items.
      state.fingerprint = _computeFingerprint(state.renders);
      _save(state);
    } catch (_) {}
  }

  function reset() {
    _save(_emptyState());
  }

  return {
    init,
    recordRender,
    recordReviewAction,
    getSeriesContext,
    getNudges,
    getAppliedHint,
    getAppliedChip,
    reset,
  };

})();
