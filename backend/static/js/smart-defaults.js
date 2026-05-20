// ── Smart Defaults (S1.5) ────────────────────────────────────────────────────
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
  var _dismissed   = false; // strip dismissed (chips remain, reset on new video)
  var _chipTone    = 'Suggested'; // 'Recommended' (strong match) or 'Suggested' (weak)
  var _listenersBound = false;
  var _apRafToken  = null;       // S1.4A: coalescing guard for Autopilot rAF

  // ── Profile strip copy (FIX 2) ────────────────────────────────────────────
  var _STRIP_LABEL = {
    podcast_interview:     'Optimized for podcast clips',
    talking_head_vertical: 'Optimized for short-form video',
    screen_recording:      'Optimized for tutorials',
  };

  // ── Profile detection ─────────────────────────────────────────────────────
  // Returns { profile, score, secondScore } — score and secondScore are internal.
  // FIX 5: score details NEVER reach the UI. Only profile string is used externally.
  // FIX 2: each profile requires >= 2 distinct signal sources (keyword, duration,
  //         aspect, domain). Keyword-only fires are blocked.
  function _detectProfile(title, duration, sourceAspect, domain) {
    var t       = String(title || '').toLowerCase();
    var score   = { podcast_interview: 0, talking_head_vertical: 0, screen_recording: 0 };
    var sources = { podcast_interview: 0, talking_head_vertical: 0, screen_recording: 0 };

    // podcast / interview
    if (duration > 600)                { score.podcast_interview += 30; sources.podcast_interview++; }
    if (sourceAspect > 1.3)            { score.podcast_interview += 20; sources.podcast_interview++; }
    if (/podcast|interview|ep\.\s*\d|\bepisode\b|\bguest\b|\bhost\b|\bconversation\b|\btalk\b/.test(t))
                                       { score.podcast_interview += 25; sources.podcast_interview++; }
    if (domain && domain.indexOf('youtube.com') !== -1)
                                       { score.podcast_interview += 10; sources.podcast_interview++; }

    // talking head vertical
    if (sourceAspect < 0.85)           { score.talking_head_vertical += 40; sources.talking_head_vertical++; }
    if (domain && (domain.indexOf('tiktok.com') !== -1 || domain.indexOf('instagram.com') !== -1))
                                       { score.talking_head_vertical += 25; sources.talking_head_vertical++; }
    if (duration > 0 && duration < 120){ score.talking_head_vertical += 15; sources.talking_head_vertical++; }

    // screen recording / tutorial
    if (/how to|tutorial|\bguide\b|walkthrough|setup|install|\bdemo\b|overview/.test(t))
                                       { score.screen_recording += 35; sources.screen_recording++; }
    if (sourceAspect > 1.5)            { score.screen_recording += 20; sources.screen_recording++; }
    if (duration > 300)                { score.screen_recording += 10; sources.screen_recording++; }

    var THRESHOLD = { podcast_interview: 40, talking_head_vertical: 40, screen_recording: 40 };

    // Collect qualifying profiles: must meet threshold AND have >= 2 signal sources
    var qualified = [];
    Object.keys(score).forEach(function (p) {
      if (sources[p] >= 2 && score[p] >= THRESHOLD[p]) qualified.push({ profile: p, score: score[p] });
    });
    qualified.sort(function (a, b) { return b.score - a.score; });

    if (qualified.length === 0) return { profile: 'generic', score: 0, secondScore: 0 };
    return {
      profile:     qualified[0].profile,
      score:       qualified[0].score,
      secondScore: qualified[1] ? qualified[1].score : 0,
    };
  }

  // ── Build suggestions for the 3 tracked fields ───────────────────────────
  function _buildSuggestions(profile) {
    if (profile === 'podcast_interview') return {
      aspect_ratio:   { selectId: 'evFrameRatioSelect', value: '9:16' },
      reframe_mode:   { selectId: 'evReframeSelect',    value: 'fast_center' },
      subtitle_style: { selectId: 'evSubStyle',         value: 'pro_karaoke' },
    };
    if (profile === 'talking_head_vertical') return {
      aspect_ratio:   { selectId: 'evFrameRatioSelect', value: '9:16' },
      reframe_mode:   { selectId: 'evReframeSelect',    value: 'fast_center' },
      subtitle_style: { selectId: 'evSubStyle',         value: 'tiktok_bounce_v1' },
    };
    if (profile === 'screen_recording') return {
      aspect_ratio:   { selectId: 'evFrameRatioSelect', value: '16:9' },
      reframe_mode:   { selectId: 'evReframeSelect',    value: 'fast_center' },
      subtitle_style: { selectId: 'evSubStyle',         value: 'story_clean_01' },
    };
    return {};
  }

  // ── DNA suggestions ───────────────────────────────────────────────────────
  // Maps CreatorDNA dimensions to field suggestions (S1.3A).
  // One signal → one field. No cross-field bleed.
  // Returns {} when DNA is not confident (< 10 action sessions).
  function _buildDNASuggestions(dnaCtx) {
    var dna = {};
    if (!dnaCtx || !dnaCtx.confident) return dna;
    // hook_forward → caption style only (not video style)
    if (dnaCtx.hook_forward >= 0.5) {
      dna.subtitle_style = { selectId: 'evSubStyle',         value: 'tiktok_bounce_v1', tone: 'Usually used' };
    }
    // clean_visual → video style only (not subtitle style)
    if (dnaCtx.clean_visual >= 0.67) {
      dna.video_style    = { selectId: 'evVideoStyleSelect', value: 'balanced',          tone: 'Usually used' };
    }
    return dna;
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

  // ── DOM: per-field chip in field label row ────────────────────────────────
  // Chip text is _chipTone ('Recommended' or 'Suggested') — set per session
  // based on overall profile confidence score. No score shown to creator.
  var _SELECT_IDS = {
    aspect_ratio:   'evFrameRatioSelect',
    reframe_mode:   'evReframeSelect',
    subtitle_style: 'evSubStyle',
    video_style:    'evVideoStyleSelect',
  };

  function _applyField(fieldId, sug) {
    if (_dirty[fieldId] || !sug) return;
    // S1.4: defer to EditingAutopilot for its owned fields
    if (typeof EditingAutopilot !== 'undefined' && EditingAutopilot.isActive(fieldId)) return;
    var sel = document.getElementById(sug.selectId);
    if (!sel) return;

    if (document.getElementById('sdChip_' + fieldId)) return; // already rendered

    var labelWrap      = sel.closest('label');
    var fieldLabelSpan = labelWrap ? labelWrap.querySelector('.fieldLabel') : null;
    if (!fieldLabelSpan) return;

    var chip = document.createElement('span');
    chip.id        = 'sdChip_' + fieldId;
    chip.className = 'sd-chip';
    chip.textContent = sug.tone || _chipTone;

    fieldLabelSpan.classList.add('sd-label-row');
    fieldLabelSpan.appendChild(chip);
  }

  function _clearField(fieldId) {
    var chip = document.getElementById('sdChip_' + fieldId);
    if (chip) {
      var parent = chip.parentElement;
      if (parent) parent.classList.remove('sd-label-row');
      chip.remove();
    }
  }

  function _clearAll() {
    Object.keys(_SELECT_IDS).forEach(_clearField);
  }

  // Chips are independent of strip dismiss state — no _dismissed guard here.
  function _renderSuggestions(suggestions) {
    Object.keys(suggestions).forEach(function (field) {
      if (!_dirty[field]) _applyField(field, suggestions[field]);
    });
  }

  // ── Dirty-flag listeners (bound once on first video load) ─────────────────
  function _bindListeners() {
    if (_listenersBound) return;
    _listenersBound = true;
    function _bind(selId, field) {
      var el = document.getElementById(selId);
      if (el) el.addEventListener('change', function () { markDirty(field); });
    }
    _bind('evFrameRatioSelect',  'aspect_ratio');
    _bind('evReframeSelect',     'reframe_mode');
    _bind('evSubStyle',          'subtitle_style');
    _bind('evVideoStyleSelect',  'video_style');
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

    var sourceAspect = 1.78;
    if (videoEl && videoEl.videoWidth && videoEl.videoHeight) {
      sourceAspect = videoEl.videoWidth / videoEl.videoHeight;
    }

    var result = _detectProfile(title, duration, sourceAspect, domain);
    _profile   = result.profile;

    // FIX 1+4: mixed-signal suppression — when top two profiles are within 15 pts,
    // confidence is unreliable. Degrade Recommended→Suggested or treat as generic.
    if (_profile !== 'generic') {
      var delta = result.score - result.secondScore;
      if (delta < 15) {
        if (result.score >= 65) {
          _chipTone = 'Suggested';   // degrade: strong score but contested
        } else {
          _profile = 'generic';      // low confidence + contested = show nothing
        }
      } else {
        _chipTone = result.score >= 65 ? 'Recommended' : 'Suggested';
      }
    }

    _suggestions = _buildSuggestions(_profile);

    // S1.3: DNA overlay — DNA wins over content profile for same fields
    if (window.CreatorDNA) {
      try {
        var dnaSug = _buildDNASuggestions(CreatorDNA.getDNAContext());
        Object.keys(dnaSug).forEach(function (field) { _suggestions[field] = dnaSug[field]; });
      } catch (e) {}
    }

    // FIX 4: generic safe mode — show nothing when confidence is insufficient
    if (_profile === 'generic' && Object.keys(_suggestions).length === 0) {
      _removeStrip(); _clearAll(); return;
    }

    if (_profile !== 'generic') _renderStrip(_profile);
    _renderSuggestions(_suggestions);

    // S1.4: Autopilot takes ownership of advanced fields after SD renders.
    // S1.4A: cancelAnimationFrame guard ensures only the latest call fires.
    if (typeof EditingAutopilot !== 'undefined') {
      if (_apRafToken) cancelAnimationFrame(_apRafToken);
      _apRafToken = requestAnimationFrame(function () {
        _apRafToken = null;
        EditingAutopilot.onVideoLoaded(_profile);
      });
    }
  }

  // Called when creator explicitly switches platform — re-evaluate active chips
  function onPlatformChanged(platform) {
    if (!_profile || _profile === 'generic') return;
    _renderSuggestions(_suggestions);
  }

  // Called after evApplyOutputPreset() — clear chips for fields preset touched
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

  // Called at the top of _evLoadVideo() — clears all previous video state
  function reset() {
    if (_apRafToken) { cancelAnimationFrame(_apRafToken); _apRafToken = null; }
    _profile     = null;
    _suggestions = {};
    _dirty       = {};
    _dismissed   = false; // FIX 4: new video always starts fresh
    _chipTone    = 'Suggested';
    _removeStrip();
    _clearAll();
  }

  // FIX 4+5: dismiss ONLY hides the strip for this video session.
  // Chips remain. Tabs changes cannot restore strip (_dismissed persists until reset).
  function _dismiss() {
    _dismissed = true;
    _removeStrip();
  }

  return {
    onVideoLoaded:     onVideoLoaded,
    onPlatformChanged: onPlatformChanged,
    onPresetApplied:   onPresetApplied,
    markDirty:         markDirty,
    reset:             reset,
    _dismiss:          _dismiss,
  };
}());
