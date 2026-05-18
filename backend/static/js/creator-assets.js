/* UP27 — CreatorAssets: local brand asset pack.
   Stores: logo path, intro sting path, outro path, music profile, brand subtitle style.
   All paths are local absolute paths (Electron provides file.path).
   Local-only. No backend. No upload. No cloud.
   Storage key: creator_assets_v1 */
'use strict';

window.CreatorAssets = (() => {
  const LS_KEY = 'creator_assets_v1';

  function _load() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); } catch (_) { return {}; }
  }

  function _save(state) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (_) {}
  }

  function setAsset(type, path, label) {
    const st = _load();
    st[type] = { path: path, label: label || String(path).split(/[/\\]/).pop() };
    _save(st);
    _refresh();
  }

  function removeAsset(type) {
    const st = _load();
    delete st[type];
    _save(st);
    _refresh();
  }

  function getAsset(type) {
    return _load()[type] || null;
  }

  function getPayload() {
    const st = _load();
    return {
      asset_logo_path:      (st.logo   && st.logo.path)  || null,
      asset_intro_path:     (st.intro  && st.intro.path) || null,
      asset_outro_path:     (st.outro  && st.outro.path) || null,
      asset_music_profile:  st.music_profile  || null,
      asset_brand_subtitle: st.brand_subtitle || null,
    };
  }

  function clear() { _save({}); _refresh(); }

  function _pickFile(accept, type) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    input.style.display = 'none';
    document.body.appendChild(input);
    input.onchange = function() {
      const file = this.files[0];
      if (file) {
        const path = file.path || file.name; // Electron provides .path; browser fallback to name
        setAsset(type, path, file.name);
      }
      try { document.body.removeChild(input); } catch (_) {}
    };
    input.click();
  }

  function pickLogo()  { _pickFile('image/png,image/jpeg,image/webp', 'logo'); }
  function pickIntro() { _pickFile('video/*', 'intro'); }
  function pickOutro() { _pickFile('video/*', 'outro'); }

  function setMusicProfile(val) {
    const st = _load();
    if (val) st.music_profile = val; else delete st.music_profile;
    _save(st);
    _refresh();
  }

  function setBrandSubtitle(val) {
    const st = _load();
    if (val) st.brand_subtitle = val; else delete st.brand_subtitle;
    _save(st);
    _refresh();
  }

  function _setPathLabel(id, label) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = label || 'Not set';
    el.classList.toggle('v3AssetSet', !!label);
  }

  function _refresh() {
    const st = _load();
    _setPathLabel('assetLogoPath',  (st.logo  && st.logo.label)  || null);
    _setPathLabel('assetIntroPath', (st.intro && st.intro.label) || null);
    _setPathLabel('assetOutroPath', (st.outro && st.outro.label) || null);
    const mp = document.getElementById('assetMusicProfile');
    if (mp) mp.value = st.music_profile || '';
    const bs = document.getElementById('assetBrandSubtitle');
    if (bs) bs.value = st.brand_subtitle || '';
    if (typeof v3RefreshSteeringPanel === 'function') v3RefreshSteeringPanel();
  }

  function init() { _refresh(); }

  return {
    init, setAsset, removeAsset, getAsset, getPayload, clear,
    pickLogo, pickIntro, pickOutro, setMusicProfile, setBrandSubtitle,
  };
})();
