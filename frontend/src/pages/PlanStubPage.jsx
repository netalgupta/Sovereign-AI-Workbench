import { GitBranch } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function PlanStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={GitBranch}
        title="Plan Graph"
        description="Full-screen plan graph view for a running session — arriving Day 5 (react-flow + dagre)."
      />
    </div>
  )
}
