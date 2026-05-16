/* =========================================================
   editor-converse.js  —  P3.2: Conversational Editing
   Lightweight intent-to-patch conversational layer.

   Flow:
     user text → intent parser → EditorAiActions.previewAction()
     → accept/reject via existing preview card

   NOT a chatbot. Every message must change the edit.
   ========================================================= */
'use strict';

window.EditorConverse = (() => {

  const MAX_TURNS = 6;
  let _turns = [];
  let _initialized = false;
  let _waitingForResult = false; // true while a conversation-triggered preview is live

  // ── Intent rules ─────────────────────────────────────────
  // Keywords scored by substring match. Multi-word phrases score double.
  const _RULES = [
    {
      id: 'strongerHook',
      keywords: ['hook', 'intro', 'opening', 'start', 'beginning', 'lead', 'not engaging', 'weak hook', 'slow intro'],
      interpretation: 'stronger opening hook',
      desc: 'Promote the highest-energy clip to position 1. Tighten the opening seconds.',
    },
    {
      id: 'fasterPacing',
      keywords: ['slow', 'boring', 'dragging', 'pace', 'pacing', 'long', 'tighten', 'momentum', 'faster', 'speed up', 'too long'],
      interpretation: 'faster pacing',
      desc: 'Trim long clips and tighten rhythm across the timeline.',
    },
    {
      id: 'removeDeadSpace',
      keywords: ['silence', 'dead', 'gap', 'pauses', 'quiet', 'empty', 'dead air', 'dead space', 'air'],
      interpretation: 'remove silence and dead air',
      desc: 'Tighten clip edges around pauses and silence zones.',
    },
    {
      id: 'viralMode',
      keywords: ['viral', 'algorithm', 'tiktok', 'energy', 'energetic', 'engagement', 'hook score', 'perform'],
      interpretation: 'viral energy optimization',
      desc: 'Reorder clips by hook score. Trim low-energy moments.',
    },
    {
      id: 'cinematicMode',
      keywords: ['cinematic', 'emotional', 'story', 'narrative', 'flow', 'jumpy', 'choppy', 'too many cuts', 'less cuts', 'breathing', 'calm', 'smooth', 'natural'],
      interpretation: 'cinematic narrative flow',
      desc: 'Sort clips chronologically. Extend short clips for breathing room.',
    },
    {
      id: 'subtitleCleanup',
      keywords: ['subtitle', 'subtitles', 'caption', 'captions', 'captions messy', 'hard to read', 'messy text', 'clean text'],
      interpretation: 'subtitle cleanup',
      desc: 'Clean up caption timing and improve readability.',
    },
    {
      id: 'smartClipPrioritization',
      keywords: ['best clips', 'rank clips', 'quality', 'priority', 'highlight', 'weakest', 'top clips', 'strongest'],
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

  // ── Intent parser ─────────────────────────────────────────
  function _parseIntent(text) {
    const lower = text.toLowerCase().trim();
    const scored = _RULES.map(rule => {
      let score = 0;
      rule.keywords.forEach(kw => {
        if (lower.includes(kw)) {
          score += kw.includes(' ') ? 2 : 1; // multi-word match = double score
        }
      });
      return { rule, score };
    }).filter(s => s.score > 0).sort((a, b) => b.score - a.score);

    if (!scored.length) {
      return { action: null, ambiguous: false };
    }
    // Ambiguous: top 2 tied AND both > 0
    if (scored.length >= 2 && scored[0].score === scored[1].score) {
      return {
        action: null,
        ambiguous: true,
        options: scored.slice(0, 2).map(s => ({
          label:          _LABELS[s.rule.id] || s.rule.id,
          action:         s.rule.id,
          interpretation: s.rule.interpretation,
          desc:           s.rule.desc,
        })),
      };
    }
    return {
      action:         scored[0].rule.id,
      interpretation: scored[0].rule.interpretation,
      desc:           scored[0].rule.desc,
      ambiguous:      false,
    };
  }

  // ── Memory context ────────────────────────────────────────
  function _memCtx(action) {
    if (typeof CreatorMemory === 'undefined') return '';
    const prefs = CreatorMemory.getDerivedPreferences();
    if (!prefs.confident) return '';
    if (prefs.favored.includes(action)) return 'You usually keep this one.';
    if (prefs.avoided.includes(action)) return "You’ve skipped this before — still worth a look.";
    return '';
  }

  // ── Handle input ──────────────────────────────────────────
  function handleInput(text) {
    const field = document.getElementById('convInputField');
    const raw = (text !== undefined ? text : (field ? field.value : '')).trim();
    if (!raw) return;
    if (field) field.value = '';

    _waitingForResult = false;
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

    _fireIntent(result.action, result.interpretation, result.desc);
  }

  function _fireIntent(action, interpretation, desc) {
    const mem   = _memCtx(action);
    const intro = 'I understood: <strong>' + _esc(interpretation) + '</strong>.' + (mem ? ' ' + _esc(mem) : '') + ' Here’s a preview — accept or discard above.';
    _addTurn('ai', intro, action, desc);
    _waitingForResult = true;
    if (typeof EditorAiActions !== 'undefined') EditorAiActions.previewAction(action);
  }

  // Called by modified accept/reject buttons in preview card
  function _onAccept() {
    if (!_waitingForResult) return;
    _waitingForResult = false;
    _addTurn('ai', 'Applied. What else would you like to change?');
  }

  function _onReject() {
    if (!_waitingForResult) return;
    _waitingForResult = false;
    _addTurn('ai', 'Discarded. Try a different direction, or describe it another way.');
  }

  // Used by clarify buttons
  function _clarify(action, label) {
    const rule = _RULES.find(r => r.id === action);
    _addTurn('user', label);
    _fireIntent(action, rule ? rule.interpretation : action, rule ? rule.desc : '');
  }

  // Shortcut from example chips
  function quickInput(text) {
    const field = document.getElementById('convInputField');
    if (field) field.value = text;
    handleInput(text);
  }

  // ── Turn rendering ────────────────────────────────────────
  function _addTurn(role, html, action, desc, clarifyOpts) {
    _turns.push({ role, html, action, desc, clarifyOpts: clarifyOpts || null });
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
      if (t.desc) inner += '<div class="convDesc">' + _esc(t.desc) + '</div>';
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

    // Hide example chips once history exists
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
    _turns = [];
    _waitingForResult = false;
    _render();
  }

  return { init, handleInput, quickInput, reset, _clarify, _onAccept, _onReject };

})();
