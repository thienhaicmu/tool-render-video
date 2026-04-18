// ── Warmup status ──────────────────────────────────────────────────────────
let _warmupInterval = null;
let _warmupPanelVisible = false;

function toggleWarmupPanel(){
  let panel = document.getElementById('warmup_panel');
  if(!panel) return;
  _warmupPanelVisible = !_warmupPanelVisible;
  panel.style.display = _warmupPanelVisible ? 'block' : 'none';
}

async function pollWarmupStatus(){
  try {
    const res = await fetch('/api/warmup/status');
    const data = await res.json();
    const chip = document.getElementById('warmup_chip');
    if(!chip) return;

    const { ready_count, total_count, all_ready, items, errors } = data;

    if(all_ready){
      chip.textContent = '✅ Ready';
      chip.style.background = '#22c55e22';
      chip.style.color = '#22c55e';
      clearInterval(_warmupInterval);
      _warmupInterval = null;
    } else if(errors && errors.length){
      chip.textContent = `⚠️ ${ready_count}/${total_count} ready`;
      chip.style.color = '#f59e0b';
    } else {
      // Find what's currently downloading
      const active = (items || []).find(i => i.status === 'downloading');
      chip.textContent = active
        ? `⏳ ${active.message.replace(/\(.*?\)/,'').trim()}`
        : `⏳ ${ready_count}/${total_count} ready`;
    }

    // Update detail panel
    const panel = document.getElementById('warmup_panel');
    if(panel){
      panel.innerHTML = (items || []).map(i => {
        const icon = i.status === 'ready' ? '✅'
                   : i.status === 'error' ? '❌'
                   : i.status === 'downloading' ? '⏳'
                   : '🔲';
        const size = i.size_mb > 0 ? ` (${i.size_mb}MB)` : '';
        return `<div style="padding:4px 0;font-size:12px">${icon} <b>${i.key}</b>${size} — ${i.message}</div>`;
      }).join('');
    }
  } catch(_){}
}

function initWarmup(){
  // Insert detail panel after chip
  const chip = document.getElementById('warmup_chip');
  if(chip && !document.getElementById('warmup_panel')){
    const panel = document.createElement('div');
    panel.id = 'warmup_panel';
    panel.style.cssText = 'display:none;position:absolute;top:48px;right:12px;background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px 16px;min-width:320px;z-index:999;box-shadow:0 8px 24px #0008';
    document.querySelector('.headerChips').style.position = 'relative';
    document.querySelector('.headerChips').appendChild(panel);
  }
  pollWarmupStatus();
  _warmupInterval = setInterval(pollWarmupStatus, 3000);
}
// ── End warmup ─────────────────────────────────────────────────────────────
