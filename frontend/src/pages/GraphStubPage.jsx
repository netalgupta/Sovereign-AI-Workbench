import { Network } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function GraphStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={Network}
        title="Knowledge Graph Explorer"
        description="Interactive Neo4j knowledge graph — entities, pipeline segments, equipment, SOPs. Arriving Day 8 (Netal)."
      />
    </div>
  )
}
