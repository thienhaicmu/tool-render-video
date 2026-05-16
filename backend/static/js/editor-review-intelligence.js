/* =========================================================
   editor-review-intelligence.js  —  P2-C: Review Intelligence
   Analyzes completed render output and injects AI explanation
   badges into .clipCard DOM elements (non-destructive overlay).
   Derives per-part scores from clip scoring data held in EditorState.
   ========================================================= */
'use strict';

window.EditorReviewIntelligence = (() => {

  let _data = null;

  // ── Analyze ──────────────────────────────────────────────
  // parts    — array of rendered part objects from render-ui
  // clips    — EditorState.clips at render time
  // subtitles— EditorState.subtitles
  // duration — total source duration
  function analyze(parts, clips, subtitles, duration) {
    if (!parts || !parts.length) return null;

    const sorted = (clips || []).slice().sort((a, b) => a.start - b.start);

    // Hook score: avg score of first 2 clips
    const hookClips = sorted.slice(0, 2);
    const hookScore = hookClips.length
      ? hookClips.reduce((s, c) => s + (c.score || 0), 0) / hookClips.length
      : 0;

    // Retention risks
    const retentionRisks = sorted
      .filter(c => (c.score || 0) < 0.4 || (c.end - c.start) > 10)
      .map(c => c.id);

    // Subtitle readability (chars per second > 24 is hard to read)
    const badSubCount = (subtitles || []).filter(s => {
      const d = Math.max(0.1, (s.end || 0) - (s.start || 0));
      return ((s.text || '').length / d) > 24;
    }).length;

    // Per-part scoring
    const partScores = {};
    const explanations = {};

    parts.forEach((p, idx) => {
      const partNo = Number(p.part_no || idx + 1);
      const startS = Number(p.start_sec || 0);
      const endS   = Number(p.end_sec || p.duration || 0);
      const dur    = Math.max(0.01, endS - startS);

      // Pull matching clip by index (best effort)
      const clip   = sorted[idx] || sorted[0];
      const rawSc  = Number(p.viral_score ?? p.score ?? p.viralScore ?? 0);
      const clipSc = clip ? Math.max(rawSc, clip.score || 0) : rawSc;

      // Dimension scores (0 – 1)
      const energy    = Math.min(1, clipSc * 1.05);
      const pacing    = Math.max(0, Math.min(1, 1 - Math.max(0, dur - 5) / 20));
      const emotion   = clipSc >= 0.7 ? 0.85 : clipSc >= 0.5 ? 0.65 : 0.4;
      const narrative = dur >= 3 ? Math.min(1, clipSc + 0.15) : 0.3;
      const viral     = Math.min(1, energy * 0.45 + pacing * 0.3 + emotion * 0.25);

      partScores[partNo] = { energy, pacing, emotion, narrative, viral, clipSc };

      // Editorial-language explanations
      const msgs = [];
      if (viral    >= 0.75) msgs.push('Hook energy drives algorithm reach');
      if (energy   >= 0.8)  msgs.push('Visual intensity holds attention');
      if (pacing   >= 0.75) msgs.push('Tight pacing sustains viewer engagement');
      if (emotion  >= 0.8)  msgs.push('Emotional resonance — high retention signal');
      if (clipSc   <  0.4)  msgs.push('Hook energy is moderate — consider tightening');
      if (dur      >  10)   msgs.push('Runtime may dilute impact — trim edges');
      else if (dur <  2)    msgs.push('Brief cut — ensure context lands');
      if (!msgs.length)     msgs.push('Clean content — solid foundation');
      explanations[partNo] = msgs.slice(0, 2);

      // Single-sentence editorial review summary
      const summary = viral >= 0.75 ? 'Strong hook clarity — this cut maintains pacing momentum.'
        : viral >= 0.55             ? 'Solid energy level — hook could be pushed further.'
        : energy >= 0.7             ? 'Visual energy is present — pacing could tighten.'
        : pacing >= 0.75            ? 'Clean delivery and rhythm — retention looks healthy.'
        : clipSc < 0.4              ? 'Hook signal is weak here — consider reordering.'
        : dur > 10                  ? 'Clip runs long — emotional peak may arrive too late.'
        :                             'Neutral baseline — suitable for further AI refinement.';
      explanations[partNo + '_summary'] = summary;
    });

    const retentionScore = sorted.length
      ? sorted.reduce((s, c) => s + (c.score || 0), 0) / sorted.length
      : 0;

    _data = {
      hookScore,
      retentionScore,
      retentionRisks,
      badSubCount,
      partScores,
      explanations,
    };
    return _data;
  }

  // ── Annotate output cards ────────────────────────────────
  // Injects .aiReviewBadge into each .clipCard[data-part-no].
  // Safe to call multiple times; skips cards that already have a badge.
  function annotateCards(container) {
    if (!_data || !container) return;
    container.querySelectorAll('.clipCard[data-part-no]').forEach(card => {
      const partNo = parseInt(card.dataset.partNo, 10);
      if (isNaN(partNo) || card.querySelector('.aiReviewBadge')) return;

      const expl   = _data.explanations[partNo];
      const scores = _data.partScores[partNo];
      if (!expl || !expl.length || !scores) return;

      const body = card.querySelector('.clipCardBody');
      if (!body) return;

      const viralPct  = Math.round((scores.viral  || 0) * 100);
      const energyPct = Math.round((scores.energy || 0) * 100);
      const tier      = viralPct >= 75 ? 'high' : viralPct >= 50 ? 'mid' : 'low';

      const summary = _data.explanations[partNo + '_summary'] || '';
      const badge = document.createElement('div');
      badge.className = 'aiReviewBadge';
      badge.innerHTML =
        `<div class="aiReviewRow">` +
          `<span class="aiReviewChip" data-tier="${tier}">${viralPct}% viral</span>` +
          `<span class="aiReviewEnergy" title="Visual energy">${energyPct}% energy</span>` +
        `</div>` +
        (summary ? `<div class="aiReviewSummary">${_esc(summary)}</div>` : '') +
        `<ul class="aiReviewList">${expl.map(e => `<li>${_esc(e)}</li>`).join('')}</ul>`;

      const actions = body.querySelector('.clipCardActions');
      if (actions) body.insertBefore(badge, actions);
      else body.appendChild(badge);
    });
  }

  function _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function getReviewData() { return _data; }
  function reset()         { _data = null; }

  return { analyze, annotateCards, getReviewData, reset };

})();
