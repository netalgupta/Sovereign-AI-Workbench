import { FileText } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function OutputsStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={FileText}
        title="Generated Outputs"
        description="Generated file library — DOCX approval notes, XLSX reports, PPTX presentations. Arriving Day 8 (Kanishka)."
      />
    </div>
  )
}
