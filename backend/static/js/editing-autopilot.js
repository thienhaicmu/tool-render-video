// ── Editing Autopilot (S1.4A) ────────────────────────────────────────────────
// AI ownership layer for advanced editing fields.
// Shows "AI: <value>" on owned fields; switches to "Manual: <value>" when creator
// changes a field. NEVER mutates form values. Suggestion layer only.
//
// Activated by SmartDefaults after profile detection. Fails silently.
// Guard all call sites: if (typeof EditingAutopilot !== 'undefined')

var EditingAutopilot = (function () {
  'use strict';

  // ── Visible fields under AI ownership ────────────────────────────────────
  var _OWNED_FIELDS = {
    reframe_mode:   'evReframeSelect',
    subtitle_style: 'evSubStyle',
  };

  // ── Internal bias hints (never written to DOM fields) ─────────────────────
  var _PROFILE_BIAS = {
    podcast_interview: {
      duration:         { min_s: 20, max_s: 45 },
      structure:        'hook_context_payoff',
      subtitle_density: 'medium',
      speed:            'normal',
    },
    talking_head_vertical: {
      duration:         { min_s: 15, max_s: 30 },
      structure:        'hook_insight_reaction',
      subtitle_density: 'high',
      speed:            'normal',
    },
    screen_recording: {
      duration:         { min_s: 30, max_s: 90 },
      structure:        'problem_steps_result',
      subtitle_density: 'low',
      speed:            'normal',
    },
  };

  // ── AI field recommendations per profile (value = suggestion, never forced) ─
  // 16:9 source → center reframe; vertical/square source → auto reframe.
  // Subtitle styles align with SmartDefaults content-profile choices.
  var _PROFILE_RECS = {
    podcast_interview: {
      reframe_mode:   { selectId: 'evReframeSelect', value: 'center' },
      subtitle_style: { selectId: 'evSubStyle',      value: 'pro_karaoke' },
    },
    talking_head_vertical: {
      reframe_mode:   { selectId: 'evReframeSelect', value: 'auto' },
      subtitle_style: { selectId: 'evSubStyle',      value: 'tiktok_bounce_v1' },
    },
    screen_recording: {
      reframe_mode:   { selectId: 'evReframeSelect', value: 'center' },
      subtitle_style: { selectId: 'evSubStyle',      value: 'story_clean_01' },
    },
  };

  // ── Human-friendly value labels (FIX 1 + FIX 2) ─────────────────────────
  var _FRIENDLY_LABEL = {
    'center':           'Center',
    'auto':             'Auto',
    'fast_center':      'Center',
    'pro_karaoke':      'Karaoke',
    'tiktok_bounce_v1': 'TikTok',
    'story_clean_01':   'Clean',
  };

  // ── State ─────────────────────────────────────────────────────────────────
  var _profile        = null;
  var _ownership      = {};   // fieldId → 'ai' | 'manual' | 'dismissed'
  var _overrideCount  = {};   // FIX 3: counts manual changes per field this session
  var _biases         = {};
  var _listenersBound = false;

  // ── DOM: per-field chip ───────────────────────────────────────────────────
  function _renderChip(fieldId, state) {
    var existing = document.getElementById('apChip_' + fieldId);
    if (existing) existing.remove();

    // AP takes ownership — remove any SmartDefaults chip for the same field
    var sdChip = document.getElementById('sdChip_' + fieldId);
    if (sdChip) sdChip.remove();

    var selId = _OWNED_FIELDS[fieldId];
    if (!selId) return;
    var sel = document.getElementById(selId);
    if (!sel) return;
    var labelWrap      = sel.closest('label');
    var fieldLabelSpan = labelWrap ? labelWrap.querySelector('.fieldLabel') : null;
    if (!fieldLabelSpan) return;

    var chipText;
    if (state === 'manual') {
      // FIX 2: show what value the creator actually selected
      var curVal = _FRIENDLY_LABEL[sel.value] || sel.value;
      chipText = 'Manual: ' + curVal;
    } else {
      // FIX 1: show what the AI specifically recommends, not "AI Managed"
      var rec    = _PROFILE_RECS[_profile] && _PROFILE_RECS[_profile][fieldId];
      var recVal = _FRIENDLY_LABEL[rec ? rec.value : ''] || '';
      chipText   = recVal ? 'AI: ' + recVal : 'AI';
    }

    var chip = document.createElement('span');
    chip.id        = 'apChip_' + fieldId;
    chip.className = state === 'manual' ? 'ap-chip ap-manual' : 'ap-chip ap-managed';
    chip.textContent = chipText;
    fieldLabelSpan.classList.add('sd-label-row');
    fieldLabelSpan.appendChild(chip);
  }

  function _clearChip(fieldId) {
    var chip = document.getElementById('apChip_' + fieldId);
    if (chip) chip.remove();
  }

  function _clearAll() { Object.keys(_OWNED_FIELDS).forEach(_clearChip); }

  // ── Dirty-flag listeners (bound once on first video load) ─────────────────
  function _bindListeners() {
    if (_listenersBound) return;
    _listenersBound = true;
    Object.keys(_OWNED_FIELDS).forEach(function (fieldId) {
      var el = document.getElementById(_OWNED_FIELDS[fieldId]);
      if (el) el.addEventListener('change', function () { markManual(fieldId); });
    });
  }

  // ── Public API ────────────────────────────────────────────────────────────

  // Called by SmartDefaults after profile detection (passes detected profile string)
  function onVideoLoaded(profile) {
    _bindListeners();
    _profile   = profile || 'generic';
    _ownership = {};
    _biases    = _PROFILE_BIAS[_profile] || {};

    if (!_PROFILE_RECS[_profile]) { _clearAll(); return; }

    Object.keys(_OWNED_FIELDS).forEach(function (fieldId) {
      _ownership[fieldId] = 'ai';
      _renderChip(fieldId, 'ai');
    });
  }

  // Called when creator explicitly changes an owned field
  function markManual(fieldId) {
    if (!_profile || !_ownership[fieldId] || _ownership[fieldId] === 'dismissed') return;
    _overrideCount[fieldId] = (_overrideCount[fieldId] || 0) + 1;
    // FIX 3: 2+ overrides = AI stops suggesting for this field this session
    if (_overrideCount[fieldId] >= 2) {
      _ownership[fieldId] = 'dismissed';
      _clearChip(fieldId);
      return;
    }
    _ownership[fieldId] = 'manual';
    _renderChip(fieldId, 'manual');
  }

  // Called after evApplyOutputPreset() — preset counts as manual for owned fields
  function onPresetApplied(fields) {
    if (!Array.isArray(fields)) return;
    var MAP = { 'reframe mode': 'reframe_mode', 'subtitle style': 'subtitle_style' };
    fields.forEach(function (f) {
      var field = MAP[f];
      if (field) markManual(field);
    });
  }

  // Used by SmartDefaults._applyField to avoid double-chips on owned fields
  function isActive(fieldId) {
    return !!(_profile && _PROFILE_RECS[_profile] && _ownership[fieldId] && _ownership[fieldId] !== 'dismissed');
  }

  // Internal bias hints for ranking/scoring consumers (read-only)
  function getBiases()          { return _biases; }
  function getRecommendations() { return (_profile && _PROFILE_RECS[_profile]) ? _PROFILE_RECS[_profile] : {}; }

  // Called at top of _evLoadVideo() — clears all previous session state
  function reset() {
    _profile       = null;
    _ownership     = {};
    _overrideCount = {};
    _biases        = {};
    _clearAll();
  }

  return {
    onVideoLoaded:    onVideoLoaded,
    markManual:       markManual,
    onPresetApplied:  onPresetApplied,
    isActive:         isActive,
    getBiases:        getBiases,
    getRecommendations: getRecommendations,
    reset:            reset,
  };
}());
