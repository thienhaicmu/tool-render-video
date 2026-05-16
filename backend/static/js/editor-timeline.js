/* =========================================================
   editor-timeline.js  —  P1-C/D: Timeline Engine + Clip Segments
   DOM-based multi-track timeline with ruler, playhead, zoom.
   Tracks: Source video / Waveform / AI Clips / Subtitles / Text.
   ========================================================= */
'use strict';

window.EditorTimeline = (() => {

  // ── DOM refs ──────────────────────────────────────────────
  let _root   = null;   // #evRichTimeline
  let _ruler  = null;   // #evTLRulerContent
  let _ph     = null;   // #evTLPlayhead
  let _scroll = null;   // #evTLScrollBody
  let _inner  = null;   // #evTLInner (width = totalPx)
  let _tracks = {};     // {source, wave, clips, subs, text} → DOM el

  // ── State ─────────────────────────────────────────────────
  let _dur        = 0;
  let _pps        = 50;    // px per second
  let _videoSrc   = null;  // source video URL for waveform + filmstrip
  let _unsub      = null;
  let _ro         = null;  // ResizeObserver
  let _prevT      = -1;
  let _prevSelId  = null;  // cached for selection diff
  let _prevHovId  = null;  // cached for hover diff
  let _onScrollFn = null;  // scroll listener ref (for removal)
  // P2-A: AI overlay data
  let _markerData  = [];   // [{type, time, label, duration?}]
  let _heatmapData = [];   // [{start, end, energy}]
  // P2.4: ghost overlay
  let _ghostLayer  = null; // div appended to _tracks.clips during preview

  const LABEL_W = 52;     // track label width px
  const FILM_H  = 22;     // filmstrip frame height inside clip px (track h - 4)

  // ── Lane registry (P1.6-D) ────────────────────────────────
  const LANES = [
    { id: 'video', domId: 'evTLTrackSource', label: 'Video', type: 'source' },
    { id: 'wave',  domId: 'evTLTrackWave',   label: 'Wave',  type: 'wave'   },
    { id: 'clips', domId: 'evTLTrackClips',  label: 'Clips', type: 'clips'  },
    { id: 'subs',  domId: 'evTLTrackSubs',   label: 'Subs',  type: 'subs'   },
    { id: 'text',  domId: 'evTLTrackText',   label: 'Text',  type: 'text'   },
  ];

  // ── Score tier ────────────────────────────────────────────
  function _tier(score) {
    if (score >= 0.8) return 'is-high';
    if (score >= 0.6) return 'is-mid';
    if (score >= 0.4) return 'is-low';
    return 'is-weak';
  }

  function _fmtT(s) {
    const m = Math.floor(s / 60);
    return m + ':' + String(Math.floor(s % 60)).padStart(2, '0');
  }

  // ── Init ─────────────────────────────────────────────────
  function init(rootId) {
    _root   = document.getElementById(rootId || 'evRichTimeline');
    if (!_root) return;

    _ruler  = document.getElementById('evTLRulerContent');
    _ph     = document.getElementById('evTLPlayhead');
    _scroll = document.getElementById('evTLScrollBody');
    _inner  = document.getElementById('evTLInner');
    _tracks = {
      source:  document.getElementById('evTLTrackSource'),
      heat:    document.getElementById('evTLTrackHeat'),
      wave:    document.getElementById('evTLTrackWave'),
      clips:   document.getElementById('evTLTrackClips'),
      markers: document.getElementById('evTLTrackMarkers'),
      subs:    document.getElementById('evTLTrackSubs'),
      text:    document.getElementById('evTLTrackText'),
    };

    // Watch width changes → re-fit
    if (window.ResizeObserver) {
      _ro = new ResizeObserver(() => { if (_dur) { _fitZoom(); _renderAll(); } });
      _ro.observe(_root);
    }

    // Scroll → re-render visible subtitle/clip ranges (virtualization)
    if (_scroll) {
      _onScrollFn = () => {
        if (!_dur) return;
        const state = EditorState.getState();
        renderSubtitles(state.subtitles);
        renderClips(state.clips);
        _renderRuler(Math.round(_dur * _pps));
      };
      _scroll.addEventListener('scroll', _onScrollFn, { passive: true });
    }

    // Subscribe to EditorState
    if (_unsub) _unsub();
    _unsub = EditorState.subscribeEditorState(_onState);
  }

  function setDuration(dur) {
    _dur = Math.max(0, dur);
    if (_dur) { _fitZoom(); _renderAll(); }
  }

  function setVideoSrc(src) {
    _videoSrc = src || null;
    if (_dur && src) _renderWaveform(Math.round(_dur * _pps));
  }

  // ── Auto-fit zoom so full duration fills view ────────────
  function _fitZoom() {
    if (!_dur || !_scroll) return;
    const usable = Math.max(1, _scroll.clientWidth - 4);
    _pps = usable / (_dur * 1.02);   // 2% padding
    EditorState.setEditorState({ zoom: _pps });
  }

  function fit() { _fitZoom(); _renderAll(); }

  function zoom(dir) {
    // dir: +1 = zoom in (more px/s), -1 = zoom out
    const factor = dir > 0 ? 1.5 : (1 / 1.5);
    _pps = Math.max(2, Math.min(4000, _pps * factor));
    EditorState.setEditorState({ zoom: _pps });
    _renderAll();
  }

  function setZoom(pps) {
    _pps = Math.max(2, Math.min(4000, pps));
    EditorState.setEditorState({ zoom: _pps });
    _renderAll();
  }

  function getPxPerSec() { return _pps; }

  function scrollToTime(t) {
    if (!_scroll) return;
    const targetX = t * _pps - _scroll.clientWidth * 0.3;
    _scroll.scrollLeft = Math.max(0, targetX);
  }

  function getScrollOffsetSec() {
    return _scroll ? (_scroll.scrollLeft / _pps) : 0;
  }

  // ── State subscriber ─────────────────────────────────────
  function _onState(state) {
    if (!_root) return;

    // Playhead — only update on currentTime change
    if (state.currentTime !== _prevT) {
      _prevT = state.currentTime;
      _updatePlayhead(state.currentTime);
    }

    // Clip selection — only update DOM when selection/hover actually changed
    const selChanged = state.selectedClipId !== _prevSelId;
    const hovChanged = state.hoveredClipId  !== _prevHovId;
    if (selChanged || hovChanged) {
      _prevSelId = state.selectedClipId;
      _prevHovId = state.hoveredClipId;
      _root.querySelectorAll('.evTLClip').forEach(el => {
        if (selChanged) el.classList.toggle('is-selected', el.dataset.clipId === state.selectedClipId);
        if (hovChanged) el.classList.toggle('is-hovered',  el.dataset.clipId === state.hoveredClipId);
      });
    }
  }

  // ── Render all ───────────────────────────────────────────
  function _renderAll() {
    if (!_root || !_dur) return;
    const totalPx = Math.round(_dur * _pps);

    // Set inner width so scroll works
    if (_inner) _inner.style.width = (totalPx + LABEL_W) + 'px';

    _renderRuler(totalPx);
    _renderSourceTrack(totalPx);
    _drawHeatmapTrack(totalPx);
    _renderWaveform(totalPx);
    const state = EditorState.getState();
    renderClips(state.clips, totalPx);
    _drawMarkersTrack(totalPx);
    renderSubtitles(state.subtitles, totalPx);
    renderTextLayers(state.textLayers, totalPx);
    _updatePlayhead(state.currentTime);
  }

  // ── Ruler (virtualized) ──────────────────────────────────
  function _renderRuler(totalPx) {
    if (!_ruler) return;
    const interval = _pickInterval();
    // Render only visible range + buffer
    const vr = (typeof EditorVirtualization !== 'undefined')
      ? EditorVirtualization.rulerVisibleRange(_scroll, _pps, _dur)
      : { start: 0, end: _dur };
    const tStart = Math.floor(vr.start / interval) * interval;
    const tEnd   = vr.end;

    let html = '<div style="position:relative;height:100%;width:' + totalPx + 'px">';
    let t = Math.max(0, tStart);
    while (t <= Math.min(_dur + interval, tEnd + interval)) {
      const x = Math.round(t * _pps);
      const isMajor = Math.round(t / interval) % 5 === 0;
      const label = isMajor ? _fmtT(t) : '';
      html += '<div class="evTLTick' + (isMajor ? ' is-major' : '') + '"'
            + ' style="left:' + x + 'px">'
            + (label ? '<span>' + label + '</span>' : '')
            + '</div>';
      t = Math.round((t + interval) * 1000) / 1000;
    }
    html += '</div>';
    _ruler.innerHTML = html;
  }

  function _pickInterval() {
    const targetPx = 60;
    const rawSec = targetPx / _pps;
    const nice = [0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
    return nice.find(n => n >= rawSec) || 600;
  }

  // ── Source track ─────────────────────────────────────────
  function _renderSourceTrack(totalPx) {
    const el = _tracks.source;
    if (!el) return;
    el.innerHTML = '<div class="evTLSourceBar" style="width:' + totalPx + 'px"></div>';
  }

  // ── Waveform track (P1.7-C) ───────────────────────────────
  function _renderWaveform(totalPx) {
    const el = _tracks.wave;
    if (!el || !_videoSrc || typeof EditorWaveform === 'undefined') return;
    EditorWaveform.renderInto(el, _videoSrc, totalPx, el.offsetHeight || 26, 'rgba(77,124,255,.45)');
  }

  // ── AI Clips track (viewport-culled) ─────────────────────
  function renderClips(clips, totalPx) {
    const el = _tracks.clips;
    if (!el) return;
    if (!Array.isArray(clips) || !clips.length) { el.innerHTML = ''; if (_ghostLayer) el.appendChild(_ghostLayer); return; }
    const tw = totalPx || Math.round(_dur * _pps);

    // Viewport culling — only render visible clips + buffer
    let visible = clips;
    if (typeof EditorVirtualization !== 'undefined' && _scroll) {
      const vp = EditorVirtualization.viewportSec(_scroll, _pps);
      visible  = EditorVirtualization.filterClips(clips, vp.start, vp.end);
    }

    const selId = EditorState.getState().selectedClipId;
    const hovId = EditorState.getState().hoveredClipId;
    let html = '<div style="position:relative;height:100%;width:' + tw + 'px">';
    visible.forEach(c => {
      const x    = Math.round(c.start * _pps);
      const w    = Math.max(3, Math.round((c.end - c.start) * _pps));
      const tier = _tier(c.score);
      const pct  = c.score >= 0.01 ? Math.round(c.score * 100) + '%' : '';
      const isSel = c.id === selId ? ' is-selected' : '';
      const isHov = c.id === hovId ? ' is-hovered'  : '';
      html += '<div class="evTLClip ' + tier + isSel + isHov + '"'
            + ' data-clip-id="' + c.id + '"'
            + ' style="left:' + x + 'px;width:' + w + 'px"'
            + ' title="' + (c.label || '') + ' · ' + c.start.toFixed(1) + 's–' + c.end.toFixed(1) + 's">'
            + '<div class="evTLClipResize is-left"  data-resize="start" data-clip-id="' + c.id + '"></div>'
            + '<span class="evTLClipLabel">' + pct + '</span>'
            + '<div class="evTLClipResize is-right" data-resize="end"   data-clip-id="' + c.id + '"></div>'
            + '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
    // P2.4: re-attach ghost layer if a preview is active (innerHTML wiped it)
    if (_ghostLayer) el.appendChild(_ghostLayer);

    // P1.7-B: async filmstrip thumbnails for wide clips
    _injectFilmstrip(el, visible);
  }

  // ── P1.7-B: Filmstrip thumbnails inside clips ─────────────
  // Only requests frames for clips wider than FILM_MIN_W px.
  // Frames arrive async — injected directly into the DOM element.
  const FILM_MIN_W = 40;   // px below which filmstrip is skipped
  const FILM_FW    = 36;   // width of each filmstrip frame px

  function _injectFilmstrip(trackEl, clips) {
    if (!_videoSrc || typeof ThumbnailCache === 'undefined') return;
    clips.forEach(c => {
      const w = Math.max(3, Math.round((c.end - c.start) * _pps));
      if (w < FILM_MIN_W) return;

      // Find the live DOM element (just inserted via innerHTML)
      const clipEl = trackEl.querySelector('[data-clip-id="' + c.id + '"]');
      if (!clipEl) return;

      const frameCount = Math.max(1, Math.min(6, Math.floor(w / FILM_FW)));
      const fh = FILM_H;
      const fw = Math.floor(w / frameCount);

      ThumbnailCache.filmstrip(_videoSrc, c.start, c.end, fw, fh, frameCount, (i, url, x) => {
        if (!url) return;
        // Re-query in case the DOM was replaced by a subsequent renderClips call
        const el = trackEl.querySelector('[data-clip-id="' + c.id + '"]');
        if (!el) return;
        let film = el.querySelector('.evTLFilmstrip');
        if (!film) {
          film = document.createElement('div');
          film.className = 'evTLFilmstrip';
          el.insertBefore(film, el.firstChild);
        }
        const img = document.createElement('img');
        img.className = 'evTLFilmFrame';
        img.src   = url;
        img.style.cssText = 'left:' + x + 'px;width:' + fw + 'px;height:' + fh + 'px';
        film.appendChild(img);
      });
    });
  }

  // ── Subtitles track (viewport-culled, sub-pixel skipped) ─
  function renderSubtitles(segs, totalPx) {
    const el = _tracks.subs;
    if (!el) return;
    if (!Array.isArray(segs) || !segs.length) { el.innerHTML = ''; return; }
    const tw = totalPx || Math.round(_dur * _pps);

    // Viewport culling — renders 300+ subs without DOM flood
    let visible = segs;
    if (typeof EditorVirtualization !== 'undefined' && _scroll) {
      const vp = EditorVirtualization.viewportSec(_scroll, _pps);
      visible  = EditorVirtualization.filterSubtitles(segs, vp.start, vp.end, _pps);
    }

    let html = '<div style="position:relative;height:100%;width:' + tw + 'px">';
    visible.forEach((s, _unused) => {
      if (!s || typeof s.start !== 'number') return;
      const origIdx = segs.indexOf(s);  // preserve original index for interactions
      const x   = Math.round(s.start * _pps);
      const w   = Math.max(3, Math.round((s.end - s.start) * _pps));
      const txt = String(s.text || '').slice(0, 24);
      html += '<div class="evTLSub" data-sub-idx="' + origIdx + '"'
            + ' style="left:' + x + 'px;width:' + w + 'px"'
            + ' title="' + txt + '">'
            + '<span class="evTLSubLabel">' + txt + '</span>'
            + '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  // ── Text layers track ─────────────────────────────────────
  function renderTextLayers(layers, totalPx) {
    const el = _tracks.text;
    if (!el) return;
    const valid = (layers || []).filter(l => l && (l.start_time || l.end_time));
    if (!valid.length) { el.innerHTML = ''; return; }
    const tw = totalPx || Math.round(_dur * _pps);
    let html = '<div style="position:relative;height:100%;width:' + tw + 'px">';
    valid.forEach((l, i) => {
      const x = Math.round((l.start_time || 0) * _pps);
      const w = Math.max(4, Math.round(((l.end_time || _dur) - (l.start_time || 0)) * _pps));
      html += '<div class="evTLTextLayer" style="left:' + x + 'px;width:' + w + 'px"'
            + ' title="' + String(l.text || 'Text').replace(/"/g, '') + '">'
            + '<span class="evTLSubLabel">' + String(l.text || 'T').slice(0, 12) + '</span>'
            + '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  // ── P2-A: Heatmap track ──────────────────────────────────
  // Renders energy gradient band; uses CSS linear-gradient for performance.
  function _drawHeatmapTrack(totalPx) {
    const el = _tracks.heat;
    if (!el) return;
    if (!_heatmapData.length || !_dur) { el.innerHTML = ''; return; }
    const tw   = totalPx || Math.round(_dur * _pps);
    // Downsample to max 120 stops to keep CSS compact
    const src  = _heatmapData.length > 120 ? _dsHeatmap(_heatmapData, 120) : _heatmapData;
    const stops = src.map(b => {
      const e   = Math.max(0, Math.min(1, b.energy || 0));
      const hue = Math.round(e * 120);        // red→green
      const a   = (0.12 + e * 0.55).toFixed(2);
      const pct = ((_dur > 0 ? b.start / _dur : 0) * 100).toFixed(2);
      return `hsla(${hue},72%,52%,${a}) ${pct}%`;
    });
    // Close at 100 %
    const last  = src[src.length - 1];
    const lastE = Math.max(0, Math.min(1, last.energy || 0));
    stops.push(`hsla(${Math.round(lastE * 120)},72%,52%,${(0.12 + lastE * 0.55).toFixed(2)}) 100%`);
    el.innerHTML =
      `<div style="position:relative;height:100%;width:${tw}px;` +
      `background:linear-gradient(to right,${stops.join(',')})"></div>`;
  }

  function _dsHeatmap(arr, max) {
    const step = arr.length / max;
    const out  = [];
    for (let i = 0; i < max; i++) out.push(arr[Math.min(Math.floor(i * step), arr.length - 1)]);
    return out;
  }

  // ── P2-A: Markers track ───────────────────────────────────
  // Small type-colored pips at their timeline positions.
  function _drawMarkersTrack(totalPx) {
    const el = _tracks.markers;
    if (!el) return;
    if (!_markerData.length || !_dur) { el.innerHTML = ''; return; }
    const tw   = totalPx || Math.round(_dur * _pps);
    let html   = `<div style="position:relative;height:100%;width:${tw}px">`;
    _markerData.forEach(m => {
      const x   = Math.round(Math.max(0, m.time) * _pps);
      const type = m.type || 'default';
      const lbl  = (m.label || '').replace(/"/g, '');
      const hint = m.reasonHint ? (' — ' + m.reasonHint.replace(/"/g, '')) : '';
      html += `<div class="evTLMarker evTLMk-${type}" style="left:${x}px" title="${lbl}${hint}"></div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  }

  // ── P2-A: Public setters (called by EditorSceneIntelligence) ──
  function renderMarkers(markers) {
    _markerData = Array.isArray(markers) ? markers : [];
    if (_dur) _drawMarkersTrack(Math.round(_dur * _pps));
    else if (_tracks.markers) _tracks.markers.innerHTML = '';
  }

  function renderHeatmap(heatmap) {
    _heatmapData = Array.isArray(heatmap) ? heatmap : [];
    if (_dur) _drawHeatmapTrack(Math.round(_dur * _pps));
    else if (_tracks.heat) _tracks.heat.innerHTML = '';
  }

  // ── P2.4: Ghost overlay (preview diffs on clips track) ───
  function renderGhosts(patches, clips, duration, reasoning) {
    clearGhosts();
    const el = _tracks.clips;
    if (!el || !Array.isArray(patches) || !patches.length) return;
    const dur = duration || _dur;
    if (!dur) return;

    // Extract hover hints from reasoning
    const reasons     = (reasoning && reasoning.reasons) || [];
    const silReason   = reasons.find(r => r.type === 'silence');
    const pacingReason= reasons.find(r => r.type === 'pacing');
    const trimHint    = silReason   ? silReason.label
                      : pacingReason ? pacingReason.label
                      : 'AI recommended trim';

    // Build clip lookup
    const clipMap = {};
    (clips || []).forEach(c => { clipMap[c.id] = c; });

    _ghostLayer = document.createElement('div');
    _ghostLayer.className = 'evTLGhostLayer';
    _ghostLayer.style.cssText =
      'position:absolute;top:0;left:0;bottom:0;pointer-events:none;z-index:8;' +
      'width:' + Math.round(dur * _pps) + 'px';

    patches.forEach(p => {
      if (p.type === 'trim') {
        const c = clipMap[p.clipId];
        if (!c) return;
        // Hatched band over left-trimmed region
        const leftTrim = p.newStart - c.start;
        if (leftTrim > 0.01) {
          const g = document.createElement('div');
          g.className = 'evTLGhost evTLGhost--trim';
          g.style.left  = Math.round(c.start * _pps) + 'px';
          g.style.width = Math.max(2, Math.round(leftTrim * _pps)) + 'px';
          g.title = trimHint;
          _ghostLayer.appendChild(g);
        }
        // Hatched band over right-trimmed region
        const rightTrim = c.end - p.newEnd;
        if (rightTrim > 0.01) {
          const g = document.createElement('div');
          g.className = 'evTLGhost evTLGhost--trim';
          g.style.left  = Math.round(p.newEnd * _pps) + 'px';
          g.style.width = Math.max(2, Math.round(rightTrim * _pps)) + 'px';
          g.title = trimHint;
          _ghostLayer.appendChild(g);
        }
        // Dashed outline at proposed position
        const gp = document.createElement('div');
        gp.className = 'evTLGhost evTLGhost--proposed';
        gp.style.left  = Math.round(p.newStart * _pps) + 'px';
        gp.style.width = Math.max(3, Math.round((p.newEnd - p.newStart) * _pps)) + 'px';
        gp.title = 'Proposed boundary after edit';
        _ghostLayer.appendChild(gp);
      } else if (p.type === 'reorder' && Array.isArray(p.ids)) {
        p.ids.forEach((id, newIdx) => {
          const origIdx = (clips || []).findIndex(c => c.id === id);
          if (origIdx < 0 || origIdx === newIdx) return;
          const c = clipMap[id];
          if (!c) return;
          const g = document.createElement('div');
          g.className = 'evTLGhost evTLGhost--reorder';
          g.style.left  = Math.round(c.start * _pps) + 'px';
          g.style.width = Math.max(3, Math.round((c.end - c.start) * _pps)) + 'px';
          g.title = 'Clip will move to position ' + (newIdx + 1);
          const badge = document.createElement('span');
          badge.className = 'evTLGhostBadge';
          badge.textContent = '⟳';
          g.appendChild(badge);
          _ghostLayer.appendChild(g);
        });
      }
    });

    el.appendChild(_ghostLayer);
  }

  function clearGhosts() {
    if (_ghostLayer) {
      if (_ghostLayer.parentNode) _ghostLayer.parentNode.removeChild(_ghostLayer);
      _ghostLayer = null;
    }
  }

  // ── Playhead ──────────────────────────────────────────────
  function _updatePlayhead(t) {
    if (!_ph) return;
    const x = Math.round(t * _pps);
    _ph.style.setProperty('--ph-x', x + 'px');
    _autoScrollPlayhead(x);
  }

  // Keep playhead visible — only during active playback, not during scrub/drag
  function _autoScrollPlayhead(px) {
    if (!_scroll || !_inner) return;
    if (!EditorState.getState().isPlaying) return;
    const vw = _scroll.clientWidth - LABEL_W;
    if (vw <= 0) return;
    const viewLeft  = _scroll.scrollLeft;
    const viewRight = viewLeft + vw;
    const margin    = vw * 0.15;
    if (px < viewLeft + margin)       { _scroll.scrollLeft = Math.max(0, px - margin); }
    else if (px > viewRight - margin) { _scroll.scrollLeft = px - vw + margin; }
  }

  // ── Public helpers for interactions ──────────────────────
  function getScrollEl()     { return _scroll; }
  function getPlayheadEl()   { return _ph; }

  // Direct playhead update (used by interactions during drag — no state roundtrip)
  function updatePlayheadDirect(t) { _updatePlayhead(t); }

  // ── Lane registry (P1.6-D) ────────────────────────────────
  function getLanes() { return LANES.slice(); }

  // ── Destroy ───────────────────────────────────────────────
  function destroy() {
    if (_unsub) { _unsub(); _unsub = null; }
    if (_ro) { _ro.disconnect(); _ro = null; }
    if (_scroll && _onScrollFn) {
      _scroll.removeEventListener('scroll', _onScrollFn);
      _onScrollFn = null;
    }
    clearGhosts();
    _prevSelId   = null;
    _prevHovId   = null;
    _videoSrc    = null;
    _markerData  = [];
    _heatmapData = [];
    _root = null;
  }

  return {
    init,
    setDuration,
    setVideoSrc,
    fit,
    zoom,
    setZoom,
    getPxPerSec,
    getScrollOffsetSec,
    getScrollEl,
    getPlayheadEl,
    getLanes,
    updatePlayheadDirect,
    scrollToTime,
    renderClips,
    renderSubtitles,
    renderTextLayers,
    renderMarkers,
    renderHeatmap,
    renderGhosts,
    clearGhosts,
    destroy,
  };

})();
