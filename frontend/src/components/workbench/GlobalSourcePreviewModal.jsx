import { useLocation } from 'react-router-dom'
import { usePreviewStore } from '../../store/previewStore'
import { SourcePreviewPanel } from './SourcePreviewPanel'

/**
 * GlobalSourcePreviewModal — Fallback slide-over drawer for non-workbench pages (e.g. /audit, /retrieval).
 * On /workbench and /chat, the preview is embedded seamlessly side-by-side inside WorkspaceCanvas.
 */
export function GlobalSourcePreviewModal() {
  const file = usePreviewStore((s) => s.file)
  const isOpen = usePreviewStore((s) => s.isOpen)
  const closePreview = usePreviewStore((s) => s.closePreview)
  const location = useLocation()

  // On Workbench / Chat pages, WorkspaceCanvas renders the preview side-by-side beside the chat.
  if (!isOpen || !file) return null
  if (location.pathname.startsWith('/chat') || location.pathname === '/workbench' || location.pathname === '/') {
    return null
  }

  return (
    <div className="fixed inset-y-0 right-0 z-[10050] shadow-2xl flex">
      <SourcePreviewPanel
        file={file}
        isOpen={isOpen}
        onClose={closePreview}
      />
    </div>
  )
}

