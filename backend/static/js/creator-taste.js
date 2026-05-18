/* =========================================================
   creator-taste.js — UP12: Creator Taste Memory
   Tracks real render choices (subtitle style, clip download rank)
   using EMA decay. No ML. No embeddings. No cloud sync.
   Preferences are gently applied as form defaults — creator
   can always override. Manual choice wins.
   ========================================================= */
'use strict';

window.CreatorTaste = (() => {

  const LS_KEY     = 'ct_taste_v1';
  const EMA_ALPHA  = 0.85;  // decay per recorded session (~15 sessions to forget)
  const MIN_SESS   = 3;     // renders before any preference activates
  const MIN_SCORE  = 1.5;   // EMA score threshold (≈ 2 consistent recent choices)
  const PREF_RATIO = 1.5;   // top must beat second by this factor (clear preference, not noise)

  const SUBTITLE_LABELS = {
    'pro_karaoke':       'Karaoke',
    'tiktok_bounce_v1':  'TikTok Bounce',
    'story_clean_01':    'Clean',
    'viral_bold':        'Viral Bold',
    'clean_karaoke':     'Karaoke',
    'gaming_style':      'Gaming',
    'minimal_clean':     'Minimal',
    'split_line':        'Split Line',
  };

  // ── Storage ────────────────────────────────────────────────
  function _empty() {
    return {
      subtitle: {},                                 // style → EMA count
      download_rank: { rank_1: 0, rank_other: 0 }, // rank_1 vs rank_other exports
      sessions: 0,                                  // total renders recorded
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
    try { localStorage.setItem(LS_KEY, JSON.stringify(_data)); } catch (_) {}
  }

  // ── EMA helpers ───────────────────────────────────────────
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

  // ── Public: record signals ────────────────────────────────
  function recordSubtitleStyle(style) {
    if (!style || typeof style !== 'string') return;
    _emaRecord(_data.subtitle, style);
    _data.sessions = (_data.sessions || 0) + 1;
    _save();
    _syncHint();
  }

  function recordDownload(rank) {
    const n = Number(rank) || 0;
    if (n < 1) return;
    _emaRecord(_data.download_rank, n === 1 ? 'rank_1' : 'rank_other');
    _save();
  }

  // ── Public: read preferences ──────────────────────────────
  function getSubtitleStyleHint() {
    if ((_data.sessions || 0) < MIN_SESS) return null;
    const style = _topKey(_data.subtitle);
    if (!style) return null;
    return { style, label: SUBTITLE_LABELS[style] || style, confident: true };
  }

  function getPreferences() {
    return {
      subtitleStyle:          getSubtitleStyleHint(),
      prefersAlternativeClip: _topKey(_data.download_rank) === 'rank_other',
      sessions:               _data.sessions || 0,
    };
  }

  // ── UI: hint element ──────────────────────────────────────
  function _ensureHintEl() {
    if (document.getElementById('ctSubtitleHint')) return;
    const sel = document.getElementById('evSubStyle');
    if (!sel) return;
    const span = document.createElement('span');
    span.id = 'ctSubtitleHint';
    span.style.cssText = 'display:none;font-size:11px;color:#888;margin-left:6px;font-style:italic;vertical-align:middle;';
    sel.parentNode.insertBefore(span, sel.nextSibling);
    sel.addEventListener('change', function () {
      sel.dataset.ctManual = '1';
      span.style.display = 'none';
    });
  }

  function _syncHint() {
    const hint   = getSubtitleStyleHint();
    const hintEl = document.getElementById('ctSubtitleHint');
    const sel    = document.getElementById('evSubStyle');
    if (!hint) {
      if (hintEl) hintEl.style.display = 'none';
      return;
    }
    if (sel && !sel.dataset.ctManual) {
      sel.value = hint.style;
    }
    if (hintEl) {
      hintEl.textContent = 'Using ' + hint.label + ' (recent preference)';
      hintEl.style.display = 'inline';
    }
  }

  // ── Public: lifecycle ─────────────────────────────────────
  function init() {
    _data = _load();
    // Reset per-session manual flag — new editor open = fresh preference application
    const sel = document.getElementById('evSubStyle');
    if (sel) delete sel.dataset.ctManual;
    _ensureHintEl();
    _syncHint();
  }

  function reset() {
    _data = _empty();
    _save();
    const hintEl = document.getElementById('ctSubtitleHint');
    if (hintEl) hintEl.style.display = 'none';
  }

  return { init, recordSubtitleStyle, recordDownload, getSubtitleStyleHint, getPreferences, reset };

})();
