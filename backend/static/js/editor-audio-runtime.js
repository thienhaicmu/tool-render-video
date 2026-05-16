/* =========================================================
   editor-audio-runtime.js  —  P1.8-J: Audio Track Runtime
   Track registry for source/BGM/voice with real state binding.
   Syncs controls ↔ EditorState ↔ render payload (editor_audio_plan).
   ========================================================= */
'use strict';

window.EditorAudioRuntime = (() => {

  // ── Track registry ────────────────────────────────────────
  const _tracks = {
    source: { enabled: true,  volume: 100, muted: false },
    bgm:    { enabled: false, volume: 18,  muted: false, path: '', fadeIn: 1, fadeOut: 2 },
    voice:  { enabled: false, volume: 100, muted: false },
  };

  // ── Source audio ──────────────────────────────────────────
  function onSourceToggle() {
    _tracks.source.enabled = !!document.getElementById('edAudioSourceEnabled')?.checked;
    _notifyState();
  }

  function onVolumeSlider(track, val) {
    const v = Math.max(0, Math.min(200, Math.round(Number(val) || 0)));
    _tracks[track] && (_tracks[track].volume = v);
    if (track === 'source') {
      const numEl = document.getElementById('evVolumeNum');
      if (numEl && String(numEl.value) !== String(v)) numEl.value = v;
    } else if (track === 'bgm') {
      const gainEl = document.getElementById('evBgmGain');
      const gain = (v / 100).toFixed(2);
      if (gainEl && gainEl.value !== gain) gainEl.value = gain;
      _tracks.bgm.volume = v;
    }
    _notifyState();
  }

  function onVolumeNum(track, val) {
    const v = Math.max(0, Math.min(200, Math.round(Number(val) || 0)));
    _tracks[track] && (_tracks[track].volume = v);
    if (track === 'source') {
      const slEl = document.getElementById('evVolume');
      if (slEl && String(slEl.value) !== String(v)) slEl.value = v;
    }
    _notifyState();
  }

  // ── BGM track ─────────────────────────────────────────────
  function onBgmToggle() {
    const cb = document.getElementById('evBgmEnable');
    _tracks.bgm.enabled = !!cb?.checked;
    const body = document.getElementById('edBgmControls');
    if (body) body.style.display = _tracks.bgm.enabled ? 'block' : 'none';
    _notifyState();
  }

  function onBgmGainInput(val) {
    const gain = Math.max(0.01, Math.min(1.0, Number(val) || 0.18));
    _tracks.bgm.volume = Math.round(gain * 100);
    const slEl = document.getElementById('edBgmGainSlider');
    if (slEl) slEl.value = _tracks.bgm.volume;
    _notifyState();
  }

  async function pickBgmFile() {
    if (typeof window.__electronIpc !== 'undefined') {
      try {
        const result = await window.__electronIpc.invoke('dialog:openFile', {
          filters: [{ name: 'Audio', extensions: ['mp3', 'wav', 'aac', 'm4a', 'ogg', 'flac'] }],
        });
        if (result && result.filePath) {
          _setBgmPath(result.filePath);
        }
      } catch (_) {}
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'audio/*';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (file.path) {
        _setBgmPath(file.path);
      } else {
        const fd = new FormData();
        fd.append('file', file);
        try {
          const r = await fetch('/api/upload-file', { method: 'POST', body: fd });
          if (r.ok) { const d = await r.json(); _setBgmPath(d.path || file.name); }
        } catch (_) { _setBgmPath(file.name); }
      }
    };
    input.click();
  }

  function _setBgmPath(path) {
    _tracks.bgm.path = path || '';
    const pathEl = document.getElementById('evBgmPath');
    if (pathEl) pathEl.value = _tracks.bgm.path;
    if (typeof _ev !== 'undefined') _ev.bgmPath = _tracks.bgm.path;
    _notifyState();
  }

  // ── Voice track ───────────────────────────────────────────
  function onVoiceToggle() {
    const cb = document.getElementById('evVoiceEnable');
    _tracks.voice.enabled = !!cb?.checked;
    const body = document.getElementById('edVoiceControls');
    if (body) body.style.display = _tracks.voice.enabled ? 'block' : 'none';
    if (typeof evToggleVoiceFields === 'function') evToggleVoiceFields();
    _notifyState();
  }

  // ── State notification ────────────────────────────────────
  function _notifyState() {
    if (typeof EditorState !== 'undefined') {
      EditorState.setEditorState({ audioTracks: Object.assign({}, _tracks) });
    }
  }

  // ── Serialize for render payload ──────────────────────────
  function serializeForRender() {
    const bgmEnabled = _tracks.bgm.enabled && !!_tracks.bgm.path;
    return {
      source: {
        enabled: _tracks.source.enabled,
        volume:  _tracks.source.volume,
      },
      bgm: {
        enabled:  bgmEnabled,
        path:     _tracks.bgm.path || null,
        gain:     parseFloat((_tracks.bgm.volume / 100).toFixed(2)),
        fade_in:  Number(document.getElementById('edBgmFadeIn')?.value  || 1),
        fade_out: Number(document.getElementById('edBgmFadeOut')?.value || 2),
      },
      voice: {
        enabled: _tracks.voice.enabled,
        volume:  _tracks.voice.volume,
      },
    };
  }

  // ── Tab activation hook ───────────────────────────────────
  function onTabActivate() {
    // Reflect current state back to controls
    const g = (id) => document.getElementById(id);
    if (g('edAudioSourceEnabled')) g('edAudioSourceEnabled').checked = _tracks.source.enabled;
    if (g('evVolume'))    g('evVolume').value    = _tracks.source.volume;
    if (g('evVolumeNum')) g('evVolumeNum').value = _tracks.source.volume;
    if (g('evBgmEnable')) g('evBgmEnable').checked = _tracks.bgm.enabled;
    const bgmBody = g('edBgmControls');
    if (bgmBody) bgmBody.style.display = _tracks.bgm.enabled ? 'block' : 'none';
    if (g('evBgmGain')) g('evBgmGain').value = (_tracks.bgm.volume / 100).toFixed(2);
    if (g('edBgmGainSlider')) g('edBgmGainSlider').value = _tracks.bgm.volume;
    if (g('evBgmPath')) g('evBgmPath').value = _tracks.bgm.path || '';
    if (g('evVoiceEnable')) g('evVoiceEnable').checked = _tracks.voice.enabled;
    const voiceBody = g('edVoiceControls');
    if (voiceBody) voiceBody.style.display = _tracks.voice.enabled ? 'block' : 'none';
  }

  // ── Init: sync initial hidden-input state in ─────────────
  function init() {
    // Pull initial values from any existing hidden inputs
    const g = (id) => document.getElementById(id);
    const vol = Number(g('evVolume')?.value || 100);
    _tracks.source.volume = vol;
    const bgmGain = Number(g('evBgmGain')?.value || 0.18);
    _tracks.bgm.volume = Math.round(bgmGain * 100);
    _tracks.bgm.path = g('evBgmPath')?.value || '';
    _tracks.bgm.enabled = !!g('evBgmEnable')?.checked;
    _tracks.voice.enabled = !!g('evVoiceEnable')?.checked;
  }

  // ── Reset (called on editor cancel/reopen) ────────────────
  function reset() {
    _tracks.source.enabled = true;
    _tracks.source.volume  = 100;
    _tracks.bgm.enabled    = false;
    _tracks.bgm.volume     = 18;
    _tracks.bgm.path       = '';
    _tracks.voice.enabled  = false;
    _tracks.voice.volume   = 100;
    const g = (id) => document.getElementById(id);
    if (g('edAudioSourceEnabled')) g('edAudioSourceEnabled').checked = true;
    if (g('evVolume'))    g('evVolume').value    = 100;
    if (g('evVolumeNum')) g('evVolumeNum').value = 100;
    if (g('evBgmEnable')) g('evBgmEnable').checked = false;
    const bgmBody = g('edBgmControls');
    if (bgmBody) bgmBody.style.display = 'none';
    if (g('evVoiceEnable')) g('evVoiceEnable').checked = false;
    const voiceBody = g('edVoiceControls');
    if (voiceBody) voiceBody.style.display = 'none';
  }

  // Auto-init after DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    onSourceToggle,
    onVolumeSlider,
    onVolumeNum,
    onBgmToggle,
    onBgmGainInput,
    pickBgmFile,
    onVoiceToggle,
    serializeForRender,
    onTabActivate,
    reset,
  };

})();
