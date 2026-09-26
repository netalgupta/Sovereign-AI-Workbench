import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
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

import { GlobalSourcePreviewModal } from './components/workbench/GlobalSourcePreviewModal'
import { LandingPage } from './pages/LandingPage'

/**
 * PageTransition helper for smooth, professional 160ms ease-out page route animations.
 */
function PageTransition({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -5 }}
      transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
      className="w-full h-full flex flex-col min-h-0 flex-1"
    >
      {children}
    </motion.div>
  )
}

/**
 * App — top-level router.
 * All routes render inside AppShell (persistent nav chrome).
 */
export default function App() {
  const location = useLocation()

  return (
    <AppShell>
      <AnimatePresence mode="wait" initial={false}>
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<PageTransition><LandingPage /></PageTransition>} />
          <Route path="/chat" element={<PageTransition><WorkbenchPage /></PageTransition>} />
          <Route path="/workbench" element={<PageTransition><WorkbenchPage /></PageTransition>} />
          <Route path="/plan/:sessionId" element={<PageTransition><PlanStubPage /></PageTransition>} />
          <Route path="/sources" element={<PageTransition><SourcesPage /></PageTransition>} />
          <Route path="/graph" element={<PageTransition><GraphExplorerPage /></PageTransition>} />
          <Route path="/instrumentation" element={<PageTransition><InstrumentationPage /></PageTransition>} />
          <Route path="/outputs" element={<PageTransition><OutputCards /></PageTransition>} />
          <Route path="/audit" element={<PageTransition><AuditLog /></PageTransition>} />
          <Route path="/settings" element={<PageTransition><SettingsPage /></PageTransition>} />
          <Route path="/monitor" element={<PageTransition><NetworkMonitor mode="full" /></PageTransition>} />
        </Routes>
      </AnimatePresence>
      {/* Source preview, mounted once so a citation, a source row or an
          attachment chip can open a document from anywhere in the app. */}
      <GlobalSourcePreviewModal />
    </AppShell>
  )
}
