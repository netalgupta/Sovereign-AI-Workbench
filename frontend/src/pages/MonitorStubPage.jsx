import { Activity } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function MonitorStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={Activity}
        title="Network Monitor"
        description="Live network connection table — proves zero external egress (FR-15, NFR-1). Wired to Aditya's psutil WebSocket feed Day 6 (Sahil)."
      />
    </div>
  )
}
