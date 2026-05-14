/* WebSocket transport with polling fallback.
   Primary:  ws(s)://host/api/jobs/{jobId}/ws  → messages: { job, parts, summary }
   Fallback: GET /api/jobs/{jobId} + GET /api/jobs/{jobId}/parts every 3s
*/

const POLL_INTERVAL = 3000;

function wsUrl(jobId) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/api/jobs/${jobId}/ws`;
}

export function openJobStream(jobId, callbacks) {
  const { onMessage, onError, onClose } = callbacks;
  let ws = null;
  let pollTimer = null;
  let closed = false;

  function startPolling() {
    if (pollTimer || closed) return;
    pollTimer = setInterval(async () => {
      if (closed) { clearInterval(pollTimer); return; }
      try {
        const [jobRes, partsRes] = await Promise.all([
          fetch(`/api/jobs/${encodeURIComponent(jobId)}`),
          fetch(`/api/jobs/${encodeURIComponent(jobId)}/parts`),
        ]);
        if (!jobRes.ok || !partsRes.ok) return;
        const job   = await jobRes.json();
        const parts = await partsRes.json();
        onMessage({ job, parts, summary: null });
      } catch (err) {
        onError && onError(err);
      }
    }, POLL_INTERVAL);
  }

  function tryWs() {
    try {
      ws = new WebSocket(wsUrl(jobId));
    } catch {
      startPolling();
      return;
    }

    ws.onmessage = ev => {
      try {
        const data = JSON.parse(ev.data);
        onMessage(data);
      } catch { /* ignore malformed */ }
    };

    ws.onerror = () => {
      if (!closed) startPolling();
    };

    ws.onclose = () => {
      if (!closed) startPolling();
      onClose && onClose();
    };
  }

  tryWs();

  return function close() {
    closed = true;
    clearInterval(pollTimer);
    if (ws && ws.readyState < 2) ws.close();
  };
}

export async function fetchJson(url, options) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* ignore */ }
    const err = new Error(body?.detail || body?.message || `HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}
