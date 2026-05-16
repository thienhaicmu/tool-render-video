/* =========================================================
   editor-consensus.js  —  P3.6: Agent Debate & Consensus Intelligence
   Groups specialized agent outputs by creative direction,
   detects agreement and conflict, produces a consensus
   recommendation with explainable reasoning.

   Directions:
     aggressive — fasterPacing, strongerHook, viralMode, removeDeadSpace
     narrative  — cinematicMode
     clarity    — subtitleCleanup, smartClipPrioritization

   Agreement   → confidence boost, multi-agent label
   Conflict    → dissent note, optional compromise action
   Extreme     → creator clarification (returned as ambiguous: true path)

   Public API:
     EditorConsensus.resolve(signals) → debate object or null
     EditorConsensus.resolveFromLive(parts) → debate object or null
   ========================================================= */
'use strict';

window.EditorConsensus = (() => {

  // Creative direction groups
  const _AGGRESSIVE = new Set(['fasterPacing', 'strongerHook', 'viralMode', 'removeDeadSpace']);
  const _NARRATIVE  = new Set(['cinematicMode']);
  const _CLARITY    = new Set(['subtitleCleanup', 'smartClipPrioritization']);

  function _dirOf(action) {
    if (_AGGRESSIVE.has(action)) return 'aggressive';
    if (_NARRATIVE.has(action))  return 'narrative';
    if (_CLARITY.has(action))    return 'clarity';
    return 'other';
  }

  // When aggressive and narrative conflict, this is the compromise —
  // removes only dead air, preserves intentional pacing decisions.
  const _COMPROMISE = {
    aggressive_narrative: {
      action:        'removeDeadSpace',
      note:          'Removed dead air only — intentional pacing preserved for emotional impact.',
    },
    narrative_aggressive: {
      action:        'removeDeadSpace',
      note:          'Tightened silence only — breathing room around emotional beats kept intact.',
    },
  };

  const _ACTION_LABEL = {
    strongerHook:            'Stronger Hook',
    fasterPacing:            'Faster Pacing',
    removeDeadSpace:         'Remove Dead Air',
    viralMode:               'Viral Mode',
    cinematicMode:           'Cinematic Flow',
    subtitleCleanup:         'Subtitle Cleanup',
    smartClipPrioritization: 'Clip Prioritization',
  };

  // ── resolve ───────────────────────────────────────────────
  // Core debate engine. Runs all agents, groups by direction,
  // scores agreement and conflict, produces consensus output.
  function resolve(signals) {
    if (typeof EditorAgents === 'undefined') return null;
    const results = EditorAgents.runAll(signals);
    if (!results.length) return null;

    // Group by creative direction
    const groups = { aggressive: [], narrative: [], clarity: [], other: [] };
    results.forEach(r => groups[_dirOf(r.action)].push(r));

    // Select winning direction: highest total weighted confidence
    // Multi-agent bonus: each extra agent in a group adds 10% weight
    let bestDir = null, bestGroup = [], bestWeight = 0;
    ['aggressive', 'narrative', 'clarity', 'other'].forEach(dir => {
      const g = groups[dir];
      if (!g.length) return;
      const totalConf = g.reduce((s, r) => s + r.confidence, 0);
      const w         = totalConf * (1 + (g.length - 1) * 0.10);
      if (w > bestWeight) { bestWeight = w; bestDir = dir; bestGroup = [...g]; }
    });
    if (!bestDir || !bestGroup.length) return null;

    // Sort best group by confidence — top agent leads
    bestGroup.sort((a, b) => b.confidence - a.confidence);
    const topAgent    = bestGroup[0];
    const agreeCount  = bestGroup.length;

    // Agreement score: fraction of active agents on this side
    const agreementScore = agreeCount / results.length;

    // Opposing direction for conflict detection
    const opposingDir  = bestDir === 'aggressive' ? 'narrative' : bestDir === 'narrative' ? 'aggressive' : null;
    const opposers     = opposingDir ? groups[opposingDir] : [];
    const bestConfSum  = bestGroup.reduce((s, r) => s + r.confidence, 0);
    const oppConfSum   = opposers.reduce((s, r)  => s + r.confidence, 0);
    const conflictLevel = opposers.length
      ? Math.min(1, oppConfSum / (bestConfSum + 0.01))
      : 0;

    // Confidence: boosted by agreement, reduced by conflict
    let confidence = topAgent.confidence;
    confidence    *= (1 + (agreeCount - 1) * 0.08); // +8% per extra ally
    confidence    *= (1 - conflictLevel * 0.10);     // max -10% for conflict pressure
    confidence     = Math.min(0.97, confidence);

    // Build ally label — names the agents on the winning side
    const allyLabel = agreeCount >= 2
      ? bestGroup.slice(0, 2).map(r => r.agentLabel).join(' + ')
      : topAgent.agentLabel;

    // Consensus message
    let consensusMsg;
    if (agreeCount >= 2) {
      consensusMsg = allyLabel + ' agree — ' + topAgent.reason;
    } else {
      consensusMsg = topAgent.agentLabel + ': ' + topAgent.reason;
    }

    // Dissent and compromise
    let dissentMsg    = null;
    let compromiseNote = null;
    let finalAction   = topAgent.action;
    const isExtremeConflict = conflictLevel > 0.45 && opposers.length && opposers[0].confidence >= 0.60;

    if (opposers.length) {
      const mainOpposer = opposers[0];
      dissentMsg = mainOpposer.agentLabel + ' preferred ' + (_ACTION_LABEL[mainOpposer.action] || mainOpposer.action) + '.';

      if (isExtremeConflict) {
        const compKey = bestDir + '_' + opposingDir;
        const comp    = _COMPROMISE[compKey];
        if (comp && comp.action !== topAgent.action) {
          // Both sides are strong — apply compromise action
          finalAction    = comp.action;
          compromiseNote = comp.note;
          confidence    *= 0.93; // slight penalty for compromise uncertainty
        } else {
          // Same action wins but acknowledge concern
          compromiseNote = topAgent.agentLabel + ' priority maintained — ' + mainOpposer.agentLabel + '\'s concern noted.';
        }
      }
    }

    // Conflict options for clarification (extreme conflict path in conversation)
    const conflictOptions = isExtremeConflict ? [
      {
        label:          _ACTION_LABEL[topAgent.action]        || topAgent.action,
        action:         topAgent.action,
        interpretation: topAgent.reason.substring(0, 85),
        desc:           '',
      },
      {
        label:          _ACTION_LABEL[opposers[0].action] || opposers[0].action,
        action:         opposers[0].action,
        interpretation: opposers[0].reason.substring(0, 85),
        desc:           '',
      },
    ] : null;

    return {
      action:           finalAction,
      confidence:       Math.min(0.97, confidence),
      agreementScore,
      conflictLevel,
      allyLabel,
      consensus:        consensusMsg,
      dissent:          dissentMsg,
      compromiseNote,
      isExtremeConflict,
      conflictOptions,
      agentResults:     results,
    };
  }

  // Convenience: builds signals from live sources then resolves.
  // parts: optional render parts array for Viral Agent.
  function resolveFromLive(parts) {
    if (typeof EditorAgents === 'undefined') return null;
    return resolve(EditorAgents.buildSignals(Array.isArray(parts) ? parts : []));
  }

  return { resolve, resolveFromLive };

})();
