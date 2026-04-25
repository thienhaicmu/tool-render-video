async function loadPartials() {
  const map = {
    partial_render_home:    '/static/partials/render-home.html',
    partial_download_view:  '/static/partials/download-view.html',
    partial_history_view:   '/static/partials/history-view.html',
    partial_settings_view:  '/static/partials/settings-view.html',
  };
  for (const id in map) {
    const res = await fetch(map[id]);
    const html = await res.text();
    document.getElementById(id).innerHTML = html;
  }
}
