function _resolveLogScope(scope = 'auto'){
  const s = String(scope || 'auto').trim().toLowerCase();
  if(s && s !== 'auto' && ['render', 'upload', 'channels'].includes(s)) return s;
  if(currentView === 'channels') return 'channels';
  if(currentView === 'upload') return 'upload';
  return 'render';
}

function _getLogBox(scope){
  const idMap = {
    render: 'event_log_render',
    upload: 'event_log_upload',
    channels: 'event_log_channels',
  };
  return qs(idMap[scope] || 'event_log_render');
}

function _sanitizeEventText(text){
  let t = String(text || '');
  // hide UUID/job ids to keep UI clean
  t = t.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, '[job]');
  return t;
}

function addEvent(text, scope = 'auto'){
  const normalized = _sanitizeEventText(String(text || '').trim());
  if(!normalized) return;
  const skipPrefixes = ['GET /api/jobs', 'GET /api/jobs/', 'GET /health'];
  if (skipPrefixes.some(p => normalized.startsWith(p))) return;
  const techNoise = [
    'traceback (most recent call last)',
    'file "',
    'runtimeerror:',
    'raise runtimeerror',
    '---- latest failure logs ----'
  ];
  const low = normalized.toLowerCase();
  if (techNoise.some(t => low.includes(t))) return;

  const resolvedScope = _resolveLogScope(scope);
  const st = logStateByScope[resolvedScope] || logStateByScope.render;
  const now = Date.now();
  const box = _getLogBox(resolvedScope);
  if (!box) return;
  if (normalized === st.lastText && (now - st.lastAt) <= LOG_DEDUPE_WINDOW_MS && st.lastNode) {
    st.lastCount += 1;
    st.lastNode.textContent = `[${new Date().toLocaleTimeString()}] ${normalized} (x${st.lastCount})`;
    st.lastAt = now;
    return;
  }

  const div = document.createElement('div');
  div.className = 'logLine';
  if (/failed|error/i.test(normalized)) div.classList.add('important', 'error');
  else if (/render complete|job completed|complete/i.test(normalized)) div.classList.add('important', 'success');
  else if (/stage:|resume queued|render queued|download complete|downloading youtube/i.test(normalized)) div.classList.add('important');
  div.textContent = `[${new Date().toLocaleTimeString()}] ${normalized}`;
  box.prepend(div);
  while (box.children.length > 28) box.removeChild(box.lastChild);
  st.lastText = normalized;
  st.lastAt = now;
  st.lastNode = div;
  st.lastCount = 1;
}

// ── Toast notifications ─────────────────────────────────────────────────────
// Ephemeral, non-blocking feedback. Does NOT replace addEvent() or status lines.
// type: 'info' (4 s) | 'success' (4 s) | 'error' (6 s)
function showToast(message, type = 'info') {
  const root = document.getElementById('toastRoot');
  if (!root) return; // container missing → fail silently
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = String(message || '');
  root.appendChild(el);
  const delay = type === 'error' ? 6000 : 4000;
  setTimeout(() => {
    el.classList.add('dismissing');
    setTimeout(() => el.remove(), 120); // wait for toastOut animation
  }, delay);
}

