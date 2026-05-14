/* Transport layer — WebSocket primary, polling fallback.
   Primary:  ws(s)://host/api/jobs/{jobId}/ws  → {job, parts, summary}
   Fallback: GET /api/jobs/{jobId} + GET /api/jobs/{jobId}/parts every 3s
   Terminal: completed, completed_with_errors, failed, interrupted
*/

const POLL_INTERVAL = 3000;
export const TERMINAL_STATUSES = new Set([
  'completed', 'completed_with_errors', 'failed', 'interrupted',
]);

function wsUrl(jobId) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/api/jobs/${encodeURIComponent(jobId)}/ws`;
}

/* Low-level stream — returns { close(), usingPolling } */
export function openJobStream(jobId, callbacks) {
  const { onMessage, onError, onClose } = callbacks;
  let ws = null;
  let pollTimer = null;
  let closed = false;
  let usingPolling = false;

  function stopPolling() { clearInterval(pollTimer); pollTimer = null; }

  async function doPoll() {
    if (closed) { stopPolling(); return; }
    try {
      const [jobRes, partsRes] = await Promise.all([
        fetch(`/api/jobs/${encodeURIComponent(jobId)}`),
        fetch(`/api/jobs/${encodeURIComponent(jobId)}/parts`),
      ]);
      if (!jobRes.ok) {
        if (jobRes.status === 404) { stopPolling(); onClose && onClose(null); }
        return;
      }
      const job   = await jobRes.json();
      const raw   = partsRes.ok ? await partsRes.json() : {};
      const parts = Array.isArray(raw) ? raw : (raw?.items ?? []);
      onMessage({ job, parts, summary: null, _transport: 'polling' });
      if (TERMINAL_STATUSES.has(job?.status)) {
        stopPolling();
        onClose && onClose(job.status);
      }
    } catch (err) {
      onError && onError(err);
    }
  }

  function startPolling() {
    if (pollTimer || closed) return;
    usingPolling = true;
    doPoll();
    pollTimer = setInterval(doPoll, POLL_INTERVAL);
  }

  function tryWs() {
    try { ws = new WebSocket(wsUrl(jobId)); } catch { startPolling(); return; }

    ws.onopen = () => { usingPolling = false; };

    ws.onmessage = ev => {
      try {
        const data = JSON.parse(ev.data);
        if (data?.error) return;
        onMessage({ ...data, _transport: 'websocket' });
        if (TERMINAL_STATUSES.has(data?.job?.status) && !pollTimer) {
          // One authoritative poll after WS terminal signal (WS may not close)
          setTimeout(() => { if (!closed) doPoll(); }, 600);
        }
      } catch { /* ignore malformed */ }
    };

    ws.onerror = () => { if (!closed && !usingPolling) startPolling(); };
    ws.onclose = ev => {
      if (!closed && !usingPolling) startPolling();
      if (ev.wasClean) onClose && onClose(null);
    };
  }

  tryWs();

  return {
    get usingPolling() { return usingPolling; },
    close() {
      closed = true;
      stopPolling();
      if (ws && ws.readyState < 2) ws.close();
    },
  };
}

/* High-level subscribe API used by screens. */
export function subscribeJob(jobId, { onUpdate, onTerminal, onTransportChange } = {}) {
  let transportMode = 'connecting';

  const stream = openJobStream(jobId, {
    onMessage(data) {
      const next = data._transport === 'polling' ? 'polling' : 'websocket';
      if (next !== transportMode) {
        transportMode = next;
        onTransportChange && onTransportChange(transportMode);
      }
      onUpdate && onUpdate(data);
    },
    onError() {
      if (transportMode !== 'polling') {
        transportMode = 'polling';
        onTransportChange && onTransportChange('polling');
      }
    },
    onClose(status) {
      if (status && TERMINAL_STATUSES.has(status)) {
        onTerminal && onTerminal(status);
      }
    },
  });

  return {
    getTransportMode() { return transportMode; },
    unsubscribe() { stream.close(); },
  };
}

/* Typed HTTP client */
export async function fetchJson(url, options) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* ignore */ }
    const detail = body?.detail;
    let msg;
    if (Array.isArray(detail)) {
      msg = detail.map(e => e?.msg || JSON.stringify(e)).join('; ');
    } else {
      msg = typeof detail === 'string' ? detail : (body?.message || `HTTP ${res.status}`);
    }
    const err = new Error(msg);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}
