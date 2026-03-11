import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BlinkProvider, BlinkAuthProvider } from '@blinkdotnew/react'
import { Toaster } from 'sonner'
import App from './App'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary'

function getProjectId(): string {
  const envId = import.meta.env.VITE_BLINK_PROJECT_ID
  if (envId) return envId
  const hostname = window.location.hostname
  const match = hostname.match(/^([^.]+)\.sites\.blink\.new$/)
  if (match) return match[1]
  return 'demo-project'
}

const blinkExplicitlyEnabled = String(import.meta.env.VITE_ENABLE_BLINK_AUTH || '').toLowerCase() === 'true'
const blinkProjectId = import.meta.env.VITE_BLINK_PROJECT_ID || getProjectId()
const blinkPublishableKey = import.meta.env.VITE_BLINK_PUBLISHABLE_KEY
const blinkEnabled = Boolean(blinkExplicitlyEnabled && import.meta.env.VITE_BLINK_PROJECT_ID && blinkPublishableKey)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      {blinkEnabled ? (
        <BlinkProvider
          projectId={blinkProjectId}
          publishableKey={blinkPublishableKey}
        >
          <BlinkAuthProvider>
            <Toaster position="top-right" richColors />
            <App />
          </BlinkAuthProvider>
        </BlinkProvider>
      ) : (
        <>
          <Toaster position="top-right" richColors />
          <App />
        </>
      )}
    </ErrorBoundary>
  </StrictMode>
)
