import { StrictMode, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import GraphPage from './GraphPage.jsx'

function subscribeHash(callback) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

function Router() {
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash)
  return hash === '#graph' ? <GraphPage /> : <App />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Router />
  </StrictMode>,
)
