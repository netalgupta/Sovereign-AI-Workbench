import { usePreviewStore } from '../../store/previewStore'
import { SourcePreviewPanel } from './SourcePreviewPanel'

/**
 * GlobalSourcePreviewModal — Mounts at AppShell level to render preview panel anywhere.
 */
export function GlobalSourcePreviewModal() {
  const file = usePreviewStore((s) => s.file)
  const isOpen = usePreviewStore((s) => s.isOpen)
  const closePreview = usePreviewStore((s) => s.closePreview)

  if (!isOpen || !file) return null

  return (
    <SourcePreviewPanel
      file={file}
      isOpen={isOpen}
      onClose={closePreview}
    />
  )
}

