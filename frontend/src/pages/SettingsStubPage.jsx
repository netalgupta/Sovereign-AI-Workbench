import { Settings } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'

export function SettingsStubPage() {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <EmptyState
        icon={Settings}
        title="Settings"
        description="Model registry viewer, live model-add form (FR-4 demo moment), RBAC tiers, drive/encryption status — arriving Day 7."
      />
    </div>
  )
}
