/* =========================================================
   editor-virtualization.js  —  P1.6-B: Timeline Virtualization
   Viewport culling for clips, subtitles, and ruler ticks.
   Keeps timeline smooth under 300+ subtitle / 200+ clip loads.

   Strategy:
   - Track content wrappers keep full totalPx width (scrollbar correct)
   - Only DOM elements in viewport ± BUFFER are rendered
   - Sub-pixel subtitle segments are skipped entirely
   - Ruler ticks outside viewport ± RULER_BUFFER are omitted
   ========================================================= */
'use strict';

window.EditorVirtualization = (() => {

  const CLIP_BUFFER_SEC  = 3;    // seconds beyond viewport to keep clips rendered
  const SUB_BUFFER_SEC   = 5;    // seconds beyond viewport to keep subtitles rendered
  const RULER_BUFFER_PX  = 300;  // pixels beyond viewport to render ruler ticks
  const MIN_SEG_PX       = 1.5;  // skip subtitle segments narrower than this

  // ── Clips ─────────────────────────────────────────────────
  function filterClips(clips, vpStart, vpEnd) {
    const lo = vpStart - CLIP_BUFFER_SEC;
    const hi = vpEnd   + CLIP_BUFFER_SEC;
    return clips.filter(c => c.end >= lo && c.start <= hi);
  }

  // ── Subtitles ─────────────────────────────────────────────
  function filterSubtitles(segs, vpStart, vpEnd, pps) {
    const lo     = vpStart - SUB_BUFFER_SEC;
    const hi     = vpEnd   + SUB_BUFFER_SEC;
    const minDur = MIN_SEG_PX / Math.max(1, pps);
    return segs.filter(s =>
      s && typeof s.start === 'number' &&
      s.end >= lo && s.start <= hi &&
      (s.end - s.start) >= minDur
    );
  }

  // ── Ruler ticks ───────────────────────────────────────────
  // Returns {start, end} time range to render ticks for
  function rulerVisibleRange(scrollEl, pps, dur) {
    if (!scrollEl || pps <= 0) return { start: 0, end: dur };
    const LABEL_W  = 52;
    const bufferSec = RULER_BUFFER_PX / pps;
    const vpStart  = Math.max(0, scrollEl.scrollLeft / pps);
    const vpEnd    = (scrollEl.scrollLeft + scrollEl.clientWidth - LABEL_W) / pps;
    return {
      start: Math.max(0,   vpStart - bufferSec),
      end:   Math.min(dur, vpEnd   + bufferSec),
    };
  }

  // ── Viewport seconds ──────────────────────────────────────
  function viewportSec(scrollEl, pps) {
    if (!scrollEl || pps <= 0) return { start: 0, end: 9999 };
    const LABEL_W = 52;
    return {
      start: Math.max(0, scrollEl.scrollLeft / pps),
      end:   (scrollEl.scrollLeft + Math.max(1, scrollEl.clientWidth - LABEL_W)) / pps,
    };
  }

  return {
    CLIP_BUFFER_SEC,
    SUB_BUFFER_SEC,
    filterClips,
    filterSubtitles,
    rulerVisibleRange,
    viewportSec,
  };

})();
