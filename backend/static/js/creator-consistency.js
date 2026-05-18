/* =========================================================
   creator-consistency.js — UP34: Quality Consistency
   Reads approved clips (kept + favorited) from review queue.
   Derives a quality baseline: which subtitle style and
   structure bias the creator has consistently approved.
   Publishes consistency nudges — advisory only, never forced.

   Drift audit (STEP 0) root causes addressed:
     - subtitle_style has no feedback loop from review approvals
     - structure_bias defaults to "balanced" on each new session
     - variant personality drifts when base subtitle drifts
     - cover frame vibe varies because structure_bias anchor drifts

   Philosophy:
     - Reads review_queue_v1 + creator_series_v1 directly.
     - No new storage. No cloud. No ML.
     - Advisory only. Creator always wins.
     - Silent when not enough approved items (< MIN_APPROVED).

   Signal hierarchy (advisory order, not enforcement):
     manual > preset > series > consistency > DNA > platform > default
   ========================================================= */
'use strict';

window.CreatorConsistency = (() => {

  const MIN_APPROVED  = 2;     // minimum kept/favorited items to attempt detection
  const DETECT_GATE   = 0.35;  // confidence floor: hint + chip fire in steering panel
  const CHIP_GATE     = 0.55;  // confidence floor: trust bar chip fires

  let _cachedProfile = null;   // in-memory cache, cleared on init()

  // ── Storage readers ────────────────────────────────────────────────
  function _loadQueue() {
    try { return JSON.parse(localStorage.getItem('review_queue_v1') || '[]'); } catch (_) { return []; }
  }

  function _loadFingerprint() {
    try {
      const d = JSON.parse(localStorage.getItem('creator_series_v1') || '{}');
      return (d && d.fingerprint) ? d.fingerprint : null;
    } catch (_) { return null; }
  }

  // ── Dominant value: most frequent non-null value in an array ───────
  function _dominant(arr) {
    const counts = {};
    arr.forEach(v => { if (v) counts[v] = (counts[v] || 0) + 1; });
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return entries.length ? entries[0] : null;   // [value, count] or null
  }

  // ── Compute consistency profile from approved clips ────────────────
  function _computeProfile() {
    const items    = _loadQueue();
    const approved = items.filter(it =>
      (it.state === 'kept' || it.state === 'favorited') && it.payload
    );

    if (approved.length < MIN_APPROVED) {
      _cachedProfile = null;
      return null;
    }

    // Extract style dimensions from approved items' stored payloads
    const subtitleStyles  = approved.map(it => (it.payload.subtitle_style || '').trim()).filter(Boolean);
    const structureBiases = approved.map(it => (it.payload.structure_bias || '').trim()).filter(Boolean);

    const topSub = _dominant(subtitleStyles);   // [style, count] or null
    const topStr = _dominant(structureBiases);  // [bias, count] or null

    // Approval confidence: fraction of approved items with the dominant value
    const subConf = (topSub && subtitleStyles.length >= MIN_APPROVED)
      ? topSub[1] / subtitleStyles.length
      : 0;
    const strConf = (topStr && structureBiases.length >= MIN_APPROVED)
      ? topStr[1] / structureBiases.length
      : 0;

    // Cross-validate subtitle against series fingerprint:
    //  +10% when series fingerprint agrees (double evidence)
    //  -10% when it disagrees (conflicting signals)
    const fp = _loadFingerprint();
    let subFinal = subConf;
    if (fp && fp.subtitle_style && topSub) {
      subFinal = fp.subtitle_style === topSub[0]
        ? Math.min(1.0, subConf + 0.1)
        : Math.max(0.0, subConf - 0.1);
    }

    const confidence = Math.min(1.0, Math.round(((subFinal + strConf) / 2) * 100) / 100);

    const profile = {
      subtitle_style:  topSub  ? topSub[0]  : null,
      structure_bias:  topStr  ? topStr[0]  : null,
      confidence,
      approved_count:  approved.length,
    };
    _cachedProfile = profile;
    return profile;
  }

  function _getProfile() {
    return _cachedProfile !== undefined ? _cachedProfile : _computeProfile();
  }

  // ── Style label for display ────────────────────────────────────────
  function _styleLabel(style) {
    const LABELS = {
      'pro_karaoke':       'karaoke',
      'tiktok_bounce_v1':  'viral',
      'story_clean_01':    'clean',
      'bold_cap':          'bold cap',
      'boxed_caption':     'boxed',
    };
    return LABELS[style] || style;
  }

  function _biasLabel(bias) {
    const LABELS = { 'hook': 'hook-forward', 'story': 'story-first', 'balanced': 'balanced' };
    return LABELS[bias] || bias;
  }

  // ── Public: hint text for steering panel (cpConsistencyHint) ──────
  function getAppliedHint() {
    const p = _getProfile();
    if (!p) return null;

    if (p.confidence < DETECT_GATE) {
      if (p.confidence > 0) {
        _log('consistency_suppressed',
          `below gate (${Math.round(p.confidence * 100)}% < ${Math.round(DETECT_GATE * 100)}%)`);
      }
      return null;
    }

    const parts = [];
    if (p.subtitle_style) {
      parts.push(`subtitle: ${_styleLabel(p.subtitle_style)}`);
      _log('subtitle_consistency', p.subtitle_style);
    }
    if (p.structure_bias && p.structure_bias !== 'balanced') {
      parts.push(`energy: ${_biasLabel(p.structure_bias)}`);
      _log('hook_consistency', p.structure_bias);
    }
    if (!parts.length) return null;

    const hint = `Style baseline: ${parts.join(' · ')}`;
    _log('consistency_nudge', hint);

    // Cover vibe and variant consistency logs
    const currentSb = (document.getElementById('qsStructureBias')?.value || '').trim();
    if (currentSb && p.structure_bias) {
      _log('cover_consistency', currentSb === p.structure_bias ? 'aligned' : 'drift');
    }
    const currentSub = (document.getElementById('evSubStyle')?.value || '').trim();
    if (currentSub && p.subtitle_style) {
      _log('variant_consistency', currentSub === p.subtitle_style ? 'aligned' : 'drift');
    }

    return hint;
  }

  // ── Public: trust bar chip (when confidence >= CHIP_GATE) ─────────
  function getAppliedChip() {
    const p = _getProfile();
    if (!p || p.confidence < CHIP_GATE) return null;
    return p.approved_count >= 5 ? 'Consistent creator style' : 'Style consistent';
  }

  // ── Public: payload annotation ─────────────────────────────────────
  function getConsistencyContext() {
    const p = _getProfile();
    return p
      ? { subtitle_style: p.subtitle_style, structure_bias: p.structure_bias,
          confidence: p.confidence, approved_count: p.approved_count }
      : { subtitle_style: null, structure_bias: null, confidence: 0, approved_count: 0 };
  }

  // ── Logging ────────────────────────────────────────────────────────
  function _log(event, detail) {
    try {
      const msg = detail ? `${event}: ${detail}` : event;
      if (typeof addEvent === 'function') addEvent(msg, 'render');
    } catch (_) {}
  }

  // ── Lifecycle ──────────────────────────────────────────────────────
  function init() {
    _cachedProfile = undefined;   // clear cache — recomputed on next getAppliedHint() call
    _computeProfile();            // warm cache immediately
  }

  return {
    init,
    getAppliedHint,
    getAppliedChip,
    getConsistencyContext,
  };

})();
