import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import AppShell from './pages/AppShell'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<AppShell />} />
    </Routes>
  )
}
