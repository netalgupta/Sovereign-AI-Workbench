import { useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  PanelLeftOpen,
  Plus,
} from 'lucide-react'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { usePreviewStore } from '../../store/previewStore'
import { SourcePreviewPanel } from '../workbench/SourcePreviewPanel'
import { springs } from '../../lib/motion'

/**
 * WorkspaceCanvas — The spatial canvas orchestrator.
 *
 * Hosts docked fluid panes, floating movable panels, and manages
 * focus mode transitions with clean, distraction-free spatial continuity.
 */
export function WorkspaceCanvas({
  sourcesContent,
  chatContent,
  graphContent,
  evidenceContent,
  monitorContent,
}) {
  const {
    panels,
    focusedPanelId,
    openPanel,
    exitFocus,
    updatePanelSize,
  } = useWorkspaceStore()

  const previewFile = usePreviewStore((s) => s.file)
  const isPreviewOpen = usePreviewStore((s) => s.isOpen)
  const closePreview = usePreviewStore((s) => s.closePreview)

  // Handle ESC key to exit focus mode
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && focusedPanelId) {
        exitFocus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [focusedPanelId, exitFocus])

  const sourcesPanel = panels.sources
  const chatPanel = panels.chat

  return (
    <div
      className="flex-1 flex flex-col h-full w-full overflow-hidden relative"
      style={{ background: 'var(--color-bg)' }}
    >

      {/* ── Main Canvas Stage ────────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0 w-full relative overflow-hidden">
        {/* 1. Left Dock (Sources Panel — Full Tree or Minimalist Collapsed Rail) */}
        {sourcesPanel?.isOpen ? (
          <motion.div
            layout
            initial={false}
            animate={{
              width: sourcesPanel.isCollapsed ? 44 : sourcesPanel.width || 320,
              opacity: focusedPanelId && focusedPanelId !== 'sources' ? 0.25 : 1,
            }}
            transition={springs.spatial}
            className="flex-shrink-0 flex flex-col h-full relative"
          >
            {/* Resize handle on right edge (only when expanded) */}
            {!sourcesPanel.isCollapsed && !focusedPanelId && (
              <div
                onMouseDown={() => {
                  const onMouseMove = (e) => {
                    const newW = Math.max(240, Math.min(600, e.clientX))
                    updatePanelSize('sources', { width: newW })
                  }
                  const onMouseUp = () => {
                    window.removeEventListener('mousemove', onMouseMove)
                    window.removeEventListener('mouseup', onMouseUp)
                  }
                  window.addEventListener('mousemove', onMouseMove)
                  window.addEventListener('mouseup', onMouseUp)
                }}
                className="absolute top-0 right-[-4px] bottom-0 w-2 cursor-col-resize z-20 group flex items-center justify-center hover:bg-[var(--color-accent-border)] transition-colors opacity-0 hover:opacity-100"
                title="Drag to resize sources panel"
              >
                <div className="w-[2px] h-8 rounded-full bg-[var(--color-border-strong)]" />
              </div>
            )}

            {sourcesContent}
          </motion.div>
        ) : (
          /* Left Edge Restore Tab when Sources is closed */
          <motion.button
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={springs.spatial}
            onClick={() => openPanel('sources')}
            className="h-full w-9 flex flex-col items-center justify-between py-3 rounded-xl border border-dashed hover:border-solid select-none cursor-pointer group transition-all shrink-0"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border-strong)',
            }}
            title="Sources Panel is closed — Click to reopen"
          >
            <div className="flex flex-col items-center gap-1.5">
              <div className="w-6 h-6 rounded-md flex items-center justify-center bg-[var(--color-overlay)] text-[var(--color-accent)] group-hover:bg-[var(--color-accent)] group-hover:text-white transition-colors">
                <PanelLeftOpen size={13} strokeWidth={2.2} />
              </div>
              <Plus size={11} className="text-[var(--color-accent)]" />
            </div>

            <div className="flex-1 flex items-center justify-center my-2">
              <span
                className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[var(--color-accent)] group-hover:text-[var(--color-text)] transition-colors whitespace-nowrap"
                style={{
                  writingMode: 'vertical-rl',
                  transform: 'rotate(180deg)',
                }}
              >
                + SOURCES
              </span>
            </div>

            <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-text-faint)] group-hover:bg-[var(--color-accent)] transition-colors" />
          </motion.button>
        )}

        {/* 2. Primary Center / Main Stage (Chat & Intelligence Stream) */}
        <motion.div
          layout
          initial={false}
          animate={{
            opacity: focusedPanelId && focusedPanelId !== 'chat' ? 0.25 : 1,
          }}
          transition={springs.spatial}
          className="flex-1 flex flex-col h-full min-w-0 relative"
        >
          {chatContent}
        </motion.div>

        {/* 3. Right Dock: Document Preview Panel — Side by Side with Chat! */}
        <AnimatePresence>
          {previewFile && isPreviewOpen && (
            <motion.div
              key={previewFile.id || previewFile.name || previewFile.relativePath || 'doc-preview'}
              layout
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 50 }}
              transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              className="h-full flex-shrink-0 flex flex-col relative z-20"
            >
              <SourcePreviewPanel
                file={previewFile}
                isOpen={isPreviewOpen}
                onClose={closePreview}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* 4. Floating Spatial Overlays (Graph, Evidence, Monitor, etc.) */}
        {graphContent}
        {evidenceContent}
        {monitorContent}
      </div>

      {/* ── Focus Mode Exit Pill (Floats when in focus mode) ────────── */}
      {focusedPanelId && (
        <div className="fixed bottom-4 right-4 z-[10000] flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xl">
          <span>Focus Mode: {panels[focusedPanelId]?.title}</span>
          <button
            type="button"
            onClick={exitFocus}
            className="hover:underline font-semibold text-[var(--color-accent)] cursor-pointer"
          >
            Exit (Esc)
          </button>
        </div>
      )}
    </div>
  )
}
