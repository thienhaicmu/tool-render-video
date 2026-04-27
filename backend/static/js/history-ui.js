let historyItems = [];
let historyLoading = false;
let historyError = '';
let historyFilter = 'all';

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

function setHistoryFilter(filter) {
  historyFilter = String(filter || 'all');
  document.querySelectorAll('.hwFilterBtn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.filter === historyFilter);
  });
  renderHistoryView();
}

function _historySetStatus(text) {
  const el = qs('history_status_text');
  if (el) el.textContent = text;
}

function renderHistoryView() {
  const list = qs('history_list');
  if (!list) return;

  if (historyLoading) {
    list.innerHTML = `
      <div class="hwState">
        <div class="hwStateIcon">&#8635;</div>
        <div class="hwStateTitle">Loading&hellip;</div>
      </div>`;
    _historySetStatus('Loading…');
    return;
  }

  if (historyError) {
    list.innerHTML = `
      <div class="hwState error">
        <div class="hwStateIcon">&#9888;</div>
        <div class="hwStateTitle">Could not load history</div>
        <div class="hwStateSub">${esc(historyError)}</div>
        <button class="secondaryButton" style="margin-top:12px" type="button" onclick="loadHistoryView()">Retry</button>
      </div>`;
    _historySetStatus('Error');
    return;
  }

  const filtered = historyItems.filter((item) => {
    const kind   = String(item.kind   || 'render').toLowerCase();
    const status = String(item.status || '').toLowerCase();
    if (historyFilter === 'render')    return kind === 'render';
    if (historyFilter === 'download')  return kind === 'download';
    if (historyFilter === 'completed') return status === 'completed';
    if (historyFilter === 'failed')    return status === 'failed' || status === 'interrupted';
    return true;
  });

  if (!filtered.length) {
    const emptyMsg = historyItems.length && historyFilter !== 'all'
      ? 'No jobs match this filter.'
      : 'No recent activity yet. Completed render, download, and upload jobs will appear here.';
    list.innerHTML = `
      <div class="hwEmpty">
        <div class="hwEmptyIcon">&#128203;</div>
        <div class="hwEmptyTitle">${historyItems.length ? 'No matches' : 'No history yet'}</div>
        <div class="hwEmptySub">${emptyMsg}</div>
      </div>`;
    _historySetStatus(historyItems.length ? `${historyItems.length} jobs, none match filter` : 'No recent jobs');
    return;
  }

  _historySetStatus(`${filtered.length} job${filtered.length === 1 ? '' : 's'}`);

  list.innerHTML = filtered.map((item) => {
    const kind   = String(item.kind   || 'render').toLowerCase();
    const status = String(item.status || '').toLowerCase();

    const kindIcon = kind === 'download' ? '&#11015;' : '&#127916;';

    const openBtn = item.can_open_folder
      ? `<button class="hwActionBtn ghost" type="button" onclick="openHistoryOutputFolder('${encodeURIComponent(item.job_id)}')">Open Folder</button>`
      : '';
    const retryBtn = item.can_retry
      ? `<button class="hwActionBtn" type="button" onclick="retryHistoryDownload('${encodeURIComponent(item.job_id)}')">Retry</button>`
      : '';
    const rerunBtn = item.can_rerun
      ? `<button class="hwActionBtn" type="button" onclick="rerunHistoryRender('${encodeURIComponent(item.job_id)}')">Rerun</button>`
      : '';

    const sourceHint = item.source_hint
      ? `<div class="hwCardSource" title="${esc(item.source_hint)}">${esc(item.source_hint)}</div>`
      : '';
    const outputHint = item.output_dir
      ? `<div class="hwCardOutput" title="${esc(item.output_dir)}">&#128193; ${esc(item.output_dir)}</div>`
      : '';
    const summary = item.summary_text
      ? `<div class="hwCardSummary">${esc(item.summary_text)}</div>`
      : '';

    return `
      <div class="hwCard ${esc(status)}">
        <div class="hwCardLeft">
          <span class="hwKindIcon" aria-hidden="true">${kindIcon}</span>
          <span class="hwKindBadge ${esc(kind)}">${esc(historyKindLabel(kind))}</span>
        </div>
        <div class="hwCardMain">
          <div class="hwCardTitle">${esc(item.title || 'Job')}</div>
          <div class="hwCardMeta">
            <span class="hwCardTime">${esc(historyRelativeTime(item.timestamp || item.updated_at || item.created_at))}</span>
            ${summary}
          </div>
          ${sourceHint}
          ${outputHint}
        </div>
        <div class="hwCardRight">
          <span class="hwStatusBadge ${esc(status)}">${esc(historyStatusLabel(status))}</span>
          <div class="hwCardActions">${openBtn}${retryBtn}${rerunBtn}</div>
        </div>
      </div>`;
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
