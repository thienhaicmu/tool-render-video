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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
