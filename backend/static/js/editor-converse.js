/* =========================================================
   editor-converse.js  —  P3.2/P3.3: Conversational Editing
   P3.3 adds: taste-adaptive intent, micro conversation memory,
   tie-breaking via taste model, and explainability text.

   Flow:
     user text
       → micro-context resolve (last turn patterns)
       → keyword parse (7 rules)
       → taste model tie-break (ambiguous scores)
       → vague power resolve (stronger/better/improve)
       → clarification (still ambiguous)
       → EditorAiActions.previewAction()
       → accept/reject via preview card

   Every message must change the edit.
   ========================================================= */
'use strict';

window.EditorConverse = (() => {

  const MAX_TURNS = 6;
  let _turns        = [];
  let _initialized  = false;
  let _waitingForResult = false;

  // Micro conversation context (P3.3-C / P3.7)
  let _ctx = {
    lastAction:          null,   // last resolved action id
    lastIntent:          null,   // last resolved interpretation string
    lastRaw:             null,   // last user text
    lastWasAgentRouted:  false,  // P3.7: true when last intent came from _resolveWithAgents
    lastAgentDir:        null,   // P3.7: creative direction of last agent-routed turn
  };

  // ── Intent rules ─────────────────────────────────────────
  // Keywords scored by substring match; multi-word = double score.
  // P3.3: expanded keyword lists to reduce false-negatives.
  const _RULES = [
    {
      id: 'strongerHook',
      keywords: ['hook', 'intro', 'opening', 'start', 'beginning', 'lead', 'not engaging',
                 'weak hook', 'slow intro', 'first impression', 'attention'],
      interpretation: 'stronger opening hook',
      desc: 'Promote the highest-energy clip to position 1. Tighten the opening seconds.',
    },
    {
      id: 'fasterPacing',
      keywords: ['slow', 'boring', 'dragging', 'pace', 'pacing', 'long', 'tighten', 'momentum',
                 'faster', 'speed up', 'too long', 'too slow', 'drags', 'feels long', 'snappier'],
      interpretation: 'faster pacing',
      desc: 'Trim long clips and tighten rhythm across the timeline.',
    },
    {
      id: 'removeDeadSpace',
      keywords: ['silence', 'dead', 'gap', 'pauses', 'quiet', 'empty', 'dead air', 'dead space',
                 'air', 'filler', 'um', 'uh', 'hesitation'],
      interpretation: 'remove silence and dead air',
      desc: 'Tighten clip edges around pauses and silence zones.',
    },
    {
      id: 'viralMode',
      keywords: ['viral', 'algorithm', 'tiktok', 'energy', 'energetic', 'engagement',
                 'hook score', 'perform', 'perform well', 'get views', 'shareable'],
      interpretation: 'viral energy optimization',
      desc: 'Reorder clips by hook score. Trim low-energy moments.',
    },
    {
      id: 'cinematicMode',
      keywords: ['cinematic', 'emotional', 'story', 'narrative', 'flow', 'jumpy', 'choppy',
                 'too many cuts', 'less cuts', 'breathing', 'calm', 'smooth', 'natural',
                 'calmer', 'slower', 'less aggressive', 'less intense', 'tone down',
                 'more relaxed', 'softer', 'gentle', 'dramatic'],
      interpretation: 'cinematic narrative flow',
      desc: 'Sort clips chronologically. Extend short clips for breathing room.',
    },
    {
      id: 'subtitleCleanup',
      keywords: ['subtitle', 'subtitles', 'caption', 'captions', 'captions messy', 'hard to read',
                 'messy text', 'clean text', 'text too small', 'cleaner text', 'readable',
                 'more readable', 'clarity', 'clearer words'],
      interpretation: 'subtitle cleanup',
      desc: 'Clean up caption timing and improve readability.',
    },
    {
      id: 'smartClipPrioritization',
      keywords: ['best clips', 'rank clips', 'quality', 'priority', 'highlight', 'weakest',
                 'top clips', 'strongest', 'best moments', 'weak moments', 'rank', 'sort by quality'],
      interpretation: 'AI clip prioritization',
      desc: 'Rank clips by AI quality score. Deprioritize weaker moments.',
    },
  ];

  const _LABELS = {
    strongerHook:            'Stronger Hook',
    fasterPacing:            'Faster Pacing',
    removeDeadSpace:         'Remove Dead Air',
    viralMode:               'Viral Mode',
    cinematicMode:           'Cinematic Flow',
    subtitleCleanup:         'Clean Subtitles',
    smartClipPrioritization: 'Prioritize Clips',
  };

  // ── P3.3-B: Vague power keywords ─────────────────────────
  // These words have no keyword rule match. They need taste resolution.
  const _VAGUE_POWER = ['stronger', 'better', 'improve', 'boost', 'upgrade', 'amp up',
                        'punch up', 'level up', 'more impact', 'more punch', 'more powerful'];

  // ── P3.3-B: Taste-based style → action preference map ────
  const _STYLE_PREF = {
    viral:       ['strongerHook', 'viralMode', 'fasterPacing'],
    cinematic:   ['cinematicMode', 'removeDeadSpace'],
    educational: ['subtitleCleanup', 'smartClipPrioritization'],
    balanced:    [],
  };

  // ── P3.3-C: Micro context patterns ───────────────────────
  // Checked before keyword parse. Returns resolved intent or null.
  const _OPPOSITE = {
    fasterPacing:            'cinematicMode',
    viralMode:               'cinematicMode',
    strongerHook:            'cinematicMode',
    removeDeadSpace:         'cinematicMode',
    cinematicMode:           'fasterPacing',
    subtitleCleanup:         null,
    smartClipPrioritization: null,
  };

  function _tryContextResolve(text) {
    const lower = text.toLowerCase().trim();

    // "again" / "repeat" / "more of that" → repeat last action
    if (_ctx.lastAction && /\b(again|repeat|once more|do it again|more of that|same thing)\b/.test(lower)) {
      const rule = _RULES.find(r => r.id === _ctx.lastAction);
      return {
        action:        _ctx.lastAction,
        interpretation: _ctx.lastIntent || 'repeat previous',
        desc:          rule ? rule.desc : '',
        explainText:   'Applying the same change once more.',
      };
    }

    // "just the intro" / "only the opening" → scope to hook
    if (/\b(just the intro|only the intro|just the opening|only the opening|just the beginning|just the start|intro only|opening only)\b/.test(lower)) {
      return {
        action:        'strongerHook',
        interpretation: 'opening hook only',
        desc:          'Promote the highest-energy clip to position 1.',
        explainText:   'Scoping to the intro based on context.',
      };
    }

    // "just the subtitles" / "only captions" → subtitle cleanup
    if (/\b(just the subtitles?|only the subtitles?|just the captions?|only the captions?|subtitles? only|captions? only)\b/.test(lower)) {
      return {
        action:        'subtitleCleanup',
        interpretation: 'subtitle cleanup only',
        desc:          'Clean up caption timing and improve readability.',
        explainText:   'Scoping to subtitles based on context.',
      };
    }

    // "a bit less" / "dial it back" → apply opposite of last action
    if (_ctx.lastAction && /\b(a bit less|not as much|less of that|tone it down|dial it back|dial back|scale back|back off)\b/.test(lower)) {
      const opp = _OPPOSITE[_ctx.lastAction];
      if (opp) {
        const rule = _RULES.find(r => r.id === opp);
        return {
          action:        opp,
          interpretation: rule ? rule.interpretation : opp,
          desc:          rule ? rule.desc : '',
          explainText:   'Dialing back from ' + (_ctx.lastIntent || 'the last edit') + '.',
        };
      }
    }

    return null;
  }

  // ── P3.3-B: Tie-break with taste model ───────────────────
  // When two rules tie in keyword score, pick the one matching creator taste.
  function _breakTieWithTaste(tied, taste) {
    if (!taste || !taste.confident) return null;
    const preferred = _STYLE_PREF[taste.editStyle] || [];
    const winner    = tied.find(s => preferred.includes(s.rule.id));
    if (!winner) return null;
    return {
      action:         winner.rule.id,
      interpretation: winner.rule.interpretation,
      desc:           winner.rule.desc,
      ambiguous:      false,
      explainText:    'Your ' + _styleLabel(taste.editStyle) + ' tendency resolved this.',
    };
  }

  // ── P3.3-B: Vague power resolution with taste ────────────
  // Called when no keyword rule matches and text contains vague power words.
  function _resolveWithTaste(text) {
    const lower   = text.toLowerCase();
    const isVague = _VAGUE_POWER.some(kw => lower.includes(kw));
    if (!isVague) return null;
    if (typeof CreatorMemory === 'undefined') return null;
    const taste = CreatorMemory.getTasteModel();
    if (!taste.confident) return null;

    let action, explainText;
    if (taste.editStyle === 'viral' || (taste.pace === 'fast' && taste.hook !== 'soft')) {
      action      = 'strongerHook';
      explainText = 'Your high-energy editing style shaped this — I read "' + _sanitizeQuote(text) + '" as a tighter opening hook.';
    } else if (taste.editStyle === 'cinematic') {
      action      = 'cinematicMode';
      explainText = 'Your cinematic tendency shaped this — I read "' + _sanitizeQuote(text) + '" as deeper narrative flow.';
    } else if (taste.editStyle === 'educational') {
      action      = 'smartClipPrioritization';
      explainText = 'Your clarity-forward style shaped this — I took "' + _sanitizeQuote(text) + '" as better clip organization.';
    } else {
      return null; // balanced — show clarification
    }

    const rule = _RULES.find(r => r.id === action);
    return {
      action,
      interpretation: rule ? rule.interpretation : action,
      desc:           rule ? rule.desc : '',
      explainText,
      ambiguous:      false,
    };
  }

  // ── P3.7: Direction lookup — mirrors EditorConsensus ─────
  function _dirOf(action) {
    if (['fasterPacing', 'strongerHook', 'viralMode', 'removeDeadSpace'].indexOf(action) >= 0) return 'aggressive';
    if (action === 'cinematicMode') return 'narrative';
    return 'clarity';
  }

  // ── P3.6: Consensus debate resolution ────────────────────
  // Runs the full agent debate via EditorConsensus.
  // Falls back to single-agent resolution (P3.5) when consensus unavailable.
  function _resolveWithAgents() {
    // P3.6: Full debate consensus
    if (typeof EditorConsensus !== 'undefined' && typeof EditorAgents !== 'undefined') {
      const signals = EditorAgents.buildSignals();
      const debate  = EditorConsensus.resolve(signals);
      if (!debate || debate.confidence < 0.65) return null;

      // Extreme conflict — surface both directions and ask creator to choose
      if (debate.isExtremeConflict && debate.conflictOptions) {
        return {
          action:      null,
          ambiguous:   true,
          options:     debate.conflictOptions,
          explainText: debate.consensus,
        };
      }

      const rule = _RULES.find(r => r.id === debate.action);
      if (!rule) return null;
      const tier      = debate.confidence >= 0.80 ? 'high' : 'moderate';
      const debateDir = _dirOf(debate.action);

      // P3.7: Co-pilot reasoning — explain when recommendation diverges from collab history
      let copilotNote = null;
      if (typeof CreatorMemory !== 'undefined') {
        const collab = CreatorMemory.getCollabProfile();
        if (collab.confident && collab.preferredDir && collab.preferredDir !== debateDir) {
          if (debateDir === 'aggressive') {
            copilotNote = 'You tend to preserve emotional pacing. Applied a conservative adjustment.';
          } else if (debateDir === 'narrative') {
            copilotNote = 'You usually favor high-energy edits. Cinematic approach taken — signal was compelling.';
          }
        } else if (collab.confident && collab.compromiseTolerant && debate.compromiseNote) {
          copilotNote = 'Balanced compromise applied — aligns with how you usually resolve these.';
        }
      }

      return {
        action:         debate.action,
        interpretation: rule.interpretation,
        desc:           rule.desc,
        ambiguous:      false,
        explainText:    null,
        agentMeta: {
          label:          debate.allyLabel,
          tier,
          consensus:      debate.consensus,
          dissent:        debate.dissent,
          compromiseNote: debate.compromiseNote,
          agreementScore: debate.agreementScore,
          copilotNote,
        },
      };
    }

    // P3.5 fallback: single-agent resolution
    if (typeof EditorAgents === 'undefined') return null;
    const signals = EditorAgents.buildSignals();
    const rec     = EditorAgents.getTopRecommendation(signals);
    if (!rec || rec.confidence < 0.65) return null;
    const rule = _RULES.find(r => r.id === rec.action);
    if (!rule) return null;
    const tier = rec.confidence >= 0.80 ? 'high' : 'moderate';
    return {
      action:         rec.action,
      interpretation: rule.interpretation,
      desc:           rule.desc,
      ambiguous:      false,
      explainText:    rec.agentLabel + ' identified this — ' + rec.reason,
      agentMeta:      { label: rec.agentLabel, tier },
    };
  }

  function _sanitizeQuote(s) {
    return String(s).substring(0, 40).replace(/[<>"']/g, '');
  }

  function _styleLabel(s) {
    return { viral: 'high-energy', cinematic: 'cinematic', educational: 'clarity-forward', balanced: 'balanced' }[s] || s;
  }

  // ── Intent parser ─────────────────────────────────────────
  function _parseIntent(text) {
    // 1. Micro context resolve (P3.3-C)
    const ctxResult = _tryContextResolve(text);
    if (ctxResult) return ctxResult;

    // 2. Normal keyword scoring
    const lower  = text.toLowerCase().trim();
    const scored = _RULES.map(rule => {
      let score = 0;
      rule.keywords.forEach(kw => {
        if (lower.includes(kw)) score += kw.includes(' ') ? 2 : 1;
      });
      return { rule, score };
    }).filter(s => s.score > 0).sort((a, b) => b.score - a.score);

    if (scored.length >= 1) {
      // Clear winner
      if (scored.length === 1 || scored[0].score > scored[1].score) {
        return {
          action:         scored[0].rule.id,
          interpretation: scored[0].rule.interpretation,
          desc:           scored[0].rule.desc,
          ambiguous:      false,
        };
      }
      // Tied — try taste model to break tie (P3.3-B)
      const taste = typeof CreatorMemory !== 'undefined' ? CreatorMemory.getTasteModel() : null;
      const broken = _breakTieWithTaste(scored.slice(0, 2), taste);
      if (broken) return broken;
      // Still tied — show clarification
      return {
        action:    null,
        ambiguous: true,
        options:   scored.slice(0, 2).map(s => ({
          label:          _LABELS[s.rule.id] || s.rule.id,
          action:         s.rule.id,
          interpretation: s.rule.interpretation,
          desc:           s.rule.desc,
        })),
      };
    }

    // 3. No keyword match → try vague power with taste (P3.3-B)
    const vagueResult = _resolveWithTaste(text);
    if (vagueResult) return vagueResult;

    // 4. No keyword, no vague power → try agent consensus (P3.5)
    const agentResult = _resolveWithAgents();
    if (agentResult) return agentResult;

    // 5. Complete no-match
    return { action: null, ambiguous: false };
  }

  // ── Memory context (P3.1) ─────────────────────────────────
  function _memCtx(action) {
    if (typeof CreatorMemory === 'undefined') return '';
    const prefs = CreatorMemory.getDerivedPreferences();
    if (!prefs.confident) return '';
    if (prefs.favored.includes(action)) return 'You usually keep this one.';
    if (prefs.avoided.includes(action)) return "You've skipped this before — still worth a look.";
    return '';
  }

  // ── Handle input ──────────────────────────────────────────
  function handleInput(text) {
    const field = document.getElementById('convInputField');
    const raw   = (text !== undefined ? text : (field ? field.value : '')).trim();
    if (!raw) return;
    if (field) field.value = '';

    _waitingForResult = false;
    _ctx.lastRaw = raw;
    _addTurn('user', raw);
    const result = _parseIntent(raw);

    if (!result.action && !result.ambiguous) {
      _addTurn('ai', 'Not sure what to change. Try one of these:', null, null, [
        { label: 'Stronger Hook',  action: 'strongerHook' },
        { label: 'Faster Pacing',  action: 'fasterPacing' },
        { label: 'Clean Subtitles', action: 'subtitleCleanup' },
        { label: 'Viral Mode',     action: 'viralMode' },
      ]);
      return;
    }

    if (result.ambiguous) {
      _addTurn('ai', 'Which did you mean?', null, null, result.options);
      return;
    }

    _fireIntent(result.action, result.interpretation, result.desc, result.explainText || null, result.agentMeta || null);
  }

  function _fireIntent(action, interpretation, desc, explainText, agentMeta) {
    const mem   = _memCtx(action);
    let   intro = ‘I understood: <strong>’ + _esc(interpretation) + ‘</strong>.’;
    if (mem) intro += ‘ ‘ + _esc(mem);
    intro += ‘ Here’s a preview — accept or discard above.’;

    _addTurn(‘ai’, intro, action, desc, null, explainText || null, agentMeta || null);

    // Update micro context (P3.3-C / P3.7)
    _ctx.lastAction         = action;
    _ctx.lastIntent         = interpretation;
    _ctx.lastWasAgentRouted = !!agentMeta;
    _ctx.lastAgentDir       = agentMeta ? _dirOf(action) : null;

    _waitingForResult = true;
    if (typeof EditorAiActions !== ‘undefined’) EditorAiActions.previewAction(action);
  }

  // Callbacks from accept/reject buttons (P3.2)
  function _onAccept() {
    if (!_waitingForResult) return;
    _waitingForResult = false;
    // P3.7: Record debate direction preference when last intent was agent-routed
    if (_ctx.lastWasAgentRouted && _ctx.lastAgentDir && typeof CreatorMemory !== 'undefined') {
      CreatorMemory.recordDebateChoice(_ctx.lastAgentDir, true);
    }
    _addTurn('ai', 'Applied. What else would you like to change?');
  }

  function _onReject() {
    if (!_waitingForResult) return;
    _waitingForResult = false;
    // P3.7: Record debate direction rejection
    if (_ctx.lastWasAgentRouted && _ctx.lastAgentDir && typeof CreatorMemory !== 'undefined') {
      CreatorMemory.recordDebateChoice(_ctx.lastAgentDir, false);
    }
    _ctx.lastAction         = null; // reset context on reject — user wants a different direction
    _ctx.lastWasAgentRouted = false;
    _ctx.lastAgentDir       = null;
    _addTurn('ai', 'Discarded. Try a different direction, or describe it another way.');
  }

  // Clarify button onclick (P3.2)
  function _clarify(action, label) {
    const rule = _RULES.find(r => r.id === action);
    _addTurn('user', label);
    _fireIntent(action, rule ? rule.interpretation : action, rule ? rule.desc : '');
  }

  // Example chips (P3.2)
  function quickInput(text) {
    const field = document.getElementById('convInputField');
    if (field) field.value = text;
    handleInput(text);
  }

  // ── Turn rendering ────────────────────────────────────────
  function _addTurn(role, html, action, desc, clarifyOpts, explainText, agentMeta) {
    _turns.push({ role, html, action, desc, clarifyOpts: clarifyOpts || null, explainText: explainText || null, agentMeta: agentMeta || null });
    if (_turns.length > MAX_TURNS) _turns.shift();
    _render();
  }

  function _render() {
    const hist = document.getElementById('convHistory');
    if (!hist) return;
    const total = _turns.length;
    hist.innerHTML = _turns.map((t, i) => {
      const age  = total - 1 - i;
      const fade = age === 0 ? '' : age === 1 ? 'style="opacity:.78"' : age === 2 ? 'style="opacity:.55"' : 'style="opacity:.35"';

      if (t.role === 'user') {
        return '<div class="convTurn convTurnUser" ' + fade + '>' + _esc(t.html) + '</div>';
      }

      let inner = '<div class="convTurnAi" ' + fade + '>' + t.html;
      // P3.5/P3.6: Agent attribution pill + debate context
      if (t.agentMeta) {
        const m        = t.agentMeta;
        const pillText = m.consensus
          ? _esc(m.label)
          : _esc(m.label) + ' · ' + _esc(m.tier) + ' confidence';
        inner += '<div class="p35AgentPill" data-tier="' + m.tier + '">' + pillText + '</div>';
        // P3.6: Consensus message (replaces plain explainText when debate ran)
        if (m.consensus)      inner += '<div class="convExplain">'    + _esc(m.consensus)      + '</div>';
        if (m.dissent)        inner += '<div class="p36Dissent">'     + _esc(m.dissent)        + '</div>';
        if (m.compromiseNote) inner += '<div class="p36Compromise">'  + _esc(m.compromiseNote) + '</div>';
        if (m.copilotNote)    inner += '<div class="p37CopilotNote">' + _esc(m.copilotNote)    + '</div>';
      }
      // P3.3-D: Explainability text (only when no debate consensus covers it)
      if (t.explainText && !(t.agentMeta && t.agentMeta.consensus)) {
        inner += '<div class="convExplain">' + _esc(t.explainText) + '</div>';
      }
      if (t.desc) {
        inner += '<div class="convDesc">' + _esc(t.desc) + '</div>';
      }
      if (t.clarifyOpts) {
        inner += '<div class="convClarifyRow">' +
          t.clarifyOpts.map(o =>
            '<button class="convClarifyBtn" onclick="EditorConverse._clarify(' +
            JSON.stringify(o.action) + ',' + JSON.stringify(o.label) + ')">' +
            _esc(o.label) + '</button>'
          ).join('') +
        '</div>';
      }
      inner += '</div>';
      return '<div class="convTurn">' + inner + '</div>';
    }).join('');
    hist.scrollTop = hist.scrollHeight;

    const chips = document.getElementById('convExamples');
    if (chips) chips.style.display = total > 0 ? 'none' : '';
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Init / reset ──────────────────────────────────────────
  function init() {
    if (_initialized) return;
    _initialized = true;
    const field = document.getElementById('convInputField');
    if (field) {
      field.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleInput(); }
      });
    }
  }

  function reset() {
    _turns  = [];
    _ctx    = { lastAction: null, lastIntent: null, lastRaw: null, lastWasAgentRouted: false, lastAgentDir: null };
    _waitingForResult = false;
    _render();
  }

  return { init, handleInput, quickInput, reset, _clarify, _onAccept, _onReject };

})();
