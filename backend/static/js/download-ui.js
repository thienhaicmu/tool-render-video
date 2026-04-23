let downloadQueueItems = [];
let currentDownloadJobId = null;
let currentDownloadJobStatus = '';
let currentDownloadOutputDir = '';
let downloadWs = null;
let downloadPollTimer = null;
let downloadJobPartMap = {};

function detectDownloadSource(url) {
  try {
    const u = new URL(String(url || '').trim());
    const host = (u.hostname || '').toLowerCase().replace(/^www\./, '');
    if (host === 'youtube.com' || host === 'youtu.be' || host === 'youtube-nocookie.com' || host.endsWith('.youtube.com') || host.endsWith('.youtube-nocookie.com')) return 'youtube';
    if (host === 'facebook.com' || host === 'fb.watch' || host.endsWith('.facebook.com')) return 'facebook';
    if (host === 'instagram.com' || host === 'instagr.am' || host.endsWith('.instagram.com')) return 'instagram';
  } catch (_) {}
  return 'unknown';
}

function downloadSourceLabel(source) {
  return ({ youtube: 'YouTube', facebook: 'Facebook', instagram: 'Instagram', unknown: 'Unknown' })[source] || 'Unknown';
}

function downloadStatusLabel(status) {
  return ({
    waiting: 'Waiting',
    downloading: 'Downloading',
    done: 'Saved',
    failed: 'Failed',
    unsupported: 'Unsupported link',
  })[status] || 'Waiting';
}

function getDownloadQueueItem(url) {
  return downloadQueueItems.find((item) => item.url === url) || null;
}

