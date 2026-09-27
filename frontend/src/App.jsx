import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { AppShell } from './components/layout/AppShell'
import { GlobalSourcePreviewModal } from './components/workbench/GlobalSourcePreviewModal'
import { PreviewUrlSync } from './components/workbench/PreviewUrlSync'
import { useChatStore } from './store/chatStore'
import { chatPath } from './lib/nav'

// Lazy-loaded routes for optimal initial bundle and performance
const HomePage = lazy(() => import('./pages/HomePage').then((m) => ({ default: m.HomePage })))
const WorkbenchPage = lazy(() => import('./pages/WorkbenchPage').then((m) => ({ default: m.WorkbenchPage })))
const PlanStubPage = lazy(() => import('./pages/PlanStubPage').then((m) => ({ default: m.PlanStubPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const SourcesPage = lazy(() => import('./pages/SourcesPage').then((m) => ({ default: m.SourcesPage })))
const GraphExplorerPage = lazy(() => import('./pages/GraphExplorerPage').then((m) => ({ default: m.GraphExplorerPage })))
const VisionStudioPage = lazy(() => import('./pages/VisionStudioPage').then((m) => ({ default: m.VisionStudioPage })))
const RetrievalObservatoryPage = lazy(() => import('./pages/RetrievalObservatoryPage').then((m) => ({ default: m.RetrievalObservatoryPage })))
const InstrumentationPage = lazy(() => import('./pages/InstrumentationPage').then((m) => ({ default: m.InstrumentationPage })))

// Plug-and-play teammate integrations
const OutputCards = lazy(() => import('./integrations/output-cards').then((m) => ({ default: m.OutputCards })))
const AuditLog = lazy(() => import('./integrations/audit-log').then((m) => ({ default: m.AuditLog })))
const NetworkMonitor = lazy(() => import('./integrations/network-monitor').then((m) => ({ default: m.NetworkMonitor })))

/**
 * Route loading fallback skeleton with subtle brand styling
 */
function RouteLoadingFallback() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center h-full w-full select-none" style={{ background: 'var(--color-bg)' }}>
      <div className="flex flex-col items-center gap-3">
        <img src="/assets/logo-mark-transparent.png" alt="" className="h-10 w-auto animate-pulse" draggable={false} />
        <span className="text-[11px] font-mono text-[var(--color-text-muted)] tracking-wider">
          INITIALIZING WORKBENCH SURFACE...
        </span>
      </div>
    </div>
  )
}

/**
 * PageTransition helper for smooth 180ms ease-out page route animations.
 */
function PageTransition({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      className="w-full h-full flex flex-col min-h-0 flex-1 overflow-hidden"
    >
      <Suspense fallback={<RouteLoadingFallback />}>
        {children}
      </Suspense>
    </motion.div>
  )
}

/**
 * App — top-level router.
 * All routes render inside AppShell (persistent navigation & status chrome).
 */
// /chat and the old /workbench name no chat: open the current one, keeping
// any query (?tab=, ?view=) and REPLACING the entry, so back does not bounce.
function ToCurrentChat() {
  const location = useLocation()
  const sessionId = useChatStore((s) => s.sessionId)
  return <Navigate to={chatPath(sessionId) + (location.search || '')} replace />
}

export default function App() {
  const location = useLocation()
  // Keyed by SECTION, not by full path: moving between chats is not a new
  // page, and remounting the Workbench refetched the whole corpus.
  const section = location.pathname.split('/')[1] || 'home'

  return (
    <AppShell>
      <AnimatePresence mode="wait" initial={false}>
        <Routes location={location} key={section}>
          {/* Home / Command Center */}
          <Route path="/" element={<PageTransition><HomePage /></PageTransition>} />

          {/* Spatial Chat & Workbench */}
          <Route path="/chat/:sessionId" element={<PageTransition><WorkbenchPage /></PageTransition>} />
          <Route path="/chat" element={<ToCurrentChat />} />
          <Route path="/workbench" element={<ToCurrentChat />} />

          {/* Execution Plan DAG Canvas */}
          <Route path="/plan" element={<PageTransition><PlanStubPage /></PageTransition>} />
          <Route path="/plan/:sessionId" element={<PageTransition><PlanStubPage /></PageTransition>} />

          {/* Grounded Sources & Corpus Hub */}
          <Route path="/sources" element={<PageTransition><SourcesPage /></PageTransition>} />

          {/* Knowledge Graph Explorer */}
          <Route path="/graph" element={<PageTransition><GraphExplorerPage /></PageTransition>} />

          {/* Images & Vision Studio */}
          <Route path="/vision" element={<PageTransition><VisionStudioPage /></PageTransition>} />

          {/* Retrieval Observatory */}
          <Route path="/retrieval" element={<PageTransition><RetrievalObservatoryPage /></PageTransition>} />

          {/* Pipeline Instrumentation */}
          <Route path="/instrumentation" element={<PageTransition><InstrumentationPage /></PageTransition>} />

          {/* Output Documents & Deliverables */}
          <Route path="/outputs" element={<PageTransition><OutputCards /></PageTransition>} />

          {/* Operational Audit Log */}
          <Route path="/audit" element={<PageTransition><AuditLog /></PageTransition>} />

          {/* Air-Gap Network Monitor */}
          <Route path="/monitor" element={<PageTransition><NetworkMonitor mode="full" /></PageTransition>} />

          {/* System & Model Registry */}
          <Route path="/settings" element={<PageTransition><SettingsPage /></PageTransition>} />
        </Routes>
      </AnimatePresence>

      {/* Global Source Preview Reader, and its place in the URL */}
      <GlobalSourcePreviewModal />
      <PreviewUrlSync />
    </AppShell>
  )
}
