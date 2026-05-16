/* =========================================================
   editor-waveform.js  —  P1.7-C: Audio Waveform Lane
   Web Audio API decoding → amplitude peaks → SVG bars.
   Cache by src so decode only happens once per source file.
   ========================================================= */
'use strict';

window.EditorWaveform = (() => {

  const _peakCache  = new Map();   // src → Float32Array
  const _pending    = new Map();   // src → [{numBins, cb}]

  // ── Peak computation ─────────────────────────────────────
  function _computePeaks(audioBuffer, numBins) {
    const ch   = audioBuffer.getChannelData(0);
    const len  = ch.length;
    const step = Math.max(1, Math.floor(len / numBins));
    const out  = new Float32Array(numBins);
    for (let i = 0; i < numBins; i++) {
      let peak = 0;
      const off = i * step;
      const end = Math.min(off + step, len);
      for (let j = off; j < end; j++) {
        const v = Math.abs(ch[j]);
        if (v > peak) peak = v;
      }
      out[i] = peak;
    }
    return out;
  }

  // ── Decode pipeline ──────────────────────────────────────
  function getPeaks(src, numBins, cb) {
    if (!src || typeof cb !== 'function') return;

    const bins = numBins || 200;

    // Cache hit — serve immediately
    if (_peakCache.has(src)) { cb(_peakCache.get(src)); return; }

    // Already fetching — enqueue
    if (_pending.has(src)) { _pending.get(src).push(cb); return; }
    _pending.set(src, [cb]);

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      _pending.delete(src);
      cb(null);
      return;
    }

    const ctx = new AudioCtx();
    fetch(src, { cache: 'force-cache' })
      .then(r => {
        if (!r.ok) throw new Error('fetch ' + r.status);
        return r.arrayBuffer();
      })
      .then(buf => ctx.decodeAudioData(buf))
      .then(decoded => {
        const peaks = _computePeaks(decoded, bins);
        _peakCache.set(src, peaks);
        ctx.close().catch(() => {});
        const cbs = _pending.get(src) || [];
        _pending.delete(src);
        cbs.forEach(f => f(peaks));
      })
      .catch(() => {
        ctx.close().catch(() => {});
        const cbs = _pending.get(src) || [];
        _pending.delete(src);
        cbs.forEach(f => f(null));
      });
  }

  // ── SVG renderer ─────────────────────────────────────────
  function renderSvg(peaks, width, height, color) {
    if (!peaks || !peaks.length) return '';
    const w   = Math.max(1, width  || 400);
    const h   = Math.max(4, height || 32);
    const col = color || 'rgba(77,124,255,.5)';
    const n   = peaks.length;
    const bw  = w / n;

    // Normalize to max peak so quiet audio still looks visible
    let maxP = 0;
    for (let i = 0; i < n; i++) { if (peaks[i] > maxP) maxP = peaks[i]; }
    const norm = maxP > 0 ? 1 / maxP : 1;

    let bars = '';
    for (let i = 0; i < n; i++) {
      const amp = peaks[i] * norm;
      const bh  = Math.max(1, Math.round(amp * h * 0.88));
      const y   = Math.round((h - bh) / 2);
      const x   = (i * bw).toFixed(1);
      const bwStr = Math.max(0.5, bw * 0.72).toFixed(1);
      bars += `<rect x="${x}" y="${y}" width="${bwStr}" height="${bh}"/>`;
    }

    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"`
         + ` viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"`
         + ` fill="${col}">${bars}</svg>`;
  }

  // ── Render directly into a DOM element ───────────────────
  function renderInto(el, src, totalPx, height, color) {
    if (!el || !src) return;
    const w = totalPx || el.offsetWidth || 400;
    const h = height  || el.offsetHeight || 32;
    // Bins = 1 per ~3px — capped at 1000 to keep SVG small
    const bins = Math.min(1000, Math.max(50, Math.round(w / 3)));

    // Insert placeholder immediately — shows users it's loading
    el.innerHTML = `<div class="evTLWaveLoading" style="width:${w}px;height:${h}px"></div>`;

    getPeaks(src, bins, (peaks) => {
      if (!peaks) { el.innerHTML = ''; return; }
      const svg = renderSvg(peaks, w, h, color);
      // Wrap in a fixed-width container so it doesn't affect scroll width
      el.innerHTML = `<div style="position:absolute;top:0;left:0;width:${w}px;height:${h}px;pointer-events:none;">${svg}</div>`;
    });
  }

  function clear() { _peakCache.clear(); _pending.clear(); }

  return { getPeaks, renderSvg, renderInto, clear };

})();
