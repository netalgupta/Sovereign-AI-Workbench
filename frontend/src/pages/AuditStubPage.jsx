import { Shield } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function AuditStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={Shield}
        title="Audit Log"
        description="Timestamped, exportable audit trail of every tool call, document access, and output — arriving Day 8 (Kanishka)."
      />
    </div>
  )
}
