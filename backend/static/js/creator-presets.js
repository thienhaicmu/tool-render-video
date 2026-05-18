/* =========================================================
   creator-presets.js — UP21: Creator Style Presets
   Save and apply render configuration bundles.
   Local-only. No backend. No sync. No cloud.

   Covers: platform, variant mode, subtitle style, CTA,
   render profile, subtitle toggle, reframe mode.

   Hierarchy: manual change > preset-filled field > DNA nudge > platform default
   Storage: creator_presets_v1
   ========================================================= */
'use strict';

window.CreatorPresets = (() => {

  const LS_KEY = 'creator_presets_v1';

  // Settings that make up a creator style preset.
  // Each entry maps a preset field key to its form element + type.
  const PRESET_FIELDS = {
    target_platform:  { el: 'evTargetPlatform', type: 'select'   },
    multi_variant:    { el: 'evMultiVariant',    type: 'checkbox' },
    subtitle_style:   { el: 'evSubStyle',        type: 'select'   },
    cta_enabled:      { el: 'evCtaEnabled',      type: 'checkbox' },
    cta_type:         { el: 'evCtaType',         type: 'select'   },
    render_profile:   { el: 'evRenderProfile',   type: 'select'   },
    add_subtitle:     { el: 'evAddSubtitle',      type: 'checkbox' },
    reframe_strategy: { el: 'evReframeStrategy', type: 'select'   },
  };

  // Built-in defaults — always present, cannot be deleted, not stored in LS.
  const BUILT_IN = [
    {
      id: '__tiktok_fast', name: 'TikTok Fast', builtIn: true,
      settings: {
        target_platform: 'tiktok',          multi_variant: true,
        subtitle_style:  'tiktok_bounce_v1', cta_enabled: false, cta_type: 'auto',
        render_profile:  'fast',             add_subtitle: true,
        reframe_strategy: 'fast_center',
      },
    },
    {
      id: '__youtube_clean', name: 'YouTube Clean', builtIn: true,
      settings: {
        target_platform: 'youtube_shorts',  multi_variant: false,
        subtitle_style:  'story_clean_01',  cta_enabled: false, cta_type: 'auto',
        render_profile:  'balanced',         add_subtitle: true,
        reframe_strategy: 'fast_center',
      },
    },
    {
      id: '__story_creator', name: 'Story Creator', builtIn: true,
      settings: {
        target_platform: 'instagram_reels', multi_variant: true,
        subtitle_style:  'story_clean_01',  cta_enabled: true, cta_type: 'follow',
        render_profile:  'quality',          add_subtitle: true,
        reframe_strategy: 'fast_center',
      },
    },
    {
      id: '__tutorial_pro', name: 'Tutorial Pro', builtIn: true,
      settings: {
        target_platform: 'youtube_shorts',  multi_variant: false,
        subtitle_style:  'story_clean_01',  cta_enabled: true, cta_type: 'part_2',
        render_profile:  'balanced',         add_subtitle: true,
        reframe_strategy: 'fast_center',
      },
    },
  ];

  // ── Storage ───────────────────────────────────────────────────────────────
  function _emptyState() { return { custom: [], activeId: '' }; }
  let _state = _emptyState();

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) return Object.assign(_emptyState(), JSON.parse(raw));
    } catch (_) {}
    return _emptyState();
  }

  function _save() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(_state)); } catch (_) {}
  }

  // ── Preset lookup ─────────────────────────────────────────────────────────
  function _allPresets() { return [...BUILT_IN, ..._state.custom]; }

  function _findById(id) {
    if (!id) return null;
    return _allPresets().find(p => p.id === id) || null;
  }

  function _genId() {
    return 'cp_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  // ── Form I/O ──────────────────────────────────────────────────────────────
  function _readCurrent() {
    const settings = {};
    for (const [key, field] of Object.entries(PRESET_FIELDS)) {
      const el = document.getElementById(field.el);
      if (!el) continue;
      settings[key] = field.type === 'checkbox' ? !!el.checked : el.value;
    }
    return settings;
  }

  function _applySettingsToForm(settings) {
    for (const [key, val] of Object.entries(settings)) {
      const field = PRESET_FIELDS[key];
      if (!field) continue;
      const el = document.getElementById(field.el);
      if (!el) continue;
      if (field.type === 'checkbox') el.checked = !!val;
      else el.value = val;
    }
    // Sync dependent UI elements that listen for change events but need manual sync
    // when values are set programmatically.
    if (settings.cta_enabled != null) {
      const wrap = document.getElementById('evCtaTypeWrap');
      if (wrap) wrap.style.display = !!settings.cta_enabled ? '' : 'none';
    }
    if (typeof evUpdateSubPreview === 'function') evUpdateSubPreview();
  }

  // ── Dropdown render ───────────────────────────────────────────────────────
  function _renderDropdown() {
    const sel = document.getElementById('cpPresetSelect');
    if (!sel) return;
    sel.innerHTML = '<option value="">— No Preset —</option>';

    // Built-in defaults group
    const biGroup = document.createElement('optgroup');
    biGroup.label = 'Defaults';
    BUILT_IN.forEach(p => {
      const o = document.createElement('option');
      o.value = p.id; o.textContent = p.name;
      biGroup.appendChild(o);
    });
    sel.appendChild(biGroup);

    // Custom presets group (only if any exist)
    if (_state.custom.length > 0) {
      const cGroup = document.createElement('optgroup');
      cGroup.label = 'My Presets';
      _state.custom.forEach(p => {
        const o = document.createElement('option');
        o.value = p.id; o.textContent = p.name;
        cGroup.appendChild(o);
      });
      sel.appendChild(cGroup);
    }

    sel.value = _state.activeId || '';
    _syncDeleteBtn();
  }

  function _syncDeleteBtn() {
    const del = document.getElementById('cpDeleteBtn');
    if (!del) return;
    const active = _findById(_state.activeId);
    // Only show delete for custom (non-built-in) presets
    del.style.display = (active && !active.builtIn) ? '' : 'none';
  }

  // ── Public: apply preset ──────────────────────────────────────────────────
  function applyPreset(presetId) {
    const preset = _findById(presetId);
    if (!preset) {
      // "No Preset" selected
      _state.activeId = '';
      _save();
      _syncDeleteBtn();
      return;
    }
    _applySettingsToForm(preset.settings);
    _state.activeId = presetId;
    _save();
    _syncDeleteBtn();
    _log('preset_applied', preset.name);
  }

  // ── Public: save current settings as preset ───────────────────────────────
  function promptSave() {
    // Suggest the active custom preset name for overwrite flow
    const active = _findById(_state.activeId);
    const defaultName = (active && !active.builtIn) ? active.name : '';
    const name = window.prompt('Save preset as:', defaultName);
    if (!name || !name.trim()) return;
    const trimmedName = name.trim();

    // Check for existing custom preset with same name (case-insensitive)
    const existing = _state.custom.find(
      p => p.name.toLowerCase() === trimmedName.toLowerCase()
    );
    if (existing) {
      if (!window.confirm(`Overwrite "${existing.name}"?`)) return;
      existing.settings = _readCurrent();
      _state.activeId = existing.id;
      _save();
      _renderDropdown();
      _log('preset_modified', trimmedName);
      return;
    }

    // New custom preset
    const newPreset = {
      id:       _genId(),
      name:     trimmedName,
      builtIn:  false,
      settings: _readCurrent(),
    };
    _state.custom.push(newPreset);
    _state.activeId = newPreset.id;
    _save();
    _renderDropdown();
    _log('preset_saved', trimmedName);
  }

  // ── Public: delete active custom preset ───────────────────────────────────
  function deleteActive() {
    const active = _findById(_state.activeId);
    if (!active || active.builtIn) return;
    if (!window.confirm(`Delete preset "${active.name}"?`)) return;
    _state.custom = _state.custom.filter(p => p.id !== _state.activeId);
    _state.activeId = '';
    _save();
    _renderDropdown();
  }

  // ── Public: read ──────────────────────────────────────────────────────────
  function getActive() { return _findById(_state.activeId) || null; }
  function getAllPresets() { return _allPresets(); }

  // ── Logging ───────────────────────────────────────────────────────────────
  function _log(event, name) {
    if (typeof addEvent === 'function') addEvent(`${event}: ${name}`, 'render');
  }

  // ── Public: lifecycle ─────────────────────────────────────────────────────
  function init() {
    _state = _load();
    _renderDropdown();   // restore dropdown; does NOT re-apply settings
  }

  function reset() {
    _state = _emptyState();
    _save();
    _renderDropdown();
  }

  return { init, applyPreset, promptSave, deleteActive, getActive, getAllPresets, reset };

})();
