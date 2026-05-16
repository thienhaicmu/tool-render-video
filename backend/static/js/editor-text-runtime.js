/* =========================================================
   editor-text-runtime.js  —  P1.8-I: Text Layer Runtime
   Extends the existing text layer system with:
   - enabled / locked per-layer state
   - animationPreset binding
   - stylePreset quick-apply buttons
   - render payload serialization (editor_text_layers)
   - selection sync to timeline + preview overlay highlight
   ========================================================= */
'use strict';

window.EditorTextRuntime = (() => {

  // ── Runtime state overlay (keyed by layer id) ────────────
  // Stored separately from _ev.textLayers so we don't mutate
  // the existing data contract. Merged at serialize time.
  const _rt = new Map();   // id → {enabled, locked, animPreset}

  function _getRt(id) {
    if (!_rt.has(id)) _rt.set(id, { enabled: true, locked: false, animPreset: 'none' });
    return _rt.get(id);
  }

  // ── Style presets ─────────────────────────────────────────
  const STYLE_PRESETS = [
    { id: 'viral',   label: '🔥',  title: 'Viral',   font: 'Bungee',    size: 52, color: '#ffffff', bold: false, outline: { enabled: true,  thickness: 3 } },
    { id: 'clean',   label: '✨',  title: 'Clean',   font: 'Montserrat', size: 42, color: '#ffffff', bold: true,  outline: { enabled: false, thickness: 0 } },
    { id: 'bold',    label: 'B',   title: 'Bold',    font: 'Anton',      size: 58, color: '#ffff00', bold: false, outline: { enabled: true,  thickness: 2 } },
    { id: 'minimal', label: '—',   title: 'Minimal', font: 'Roboto',     size: 32, color: '#eeeeee', bold: false, outline: { enabled: false, thickness: 0 } },
  ];

  function _mountStylePresets() {
    const el = document.getElementById('edTxtStylePresets');
    if (!el) return;
    el.innerHTML = STYLE_PRESETS.map(p =>
      `<button class="evTinyBtn" title="${p.title} style" onclick="EditorTextRuntime.applyStylePreset('${p.id}')">${p.label}</button>`
    ).join('');
  }

  function applyStylePreset(presetId) {
    const preset = STYLE_PRESETS.find(p => p.id === presetId);
    if (!preset || typeof _ev === 'undefined') return;
    const idx = _ev.selectedTextLayer;
    const layer = (_ev.textLayers || [])[idx];
    if (!layer) return;
    layer.font_family = preset.font;
    layer.font_size   = preset.size;
    layer.color       = preset.color;
    layer.bold        = preset.bold;
    layer.outline     = Object.assign({}, preset.outline);
    // Reflect into form controls
    const g = (id) => document.getElementById(id);
    if (g('evTxtFont'))              g('evTxtFont').value = preset.font;
    if (g('evTxtSize'))              g('evTxtSize').value = preset.size;
    if (g('evTxtColor'))             g('evTxtColor').value = preset.color;
    if (g('evTxtBold'))              g('evTxtBold').checked = preset.bold;
    if (g('evTxtOutlineEnabled'))    g('evTxtOutlineEnabled').checked = preset.outline.enabled;
    if (g('evTxtOutlineThickness'))  g('evTxtOutlineThickness').value = preset.outline.thickness;
    if (typeof evRenderTextLayerPreview === 'function') evRenderTextLayerPreview();
    if (typeof evRenderTextLayerList    === 'function') evRenderTextLayerList();
  }

  // ── Animation preset ──────────────────────────────────────
  function onAnimPresetChange() {
    if (typeof _ev === 'undefined') return;
    const idx = _ev.selectedTextLayer;
    const layer = (_ev.textLayers || [])[idx];
    if (!layer) return;
    const rt = _getRt(layer.id);
    rt.animPreset = document.getElementById('edTxtAnimPreset')?.value || 'none';
    _applyAnimPreviewClass(layer.id, rt.animPreset);
  }

  function _applyAnimPreviewClass(layerId, preset) {
    const overlay = document.getElementById('evTextLayersOverlay');
    if (!overlay) return;
    const el = overlay.querySelector(`[data-layer-id="${CSS.escape(layerId)}"]`);
    if (!el) return;
    el.classList.remove('edTxtAnim-fade-in', 'edTxtAnim-slide-up', 'edTxtAnim-scale-in', 'edTxtAnim-typewriter');
    if (preset && preset !== 'none') {
      el.classList.add('edTxtAnim-' + preset);
    }
  }

  // ── Enabled / Locked per layer ────────────────────────────
  function onLayerEnabledChange() {
    if (typeof _ev === 'undefined') return;
    const idx = _ev.selectedTextLayer;
    const layer = (_ev.textLayers || [])[idx];
    if (!layer) return;
    const rt = _getRt(layer.id);
    rt.enabled = !!document.getElementById('edTxtLayerEnabled')?.checked;
    _refreshLayerVisibility(layer.id, rt);
    _syncLayerListItem(idx, rt);
  }

  function onLayerLockedChange() {
    if (typeof _ev === 'undefined') return;
    const idx = _ev.selectedTextLayer;
    const layer = (_ev.textLayers || [])[idx];
    if (!layer) return;
    const rt = _getRt(layer.id);
    rt.locked = !!document.getElementById('edTxtLayerLocked')?.checked;
    _refreshLayerVisibility(layer.id, rt);
    _syncLayerListItem(idx, rt);
  }

  function _refreshLayerVisibility(layerId, rt) {
    const overlay = document.getElementById('evTextLayersOverlay');
    if (!overlay) return;
    const el = overlay.querySelector(`[data-layer-id="${CSS.escape(layerId)}"]`);
    if (!el) return;
    el.style.opacity = rt.enabled ? '1' : '0.25';
    el.style.pointerEvents = rt.locked ? 'none' : '';
  }

  function _syncLayerListItem(idx, rt) {
    const box = document.getElementById('evTextLayerList');
    if (!box) return;
    const item = box.querySelectorAll('.evLayerItem')[idx];
    if (!item) return;
    item.classList.toggle('edTxtDisabled', !rt.enabled);
    item.classList.toggle('edTxtLocked', rt.locked);
  }

  // ── Sync runtime controls when selection changes ──────────
  function syncToSelection() {
    if (typeof _ev === 'undefined') return;
    const idx = _ev.selectedTextLayer;
    const layer = (_ev.textLayers || [])[idx];
    const g = (id) => document.getElementById(id);
    if (!layer) {
      if (g('edTxtLayerEnabled'))  g('edTxtLayerEnabled').checked = true;
      if (g('edTxtLayerLocked'))   g('edTxtLayerLocked').checked = false;
      if (g('edTxtAnimPreset'))    g('edTxtAnimPreset').value = 'none';
      return;
    }
    const rt = _getRt(layer.id);
    if (g('edTxtLayerEnabled'))  g('edTxtLayerEnabled').checked = rt.enabled;
    if (g('edTxtLayerLocked'))   g('edTxtLayerLocked').checked = rt.locked;
    if (g('edTxtAnimPreset'))    g('edTxtAnimPreset').value = rt.animPreset || 'none';
  }

  // ── Render payload serialization ──────────────────────────
  // Returns enabled layers with runtime fields merged.
  // Called by startRenderFromEditor() to populate editor_text_layers.
  function serializeForRender() {
    if (typeof _ev === 'undefined') return [];
    return (_ev.textLayers || [])
      .map((l) => {
        const rt = _getRt(l.id);
        return Object.assign({}, l, {
          runtime_enabled:   rt.enabled,
          runtime_locked:    rt.locked,
          anim_preset:       rt.animPreset || 'none',
        });
      })
      .filter(l => _getRt(l.id).enabled && String(l.text || '').trim().length > 0);
  }

  // ── Tab activation hook ───────────────────────────────────
  function onTabActivate() {
    _mountStylePresets();
    syncToSelection();
  }

  // ── Reset (called on editor cancel/reopen) ────────────────
  function reset() {
    _rt.clear();
    const g = (id) => document.getElementById(id);
    if (g('edTxtLayerEnabled'))  g('edTxtLayerEnabled').checked = true;
    if (g('edTxtLayerLocked'))   g('edTxtLayerLocked').checked = false;
    if (g('edTxtAnimPreset'))    g('edTxtAnimPreset').value = 'none';
  }

  // ── Auto-mount style presets on load ─────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _mountStylePresets);
  } else {
    _mountStylePresets();
  }

  return {
    applyStylePreset,
    onAnimPresetChange,
    onLayerEnabledChange,
    onLayerLockedChange,
    syncToSelection,
    serializeForRender,
    onTabActivate,
    reset,
  };

})();
