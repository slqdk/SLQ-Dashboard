import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/sofia-sans'
import '@fontsource-variable/sofia-sans-extra-condensed'
import './styles.css'
import './themes.css'
import { App } from './App'
import { savedTheme, showTheme } from './core/theme'

showTheme(savedTheme())

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
