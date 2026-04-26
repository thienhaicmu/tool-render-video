var _logActiveFilter = 'all';

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

function _setLogLineContent(node, message, count = 1) {
  if (!node) return;
  node.textContent = '';
  const rawBase = String(message || '');
  const raw = count > 1 ? `${rawBase} (x${count})` : rawBase;
  const match = raw.match(/^(\[[^\]]+\]|\d{1,2}:\d{2}:\d{2}(?:\s?[AP]M)?)\s*(.*)$/i);

  const timeEl = document.createElement('span');
  timeEl.className = 'logTime';
  timeEl.textContent = match
    ? match[1].replace(/^\[|\]$/g, '')
    : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const msgEl = document.createElement('span');
  msgEl.className = 'logMessage';
  msgEl.textContent = match ? match[2] : raw;

  node.appendChild(timeEl);
  node.appendChild(msgEl);

  const low = raw.toLowerCase();
  node.classList.toggle('isError', /error|failed|exception|traceback|fatal/.test(low));
  node.classList.toggle('isWarning', /warn|retry|stalled|timeout/.test(low));
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
  if (resolvedScope === 'render') {
    const latest = qs('abp_summary_latest');
    if (latest) latest.textContent = normalized;
    const finalLatest = qs('abp_latest');
    if (finalLatest) finalLatest.textContent = normalized;
    const rcLatest = qs('rc_latest');
    if (rcLatest) rcLatest.textContent = normalized;
  }
  if (normalized === st.lastText && (now - st.lastAt) <= LOG_DEDUPE_WINDOW_MS && st.lastNode) {
    st.lastCount += 1;
    _setLogLineContent(st.lastNode, normalized, st.lastCount);
    st.lastAt = now;
    return;
  }

  const div = document.createElement('div');
  div.className = 'logLine';
  if (/failed|error/i.test(normalized)) div.classList.add('important', 'error');
  else if (/render complete|job completed|complete/i.test(normalized)) div.classList.add('important', 'success');
  else if (/stage:|resume queued|render queued|download complete|downloading youtube/i.test(normalized)) div.classList.add('important');
  if (/failed|error|exception|traceback|fatal/i.test(normalized)) div.classList.add('isError');
  if (/warn|retry|stalled|timeout/i.test(normalized)) div.classList.add('isWarning');
  _setLogLineContent(div, normalized, 1);
  const emptyNode = box.querySelector('.rcLogEmpty');
  if (emptyNode) emptyNode.remove();
  box.prepend(div);
  if (resolvedScope === 'render' && _logActiveFilter !== 'all') {
    const low2 = normalized.toLowerCase();
    let vis = true;
    if (_logActiveFilter === 'error')       vis = /error|fail/.test(low2);
    else if (_logActiveFilter === 'ffmpeg') vis = low2.includes('ffmpeg');
    else if (_logActiveFilter === 'system') vis = !(/error|fail/.test(low2)) && !low2.includes('ffmpeg');
    if (!vis) div.style.display = 'none';
  }
  while (box.children.length > 40) box.removeChild(box.lastChild);
  if (typeof _logAutoScroll !== 'undefined' && _logAutoScroll && resolvedScope === 'render') {
    box.scrollTop = 0;
  }
  st.lastText = normalized;
  st.lastAt = now;
  st.lastNode = div;
  st.lastCount = 1;
}

// ── Log filter ──────────────────────────────────────────────────────────────
function filterRenderLogs(cat) {
  _logActiveFilter = cat || 'all';
  const box = document.getElementById('event_log_render');
  if (box) {
    box.querySelectorAll('.logLine').forEach(line => {
      const text = line.textContent.toLowerCase();
      let show = true;
      if (_logActiveFilter === 'error')       show = /error|fail/.test(text);
      else if (_logActiveFilter === 'ffmpeg') show = text.includes('ffmpeg');
      else if (_logActiveFilter === 'system') show = !(/error|fail/.test(text)) && !text.includes('ffmpeg');
      line.style.display = show ? '' : 'none';
    });
  }
  document.querySelectorAll('.rcLogFilterBtn').forEach(btn => {
    btn.classList.toggle('isActive', btn.dataset.filter === _logActiveFilter);
  });
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

