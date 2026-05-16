/* =========================================================
   editor-thumbnail-cache.js  —  P1.7-B: Filmstrip Thumbnail Cache
   Async frame extraction via a dedicated hidden <video> + canvas.
   Sequential queue prevents concurrent seeks on the same element.
   LRU cache (MAX_ENTRIES) avoids redundant extraction work.
   ========================================================= */
'use strict';

window.ThumbnailCache = (() => {

  const MAX_ENTRIES  = 300;
  const SEEK_TIMEOUT = 5000;   // ms before a stuck seek is abandoned

  // ── LRU cache (Map insertion-order gives us LRU cheaply) ─
  const _cache = new Map();

  function _lruGet(k) {
    if (!_cache.has(k)) return null;
    const v = _cache.get(k);
    _cache.delete(k);
    _cache.set(k, v);   // move to end (most-recent)
    return v;
  }

  function _lruSet(k, v) {
    if (_cache.size >= MAX_ENTRIES) {
      _cache.delete(_cache.keys().next().value);   // evict oldest
    }
    _cache.set(k, v);
  }

  // ── Extraction pipeline ───────────────────────────────────
  const _queue = [];     // pending {src, t, w, h, k, cb}
  let _busy    = false;
  let _vid     = null;   // dedicated hidden video element
  let _canvas  = null;
  let _ctx2d   = null;
  let _lastSrc = null;   // track when we need to change src

  function _ensureEl() {
    if (_vid) return;
    _vid    = document.createElement('video');
    _vid.muted       = true;
    _vid.preload     = 'auto';
    _vid.crossOrigin = 'anonymous';
    _vid.style.cssText = 'position:fixed;top:-99999px;left:-99999px;width:1px;height:1px;opacity:0;pointer-events:none;';
    document.body.appendChild(_vid);

    _canvas = document.createElement('canvas');
    _ctx2d  = _canvas.getContext('2d');
  }

  function _cacheKey(src, t, w) {
    return src + '\x00' + t.toFixed(3) + '\x00' + w;
  }

  function request(src, t, w, h, cb) {
    if (!src || typeof cb !== 'function') return;
    _ensureEl();

    const w2 = Math.max(16, Math.min(640, w || 160));
    const h2 = Math.max(9,  Math.min(360, h || Math.round(w2 * 9 / 16)));
    const k  = _cacheKey(src, t, w2);
    const hit = _lruGet(k);
    if (hit) { cb(hit); return; }

    _queue.push({ src, t, w: w2, h: h2, k, cb });
    if (!_busy) _pump();
  }

  function _pump() {
    if (!_queue.length) { _busy = false; return; }
    _busy = true;
    const job = _queue.shift();

    _canvas.width  = job.w;
    _canvas.height = job.h;

    let _settled = false;
    let _timer   = null;

    const _done = (url) => {
      if (_settled) return;
      _settled = true;
      clearTimeout(_timer);
      _vid.removeEventListener('seeked',  _onSeeked);
      _vid.removeEventListener('error',   _onError);
      if (url) { _lruSet(job.k, url); job.cb(url); }
      _pump();
    };

    const _onSeeked = () => {
      try {
        _ctx2d.drawImage(_vid, 0, 0, job.w, job.h);
        _done(_canvas.toDataURL('image/jpeg', 0.75));
      } catch (_e) {
        _done(null);
      }
    };

    const _onError = () => _done(null);

    _timer = setTimeout(() => _done(null), SEEK_TIMEOUT);
    _vid.addEventListener('seeked', _onSeeked, { once: true });
    _vid.addEventListener('error',  _onError,  { once: true });

    if (_lastSrc !== job.src) {
      _lastSrc  = job.src;
      _vid.src  = job.src;
      _vid.load();
    }
    _vid.currentTime = Math.max(0, job.t);
  }

  // ── Filmstrip helper ──────────────────────────────────────
  // Request N evenly-spaced frames across [start, end] and call
  // onFrame(i, dataUrl, x, w) for each as they arrive.
  function filmstrip(src, startSec, endSec, frameW, frameH, count, onFrame) {
    const n    = Math.max(1, count || 4);
    const span = endSec - startSec;
    for (let i = 0; i < n; i++) {
      const t  = startSec + span * (i + 0.5) / n;
      const x  = Math.round(i * frameW);
      const fi = i;
      request(src, t, frameW, frameH, (url) => onFrame(fi, url, x, frameW));
    }
  }

  function clear() {
    _cache.clear();
    _queue.length = 0;
  }

  return { request, filmstrip, clear };

})();
