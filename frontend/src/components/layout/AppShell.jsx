import { ToastContainer } from '../ui/Toast'
import { GlobalSourcePreviewModal } from '../workbench/GlobalSourcePreviewModal'

/**
 * AppShell — Clean full-height chrome wrapper.
 * Top navbar has been completely removed per 2-pane architectural redesign;
 * theme toggle, search trigger, brand identity, and user profile now live
 * directly inside the unified left Sidebar.
 */
export function AppShell({ children }) {
  return (
    <div
      className="flex flex-col h-full w-full overflow-hidden"
      style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}
    >
      <div className="flex-1 overflow-hidden flex flex-row relative w-full h-full">
        <main className="flex-1 min-w-0 h-full overflow-hidden flex flex-col relative transition-all duration-300">
          {children}
        </main>

        {/* Global Source Preview Side Panel */}
        <GlobalSourcePreviewModal />
      </div>

      {/* Global Toast Container */}
      <ToastContainer />
    </div>
  )
}

