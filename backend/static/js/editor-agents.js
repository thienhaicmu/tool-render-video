/* =========================================================
   editor-agents.js  —  P3.5: Multi-Agent Editing System
   Five specialized editing agents — pure data, no DOM.
   Each agent reads real signals only: scene markers,
   review scores, creator taste. No invented intelligence.

   Public API:
     EditorAgents.runAll(signals)              → sorted recommendation array
     EditorAgents.getTopRecommendation(signals) → single best rec or null
     EditorAgents.getPillLabels(signals)        → [{agentLabel, tier, action}]
     EditorAgents.buildSignals(parts)           → signals object from live sources
   ========================================================= */
'use strict';

window.EditorAgents = (() => {

  // ── 1. Hook Agent ─────────────────────────────────────────
  // Goal: maximize opening retention.
  // Signals: weak-intro marker, hookScore from review intelligence.
  function _runHookAgent(signals) {
    const { markers, analysis, taste } = signals;
    const weakIntro  = markers.some(m => m.type === 'weak-intro');
    const hookScore  = analysis ? (analysis.hookScore || 0) : 0;

    if (!weakIntro && hookScore >= 0.55) return null;

    let confidence, reason;
    if (weakIntro && hookScore < 0.55) {
      confidence = 0.87;
      reason     = 'Opening clip is below engagement threshold — first impression needs a stronger hook.';
    } else if (weakIntro) {
      confidence = 0.82;
      reason     = 'Low-energy opening detected — promoting a stronger first clip will lift retention.';
    } else {
      confidence = 0.62;
      reason     = 'Hook score at ' + Math.round(hookScore * 100) + '% — opening could be stronger.';
    }

    // Taste weight: aggressive hook preference amplifies urgency
    if (taste && taste.confident && taste.hook === 'aggressive') {
      confidence = Math.min(0.97, confidence + 0.09);
    }

    if (confidence < 0.55) return null;
    return { agentName: 'hook', agentLabel: 'Hook Agent', action: 'strongerHook', confidence, reason };
  }

  // ── 2. Pacing Agent ───────────────────────────────────────
  // Goal: improve rhythm across the timeline.
  // Signals: pacing-drop markers, silence zones.
  function _runPacingAgent(signals) {
    const { markers, silences, taste } = signals;
    const pacingDrop = markers.some(m => m.type === 'pacing-drop');
    const longGaps   = silences.filter(s => s.duration > 2).length;
    const deadZones  = silences.filter(s => s.duration > 0.8).length;

    if (!pacingDrop && longGaps === 0 && deadZones < 2) return null;

    let action, confidence, reason;
    if (longGaps >= 2 || deadZones >= 3) {
      action     = 'removeDeadSpace';
      confidence = 0.88;
      reason     = deadZones + ' silence zone' + (deadZones !== 1 ? 's' : '') + ' detected — dead air is diluting momentum.';
    } else if (pacingDrop) {
      action     = 'fasterPacing';
      confidence = 0.74;
      reason     = 'Long clip detected — its runtime is softening overall pacing.';
    } else {
      action     = 'fasterPacing';
      confidence = 0.62;
      reason     = 'Pacing inconsistency across the timeline — tightening will improve viewer rhythm.';
    }

    if (taste && taste.confident && taste.pace === 'fast') {
      confidence = Math.min(0.97, confidence + 0.08);
    }

    if (confidence < 0.55) return null;
    return { agentName: 'pacing', agentLabel: 'Pacing Agent', action, confidence, reason };
  }

  // ── 3. Subtitle Agent ─────────────────────────────────────
  // Goal: clarity and readability.
  // Signals: subtitle-overload marker, badSubCount from review intelligence.
  function _runSubtitleAgent(signals) {
    const { markers, analysis, taste } = signals;
    const overload    = markers.some(m => m.type === 'subtitle-overload');
    const badSubCount = analysis ? (analysis.badSubCount || 0) : 0;

    if (!overload && badSubCount < 3) return null;

    let confidence, reason;
    if (overload && badSubCount >= 3) {
      confidence = 0.84;
      reason     = 'Subtitle overload zone and ' + badSubCount + ' dense captions detected — readability is impacted.';
    } else if (overload) {
      confidence = 0.79;
      reason     = 'Subtitle density is too high in this section — viewer attention is split.';
    } else {
      confidence = 0.65;
      reason     = badSubCount + ' subtitles exceed readable density — cleanup will improve clarity.';
    }

    // Educational creators care more about text clarity
    if (taste && taste.confident && taste.editStyle === 'educational') {
      confidence = Math.min(0.97, confidence + 0.12);
    }

    if (confidence < 0.55) return null;
    return { agentName: 'subtitle', agentLabel: 'Subtitle Agent', action: 'subtitleCleanup', confidence, reason };
  }

  // ── 4. Emotion Agent ──────────────────────────────────────
  // Goal: maximize emotional impact.
  // Signals: emotional-shift markers, reaction-emphasis, avg emotion from review.
  function _runEmotionAgent(signals) {
    const { markers, analysis, taste } = signals;
    const shiftCount = markers.filter(m => m.type === 'emotional-shift').length;
    const hasPeak    = markers.some(m => m.type === 'reaction-emphasis');

    let avgEmotion = 0;
    const partScores = analysis ? (analysis.partScores || {}) : {};
    const partCount  = Object.keys(partScores).length;
    if (partCount) {
      const scores = Object.values(partScores).map(s => s.emotion || 0);
      avgEmotion   = scores.reduce((a, b) => a + b, 0) / scores.length;
    }

    const weakEmotion = partCount >= 3 && avgEmotion < 0.55;
    if (shiftCount < 2 && !hasPeak && !weakEmotion) return null;

    let confidence, reason;
    if (shiftCount >= 2) {
      confidence = 0.70;
      reason     = shiftCount + ' abrupt energy drops detected — narrative arc feels choppy.';
    } else if (weakEmotion) {
      confidence = 0.62;
      reason     = 'Emotional resonance below threshold — cinematic ordering may deepen impact.';
    } else {
      confidence = 0.58;
      reason     = 'Strong emotional peak identified — cinematic framing can amplify it.';
    }

    if (taste && taste.confident && taste.editStyle === 'cinematic') {
      confidence = Math.min(0.97, confidence + 0.12);
    }

    if (confidence < 0.55) return null;
    return { agentName: 'emotion', agentLabel: 'Emotion Agent', action: 'cinematicMode', confidence, reason };
  }

  // ── 5. Viral Agent ────────────────────────────────────────
  // Goal: maximize engagement signal.
  // Signals: retentionRisks, retentionScore from review, viral_score from parts.
  function _runViralAgent(signals) {
    const { analysis, taste, parts } = signals;
    const riskCount      = analysis ? (analysis.retentionRisks || []).length : 0;
    const retentionScore = analysis ? (analysis.retentionScore || 0) : 0;

    const completedParts = parts.filter(p => {
      const st = String(p.status || '').toLowerCase();
      return st === 'done' || st === 'completed' || st === 'complete';
    });
    const avgViralPct = completedParts.length
      ? Math.round(completedParts.reduce((s, p) => s + (Number(p.viral_score) || 0), 0) / completedParts.length * 100)
      : null;

    const hasSignal = riskCount >= 2 || retentionScore < 0.5 || (avgViralPct !== null && avgViralPct < 50);
    if (!hasSignal) return null;

    let action, confidence, reason;
    if (riskCount >= 3) {
      action     = 'smartClipPrioritization';
      confidence = 0.78;
      reason     = riskCount + ' clips below retention threshold — AI prioritization can surface stronger moments.';
    } else if (avgViralPct !== null && avgViralPct < 50) {
      action     = 'viralMode';
      confidence = 0.71;
      reason     = 'Avg render score ' + avgViralPct + '% — viral reorder can improve the engagement signal.';
    } else {
      action     = 'viralMode';
      confidence = 0.63;
      reason     = 'Retention signal below engagement threshold — viral optimization is recommended.';
    }

    if (taste && taste.confident && taste.editStyle === 'viral') {
      confidence = Math.min(0.97, confidence + 0.10);
    }

    if (confidence < 0.55) return null;
    return { agentName: 'viral', agentLabel: 'Viral Agent', action, confidence, reason };
  }

  // ── Consensus engine ──────────────────────────────────────
  // Runs all agents, returns sorted by confidence descending.
  // Silent agents (null) are excluded. No hallucination.
  function runAll(signals) {
    return [
      _runHookAgent(signals),
      _runPacingAgent(signals),
      _runSubtitleAgent(signals),
      _runEmotionAgent(signals),
      _runViralAgent(signals),
    ].filter(Boolean).sort((a, b) => b.confidence - a.confidence);
  }

  function getTopRecommendation(signals) {
    return runAll(signals)[0] || null;
  }

  // Returns pill metadata for up to 3 active agents.
  function getPillLabels(signals) {
    return runAll(signals).slice(0, 3).map(r => ({
      agentLabel: r.agentLabel,
      tier:       r.confidence >= 0.80 ? 'high' : r.confidence >= 0.65 ? 'moderate' : 'low',
      action:     r.action,
    }));
  }

  // Assembles signals from live data sources.
  // parts: optional array of render parts (for Viral Agent).
  function buildSignals(parts) {
    const scene  = (typeof EditorSceneIntelligence  !== 'undefined') ? (EditorSceneIntelligence.getLatest()     || {}) : {};
    const review = (typeof EditorReviewIntelligence !== 'undefined') ? (EditorReviewIntelligence.getReviewData() || null) : null;
    const taste  = (typeof CreatorMemory            !== 'undefined') ? CreatorMemory.getTasteModel()            : null;
    return {
      markers:  scene.markers  || [],
      scenes:   scene.scenes   || [],
      silences: scene.silences || [],
      analysis: review,
      taste,
      parts:    Array.isArray(parts) ? parts : [],
    };
  }

  return { runAll, getTopRecommendation, getPillLabels, buildSignals };

})();
