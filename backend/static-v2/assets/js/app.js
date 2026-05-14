import { router }         from './router.js';
import { shell }          from './components/shell.js';
import { systemStore }    from './store/system.js';
import { readinessStore } from './store/readiness.js';

async function boot() {
  const root = document.getElementById('app');

  root.innerHTML = shell.render();
  shell.mount(root);

  await systemStore.init();

  // Load warmup readiness in background — never blocks navigation
  readinessStore.load();

  router.init();
}

boot().catch(err => {
  console.error('[app] boot failed:', err);
  const root = document.getElementById('app');
  if (root) {
    root.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100vh;background:#0E1117;color:#C8D3DA;font-family:system-ui,sans-serif">
        <div style="max-width:420px;text-align:center;display:flex;flex-direction:column;gap:16px;padding:32px">
          <div style="font-size:22px;font-weight:600;color:#C8D3DA">Backend is not ready yet</div>
          <div style="font-size:14px;color:#6B7A89;line-height:1.5">The app could not connect to the backend. Try again in a moment.</div>
          <button onclick="location.reload()" style="margin-top:8px;padding:10px 24px;background:#76E0C0;color:#0E1117;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-size:14px">
            Retry
          </button>
        </div>
      </div>
    `;
  }
});
