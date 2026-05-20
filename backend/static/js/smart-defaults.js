// ── Smart Defaults (S1.1) ────────────────────────────────────────────────────
// Passive suggestion engine. Adds recommendation indicators to editor controls
// based on video content profile detected from title, duration, and dimensions.
//
// NEVER mutates form values automatically. Suggestions only. Creator owns all
// final settings. Module fails silently — every call site is guarded by typeof.

var SmartDefaults = (function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────────────────
  var _profile     = null;
  var _suggestions = {};
  var _dirty       = {};    // fields creator manually changed this session
  var _dismissed   = false; // strip dismissed for current video session
  var _listenersBound = false;

  // ── Profile strip copy ────────────────────────────────────────────────────
  var _STRIP_LABEL = {
    podcast_interview:     'Suggested for podcast content',
    talking_head_vertical: 'Suggested for short-form vertical content',
    screen_recording:      'Suggested for tutorial content',
  };

  // ── Profile detection ─────────────────────────────────────────────────────
  function _detectProfile(title, duration, sourceAspect, domain) {
    var t = String(title || '').toLowerCase();
    var score = { podcast_interview: 0, talking_head_vertical: 0, screen_recording: 0 };

    // podcast / interview
    if (duration > 600)                                                              score.podcast_interview += 30;
    if (sourceAspect > 1.3)                                                          score.podcast_interview += 20;
    if (/podcast|interview|ep\.\s*\d|\bepisode\b|\bguest\b|\bhost\b|\bconversation\b|\btalk\b/.test(t))
                                                                                     score.podcast_interview += 25;
    if (domain && domain.indexOf('youtube.com') !== -1)                              score.podcast_interview += 10;

    // talking head vertical
    if (sourceAspect < 0.85)                                                         score.talking_head_vertical += 40;
    if (domain && (domain.indexOf('tiktok.com') !== -1 || domain.indexOf('instagram.com') !== -1))
                                                                                     score.talking_head_vertical += 25;
    if (duration > 0 && duration < 120)                                              score.talking_head_vertical += 15;

    // screen recording / tutorial
    if (/how to|tutorial|\bguide\b|walkthrough|setup|install|\bdemo\b|overview/.test(t))
                                                                                     score.screen_recording += 35;
    if (sourceAspect > 1.5)                                                          score.screen_recording += 20;
    if (duration > 300)                                                              score.screen_recording += 10;

    var THRESHOLD = { podcast_interview: 40, talking_head_vertical: 40, screen_recording: 40 };
    var best = null, bestScore = 0;
    Object.keys(score).forEach(function (p) {
      if (score[p] >= THRESHOLD[p] && score[p] > bestScore) { bestScore = score[p]; best = p; }
    });
    return best || 'generic';
  }

  // ── Build suggestions for the 3 tracked fields ───────────────────────────
  function _buildSuggestions(profile) {
    if (profile === 'podcast_interview') return {
      aspect_ratio:   { selectId: 'evFrameRatioSelect', value: '9:16',            label: '9:16' },
      reframe_mode:   { selectId: 'evReframeSelect',    value: 'fast_center',     label: 'Center' },
      subtitle_style: { selectId: 'evSubStyle',         value: 'pro_karaoke',     label: 'Karaoke' },
    };
    if (profile === 'talking_head_vertical') return {
      aspect_ratio:   { selectId: 'evFrameRatioSelect', value: '9:16',            label: '9:16' },
      reframe_mode:   { selectId: 'evReframeSelect',    value: 'fast_center',     label: 'Center' },
      subtitle_style: { selectId: 'evSubStyle',         value: 'tiktok_bounce_v1',label: 'Viral' },
    };
    if (profile === 'screen_recording') return {
      aspect_ratio:   { selectId: 'evFrameRatioSelect', value: '16:9',            label: '16:9' },
      reframe_mode:   { selectId: 'evReframeSelect',    value: 'fast_center',     label: 'Center' },
      subtitle_style: { selectId: 'evSubStyle',         value: 'story_clean_01',  label: 'Clean' },
    };
    return {};
  }

  // ── DOM: profile strip ────────────────────────────────────────────────────
  function _renderStrip(profile) {
    _removeStrip();
    if (_dismissed || !_STRIP_LABEL[profile]) return;
    var anchor = document.getElementById('evSectionFrameRatio');
    if (!anchor || !anchor.parentNode) return;
    var strip = document.createElement('div');
    strip.id        = 'sdProfileStrip';
    strip.className = 'sd-strip';
    strip.innerHTML =
      '<span class="sd-strip-label">' + _STRIP_LABEL[profile] + '</span>' +
      '<button class="sd-dismiss" type="button" onclick="SmartDefaults._dismiss()" title="Dismiss">✕</button>';
    anchor.parentNode.insertBefore(strip, anchor);
  }

  function _removeStrip() {
    var el = document.getElementById('sdProfileStrip');
    if (el) el.remove();
  }

  // ── DOM: per-field chip + option marking ──────────────────────────────────
  var _SELECT_IDS = {
    aspect_ratio:   'evFrameRatioSelect',
    reframe_mode:   'evReframeSelect',
    subtitle_style: 'evSubStyle',
  };

  function _applyField(fieldId, sug) {
    if (_dirty[fieldId] || !sug) return;
    var sel = document.getElementById(sug.selectId);
    if (!sel) return;

    // Mark the suggested option
    Array.prototype.forEach.call(sel.options, function (opt) {
      opt.classList.toggle('sd-recommended', opt.value === sug.value);
    });

    // Chip: one per field, injected after the <select>
    if (document.getElementById('sdChip_' + fieldId)) return;
    var chip = document.createElement('span');
    chip.id        = 'sdChip_' + fieldId;
    chip.className = 'sd-chip';
    chip.textContent = 'Recommended: ' + sug.label;
    if (sel.nextSibling) sel.parentNode.insertBefore(chip, sel.nextSibling);
    else                 sel.parentNode.appendChild(chip);
  }

  function _clearField(fieldId) {
    var chip = document.getElementById('sdChip_' + fieldId);
    if (chip) chip.remove();
    var sel = document.getElementById(_SELECT_IDS[fieldId] || '');
    if (sel) Array.prototype.forEach.call(sel.options, function (opt) {
      opt.classList.remove('sd-recommended');
    });
  }

  function _clearAll() {
    Object.keys(_SELECT_IDS).forEach(_clearField);
  }

  function _renderSuggestions(suggestions) {
    if (_dismissed) return;
    Object.keys(suggestions).forEach(function (field) {
      if (!_dirty[field]) _applyField(field, suggestions[field]);
    });
  }

  // ── Dirty-flag listeners (bound once, on first video load) ────────────────
  function _bindListeners() {
    if (_listenersBound) return;
    _listenersBound = true;
    function _bind(selId, field) {
      var el = document.getElementById(selId);
      if (el) el.addEventListener('change', function () { markDirty(field); });
    }
    _bind('evFrameRatioSelect', 'aspect_ratio');
    _bind('evReframeSelect',    'reframe_mode');
    _bind('evSubStyle',         'subtitle_style');
  }

  // ── Public API ────────────────────────────────────────────────────────────

  function onVideoLoaded(ev, videoEl) {
    _bindListeners();

    var title    = '';
    var nameEl   = document.getElementById('evSourceName');
    if (nameEl) title = nameEl.textContent || '';

    var duration  = (ev && ev.duration)  || 0;
    var sourceUrl = (ev && ev.sourceUrl) || '';
    var domain    = '';
    try { domain = sourceUrl ? new URL(sourceUrl).hostname : ''; } catch (e) {}

    var sourceAspect = 1.78; // assume landscape if video dimensions unavailable
    if (videoEl && videoEl.videoWidth && videoEl.videoHeight) {
      sourceAspect = videoEl.videoWidth / videoEl.videoHeight;
    }

    _profile     = _detectProfile(title, duration, sourceAspect, domain);
    _suggestions = _buildSuggestions(_profile);

    if (_profile === 'generic') { _removeStrip(); _clearAll(); return; }

    _renderStrip(_profile);
    _renderSuggestions(_suggestions);
  }

  // Called when creator explicitly switches platform — re-evaluate active chips
  function onPlatformChanged(platform) {
    if (!_profile || _profile === 'generic') return;
    _renderSuggestions(_suggestions);
  }

  // Called after evApplyOutputPreset() — clear chips for fields the preset touched
  function onPresetApplied(fields) {
    if (!Array.isArray(fields)) return;
    var MAP = { 'reframe mode': 'reframe_mode', 'subtitle style': 'subtitle_style' };
    fields.forEach(function (f) {
      var field = MAP[f];
      if (field) { _dirty[field] = true; _clearField(field); }
    });
  }

  // Called from select change listeners when creator picks an option manually
  function markDirty(fieldId) {
    _dirty[fieldId] = true;
    _clearField(fieldId);
  }

  // Called at the top of _evLoadVideo() — clears previous video's state
  function reset() {
    _profile     = null;
    _suggestions = {};
    _dirty       = {};
    _dismissed   = false;
    _removeStrip();
    _clearAll();
  }

  // Strip dismiss button handler — hides all suggestions for current session
  function _dismiss() {
    _dismissed = true;
    _removeStrip();
    _clearAll();
  }

  return {
    onVideoLoaded:    onVideoLoaded,
    onPlatformChanged: onPlatformChanged,
    onPresetApplied:  onPresetApplied,
    markDirty:        markDirty,
    reset:            reset,
    _dismiss:         _dismiss,
  };
}());
