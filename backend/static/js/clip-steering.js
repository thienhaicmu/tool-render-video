/* UP26 — ClipSteering: persist creator clip lock / exclude decisions across renders */
const ClipSteering = (() => {
  const LS_KEY   = 'clip_steering_v1';
  const MAX_ENTRIES = 10;
  const TTL_MS   = 72 * 60 * 60 * 1000; // 72 hours

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : { lock: [], exclude: [] };
    } catch { return { lock: [], exclude: [] }; }
  }

  function _save(state) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch {}
  }

  function _prune(list) {
    const now = Date.now();
    return list
      .filter(e => (now - (e.ts || 0)) < TTL_MS)
      .slice(-MAX_ENTRIES);
  }

  function _addEntry(list, startSec, endSec, label) {
    const entry = {
      start_sec: parseFloat(startSec) || 0,
      end_sec:   parseFloat(endSec)   || 0,
      label:     String(label || '').trim(),
      ts:        Date.now(),
    };
    return _prune([...list, entry]);
  }

  function lockClip(startSec, endSec, label) {
    const st = _load();
    st.lock = _addEntry(st.lock, startSec, endSec, label);
    _save(st);
  }

  function excludeClip(startSec, endSec, label) {
    const st = _load();
    st.exclude = _addEntry(st.exclude, startSec, endSec, label);
    _save(st);
  }

  function getClipLock()    { return _prune(_load().lock);    }
  function getClipExclude() { return _prune(_load().exclude); }

  function getPayload() {
    return {
      clip_lock:    getClipLock(),
      clip_exclude: getClipExclude(),
    };
  }

  function clear() { _save({ lock: [], exclude: [] }); }

  function getCount() {
    const st = _load();
    return { lock: _prune(st.lock).length, exclude: _prune(st.exclude).length };
  }

  return { lockClip, excludeClip, getClipLock, getClipExclude, getPayload, clear, getCount };
})();
