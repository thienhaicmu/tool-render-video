/* =========================================================
   editor-runtime-intelligence.js  —  P3.4: Adaptive Runtime Intelligence
   Provides taste-aware editorial context during and after render.
   Called by RenderAiRuntime — no DOM access, pure data.
   All signals are real: viral_score from parts, taste from CreatorMemory.
   ========================================================= */
'use strict';

window.RuntimeIntelligence = (() => {

  function _taste() {
    return (typeof CreatorMemory !== 'undefined') ? CreatorMemory.getTasteModel() : null;
  }

  // ── getEvolutionContext ───────────────────────────────────
  // Returns editorial context for a single completed clip.
  // pNo: clip number (1-based), pct: viral score 0–100 or null, tier: 'high'|'mid'|'low'
  // Returns { why: string, tasteNote: string|null }
  function getEvolutionContext(pNo, pct, tier) {
    const taste    = _taste();
    const isHook   = pNo <= 2;
    const hasSignal = pct !== null;

    let why;
    if (tier === 'high') {
      if (taste && taste.confident && isHook && taste.hook === 'aggressive') {
        why = 'Strong hook — opening signal matches your high-intensity intro preference.';
      } else if (taste && taste.confident && taste.editStyle === 'viral') {
        why = 'High-energy signal — above your viral editing threshold.';
      } else if (taste && taste.confident && taste.pace === 'fast') {
        why = 'Strong clip — tight pacing holds through the cut.';
      } else {
        why = 'Strong hook from the first frame — this one is a keeper.';
      }
    } else if (tier === 'mid') {
      if (taste && taste.confident && (taste.editStyle === 'viral' || taste.hook === 'aggressive')) {
        why = 'Mid-tier signal — watchable, but hook could be sharper for your style.';
      } else if (taste && taste.confident && taste.editStyle === 'cinematic') {
        why = 'Steady clip — narrative rhythm present, hook softer.';
      } else {
        why = 'Solid clip — good bones, room to sharpen the hook.';
      }
    } else {
      if (taste && taste.confident && isHook && taste.hook === 'aggressive') {
        why = 'Weak opening signal — this sits below your usual hook threshold.';
      } else if (taste && taste.confident && taste.editStyle === 'viral') {
        why = 'Low signal — below your high-energy editing standard.';
      } else {
        why = 'Lower signal — may not crack the top picks.';
      }
    }

    let tasteNote = null;
    if (taste && taste.confident && hasSignal) {
      const STYLE = { viral: 'high-energy', cinematic: 'cinematic', educational: 'educational' };
      const s = STYLE[taste.editStyle];
      if (s) {
        tasteNote = tier === 'high'
          ? 'Aligns with your ' + s + ' editing profile.'
          : tier === 'low'
          ? 'Below your ' + s + ' profile threshold.'
          : null;
      }
    }

    return { why, tasteNote };
  }

  // ── getConcerns ───────────────────────────────────────────
  // P3.6: Delegates to EditorConsensus for debate-aware concerns.
  // Falls back through P3.5 agent layer then P3.4 taste logic.
  // Returns array of { type, label, msg } — at most 2 entries.
  function getConcerns(parts) {
    // P3.6: Consensus-based concerns — agreement and conflict context
    if (typeof EditorConsensus !== 'undefined' && typeof EditorAgents !== 'undefined') {
      const signals = EditorAgents.buildSignals(Array.isArray(parts) ? parts : []);
      const debate  = EditorConsensus.resolve(signals);
      if (!debate) return [];

      const concerns = [];

      // Primary: consensus recommendation with ally label
      if (debate.confidence >= 0.65) {
        concerns.push({
          type:  'consensus',
          label: debate.allyLabel,
          msg:   debate.consensus,
        });
      }

      // Secondary: conflict note when meaningful disagreement exists
      if (debate.dissent && debate.conflictLevel > 0.30) {
        const msg      = debate.compromiseNote ? 'Compromise: ' + debate.compromiseNote : debate.dissent;
        const opposer  = debate.agentResults.find(r => r.action !== debate.action);
        concerns.push({
          type:  opposer ? opposer.agentName : 'dissent',
          label: opposer ? opposer.agentLabel : 'Counterpoint',
          msg,
        });
      }

      // P3.7: Adapt primary concern with collab history note
      if (concerns.length && typeof CreatorMemory !== 'undefined') {
        const collab = CreatorMemory.getCollabProfile();
        if (collab.confident && collab.preferredDir && concerns[0].type === 'consensus') {
          const _AGG = new Set(['fasterPacing', 'strongerHook', 'viralMode', 'removeDeadSpace']);
          const debateDir = debate.action && _AGG.has(debate.action) ? 'aggressive' : (debate.action === 'cinematicMode' ? 'narrative' : null);
          if (debateDir && collab.preferredDir !== debateDir) {
            if (debateDir === 'aggressive') {
              concerns[0].msg += ' You usually prefer lighter adjustments.';
            } else if (debateDir === 'narrative') {
              concerns[0].msg += ' Note: you usually favor high-energy edits.';
            }
          }
        }
      }

      return concerns.slice(0, 2);
    }

    // P3.5 fallback: single-agent concerns (no consensus module)
    if (typeof EditorAgents !== 'undefined') {
      const signals = EditorAgents.buildSignals(Array.isArray(parts) ? parts : []);
      const results = EditorAgents.runAll(signals).filter(r => r.confidence >= 0.65);
      if (results.length) {
        return results.slice(0, 2).map(r => ({ type: r.agentName, label: r.agentLabel, msg: r.reason }));
      }
      return [];
    }

    // P3.4 fallback: taste-based concerns (when EditorAgents not loaded)
    if (!Array.isArray(parts) || !parts.length) return [];
    const taste = _taste();
    if (!taste || !taste.confident) return [];

    const done = parts.filter(p => {
      const st = String(p.status || '').toLowerCase();
      return st === 'done' || st === 'completed' || st === 'complete';
    });
    if (!done.length) return [];

    const concerns = [];

    const firstClip = done.find(p => Number(p.part_no) === 1);
    if (firstClip) {
      const firstPct = Math.round((Number(firstClip.viral_score) || 0) * 100);
      if (firstPct < 45 && taste.hook === 'aggressive') {
        concerns.push({ type: 'hook-risk', label: 'Retention Risk', msg: 'Opening clip at ' + firstPct + '% — below your typical hook threshold.' });
      }
    }
    if (done.length >= 3) {
      const avg = Math.round(done.reduce((s, p) => s + (Number(p.viral_score) || 0), 0) / done.length * 100);
      if (avg < 45 && (taste.editStyle === 'viral' || taste.pace === 'fast')) {
        concerns.push({ type: 'pacing-mismatch', label: 'Pacing Signal', msg: 'Avg score ' + avg + '% — softer than your high-energy editing pace.' });
      }
    }
    return concerns.slice(0, 2);
  }

  // ── getCompletionNarrative ────────────────────────────────
  // Returns taste-aware completion summary.
  // Returns { summaryMsg: string, bits: string[], tasteNote: string|null }
  function getCompletionNarrative(avgPct, topPct, completedCount) {
    const taste = _taste();

    let summaryMsg;
    let tasteNote = null;
    const bits    = [];

    if (taste && taste.confident) {
      const style = taste.editStyle;
      if (style === 'viral') {
        summaryMsg = avgPct >= 65
          ? 'High-energy output — signal density aligns with your viral editing profile.'
          : avgPct >= 50
          ? 'Solid batch — hook selection could be sharper for your high-energy style.'
          : 'Below your usual signal threshold — consider tighter hook selection.';
        tasteNote = 'Your high-energy editing profile shaped the output ranking.';
      } else if (style === 'cinematic') {
        summaryMsg = avgPct >= 55
          ? 'Output follows your cinematic rhythm — narrative signal is strong.'
          : 'Complete — pacing reflects your story-first editing approach.';
        tasteNote = 'Cinematic profile detected — narrative consistency weighted in scoring.';
      } else if (style === 'educational') {
        summaryMsg = avgPct >= 50
          ? 'Clear, structured result — well-matched to your clarity-first style.'
          : 'Complete — consider whether subtitle density supported the narrative.';
        tasteNote = 'Educational profile detected — subtitle clarity weighted in evaluation.';
      } else {
        summaryMsg = avgPct >= 70
          ? 'Strong output batch — average viral signal is above retention threshold.'
          : avgPct >= 50
          ? 'Solid batch with room to optimize — hook selection could be refined.'
          : 'Output complete — consider re-scoring with tighter clip selection.';
      }
    } else {
      summaryMsg = avgPct >= 70
        ? 'Strong output batch — average viral signal is above retention threshold.'
        : avgPct >= 50
        ? 'Solid batch with room to optimize — hook selection could be refined.'
        : 'Output complete — consider re-scoring with tighter clip selection.';
    }

    if (topPct >= 75)       bits.push('Best clip ' + topPct + '% — strong hook');
    else if (topPct >= 55)  bits.push('Top clip scored ' + topPct + '%');
    if (completedCount)     bits.push(completedCount + ' clips AI-scored');
    bits.push('avg ' + avgPct + '%');
    if (taste && taste.confident && taste.editStyle !== 'balanced') {
      const SHORT = { viral: 'high-energy profile', cinematic: 'cinematic profile', educational: 'clarity profile' };
      const s = SHORT[taste.editStyle];
      if (s) bits.push(s + ' matched');
    }

    return { summaryMsg, bits, tasteNote };
  }

  return { getEvolutionContext, getConcerns, getCompletionNarrative };

})();
