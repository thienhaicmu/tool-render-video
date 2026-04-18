function _startUploadWs(runId){
  _stopUploadWs();
  if(uploadPollTimer){ clearInterval(uploadPollTimer); uploadPollTimer = null; }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/api/upload/schedule/runs/${runId}/ws`);
  uploadWs = ws;

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if(data.error) return;
      renderUploadRun(data);
      if(data.status === 'completed' || data.status === 'failed' || data.status === 'done'){
        _stopUploadWs();
        setUploadBusy(false);
        addEvent(`Upload run ${data.status}: ${runId}`);
      }
    } catch(_) {}
  };

  ws.onerror = () => {
    // Fallback to HTTP polling
    uploadWs = null;
    if(!uploadPollTimer){
      pollUploadRun();
      uploadPollTimer = setInterval(pollUploadRun, 2000);
    }
  };

  ws.onclose = () => { uploadWs = null; };
}

async function pollUploadRun(){
  if(!currentUploadRunId) return;
  const res = await fetch(`/api/upload/schedule/runs/${currentUploadRunId}`);
  const data = await res.json();
  if(!res.ok){
    addEvent(`Upload poll failed: ${_formatApiError(data.detail)}`);
    clearInterval(uploadPollTimer);
    uploadPollTimer = null;
    return;
  }
  renderUploadRun(data);
  if(data.status === 'completed' || data.status === 'failed'){
    clearInterval(uploadPollTimer);
    uploadPollTimer = null;
    setUploadBusy(false);
    addEvent(`Upload run ${data.status}: ${currentUploadRunId}`);
  }
}

async function scheduleUpload(){
  const action = (qs('upload_action_mode')?.value || 'upload').toLowerCase();
  if(action === 'login'){
    setUploadAction('login', 'running', 'Action is Login. Switch Action = Upload Videos to run upload.');
    addEvent('Action is Login. Switch Action to Upload Videos to run upload.');
    return;
  }
  const payload = collectUploadPayload();
  const validation = refreshUploadValidationState(payload);
  if(!validation.valid){
    setUploadAction('queue', 'failed', `Validation failed: ${validation.errors[0] || 'please review Upload settings.'}`);
    addEvent(`Validation error: ${validation.errors[0] || 'please review Upload settings.'}`);
    return;
  }
  if(!payload.use_schedule){
    addEvent(`Manual upload selection: ${payload.selected_files.length} video(s).`);
  }
  const loginOk = await checkUploadLoginStatus(false);
  if(!loginOk){
    setUploadAction('login_check', 'failed', 'Upload blocked: account is not logged in.');
    addEvent('Upload blocked: account is not logged in. Click Check Login Status or TikTok Login first.');
    return;
  }
  setUploadAction('queue', 'running', 'Queueing upload run...');
  const res = await fetch('/api/upload/schedule/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){
    setUploadAction('queue', 'failed', `Upload start failed: ${_formatApiError(data.detail)}`);
    addEvent(`Upload start failed: ${_formatApiError(data.detail)}`);
    return;
  }
  currentUploadRunId = data.run_id;
  renderUploadRun({
    run_id: currentUploadRunId,
    status: 'queued',
    stage: 'queued',
    message: 'Upload queued',
    progress_percent: 0,
    current_index: 0,
    total: 0,
    items: []
  });
  setUploadBusy(true);
  setUploadAction('queued', 'running', `Upload run queued: ${currentUploadRunId}`, `Mode: ${payload.use_schedule ? 'scheduled' : 'manual'}`, 0);
  addEvent(`Upload run queued: ${currentUploadRunId}`);
  _startUploadWs(currentUploadRunId);
}

