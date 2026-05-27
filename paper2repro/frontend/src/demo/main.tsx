import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import '../index.css'
import AppShell from '../pages/AppShell'
import { getOfflineInitialTaskId, getOfflineDemoPayload } from './offlineDemo'

const payload = getOfflineDemoPayload()
const taskId = getOfflineInitialTaskId()
const initialEntry = taskId ? `/app?task=${encodeURIComponent(taskId)}` : '/app'

document.documentElement.dataset.paper2codeDemoMode = payload?.mode ?? 'static'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MemoryRouter initialEntries={[initialEntry]}>
      <AppShell />
    </MemoryRouter>
  </StrictMode>,
)
