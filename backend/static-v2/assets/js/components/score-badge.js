/* scoreColor(score) — returns CSS color var string for the score's tier.
   scoreBadge(score)  — inline progress bar + right-aligned number.
   scorePill(score)   — compact inline pill badge.
*/

export function scoreColor(score) {
  const pct = Number(score ?? 0);
  return pct >= 70 ? 'var(--color-success)' : pct >= 40 ? 'var(--color-warning)' : 'var(--color-failed)';
}

export function scoreBadge(score) {
  const pct = Math.round(Math.min(100, Math.max(0, Number(score ?? 0))));
  const color = scoreColor(pct);
  return `
    <div class="row gap-2" style="align-items:center">
      <div class="progress-bar" style="flex:1;height:3px">
        <div class="progress-bar__fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <span class="text-caption" style="color:${color};min-width:26px;text-align:right;font-variant-numeric:tabular-nums">${pct}</span>
    </div>
  `;
}

export function scorePill(score, { sm = false } = {}) {
  const pct = Math.round(Math.min(100, Math.max(0, Number(score ?? 0))));
  const color = scoreColor(pct);
  const cls = sm ? 'score-pill score-pill--sm' : 'score-pill';
  return `<span class="${cls}" style="background:${color}1a;color:${color};border-color:${color}40">${pct}</span>`;
}
