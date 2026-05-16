/* =========================================================
   editor-coordinates.js  —  P1.5-A: Timeline Coordinate System
   Single source of truth for all timeline math.
   No DOM dependencies — pure geometry functions.
   ========================================================= */
'use strict';

window.EditorCoordinates = (() => {

  const LABEL_W       = 52;    // px — sticky track label column width
  const MIN_CLIP_DUR  = 0.25;  // seconds — minimum clip duration after trim
  const SNAP_PX       = 8;     // pixel threshold for snapping

  // ── Core conversions ─────────────────────────────────────────────
  function timeToPx(t, pps) {
    return t * pps;
  }

  function pxToTime(px, pps) {
    if (pps <= 0) return 0;
    return px / pps;
  }

  // {x, w} for a clip in track-content coordinates (pixels)
  function clipRect(clip, pps) {
    const x = timeToPx(clip.start, pps);
    const w = Math.max(3, timeToPx(clip.end - clip.start, pps));
    return { x: Math.round(x), w: Math.round(w) };
  }

  // Convert a screen clientX to timeline time, accounting for scroll + label
  // scrollEl: #evTLScrollBody
  function clientXToTime(clientX, scrollEl, pps) {
    if (!scrollEl || pps <= 0) return -1;
    const rect = scrollEl.getBoundingClientRect();
    const relX  = clientX - rect.left + scrollEl.scrollLeft - LABEL_W;
    if (relX < 0) return 0;
    return relX / pps;
  }

  // Visible time range (seconds) from current scroll position
  function viewportRange(scrollEl, pps) {
    if (!scrollEl || pps <= 0) return { start: 0, end: 0 };
    const start = Math.max(0, scrollEl.scrollLeft / pps);
    const end   = (scrollEl.scrollLeft + Math.max(1, scrollEl.clientWidth - LABEL_W)) / pps;
    return { start, end };
  }

  // Scroll offset (in pixels) that keeps `anchorTime` at `screenX` after pps changes
  // Use when zooming: newScrollLeft = zoomScrollLeft(anchorTime, screenX, scrollEl, newPps)
  function zoomScrollLeft(anchorTime, screenX, scrollEl, newPps) {
    if (!scrollEl) return 0;
    const rect      = scrollEl.getBoundingClientRect();
    const cursorInTrack = screenX - rect.left - LABEL_W; // px from track left in viewport
    const anchorPx  = timeToPx(anchorTime, newPps);
    return Math.max(0, anchorPx - cursorInTrack);
  }

  // ── Snap helpers ─────────────────────────────────────────────────
  function snap(t, snapPoints, pps) {
    const threshSec = SNAP_PX / pps;
    let best = null;
    let bestDist = Infinity;
    for (let i = 0; i < snapPoints.length; i++) {
      const d = Math.abs(t - snapPoints[i]);
      if (d < threshSec && d < bestDist) { best = snapPoints[i]; bestDist = d; }
    }
    return best !== null ? best : t;
  }

  // Magnetic snap: full resistance zone + hard snap.
  // Near a snap point, movement is progressively damped (feels like magnet).
  // HARD_PX: inside → locked to snap point.
  // SOFT_PX: inside → quadratically damped movement.
  function magneticTime(rawT, snapPoints, pps) {
    const HARD_PX  = 5;
    const SOFT_PX  = 16;
    const hardSec  = HARD_PX / pps;
    const softSec  = SOFT_PX / pps;

    let bestDist = Infinity;
    let bestSp   = null;
    for (let i = 0; i < snapPoints.length; i++) {
      const d = Math.abs(rawT - snapPoints[i]);
      if (d < bestDist) { bestDist = d; bestSp = snapPoints[i]; }
    }
    if (bestSp === null) return rawT;
    if (bestDist <= hardSec) return bestSp;
    if (bestDist <= softSec) {
      // t goes 0 (at hard boundary) → 1 (at soft boundary)
      const t      = (bestDist - hardSec) / (softSec - hardSec);
      const damped = hardSec + (bestDist - hardSec) * (t * t);
      return rawT > bestSp ? bestSp + damped : bestSp - damped;
    }
    return rawT;
  }

  // Collect snap points from current editor state
  function getSnapPoints(state) {
    const pts = [0];
    if (state.duration > 0) pts.push(state.duration);
    for (const c of state.clips)     { pts.push(c.start, c.end); }
    for (const s of state.subtitles) { pts.push(s.start, s.end); }
    return pts;
  }

  // ── Clamp helpers ────────────────────────────────────────────────
  function clampTime(t, lo, hi) {
    return Math.max(lo, Math.min(hi, t));
  }

  return {
    LABEL_W,
    MIN_CLIP_DUR,
    SNAP_PX,
    timeToPx,
    pxToTime,
    clipRect,
    clientXToTime,
    viewportRange,
    zoomScrollLeft,
    snap,
    magneticTime,
    getSnapPoints,
    clampTime,
  };

})();