function parseDownloadLinks() {
  const raw = (qs('download_links_input')?.value || '');
  const lines = raw.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  const deduped = [];
  const seen = new Set();
  for (const line of lines) {
    if (seen.has(line)) continue;
    seen.add(line);
    deduped.push(line);
  }
  const next = deduped.map((url) => {
    const existing = getDownloadQueueItem(url);
    if (existing) return existing;
    const source = detectDownloadSource(url);
    return {
      id: `download_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      url,
      source,
      title: '',
      status: source === 'unknown' ? 'unsupported' : 'waiting',
      progressPercent: 0,
      message: source === 'unknown' ? 'Unsupported link' : 'Waiting',
      outputFile: '',
      partNo: null,
    };
  });
  downloadQueueItems = next;
  renderDownloadQueue();
}

function clearDownloadLinks() {
  downloadQueueItems = [];
  downloadJobPartMap = {};
  currentDownloadJobId = null;
  currentDownloadJobStatus = '';
  if (qs('download_links_input')) qs('download_links_input').value = '';
  renderDownloadQueue();
}

async function pickDownloadFolder() {
  let picked = '';
  if (window.electronAPI && typeof window.electronAPI.pickDirectory === 'function') {
    try { picked = String(await window.electronAPI.pickDirectory()).trim(); } catch (_) {}
  } else {
    picked = (prompt('Paste folder path:') || '').trim();
  }
  if (!picked) return;
  currentDownloadOutputDir = picked;
  if (qs('download_output_dir')) qs('download_output_dir').value = picked;
  renderDownloadQueue();
}

function openDownloadFolder() {
  const target = (qs('download_output_dir')?.value || currentDownloadOutputDir || '').trim();
  if (!target) {
    showToast('Choose a save folder first', 'info');
    return;
  }
  if (window.electronAPI?.openPath) {
    Promise.resolve(window.electronAPI.openPath(target))
      .then(() => showToast('Opening folder', 'success'))
      .catch(() => showToast(target, 'info'));
    return;
  }
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(target).then(() => showToast('Folder path copied', 'success')).catch(() => showToast(target, 'info'));
    return;
  }
  showToast(target, 'info');
}

function downloadQueueCounts() {
  return downloadQueueItems.reduce((acc, item) => {
    acc.total += 1;
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, { total: 0, waiting: 0, downloading: 0, done: 0, failed: 0, unsupported: 0 });
}

function renderDownloadQueue() {
  const list = qs('download_queue_list');
  if (!list) return;
  const counts = downloadQueueCounts();
  const statusEl = qs('download_batch_status');
  const statusText = currentDownloadJobId
    ? (currentDownloadJobStatus === 'completed' ? 'Completed' : currentDownloadJobStatus === 'failed' ? 'Failed' : 'Downloading')
    : 'Idle';
  if (statusEl) {
    statusEl.textContent = statusText;
    statusEl.dataset.state = String(currentDownloadJobStatus || '').toLowerCase() || 'idle';
  }
  if (qs('download_batch_meta')) {
    const bits = [];
    if (counts.done) bits.push(`${counts.done} saved`);
    if (counts.downloading) bits.push(`${counts.downloading} downloading`);
    if (counts.failed) bits.push(`${counts.failed} failed`);
    if (counts.unsupported) bits.push(`${counts.unsupported} unsupported`);
    qs('download_batch_meta').textContent = bits.join(' · ') || 'No active batch';
  }
  if (qs('download_queue_meta')) {
    qs('download_queue_meta').textContent = counts.total ? `${counts.total} item${counts.total !== 1 ? 's' : ''}` : '0 items';
  }
  if (qs('download_summary_text')) {
    if (!counts.total) qs('download_summary_text').textContent = 'Paste public social video links to build a download queue.';
    else qs('download_summary_text').textContent = `${counts.total} queued · ${counts.done} saved · ${counts.failed} failed · ${counts.unsupported} unsupported`;
  }

  if (!downloadQueueItems.length) {
    list.innerHTML = '<div class="emptyState">Paste one or more public links, then click Parse Links.</div>';
  } else {
    list.innerHTML = downloadQueueItems.map((item) => {
      const title = item.title || item.url;
      const status = item.status || 'waiting';
      const retryDisabled = (status !== 'failed') || (currentDownloadJobStatus === 'running');
      const removeDisabled = status === 'downloading';
      return `
        <div class="downloadQueueRow ${esc(status)}">
          <div class="downloadRowMain">
            <div style="display:flex;gap:8px;align-items:center;min-width:0">
              <span class="downloadSourceBadge ${esc(item.source)}">${esc(downloadSourceLabel(item.source))}</span>
              <div class="downloadRowTitle">${status === 'done' ? '✓ ' : ''}${esc(title)}</div>
            </div>
            <div class="downloadRowUrl">${esc(item.url)}</div>
            ${item.outputFile ? `<div class="downloadRowPath">${esc(item.outputFile)}</div>` : ''}
            ${(status === 'failed' || status === 'unsupported') && item.message ? `<div class="downloadRowError">${esc(item.message)}</div>` : ''}
          </div>
          <div class="downloadRowStatus">
            <span class="downloadStatusBadge ${esc(status)}">${esc(downloadStatusLabel(status))}</span>
            <div class="downloadMiniProgress"><div class="downloadMiniProgressValue" style="width:${Number(item.progressPercent || 0)}%"></div></div>
          </div>
          <div class="downloadRowStatus">
            <div class="downloadRowUrl">${esc(item.message || '')}</div>
            <div class="downloadRowUrl">${Math.round(Number(item.progressPercent || 0))}%</div>
          </div>
          <div class="downloadRowActions">
            <button class="downloadActionBtn" type="button" onclick="retryDownloadItem('${encodeURIComponent(item.url)}')" ${retryDisabled ? 'disabled' : ''}>Retry</button>
            <button class="downloadActionBtn" type="button" onclick="removeDownloadItem('${encodeURIComponent(item.url)}')" ${removeDisabled ? 'disabled' : ''}>Remove</button>
          </div>
        </div>
      `;
    }).join('');
  }

  if (qs('download_retry_failed_btn')) qs('download_retry_failed_btn').disabled = !counts.failed || currentDownloadJobStatus === 'running';
  if (qs('download_start_btn')) {
    const hasSupported = downloadQueueItems.some((item) => item.source !== 'unknown' && item.status !== 'done');
    qs('download_start_btn').disabled = !hasSupported || currentDownloadJobStatus === 'running';
  }
}

function _supportedDownloadItems(filterStatuses = null) {
  return downloadQueueItems.filter((item) => {
    if (item.source === 'unknown') return false;
    if (!filterStatuses) return true;
    return filterStatuses.includes(item.status);
  });
}

async function startDownloadBatch() {
  const outputDir = (qs('download_output_dir')?.value || currentDownloadOutputDir || '').trim();
  if (!outputDir) {
    showToast('Choose a save folder before starting downloads', 'error');
    return;
  }
  const candidates = downloadQueueItems.filter((item) => item.status !== 'done' && item.status !== 'unsupported');
  if (!candidates.length) {
    showToast('No queued links are ready to download', 'info');
    return;
  }
  const res = await fetch('/api/download/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls: candidates.map((item) => item.url), output_dir: outputDir }),
  });
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || 'Download batch could not be started', 'error');
    return;
  }
  currentDownloadJobId = data.job_id;
  currentDownloadJobStatus = 'running';
  currentDownloadOutputDir = data.output_dir || outputDir;
  downloadJobPartMap = {};
  (data.items || []).forEach((item) => {
    downloadJobPartMap[item.part_no] = item.url;
    const row = getDownloadQueueItem(item.url);
    if (row) {
      row.partNo = item.part_no;
      row.status = item.source === 'unknown' ? 'unsupported' : 'waiting';
      row.progressPercent = 0;
      row.message = item.source === 'unknown' ? 'Unsupported link' : 'Waiting';
    }
  });
  addEvent(`Download batch queued: ${currentDownloadJobId}`, 'render');
  showToast('Download batch queued', 'success');
  renderDownloadQueue();
  startDownloadPolling();
}

function _applyDownloadJobUpdate(job, parts) {
  currentDownloadJobStatus = String(job?.status || '').toLowerCase();
  for (const part of (parts || [])) {
    const partNo = Number(part.part_no || 0);
    const url = downloadJobPartMap[partNo];
    if (!url) continue;
    const item = getDownloadQueueItem(url);
    if (!item) continue;
    item.partNo = partNo;
    item.status = String(part.status || '').toLowerCase() || item.status;
    item.progressPercent = Number(part.progress_percent || 0);
    item.message = String(part.message || '').trim() || item.message;
    item.outputFile = String(part.output_file || '').trim();
    if (String(part.part_name || '').trim() && String(part.part_name || '').trim() !== item.url) {
      item.title = String(part.part_name || '').trim();
    }
  }
  if (currentDownloadJobStatus === 'completed' || currentDownloadJobStatus === 'failed') {
    stopDownloadPolling();
    showToast(currentDownloadJobStatus === 'completed' ? 'Downloads finished' : 'Downloads finished with failures', currentDownloadJobStatus === 'completed' ? 'success' : 'info');
  }
  renderDownloadQueue();
}

async function pollDownloadJob() {
  if (!currentDownloadJobId) return;
  try {
    const [jobRes, partsRes] = await Promise.all([
      fetch(`/api/jobs/${currentDownloadJobId}`),
      fetch(`/api/jobs/${currentDownloadJobId}/parts`),
    ]);
    if (!jobRes.ok || !partsRes.ok) return;
    const job = await jobRes.json();
    const partsData = await partsRes.json();
    _applyDownloadJobUpdate(job, partsData.items || []);
  } catch (_) {}
}

function stopDownloadPolling() {
  if (downloadWs) {
    try { downloadWs.close(); } catch (_) {}
    downloadWs = null;
  }
  if (downloadPollTimer) {
    clearInterval(downloadPollTimer);
    downloadPollTimer = null;
  }
}

function startDownloadPolling() {
  stopDownloadPolling();
  if (!currentDownloadJobId) return;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/api/jobs/${currentDownloadJobId}/ws`);
  downloadWs = ws;
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.error) return;
      _applyDownloadJobUpdate(data.job || {}, data.parts || []);
    } catch (_) {}
  };
  ws.onerror = () => {
    downloadWs = null;
    if (!downloadPollTimer) {
      pollDownloadJob();
      downloadPollTimer = setInterval(pollDownloadJob, 2000);
    }
  };
  ws.onclose = () => { downloadWs = null; };
}

