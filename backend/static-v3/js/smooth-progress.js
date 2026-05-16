function _easeToward(current, target, maxStep) {
  if(current >= target) return target;
  const diff = target - current;
  const step = Math.min(maxStep, Math.max(0.3, diff * 0.08));
  return Math.min(target, current + step);
}

function _tickSmooth() {
  let anyMoving = false;

  // Ease job-level bar
  if(_jobDisplayPct < _jobTargetPct) {
    _jobDisplayPct = _easeToward(_jobDisplayPct, _jobTargetPct, 1.5);
    const pct = _jobDisplayPct.toFixed(1);
    const bar = document.getElementById('job_bar');
    const pctEl = document.getElementById('job_percent');
    if(bar) bar.style.width = pct + '%';
    if(pctEl) pctEl.textContent = Math.round(_jobDisplayPct) + '%';
    anyMoving = true;
  }

  // Ease per-part bars (only update DOM elements that exist in current render)
  for(const [key, target] of Object.entries(_partTarget)) {
    const cur = _partDisplay[key] || 0;
    if(cur < target) {
      const next = _easeToward(cur, target, 2);
      _partDisplay[key] = next;
      // Update bar and pct text in-place without re-rendering
      const barEl = document.getElementById(`pbar_${key}`);
      const pctEl = document.getElementById(`ppct_${key}`);
      const rowBarEl = document.getElementById(`row_pbar_${key}`);
      const rowPctEl = document.getElementById(`row_ppct_${key}`);
      if(barEl) barEl.style.width = next.toFixed(1) + '%';
      if(pctEl) pctEl.textContent = Math.round(next) + '%';
      if(rowBarEl) rowBarEl.style.width = next.toFixed(1) + '%';
      if(rowPctEl) rowPctEl.textContent = Math.round(next) + '%';
      anyMoving = true;
    } else {
      _partDisplay[key] = target;
    }
  }

  _smoothRafId = anyMoving ? requestAnimationFrame(_tickSmooth) : null;
}

function _scheduleSmooth() {
  if(!_smoothRafId) _smoothRafId = requestAnimationFrame(_tickSmooth);
}
