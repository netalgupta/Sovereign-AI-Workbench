import { Routes, Route } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { WorkbenchPage }   from './pages/WorkbenchPage'
import { PlanStubPage }    from './pages/PlanStubPage'
import { SourcesStubPage } from './pages/SourcesStubPage'
import { GraphStubPage }   from './pages/GraphStubPage'
import { OutputsStubPage } from './pages/OutputsStubPage'
import { AuditStubPage }   from './pages/AuditStubPage'
import { SettingsStubPage } from './pages/SettingsStubPage'
import { MonitorStubPage } from './pages/MonitorStubPage'

/**
 * App — top-level router.
 * All routes render inside AppShell (persistent nav chrome).
 *
 * Route inventory (FRONTEND.md §2):
 *   /                  → WorkbenchPage  (three-pane, fully built Day 1-2)
 *   /plan/:sessionId   → PlanStubPage   (full-screen plan graph — Day 5)
 *   /sources           → SourcesStubPage (knowledge base manager — Day 8 Netal)
 *   /graph             → GraphStubPage  (graph explorer — Day 8 Netal)
 *   /outputs           → OutputsStubPage (file library — Day 8 Kanishka)
 *   /audit             → AuditStubPage  (audit log — Day 8 Kanishka)
 *   /settings          → SettingsStubPage (model registry — Day 7)
 *   /monitor           → MonitorStubPage (network monitor — Day 6 Sahil)
 */
export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/"                element={<WorkbenchPage />} />
        <Route path="/plan/:sessionId" element={<PlanStubPage />} />
        <Route path="/sources"         element={<SourcesStubPage />} />
        <Route path="/graph"           element={<GraphStubPage />} />
        <Route path="/outputs"         element={<OutputsStubPage />} />
        <Route path="/audit"           element={<AuditStubPage />} />
        <Route path="/settings"        element={<SettingsStubPage />} />
        <Route path="/monitor"         element={<MonitorStubPage />} />
      </Routes>
    </AppShell>
  )
}
