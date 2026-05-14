import { router } from './router.js';
import { shell } from './components/shell.js';
import { systemStore } from './store/system.js';

async function boot() {
  const root = document.getElementById('app');

  root.innerHTML = shell.render();
  shell.mount(root);

  await systemStore.init();

  router.init();
}

boot().catch(err => {
  console.error('[app] boot failed', err);
  const root = document.getElementById('app');
  if (root) {
    root.innerHTML = `<div style="padding:40px;color:#FF7C7C;font-family:monospace">Boot error: ${err.message}</div>`;
  }
});
