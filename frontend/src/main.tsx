import React from 'react'
import ReactDOM from 'react-dom/client'
import './styles/tokens.css'
import './styles/global.css'
import './styles/motion.css'
// polish.css MUST stay last — overrides cinematic patterns in feature CSS.
import './styles/polish.css'
import { App } from './App'
import { initThemeStore } from './stores/themeStore'
import { initClientErrorReporter } from './lib/clientErrorReporter'

initClientErrorReporter()
initThemeStore()

const _root = ReactDOM.createRoot(document.getElementById('root')!)

// WP0.4 — dev-only component gallery. `?preview=<name>` mounts the harness
// instead of the app so components can be reviewed in every state. Guarded by
// import.meta.env.DEV + a dynamic import, so it never lands in the prod bundle.
const _preview = import.meta.env.DEV
  ? new URLSearchParams(window.location.search).get('preview')
  : null

if (_preview) {
  import('./dev/PreviewHarness').then(({ PreviewHarness }) => {
    _root.render(
      <React.StrictMode>
        <PreviewHarness name={_preview} />
      </React.StrictMode>,
    )
  })
} else {
  _root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
}
