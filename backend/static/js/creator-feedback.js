/* =========================================================
   creator-feedback.js — UP18: Creator Feedback Learning
   Tracks real creator outcomes: which variant they download,
   which platform they repeatedly choose.
   EMA decay α=0.85. No ML. No cloud sync. Local only.

   Hierarchy: manual > taste (UP12) > feedback (UP18) > platform > default
   Creator explicit action always overrides a learned hint.
   ========================================================= */
'use strict';

window.CreatorFeedback = (() => {

  const LS_KEY     = 'cl_feedback_v1';
  const EMA_ALPHA  = 0.85;  // same decay as UP12 (~15 sessions to forget)
  const MIN_SESS   = 3;     // minimum platform choices before platform hint activates
  const MIN_SCORE  = 1.5;   // EMA score threshold (≈ 2 consistent recent choices)
  const PREF_RATIO = 1.5;   // top must beat second by this factor to surface as preference

  const VARIANT_LABELS = {
    aggressive:  'Aggressive',
    balanced:    'Balanced',
    story_first: 'Story-first',
  };

  const PLATFORM_LABELS = {
    tiktok:          'TikTok',
    youtube_shorts:  'YouTube Shorts',
    instagram_reels: 'Instagram Reels',
  };

  // ── Storage ────────────────────────────────────────────
  function _empty() {
    return {
      variants:  {},   // variant_type → EMA count (from downloads)
      platforms: {},   // platform key → EMA count (from render submits)
      sessions:  0,    // total render submits recorded
    };
  }

  let _data = _empty();

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) return Object.assign(_empty(), JSON.parse(raw));
    } catch (_) {}
    return _empty();
  }

  function _save() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(_data)); } catch (_) { console.warn('[preference:feedback] localStorage write failed'); }
  }

  // ── EMA helpers (identical pattern to UP12) ───────────
  function _emaRecord(obj, key) {
    for (const k in obj) obj[k] = (obj[k] || 0) * EMA_ALPHA;
    obj[key] = (obj[key] || 0) + 1.0;
  }

  function _topKey(obj) {
    const entries = Object.entries(obj).filter(([, v]) => v > 0);
    if (!entries.length) return null;
    entries.sort((a, b) => b[1] - a[1]);
    const topScore = entries[0][1];
    if (topScore < MIN_SCORE) return null;
    if (entries.length > 1 && topScore < entries[1][1] * PREF_RATIO) return null;
    return entries[0][0];
  }

  // ── Public: record signals ────────────────────────────
  function recordVariantDownload(variantType) {
    // Called when creator clicks Download on a multi-variant clip card.
    if (!variantType || typeof variantType !== 'string') return;
    _emaRecord(_data.variants, variantType);
    _save();
  }

  function recordPlatformChoice(platform) {
    // Called at every render submit — records which platform the creator chose.
    if (!platform || typeof platform !== 'string') return;
    _emaRecord(_data.platforms, platform);
    _data.sessions = (_data.sessions || 0) + 1;
    _save();
    _syncPlatformHint();
  }

  // ── Public: read preferences ──────────────────────────
  function getVariantPreference() {
    // Gated by EMA score only — no session minimum (variant fires on download, not per render).
    const v = _topKey(_data.variants);
    if (!v) return null;
    return { variant: v, label: VARIANT_LABELS[v] || v, confident: true };
  }

  function getPlatformPreference() {
    // Gated by session count — same approach as UP12 subtitle preference.
    if ((_data.sessions || 0) < MIN_SESS) return null;
    const p = _topKey(_data.platforms);
    if (!p) return null;
    return { platform: p, label: PLATFORM_LABELS[p] || p, confident: true };
  }

  function getPreferences() {
    return {
      variantPreference:  getVariantPreference(),
      platformPreference: getPlatformPreference(),
      sessions:           _data.sessions || 0,
    };
  }

  // ── UI: platform hint element ─────────────────────────
  function _ensurePlatformHintEl() {
    if (document.getElementById('cfPlatformHint')) return;
    const sel = document.getElementById('evTargetPlatform');
    if (!sel) return;
    const span = document.createElement('span');
    span.id = 'cfPlatformHint';
    span.style.cssText = 'display:none;font-size:11px;color:#888;margin-left:6px;font-style:italic;vertical-align:middle;';
    sel.parentNode.insertBefore(span, sel.nextSibling);
    sel.addEventListener('change', function () {
      sel.dataset.cfManual = '1';
      span.style.display = 'none';
    });
  }

  function _syncPlatformHint() {
    const hint   = getPlatformPreference();
    const hintEl = document.getElementById('cfPlatformHint');
    const sel    = document.getElementById('evTargetPlatform');
    if (!hint) {
      if (hintEl) hintEl.style.display = 'none';
      return;
    }
    if (sel && !sel.dataset.cfManual) {
      sel.value = hint.platform;
    }
    if (hintEl) {
      hintEl.textContent = 'Using ' + hint.label + ' (recent preference)';
      hintEl.style.display = 'inline';
    }
  }

  // ── Public: lifecycle ─────────────────────────────────
  function init() {
    _data = _load();
    // Reset per-session manual flag — new editor open = fresh preference application.
    const sel = document.getElementById('evTargetPlatform');
    if (sel) delete sel.dataset.cfManual;
    _ensurePlatformHintEl();
    _syncPlatformHint();
  }

  function reset() {
    _data = _empty();
    _save();
    const hintEl = document.getElementById('cfPlatformHint');
    if (hintEl) hintEl.style.display = 'none';
  }

  return {
    init,
    recordVariantDownload,
    recordPlatformChoice,
    getVariantPreference,
    getPlatformPreference,
    getPreferences,
    reset,
  };

})();