function _resetDownloadItemForRetry(item) {
  item.status = 'waiting';
  item.progressPercent = 0;
  item.message = 'Retry queued';
  item.outputFile = '';
}

async function retryDownloadItem(encodedUrl) {
  const url = decodeURIComponent(String(encodedUrl || ''));
  const item = getDownloadQueueItem(url);
  if (!item || !currentDownloadJobId || !item.partNo) return;
  const res = await fetch(`/api/download/retry/${currentDownloadJobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_numbers: [item.partNo] }),
  });
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || 'Retry could not be started', 'error');
    return;
  }
  currentDownloadJobStatus = 'running';
  _resetDownloadItemForRetry(item);
  renderDownloadQueue();
  startDownloadPolling();
}

async function retryFailedDownloads() {
  const failed = downloadQueueItems.filter((item) => item.status === 'failed' && item.partNo).map((item) => item.partNo);
  if (!currentDownloadJobId || !failed.length) return;
  const res = await fetch(`/api/download/retry/${currentDownloadJobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_numbers: failed }),
  });
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || 'Retry failed items could not be started', 'error');
    return;
  }
  for (const item of downloadQueueItems) {
    if (failed.includes(item.partNo)) {
      _resetDownloadItemForRetry(item);
    }
  }
  currentDownloadJobStatus = 'running';
  renderDownloadQueue();
  startDownloadPolling();
}

