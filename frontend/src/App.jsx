import { Routes, Route } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { WorkbenchPage } from './pages/WorkbenchPage'
import { PlanStubPage } from './pages/PlanStubPage'
import { SettingsPage } from './pages/SettingsPage'
import { SourcesPage } from './pages/SourcesPage'

// Plug-and-play teammate integrations (FRONTEND.md §5 / /src/integrations/)
import { GraphExplorer } from './integrations/graph-explorer'
import { OutputCards } from './integrations/output-cards'
import { AuditLog } from './integrations/audit-log'
import { NetworkMonitor } from './integrations/network-monitor'

/**
 * App — top-level router.
 * All routes render inside AppShell (persistent nav chrome).
 *
 * Route inventory (FRONTEND.md §2):
 *   /                  → WorkbenchPage  (three-pane, fully built Day 1-2)
 *   /plan/:sessionId   → PlanStubPage   (full-screen plan graph — Day 5)
 *   /sources           → SourcesPanel   (knowledge base manager — Netal)
 *   /graph             → GraphExplorer  (graph explorer — Netal)
 *   /outputs           → OutputCards    (file library — Kanishka)
 *   /audit             → AuditLog       (audit log — Kanishka)
 *   /settings          → SettingsPage   (model registry, RBAC, encrypted storage — §3.11)
 *   /monitor           → NetworkMonitor (network monitor full view — Sahil)
 */
export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/plan/:sessionId" element={<PlanStubPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/graph" element={<GraphExplorer />} />
        <Route path="/outputs" element={<OutputCards />} />
        <Route path="/audit" element={<AuditLog />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/monitor" element={<NetworkMonitor mode="full" />} />
      </Routes>
    </AppShell>
  )
}

