/* Screen-level error boundary.
   Wrap any screen mount function to catch unexpected crashes and render a
   calm, actionable recovery card instead of a blank/broken screen.
   Never exposes the stack trace in the UI — logs to console only.
*/

export function withErrorBoundary(mountFn) {
  return async function _boundaryMount(el, params) {
    try {
      await mountFn(el, params);
    } catch (err) {
      console.error('[screen] Uncaught render error:', err);
      _renderBoundary(el, () => _boundaryMount(el, params));
    }
  };
}

function _renderBoundary(el, onRetry) {
  el.innerHTML = `
    <div class="screen__header">
      <div class="screen__title">Something went wrong</div>
      <div class="screen__subtitle">This screen encountered an unexpected problem.</div>
    </div>
    <div class="screen__body">
      <div class="eb-card">
        <div class="row gap-3" style="align-items:flex-start">
          <span class="eb-card__icon" aria-hidden="true">⚠</span>
          <div class="col gap-2">
            <div class="text-body" style="font-weight:600">The screen couldn't load</div>
            <div class="text-caption text-faint">This is usually temporary. Try reloading the screen, or go back to Source to start over.</div>
          </div>
        </div>
        <div class="row gap-3 mt-4">
          <button class="btn btn-primary" id="eb-retry">Reload screen</button>
          <a class="btn btn-ghost" href="#/source">← Back to Source</a>
        </div>
      </div>
    </div>
  `;
  el.querySelector('#eb-retry')?.addEventListener('click', onRetry);
}
