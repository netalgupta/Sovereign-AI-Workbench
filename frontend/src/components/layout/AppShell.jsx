import { ToastContainer } from '../ui/Toast'

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
      <main className="flex-1 overflow-hidden flex flex-col relative">
        {children}
      </main>

      {/* Global Toast Container */}
      <ToastContainer />
    </div>
  )
}
