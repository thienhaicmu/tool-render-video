/* =========================================================
   editor-scene-intelligence.js  —  P2-A: Timeline Intelligence
   Async scene-graph analysis derived from clips + subtitles.
   Results feed EditorState.sceneGraph / aiMarkers / aiSuggestions
   and drive EditorTimeline marker/heatmap overlays.
   ========================================================= */
'use strict';

window.EditorSceneIntelligence = (() => {

  let _analysis   = null;
  let _analysisId = 0;
  let _pending    = null;

  // ── 1. Silence / gap detection ───────────────────────────
  function _silences(clips) {
    const sorted = clips.slice().sort((a, b) => a.start - b.start);
    const gaps = [];
    for (let i = 1; i < sorted.length; i++) {
      const gap = sorted[i].start - sorted[i - 1].end;
      if (gap > 0.8) gaps.push({ start: sorted[i - 1].end, end: sorted[i].start, duration: gap });
    }
    return gaps;
  }

  // ── 2. Subtitle density zones ────────────────────────────
  function _subDensity(subtitles) {
    if (!subtitles.length) return [];
    const WIN  = 3; // 3-second window
    const maxT = subtitles[subtitles.length - 1].end || 0;
    const raw  = [];
    for (let t = 0; t < maxT - WIN; t += WIN) {
      const inWin  = subtitles.filter(s => s.start < t + WIN && s.end > t);
      const chars  = inWin.reduce((n, s) => n + (s.text || '').length, 0);
      const winDur = inWin.reduce((n, s) => n + Math.max(0.01, s.end - s.start), 0);
      if (inWin.length > 4 || (winDur > 0 && chars / winDur > 22)) {
        raw.push({ start: t, end: t + WIN });
      }
    }
    // Merge adjacent windows
    const merged = [];
    raw.forEach(z => {
      const prev = merged[merged.length - 1];
      if (prev && z.start <= prev.end) { prev.end = z.end; }
      else { merged.push(Object.assign({}, z)); }
    });
    return merged;
  }

  // ── 3. Energy heatmap ────────────────────────────────────
  function _heatmap(clips, duration) {
    const BUCKET = 1.0;
    const n      = Math.max(1, Math.ceil(duration / BUCKET));
    const total  = new Float32Array(n);
    const count  = new Int32Array(n);
    clips.forEach(c => {
      const si    = Math.max(0, Math.floor(c.start / BUCKET));
      const ei    = Math.min(n - 1, Math.ceil(c.end / BUCKET));
      const score = Math.max(0, c.score || 0);
      for (let i = si; i <= ei; i++) { total[i] += score; count[i]++; }
    });
    const map = [];
    for (let i = 0; i < n; i++) {
      map.push({
        start:  i * BUCKET,
        end:    Math.min(duration, (i + 1) * BUCKET),
        energy: count[i] > 0 ? total[i] / count[i] : 0,
      });
    }
    return map;
  }

  // ── 4. AI markers ────────────────────────────────────────
  function _markers(clips, silences, densityZones) {
    const sorted = clips.slice().sort((a, b) => a.start - b.start);
    const out    = [];

    // Intro quality
    if (sorted.length) {
      if ((sorted[0].score || 0) < 0.45) {
        out.push({ type: 'weak-intro',  time: sorted[0].start, label: 'Hook intensity low here', reasonHint: 'Consider moving a higher-energy clip to the start.' });
      } else {
        out.push({ type: 'hook',        time: sorted[0].start, label: 'Strong hook',              reasonHint: 'Opening energy holds viewer attention.' });
      }
    }

    // Best-energy clip (beyond the first)
    if (sorted.length > 1) {
      const best = sorted.slice(1).reduce((b, c) => ((c.score || 0) > (b.score || 0) ? c : b), sorted[1]);
      if ((best.score || 0) >= 0.72) {
        out.push({ type: 'energy-spike', time: best.start, label: 'Reaction spike', reasonHint: 'High visual energy — audience engagement likely peaks here.' });
      }
    }

    // Silence gaps > 2 s
    silences.filter(g => g.duration > 2).forEach(g => {
      out.push({ type: 'silence', time: g.start, duration: g.duration, label: g.duration.toFixed(1) + 's dead air', reasonHint: 'Silence gap may cause viewer drop-off.' });
    });

    // Long clips → pacing drop
    sorted.filter(c => (c.end - c.start) > 8).forEach(c => {
      out.push({ type: 'pacing-drop', time: c.start, label: 'Speech pacing slows here', reasonHint: 'Clip running long — consider trimming edges.' });
    });

    // Emotional shifts (score delta > 0.35 between adjacent clips)
    for (let i = 1; i < sorted.length; i++) {
      const prev  = sorted[i - 1];
      const cur   = sorted[i];
      const delta = (cur.score || 0) - (prev.score || 0);
      if (Math.abs(delta) > 0.35) {
        if (delta > 0) {
          // Score rises: attention recovery or reaction emphasis
          out.push({ type: 'attention-recovery', time: cur.start, label: 'Emotional lift', reasonHint: 'Energy recovers — audience attention likely increases.' });
        } else {
          out.push({ type: 'emotional-shift', time: cur.start, label: 'Tone shift', reasonHint: 'Abrupt drop in energy — pacing may feel jarring.' });
        }
      }
    }

    // Reaction emphasis: highest-energy clip after midpoint
    if (sorted.length >= 3) {
      const mid     = sorted[Math.floor(sorted.length / 2)].start;
      const second  = sorted.slice(Math.floor(sorted.length / 2)).reduce((b, c) => ((c.score||0) > (b.score||0) ? c : b), sorted[Math.floor(sorted.length / 2)]);
      if ((second.score || 0) >= 0.80) {
        out.push({ type: 'reaction-emphasis', time: second.start, label: 'Emotional peak', reasonHint: 'Strong reaction moment — consider positioning near end for maximum impact.' });
      }
    }

    // Subtitle overload regions
    densityZones.forEach(z => {
      out.push({ type: 'subtitle-overload', time: z.start, label: 'Subtitle density exceeds mobile readability', reasonHint: 'Too many words on screen — risk of viewer fatigue.' });
    });

    // Deduplicate: same type within 1.5 s
    const dedup = [];
    out.sort((a, b) => a.time - b.time).forEach(m => {
      const last = dedup[dedup.length - 1];
      if (last && last.type === m.type && Math.abs(m.time - last.time) < 1.5) return;
      dedup.push(m);
    });
    return dedup;
  }

  // ── 5. Scene grouping ────────────────────────────────────
  function _scenes(clips, subtitles) {
    const sorted = clips.slice().sort((a, b) => a.start - b.start);
    if (!sorted.length) return [];
    const groups = [];
    let cur = [sorted[0]];
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].start - sorted[i - 1].end > 3) { groups.push(cur); cur = []; }
      cur.push(sorted[i]);
    }
    groups.push(cur);
    return groups.map((grp, idx) => {
      const start  = grp[0].start;
      const end    = grp[grp.length - 1].end;
      const dur    = end - start;
      const energy = grp.reduce((s, c) => s + (c.score || 0), 0) / grp.length;
      const subs   = subtitles.filter(s => s.start >= start - 0.5 && s.end <= end + 0.5);
      const words  = subs.reduce((n, s) => n + String(s.text || '').split(/\s+/).filter(Boolean).length, 0);
      return {
        id:           'scene_' + idx,
        start,        end,
        energyScore:  parseFloat(energy.toFixed(3)),
        speechDensity: dur > 0 ? parseFloat((words / dur).toFixed(2)) : 0,
        clipCount:    grp.length,
        clips:        grp.map(c => c.id),
      };
    });
  }

  // ── 6. Suggestion chips ──────────────────────────────────
  function _suggestions(markers, silences) {
    const types = new Set(markers.map(m => m.type));
    const chips = [];
    if (types.has('weak-intro'))
      chips.push({ id: 'stronger-hook',    label: 'Stronger hook', action: 'strongerHook',            confidence: 0.82 });
    if (silences.filter(g => g.duration > 1).length >= 2)
      chips.push({ id: 'remove-dead-space', label: 'Tighten cuts',  action: 'removeDeadSpace',         confidence: 0.88 });
    if (types.has('pacing-drop'))
      chips.push({ id: 'faster-pacing',    label: 'Faster pacing', action: 'fasterPacing',            confidence: 0.74 });
    if (types.has('subtitle-overload'))
      chips.push({ id: 'subtitle-cleanup', label: 'Fix subtitles', action: 'subtitleCleanup',         confidence: 0.79 });
    return chips.slice(0, 4);
  }

  // ── Core analysis (synchronous, called off main thread via setTimeout) ──
  function _run(state) {
    const { clips, subtitles, duration } = state;
    if (!clips.length || !duration) return null;
    const silences     = _silences(clips);
    const densityZones = _subDensity(subtitles);
    const heatmap      = _heatmap(clips, duration);
    const markers      = _markers(clips, silences, densityZones);
    const scenes       = _scenes(clips, subtitles);
    const suggestions  = _suggestions(markers, silences);
    return { scenes, markers, heatmap, silences, suggestions };
  }

  // ── Chip DOM renderer ────────────────────────────────────
  function _renderChips(suggestions) {
    const el = document.getElementById('aiSuggestionChips');
    if (!el) return;
    if (!suggestions || !suggestions.length) { el.innerHTML = ''; return; }
    el.innerHTML = suggestions.map(s =>
      `<button class="aiSuggestionChip" data-action="${s.action}"` +
      ` onclick="EditorAiActions?.previewAction?.('${s.action}')"` +
      ` title="${Math.round((s.confidence || 0) * 100)}% confidence — click to preview">${s.label}</button>`
    ).join('');
  }

  // ── Public API ───────────────────────────────────────────
  function runAnalysis(state, onComplete) {
    const id = ++_analysisId;
    if (_pending) { clearTimeout(_pending); _pending = null; }
    _pending = setTimeout(() => {
      _pending = null;
      const result = _run(state);
      if (id !== _analysisId) return; // superseded
      _analysis = result;
      if (!result) return;

      if (typeof EditorState !== 'undefined') {
        EditorState.setEditorState({
          sceneGraph:    result.scenes,
          aiMarkers:     result.markers,
          aiSuggestions: result.suggestions,
        });
      }
      if (typeof EditorTimeline !== 'undefined') {
        EditorTimeline.renderMarkers(result.markers);
        EditorTimeline.renderHeatmap(result.heatmap);
      }
      _renderChips(result.suggestions);
      if (typeof onComplete === 'function') onComplete(result);
      if (typeof EditorState !== 'undefined') EditorState.emit('ai:analysis-complete', result);
    }, 100);
  }

  function getLatest() { return _analysis; }

  function reset() {
    _analysis = null;
    ++_analysisId;
    if (_pending) { clearTimeout(_pending); _pending = null; }
    _renderChips([]);
    if (typeof EditorTimeline !== 'undefined') {
      EditorTimeline.renderMarkers([]);
      EditorTimeline.renderHeatmap([]);
    }
    if (typeof EditorState !== 'undefined') {
      EditorState.setEditorState({ sceneGraph: [], aiMarkers: [], aiSuggestions: [] });
    }
  }

  return { runAnalysis, getLatest, reset };

})();
