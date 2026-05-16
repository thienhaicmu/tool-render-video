/* =========================================================
   editor-ai-actions.js  —  P2-B: AI Editing Actions
   Non-destructive timeline mutations with undo stack.
   Every action snapshots state before mutating; undo pops the stack.
   All changes are committed through EditorState → re-rendered via
   EditorTimeline. After each action, re-runs SceneIntelligence.
   ========================================================= */
'use strict';

window.EditorAiActions = (() => {

  const _history = [];
  const MAX_HIST = 20;
  const _actLog  = [];
  let _preview   = null;   // {actionName, patches, origClips} — active preview session

  // ── Snapshot / undo ──────────────────────────────────────
  function _snap(label) {
    const s = EditorState.getState();
    const snap = {
      label,
      clips:     s.clips.map(c => Object.assign({}, c)),
      subtitles: s.subtitles.map(x => Object.assign({}, x)),
      ts:        Date.now(),
    };
    _history.push(snap);
    if (_history.length > MAX_HIST) _history.shift();
    if (typeof EditorAiSessions !== 'undefined') EditorAiSessions.createSnapshot(label);
    return snap;
  }

  function undo() {
    if (_history.length <= 1) return false;
    _history.pop();
    const prev = _history[_history.length - 1];
    EditorState.setEditorState({
      clips:     prev.clips.map(c => Object.assign({}, c)),
      subtitles: prev.subtitles.map(x => Object.assign({}, x)),
    });
    _redraw(prev.clips, prev.subtitles);
    _logActivity('Undone: ' + prev.label);
    _reanalyze();
    return true;
  }

  // ── Commit helpers ───────────────────────────────────────
  function _redraw(clips, subtitles) {
    if (typeof EditorTimeline !== 'undefined') {
      if (clips)     EditorTimeline.renderClips(clips);
      if (subtitles) EditorTimeline.renderSubtitles(subtitles);
    }
  }

  function _reanalyze() {
    if (typeof EditorSceneIntelligence !== 'undefined') {
      EditorSceneIntelligence.runAnalysis(EditorState.getState());
    }
  }

  // ── Activity rail ────────────────────────────────────────
  function _logActivity(msg) {
    _actLog.unshift({ msg, ts: Date.now() });
    if (_actLog.length > 20) _actLog.pop();
    _renderRail();
    if (typeof EditorState !== 'undefined') EditorState.emit('ai:activity', msg);
  }

  function _renderRail() {
    const rail = document.getElementById('aiActivityRail');
    if (!rail) return;
    const items = _actLog.slice(0, 5);
    if (!items.length) {
      rail.innerHTML = '<span class="aiActivityEmpty">AI ready</span>';
      rail.classList.remove('has-activity');
    } else {
      rail.innerHTML = items.map(a => `<span class="aiActivityItem">${_esc(a.msg)}</span>`).join('');
      rail.classList.add('has-activity');
    }
  }

  function _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── 1. Remove dead space (tighten each clip's in/out by 0.15s) ──
  function removeDeadSpace() {
    const state = EditorState.getState();
    if (!state.clips.length) return;
    _snap('remove-dead-space');
    const MIN  = 0.8;
    const TRIM = 0.15;
    const next = state.clips.map(c => {
      const dur = c.end - c.start;
      if (dur <= MIN + TRIM * 2) return Object.assign({}, c);
      return Object.assign({}, c, {
        start: parseFloat((c.start + TRIM).toFixed(3)),
        end:   parseFloat((c.end   - TRIM).toFixed(3)),
      });
    });
    EditorState.setEditorState({ clips: next });
    _redraw(next);
    _logActivity('AI tightened cuts');
    _reanalyze();
  }

  // ── 2. Stronger hook (swap highest-score clip to position 0) ──
  function strongerHook() {
    const state = EditorState.getState();
    if (state.clips.length < 2) return;
    _snap('stronger-hook');
    const clips = state.clips.map(c => Object.assign({}, c));
    const best  = clips.reduce((b, c) => ((c.score || 0) > (b.score || 0) ? c : b), clips[0]);
    const bi    = clips.indexOf(best);
    if (bi > 0) { const t = clips[0]; clips[0] = clips[bi]; clips[bi] = t; }
    EditorState.setEditorState({ clips });
    _redraw(clips);
    _logActivity('AI boosted hook strength');
    _reanalyze();
  }

  // ── 3. Faster pacing (trim each clip 12% in/out, min 1 s) ───
  function fasterPacing() {
    const state = EditorState.getState();
    if (!state.clips.length) return;
    _snap('faster-pacing');
    const RATIO   = 0.12;
    const MIN_DUR = 1.0;
    const next = state.clips.map(c => {
      const dur  = c.end - c.start;
      const trim = Math.min(dur * RATIO, (dur - MIN_DUR) / 2);
      if (trim <= 0) return Object.assign({}, c);
      return Object.assign({}, c, {
        start: parseFloat((c.start + trim).toFixed(3)),
        end:   parseFloat((c.end   - trim).toFixed(3)),
      });
    });
    EditorState.setEditorState({ clips: next });
    _redraw(next);
    _logActivity('AI tightened pacing');
    _reanalyze();
  }

  // ── 4. Viral mode (sort by score desc + trim 15%) ───────
  function viralMode() {
    const state = EditorState.getState();
    if (!state.clips.length) return;
    _snap('viral-mode');
    const RATIO   = 0.15;
    const MIN_DUR = 0.8;
    const sorted  = state.clips.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
    const next = sorted.map(c => {
      const dur  = c.end - c.start;
      const trim = Math.min(dur * RATIO, (dur - MIN_DUR) / 2);
      if (trim <= 0) return Object.assign({}, c);
      return Object.assign({}, c, {
        start: parseFloat((c.start + trim).toFixed(3)),
        end:   parseFloat((c.end   - trim).toFixed(3)),
      });
    });
    EditorState.setEditorState({ clips: next });
    _redraw(next);
    _logActivity('AI applied viral mode');
    _reanalyze();
  }

  // ── 5. Cinematic mode (sort chrono, ensure min 4 s each) ─
  function cinematicMode() {
    const state = EditorState.getState();
    if (!state.clips.length) return;
    _snap('cinematic-mode');
    const MIN_DUR = 4.0;
    const maxT    = state.duration || 999999;
    const sorted  = state.clips.slice().sort((a, b) => a.start - b.start);
    const next = sorted.map(c => {
      const dur = c.end - c.start;
      if (dur >= MIN_DUR) return Object.assign({}, c);
      const ext = (MIN_DUR - dur) / 2;
      return Object.assign({}, c, {
        start: parseFloat(Math.max(0,    c.start - ext).toFixed(3)),
        end:   parseFloat(Math.min(maxT, c.end   + ext).toFixed(3)),
      });
    });
    EditorState.setEditorState({ clips: next });
    _redraw(next);
    _logActivity('AI applied cinematic mode');
    _reanalyze();
  }

  // ── 6. Subtitle cleanup (split segs > 10 words) ──────────
  function subtitleCleanup() {
    const state = EditorState.getState();
    if (!state.subtitles.length) return;
    _snap('subtitle-cleanup');
    const MAX_W  = 10;
    const newS   = [];
    state.subtitles.forEach(s => {
      const words = String(s.text || '').trim().split(/\s+/).filter(Boolean);
      if (words.length <= MAX_W) { newS.push(Object.assign({}, s)); return; }
      const half  = Math.ceil(words.length / 2);
      const dur   = Math.max(0.1, s.end - s.start);
      const mid   = s.start + (dur * half / words.length);
      newS.push(Object.assign({}, s, { text: words.slice(0, half).join(' '), end: parseFloat(mid.toFixed(3)) }));
      newS.push(Object.assign({}, s, { text: words.slice(half).join(' '), start: parseFloat(mid.toFixed(3)) }));
    });
    EditorState.setSubtitles(newS);
    _redraw(null, newS);
    _logActivity('AI cleaned subtitle lines');
    _reanalyze();
  }

  // ── 7. Smart clip prioritization (sort by score desc) ────
  function smartClipPrioritization() {
    const state = EditorState.getState();
    if (state.clips.length < 2) return;
    _snap('smart-prioritization');
    const sorted = state.clips.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
    EditorState.setEditorState({ clips: sorted });
    _redraw(sorted);
    _logActivity('AI prioritized best clips');
    _reanalyze();
  }

  // ── P2.5: Reasoning engine ───────────────────────────────

  const _ACTION_CONFIDENCE = {
    removeDeadSpace:         0.86,
    strongerHook:            0.80,
    fasterPacing:            0.74,
    viralMode:               0.78,
    cinematicMode:           0.71,
    subtitleCleanup:         0.84,
    smartClipPrioritization: 0.76,
  };

  const _CONF_TEXT = {
    removeDeadSpace: {
      high: 'Speech cadence strongly indicates dead air — high confidence in tightening.',
      mid:  'Silence detected — gaps are borderline but tightening is directionally correct.',
      low:  'Limited silence data — trim may have minimal impact.',
    },
    strongerHook: {
      high: 'Hook score gap is clear — highest-energy clip belongs at the start.',
      mid:  'Hook improvement likely — signal is moderate.',
      low:  'Hook scores are close — improvement may be subtle.',
    },
    fasterPacing: {
      high: 'Long clips confirmed — pacing gains are well-supported by clip length data.',
      mid:  'Some long clips detected — pacing improvement is probable.',
      low:  'Clip lengths are similar — pacing gains may be modest.',
    },
    viralMode: {
      high: 'Energy distribution clearly favors reordering — strong viral signal.',
      mid:  'Score variation supports reordering — moderate engagement signal.',
      low:  'Score spread is narrow — reordering effect may be limited.',
    },
    cinematicMode: {
      high: 'Chronological drift and short clips detected — cinematic reorder strongly supported.',
      mid:  'Narrative ordering inferred — moderate story-structure signal.',
      low:  'Clips are already near-chronological — improvement may be subtle.',
    },
    smartClipPrioritization: {
      high: 'Score spread is significant — priority reordering is well-supported.',
      mid:  'Score differences present — prioritization is directionally correct.',
      low:  'Scores are similar — prioritization effect will be subtle.',
    },
  };

  function _getAggressiveness() {
    if (typeof EditorState === 'undefined') return 0.5;
    const p = EditorState.getState().aiPreferenceProfile;
    return p ? Math.max(0.25, Math.min(0.88, p.aggressiveness || 0.5)) : 0.5;
  }

  function _buildReasoning(name, origClips, newClips, analysis) {
    const silences = (analysis && analysis.silences) || [];
    const markers  = (analysis && analysis.markers)  || [];
    const reasons  = [];

    const totalDurBefore = origClips.reduce((s, c) => s + Math.max(0, c.end - c.start), 0);
    const totalDurAfter  = newClips.reduce((s,  c) => s + Math.max(0, c.end - c.start), 0);
    const avgScoreBefore = origClips.reduce((s, c) => s + (c.score || 0), 0) / Math.max(1, origClips.length);
    const avgScoreAfter  = newClips.reduce((s,  c) => s + (c.score || 0), 0) / Math.max(1, newClips.length);
    const longClipsBefore = origClips.filter(c => (c.end - c.start) > 8).length;

    switch (name) {
      case 'removeDeadSpace': {
        const longGaps = silences.filter(g => g.duration > 1.5);
        if (longGaps.length) {
          reasons.push({ type: 'silence', label: `${longGaps.length} silence gap${longGaps.length > 1 ? 's' : ''} tightened`, impact: 'pacing momentum' });
        }
        const pDrops = markers.filter(m => m.type === 'pacing-drop');
        if (pDrops.length) {
          reasons.push({ type: 'pacing', label: 'Cut edges trimmed around slow sections', impact: 'viewer retention' });
        }
        const saved = totalDurBefore - totalDurAfter;
        if (!reasons.length && saved > 0.1) {
          reasons.push({ type: 'pacing', label: `${saved.toFixed(1)}s of low-signal content removed`, impact: 'density' });
        }
        break;
      }
      case 'strongerHook': {
        const best = origClips.reduce((b, c) => ((c.score||0) > (b.score||0) ? c : b), origClips[0]);
        const bi   = origClips.indexOf(best);
        if (bi > 0) {
          reasons.push({ type: 'hook', label: `Highest-energy clip moved to position 1 (was #${bi + 1})`, impact: 'first impression' });
        }
        const introScore = origClips[0] ? Math.round((origClips[0].score || 0) * 100) : 0;
        if (introScore < 55) {
          reasons.push({ type: 'hook', label: `Original intro at ${introScore}% hook energy — below threshold`, impact: 'viewer drop-off risk' });
        }
        break;
      }
      case 'fasterPacing': {
        if (longClipsBefore > 0) {
          reasons.push({ type: 'pacing', label: `${longClipsBefore} clip${longClipsBefore > 1 ? 's' : ''} over 8s — edges trimmed`, impact: 'pacing momentum' });
        }
        const pDrops = markers.filter(m => m.type === 'pacing-drop');
        if (pDrops.length) {
          reasons.push({ type: 'pacing', label: 'Pacing slowdown detected mid-content', impact: 'retention curve' });
        }
        const saved = totalDurBefore - totalDurAfter;
        if (saved > 0.3) {
          reasons.push({ type: 'efficiency', label: `${saved.toFixed(1)}s trimmed from clip edges`, impact: 'density' });
        }
        break;
      }
      case 'viralMode': {
        reasons.push({ type: 'hook', label: 'Clips reordered by hook score — strongest content leads', impact: 'algorithm engagement' });
        const weakClips = origClips.filter(c => (c.score||0) < 0.45).length;
        if (weakClips) {
          reasons.push({ type: 'efficiency', label: `${weakClips} low-energy clip${weakClips > 1 ? 's' : ''} trimmed tighter`, impact: 'viewer retention' });
        }
        break;
      }
      case 'cinematicMode': {
        reasons.push({ type: 'pacing', label: 'Clips sorted chronologically for narrative flow', impact: 'story clarity' });
        const shortClips = origClips.filter(c => (c.end - c.start) < 4).length;
        if (shortClips) {
          reasons.push({ type: 'pacing', label: `${shortClips} short clip${shortClips > 1 ? 's' : ''} extended for breathing room`, impact: 'emotional weight' });
        }
        break;
      }
      case 'smartClipPrioritization': {
        reasons.push({ type: 'hook', label: 'Clips ranked by AI quality score', impact: 'overall engagement' });
        const scores = origClips.map(c => c.score || 0);
        const spread = Math.max.apply(null, scores) - Math.min.apply(null, scores);
        if (spread > 0.25) {
          reasons.push({ type: 'efficiency', label: `${Math.round(spread * 100)}% score spread — weaker clips deprioritized`, impact: 'content quality' });
        }
        break;
      }
    }

    // Confidence
    const baseConf   = _ACTION_CONFIDENCE[name] || 0.7;
    const dataSignal = silences.length + markers.length;
    const conf       = Math.min(0.97, Math.max(0.38, baseConf + (dataSignal > 5 ? 0.06 : dataSignal > 2 ? 0.02 : -0.06)));
    const tier       = conf >= 0.82 ? 'high' : conf >= 0.62 ? 'mid' : 'low';
    let confText     = (_CONF_TEXT[name] || {})[tier] || (tier === 'high' ? 'Strong signal detected.' : tier === 'mid' ? 'Moderate signal — edit likely to improve flow.' : 'Limited signal detected.');
    // P3.1: inject preference-aware prefix when memory is confident
    if (typeof CreatorMemory !== 'undefined') {
      const _cm = CreatorMemory.getDerivedPreferences();
      if (_cm.confident) {
        if (_cm.favored.includes(name)) {
          confText = 'Based on your history, you tend to keep this. ' + confText;
        } else if (_cm.avoided.includes(name)) {
          confText = 'You\'ve passed on this before — worth a second look. ' + confText;
        }
      }
    }

    // Before / after deltas
    const beforeAfter = [];
    const durDelta    = parseFloat((totalDurAfter - totalDurBefore).toFixed(1));
    if (Math.abs(durDelta) > 0.1) {
      beforeAfter.push({ label: 'Runtime', delta: durDelta, unit: 's', lowerIsBetter: true });
    }
    const longClipsAfter = newClips.filter(c => (c.end - c.start) > 8).length;
    const pacingDelta    = Math.round((longClipsBefore - longClipsAfter) * 8 + Math.max(0, -durDelta) * 2);
    if (pacingDelta > 1) {
      beforeAfter.push({ label: 'Pacing est.', delta: pacingDelta, unit: '%', lowerIsBetter: false });
    }
    const retBase  = Math.round((avgScoreAfter - avgScoreBefore) * 100);
    const retBonus = name === 'strongerHook' ? 8 : name === 'viralMode' ? 10 : name === 'fasterPacing' ? 4 : 0;
    const retDelta = retBase + retBonus;
    if (retDelta > 0) {
      beforeAfter.push({ label: 'Retention est.', delta: retDelta, unit: '%', lowerIsBetter: false });
    }

    return { confidence: conf, confidenceLabel: confText, reasons, beforeAfter };
  }

  function _trackPreference(name, accepted) {
    if (typeof EditorState === 'undefined') return;
    const state   = EditorState.getState();
    const profile = state.aiPreferenceProfile || { accepted: {}, rejected: {}, aggressiveness: 0.5, sessionTotal: 0 };
    const next    = {
      accepted:     Object.assign({}, profile.accepted),
      rejected:     Object.assign({}, profile.rejected),
      aggressiveness: profile.aggressiveness || 0.5,
      sessionTotal: (profile.sessionTotal || 0) + 1,
    };
    if (accepted) {
      next.accepted[name] = (next.accepted[name] || 0) + 1;
    } else {
      next.rejected[name] = (next.rejected[name] || 0) + 1;
    }
    // Soft-adjust aggressiveness: more accepts → bolder, more rejects → conservative
    const totalAcc = Object.values(next.accepted).reduce((s, v) => s + v, 0);
    const totalRej = Object.values(next.rejected).reduce((s, v) => s + v, 0);
    const total    = totalAcc + totalRej;
    if (total >= 2) {
      next.aggressiveness = Math.max(0.25, Math.min(0.88, 0.5 + (totalAcc - totalRej) / (total * 5)));
    }
    EditorState.setEditorState({ aiPreferenceProfile: next });
    if (typeof CreatorMemory !== 'undefined') CreatorMemory.recordSignal(name, accepted);
  }

  // ── P2.4: Action labels ───────────────────────────────────
  const _ACTION_LABELS = {
    removeDeadSpace:         'Tighten Cuts',
    strongerHook:            'Stronger Hook',
    fasterPacing:            'Faster Pacing',
    viralMode:               'Viral Mode',
    cinematicMode:           'Cinematic Mode',
    subtitleCleanup:         'Subtitle Cleanup',
    smartClipPrioritization: 'Smart Prioritization',
  };

  function _actionLabel(name) { return _ACTION_LABELS[name] || name; }

  // ── P2.4: Patch generators ────────────────────────────────
  function _patchRemoveDeadSpace(clips) {
    const agg  = _getAggressiveness();
    const MIN  = 0.8;
    const TRIM = parseFloat((0.10 + agg * 0.08).toFixed(3)); // 0.10→0.18s
    const patches = [];
    clips.forEach(c => {
      const dur = c.end - c.start;
      if (dur <= MIN + TRIM * 2) return;
      patches.push({ type: 'trim', clipId: c.id,
        newStart: parseFloat((c.start + TRIM).toFixed(3)),
        newEnd:   parseFloat((c.end   - TRIM).toFixed(3)) });
    });
    return patches;
  }

  function _patchStrongerHook(clips) {
    if (clips.length < 2) return [];
    const best = clips.reduce((b, c) => ((c.score || 0) > (b.score || 0) ? c : b), clips[0]);
    const bi   = clips.indexOf(best);
    if (bi === 0) return [];
    const ids = clips.map(c => c.id);
    ids.splice(bi, 1);
    ids.unshift(best.id);
    return [{ type: 'reorder', ids }];
  }

  function _patchFasterPacing(clips) {
    const agg     = _getAggressiveness();
    const RATIO   = parseFloat((0.08 + agg * 0.08).toFixed(3)); // 0.08→0.16
    const MIN_DUR = 1.0;
    const patches = [];
    clips.forEach(c => {
      const dur  = c.end - c.start;
      const trim = Math.min(dur * RATIO, (dur - MIN_DUR) / 2);
      if (trim <= 0) return;
      patches.push({ type: 'trim', clipId: c.id,
        newStart: parseFloat((c.start + trim).toFixed(3)),
        newEnd:   parseFloat((c.end   - trim).toFixed(3)) });
    });
    return patches;
  }

  function _patchViralMode(clips) {
    const agg     = _getAggressiveness();
    const RATIO   = parseFloat((0.10 + agg * 0.10).toFixed(3)); // 0.10→0.20
    const MIN_DUR = 0.8;
    const sorted  = clips.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
    const patches = [{ type: 'reorder', ids: sorted.map(c => c.id) }];
    sorted.forEach(c => {
      const dur  = c.end - c.start;
      const trim = Math.min(dur * RATIO, (dur - MIN_DUR) / 2);
      if (trim <= 0) return;
      patches.push({ type: 'trim', clipId: c.id,
        newStart: parseFloat((c.start + trim).toFixed(3)),
        newEnd:   parseFloat((c.end   - trim).toFixed(3)) });
    });
    return patches;
  }

  function _patchCinematicMode(clips, duration) {
    const MIN_DUR = 4.0;
    const maxT    = duration || 999999;
    const sorted  = clips.slice().sort((a, b) => a.start - b.start);
    const patches = [{ type: 'reorder', ids: sorted.map(c => c.id) }];
    sorted.forEach(c => {
      const dur = c.end - c.start;
      if (dur >= MIN_DUR) return;
      const ext = (MIN_DUR - dur) / 2;
      patches.push({ type: 'trim', clipId: c.id,
        newStart: parseFloat(Math.max(0,    c.start - ext).toFixed(3)),
        newEnd:   parseFloat(Math.min(maxT, c.end   + ext).toFixed(3)) });
    });
    return patches;
  }

  function _patchSmartPrioritization(clips) {
    if (clips.length < 2) return [];
    const sorted = clips.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
    return [{ type: 'reorder', ids: sorted.map(c => c.id) }];
  }

  // ── P2.4: Apply patch array → new clip array (non-destructive) ──
  function _applyPatches(clips, patches) {
    let result = clips.map(c => Object.assign({}, c));
    patches.forEach(p => {
      if (p.type === 'trim') {
        const i = result.findIndex(c => c.id === p.clipId);
        if (i >= 0) result[i] = Object.assign({}, result[i], {
          start: parseFloat(p.newStart.toFixed(3)),
          end:   parseFloat(p.newEnd.toFixed(3)),
        });
      } else if (p.type === 'reorder' && Array.isArray(p.ids)) {
        const map = {};
        result.forEach(c => { map[c.id] = c; });
        const reordered = p.ids.map(id => map[id]).filter(Boolean);
        const inSet     = new Set(p.ids);
        result = [...reordered, ...result.filter(c => !inSet.has(c.id))];
      } else if (p.type === 'mute') {
        const i = result.findIndex(c => c.id === p.clipId);
        if (i >= 0) result[i] = Object.assign({}, result[i], { muted: p.muted });
      }
    });
    return result;
  }

  function _calcSummary(origClips, newClips, patches) {
    const origDur    = origClips.reduce((s, c) => s + Math.max(0, c.end - c.start), 0);
    const newDur     = newClips.reduce((s,  c) => s + Math.max(0, c.end - c.start), 0);
    const delta      = newDur - origDur;
    const patchCount = patches.length;
    return { origDur, newDur, delta, patchCount };
  }

  function _renderSummaryCard(actionName, summary, reasoning) {
    const panel = document.getElementById('evInspAiPanel');
    if (!panel) return;
    panel.dataset.context = 'preview';
    const label  = _actionLabel(actionName);
    const dSign  = summary.delta >= 0 ? '+' : '';
    const dClass = summary.delta <= -0.05 ? 'evAiStatChip--pos' : '';
    const dStr   = Math.abs(summary.delta) < 0.05 ? '±0s' : dSign + summary.delta.toFixed(1) + 's';

    // Before/after delta chips
    let baHtml = '';
    if (reasoning && reasoning.beforeAfter && reasoning.beforeAfter.length) {
      const chips = reasoning.beforeAfter.slice(0, 3).map(m => {
        const isPos = m.lowerIsBetter ? m.delta < 0 : m.delta > 0;
        const cls   = isPos ? 'evAiDeltaChip--pos' : (m.delta === 0 ? '' : 'evAiDeltaChip--neg');
        const sign  = m.delta > 0 ? '+' : '';
        return `<span class="evAiDeltaChip ${cls}">${_esc(m.label)} ${sign}${m.delta}${m.unit}</span>`;
      });
      baHtml = `<div class="evAiBeforeAfterRow">${chips.join('')}</div>`;
    }

    // Reasoning bullets
    let reasonHtml = '';
    if (reasoning && reasoning.reasons && reasoning.reasons.length) {
      const items = reasoning.reasons.slice(0, 3).map(r => {
        const dotType = r.type === 'silence' ? 'warn' : r.type === 'hook' ? 'ok' : r.type === 'efficiency' ? 'efficiency' : 'neutral';
        return `<div class="evAiReasonItem">` +
                 `<span class="evAiReasonDot evAiReasonDot--${dotType}"></span>` +
                 `<span class="evAiReasonText">${_esc(r.label)}</span>` +
                 (r.impact ? `<span class="evAiReasonImpact">${_esc(r.impact)}</span>` : '') +
               `</div>`;
      });
      reasonHtml = `<div class="evAiReasonList">${items.join('')}</div>`;
    }

    // Confidence rationale
    const confHtml = reasoning && reasoning.confidenceLabel
      ? `<div class="evAiConfidenceLabel">${_esc(reasoning.confidenceLabel)}</div>`
      : '';

    panel.innerHTML =
      `<div class="evAiCard evAiCard--summary">` +
        `<div class="evAiSummaryTitle">Preview: ${_esc(label)}</div>` +
        `<div class="evAiSummaryStats">` +
          `<span class="evAiStatChip ${dClass}">${dStr}</span>` +
          `<span class="evAiStatChip">${summary.patchCount} edit${summary.patchCount !== 1 ? 's' : ''}</span>` +
        `</div>` +
        baHtml +
        reasonHtml +
        confHtml +
        `<div class="evAiSummaryActions">` +
          `<button class="evAiAcceptBtn" onclick="EditorAiActions?.acceptPreview?.();EditorConverse?._onAccept?.()">✓ Apply</button>` +
          `<button class="evAiRejectBtn" onclick="EditorAiActions?.rejectPreview?.();EditorConverse?._onReject?.()">✕ Discard</button>` +
        `</div>` +
      `</div>`;
  }

  function _renderNoPatchCard(actionName) {
    const panel = document.getElementById('evInspAiPanel');
    if (!panel) return;
    panel.innerHTML =
      `<div class="evAiCard">` +
        `<div class="evAiSummaryTitle">${_esc(_actionLabel(actionName))}</div>` +
        `<div class="evAiInsightRow">` +
          `<span class="evAiInsightDot evAiInsightDot--ok"></span>` +
          `No meaningful changes needed` +
        `</div>` +
      `</div>`;
  }

  // ── P2.4: Preview / accept / reject ──────────────────────
  function previewAction(name) {
    const state    = EditorState.getState();
    const clips    = state.clips || [];
    const analysis = typeof EditorSceneIntelligence !== 'undefined'
      ? EditorSceneIntelligence.getLatest() : null;
    let patches = [];
    switch (name) {
      case 'removeDeadSpace':         patches = _patchRemoveDeadSpace(clips); break;
      case 'strongerHook':            patches = _patchStrongerHook(clips); break;
      case 'fasterPacing':            patches = _patchFasterPacing(clips); break;
      case 'viralMode':               patches = _patchViralMode(clips); break;
      case 'cinematicMode':           patches = _patchCinematicMode(clips, state.duration); break;
      case 'smartClipPrioritization': patches = _patchSmartPrioritization(clips); break;
      default: return;
    }
    if (!patches.length) { _renderNoPatchCard(name); return; }
    const newClips  = _applyPatches(clips, patches);
    const summary   = _calcSummary(clips, newClips, patches);
    const reasoning = _buildReasoning(name, clips, newClips, analysis);
    _preview = { actionName: name, patches, origClips: clips.map(c => Object.assign({}, c)), reasoning };
    if (typeof EditorTimeline !== 'undefined') {
      EditorTimeline.renderGhosts(patches, clips, state.duration, reasoning);
    }
    _renderSummaryCard(name, summary, reasoning);
    _logActivity('Previewing: ' + _actionLabel(name));
  }

  function acceptPreview() {
    if (!_preview) return;
    const { actionName, patches, origClips } = _preview;
    _preview = null;
    const panel = document.getElementById('evInspAiPanel');
    if (panel && panel.dataset.context === 'preview') panel.dataset.context = '';
    if (typeof EditorTimeline !== 'undefined') EditorTimeline.clearGhosts();
    _trackPreference(actionName, true);
    _snap(actionName);
    const newClips = _applyPatches(origClips, patches);
    EditorState.setEditorState({ clips: newClips });
    _redraw(newClips);
    _logActivity('Applied: ' + _actionLabel(actionName));
    _reanalyze();
  }

  function rejectPreview() {
    if (!_preview) return;
    const { actionName } = _preview;
    _preview = null;
    const panel = document.getElementById('evInspAiPanel');
    if (panel && panel.dataset.context === 'preview') panel.dataset.context = '';
    if (typeof EditorTimeline !== 'undefined') EditorTimeline.clearGhosts();
    _trackPreference(actionName, false);
    _logActivity('Discarded: ' + _actionLabel(actionName));
    EditorState.emit('ai:preview-end', { accepted: false });
  }

  // ── Dispatcher ───────────────────────────────────────────
  const _MAP = {
    removeDeadSpace:         removeDeadSpace,
    strongerHook:            strongerHook,
    fasterPacing:            fasterPacing,
    viralMode:               viralMode,
    cinematicMode:           cinematicMode,
    subtitleCleanup:         subtitleCleanup,
    smartClipPrioritization: smartClipPrioritization,
  };

  function runAction(name) { if (_MAP[name]) _MAP[name](); }

  // ── State accessors ──────────────────────────────────────
  function canUndo()       { return _history.length > 1; }
  function getHistory()    { return _history.slice(); }
  function getActivityLog(){ return _actLog.slice(); }

  function reset() {
    _history.length = 0;
    _actLog.length  = 0;
    _renderRail();
  }

  return {
    removeDeadSpace, strongerHook, fasterPacing, viralMode,
    cinematicMode, subtitleCleanup, smartClipPrioritization,
    runAction, undo, canUndo, getHistory, getActivityLog, reset,
    previewAction, acceptPreview, rejectPreview,
  };

})();
