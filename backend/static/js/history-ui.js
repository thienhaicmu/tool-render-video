let historyItems = [];
let historyLoading = false;
let historyError = '';

function historyKindLabel(kind) {
  return kind === 'download' ? 'Download' : 'Render';
}

function historyStatusLabel(status) {
  return ({
    completed: 'Completed',
    partial: 'Partial',
    failed: 'Failed',
    interrupted: 'Interrupted',
    running: 'Running',
    queued: 'Queued',
  })[String(status || '').toLowerCase()] || 'Unknown';
}

function historyRelativeTime(value) {
  const ts = Date.parse(String(value || ''));
  if (!ts) return 'Unknown time';
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (sec < 60) return 'Just now';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} minute${min === 1 ? '' : 's'} ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? '' : 's'} ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} day${day === 1 ? '' : 's'} ago`;
  return new Date(ts).toLocaleString();
}

function renderHistoryState(html, statusText = '') {
  const list = qs('history_list');
  if (!list) return;
  list.innerHTML = html;
  if (qs('history_status_text')) qs('history_status_text').textContent = statusText;
}

function renderHistoryView() {
  const list = qs('history_list');
  if (!list) return;
  if (historyLoading) {
    renderHistoryState('<div class="historyState">Loading recent activity...</div>', 'Loading...');
    return;
  }
  if (historyError) {
    renderHistoryState(
      '<div class="historyState error">Could not load History<div style="margin-top:10px"><button class="secondaryButton" type="button" onclick="loadHistoryView()">Retry</button></div></div>',
      'Error'
    );
    return;
  }
  if (!historyItems.length) {
    renderHistoryState(
      '<div class="historyState">No recent activity yet<div style="margin-top:4px">Your recent Download and Render jobs will appear here.</div></div>',
      'No recent jobs'
    );
    return;
  }
  if (qs('history_status_text')) qs('history_status_text').textContent = `${historyItems.length} recent job${historyItems.length === 1 ? '' : 's'}`;
  list.innerHTML = historyItems.map((item) => {
    const kind = String(item.kind || 'render').toLowerCase();
    const status = String(item.status || '').toLowerCase();
    const openBtn = item.can_open_folder
      ? `<button class="ghostButton" type="button" onclick="openHistoryOutputFolder('${encodeURIComponent(item.job_id)}')">Open Output Folder</button>`
      : '';
    const retryBtn = item.can_retry
      ? `<button class="secondaryButton" type="button" onclick="retryHistoryDownload('${encodeURIComponent(item.job_id)}')">Retry Failed</button>`
      : '';
    const rerunBtn = item.can_rerun
      ? `<button class="secondaryButton" type="button" onclick="rerunHistoryRender('${encodeURIComponent(item.job_id)}')">Rerun</button>`
      : '';
    const sourceHint = item.source_hint ? `<div class="historySourceHint">${esc(item.source_hint)}</div>` : '';
    const outputHint = item.output_dir ? `<div class="historyOutputHint">Output: ${esc(item.output_dir)}</div>` : '';
    return `
      <div class="historyItem">
        <div class="historyMain">
          <div class="historyTop">
            <span class="historyKindBadge ${esc(kind)}">${esc(historyKindLabel(kind))}</span>
            <div class="historyTitle">${esc(item.title || 'Job')}</div>
            <span class="historyStatusBadge ${esc(status)}">${esc(historyStatusLabel(status))}</span>
            <span class="historyTime">${esc(historyRelativeTime(item.timestamp || item.updated_at || item.created_at))}</span>
          </div>
          ${sourceHint}
          <div class="historySummary">${esc(item.summary_text || '')}</div>
          ${outputHint}
        </div>
        <div class="historyActions">
          ${openBtn}
          ${retryBtn}
          ${rerunBtn}
        </div>
      </div>
    `;
  }).join('');
}

async function loadHistoryView() {
  historyLoading = true;
  historyError = '';
  renderHistoryView();
  try {
    const res = await fetch('/api/jobs/history?limit=20');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'History could not be loaded');
    historyItems = Array.isArray(data.items) ? data.items : [];
  } catch (err) {
    historyError = String(err?.message || 'History could not be loaded');
  } finally {
    historyLoading = false;
    renderHistoryView();
  }
}

function openHistoryOutputFolder(encodedJobId) {
  const jobId = decodeURIComponent(String(encodedJobId || ''));
  const item = historyItems.find((entry) => entry.job_id === jobId);
  if (!item || !item.output_dir) {
    showToast('Output folder is unavailable for this job', 'info');
    return;
  }
  if (typeof openStoredOutputPath === 'function') {
    openStoredOutputPath(item.output_dir);
    return;
  }
  showToast(item.output_dir, 'info');
}

async function retryHistoryDownload(encodedJobId) {
  const jobId = decodeURIComponent(String(encodedJobId || ''));
  try {
    if (typeof retryDownloadJobFromHistory !== 'function') throw new Error('Retry flow is unavailable');
    await retryDownloadJobFromHistory(jobId);
    await loadHistoryView();
  } catch (err) {
    showToast(String(err?.message || 'Retry could not be started'), 'error');
  }
}

async function rerunHistoryRender(encodedJobId) {
  const jobId = decodeURIComponent(String(encodedJobId || ''));
  try {
    if (typeof rerunRenderJob !== 'function') throw new Error('Render rerun is unavailable');
    await rerunRenderJob(jobId);
  } catch (err) {
    showToast(String(err?.message || 'Render job could not be loaded'), 'error');
  }
}
