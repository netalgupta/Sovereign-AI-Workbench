import { BookOpen } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function SourcesStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={BookOpen}
        title="Knowledge Base"
        description="Full sources manager — NotebookLM-style document ingestion and knowledge base management. Arriving Day 8 (Netal)."
      />
    </div>
  )
}