function removeDownloadItem(encodedUrl) {
  const url = decodeURIComponent(String(encodedUrl || ''));
  downloadQueueItems = downloadQueueItems.filter((item) => item.url !== url);
  renderDownloadQueue();
}

async function loadDownloadJobIntoQueue(jobId) {
  const id = String(jobId || '').trim();
  if (!id) return;
  const [jobRes, partsRes] = await Promise.all([
    fetch(`/api/jobs/${encodeURIComponent(id)}`),
    fetch(`/api/jobs/${encodeURIComponent(id)}/parts`),
  ]);
  const job = await jobRes.json();
  const partsData = await partsRes.json();
  if (!jobRes.ok || !partsRes.ok) {
    throw new Error(job.detail || partsData.detail || 'Download job could not be loaded');
  }
  let payload = {};
  try {
    payload = job.payload_json ? (typeof job.payload_json === 'string' ? JSON.parse(job.payload_json) : job.payload_json) : {};
  } catch (_) {}
  let result = {};
  try {
    result = job.result_json ? (typeof job.result_json === 'string' ? JSON.parse(job.result_json) : job.result_json) : {};
  } catch (_) {}
  const urls = Array.isArray(payload.urls) ? payload.urls : [];
  const parts = Array.isArray(partsData.items) ? partsData.items : [];
  downloadJobPartMap = {};
  downloadQueueItems = urls.map((url, idx) => {
    const partNo = idx + 1;
    const part = parts.find((item) => Number(item.part_no || 0) === partNo) || null;
    if (part) downloadJobPartMap[partNo] = url;
    const status = String(part?.status || (detectDownloadSource(url) === 'unknown' ? 'unsupported' : 'waiting')).toLowerCase();
    return {
      id: `download_${partNo}_${Date.now()}`,
      url,
      source: detectDownloadSource(url),
      title: part && String(part.part_name || '').trim() !== url ? String(part.part_name || '').trim() : '',
      status,
      progressPercent: Number(part?.progress_percent || 0),
      message: String(part?.message || (status === 'unsupported' ? 'Unsupported link' : 'Waiting')),
      outputFile: String(part?.output_file || '').trim(),
      partNo,
    };
  });
  currentDownloadJobId = id;
  currentDownloadJobStatus = String(job.status || '').toLowerCase();
  currentDownloadOutputDir = String(result.output_dir || payload.output_dir || '').trim();
  if (qs('download_output_dir')) qs('download_output_dir').value = currentDownloadOutputDir;
  renderDownloadQueue();
  if (currentDownloadJobStatus === 'running' || currentDownloadJobStatus === 'queued') startDownloadPolling();
}

async function retryDownloadJobFromHistory(jobId) {
  const id = String(jobId || '').trim();
  const res = await fetch(`/api/download/retry/${encodeURIComponent(id)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_numbers: [] }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Retry failed items could not be started');
  }
  await loadDownloadJobIntoQueue(id);
  setView('download');
  showToast('Retry queued for failed downloads', 'success');
}
