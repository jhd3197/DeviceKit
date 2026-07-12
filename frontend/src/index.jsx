import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import { bootAccent, bootTheme } from './theme'
import { AuthProvider } from './auth/AuthContext'
import AuthGate from './auth/AuthGate'

// Demo/screenshot build (`vite --mode mock`): install the fetch/EventSource mocks
// so the whole UI renders on a fictional fleet with no backend, before anything
// makes a request. See src/mock/ and scripts/capture-screenshots.mjs.
if (import.meta.env.MODE === 'mock') {
  await import('./mock')
}

// Paint with the saved accent + theme mode before React mounts (avoids an emerald flash and
// a dark→light flash on reload). Both read localStorage; /settings reconciles them later.
bootAccent()
bootTheme()

// AuthProvider + AuthGate wrap the app (plan 20): solo mode passes straight through; a
// login-required instance shows the sign-in screen before any view mounts.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AuthGate>
          <App />
        </AuthGate>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)
