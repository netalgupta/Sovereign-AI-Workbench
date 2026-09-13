import { Routes, Route } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { WorkbenchPage } from './pages/WorkbenchPage'
import { PlanStubPage } from './pages/PlanStubPage'
import { SettingsPage } from './pages/SettingsPage'
import { SourcesPage } from './pages/SourcesPage'
import { GraphExplorerPage } from './pages/GraphExplorerPage'
import { InstrumentationPage } from './pages/InstrumentationPage'

// Plug-and-play teammate integrations (FRONTEND.md §5 / /src/integrations/)
import { OutputCards } from './integrations/output-cards'
import { AuditLog } from './integrations/audit-log'
import { NetworkMonitor } from './integrations/network-monitor'

/**
 * App — top-level router.
 * All routes render inside AppShell (persistent nav chrome).
 *
 * TWO ROUTES WERE POINTING AT NOTHING, AND NOBODY COULD SEE IT.
 *
 *   /graph rendered integrations/graph-explorer/Placeholder.jsx — 275
 *   lines drawing a hardcoded CANONICAL_GRAPH — while the real
 *   GraphExplorerPage (multi-hop traversal, hop-by-hop reveal,
 *   NetworkX centrality, the Mangalore-Hassan signature demo) sat
 *   unrouted. The placeholder looked like a working graph explorer, so
 *   the failure was invisible: the page rendered, it just rendered
 *   invented data.
 *
 *   /instrumentation did not exist at all, so the Agent Stream view,
 *   the retrieval trace and the ingestion feed could not be opened by
 *   any means.
 *
 * Both were finished work wired to nothing. The integrations/ adapter
 * layer is the mechanism that hid it — a barrel that defaults to a
 * placeholder and requires a one-line swap nobody was told to make.
 * Where a real page exists it is imported directly here, so "is this
 * the real one" is answerable by reading this file.
 *
 * Route inventory (FRONTEND.md §2):
 *   /                  → WorkbenchPage       (three-pane chat + plan + sources)
 *   /plan/:sessionId   → PlanStubPage        (full-screen plan graph)
 *   /sources           → SourcesPage         (knowledge base + chunk inspector)
 *   /graph             → GraphExplorerPage   (Netal — real, not the placeholder)
 *   /instrumentation   → InstrumentationPage (Netal — agent stream, retrieval trace, ingestion)
 *   /outputs           → OutputCards         (file library — Kanishka)
 *   /audit             → AuditLog            (audit log — Kanishka)
 *   /settings          → SettingsPage        (model registry, storage)
 *   /monitor           → NetworkMonitor      (network monitor full view)
 */
export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/plan/:sessionId" element={<PlanStubPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/graph" element={<GraphExplorerPage />} />
        <Route path="/instrumentation" element={<InstrumentationPage />} />
        <Route path="/outputs" element={<OutputCards />} />
        <Route path="/audit" element={<AuditLog />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/monitor" element={<NetworkMonitor mode="full" />} />
      </Routes>
    </AppShell>
  )
}
