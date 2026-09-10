import { useState } from 'react'
import { SourcesRail } from '../components/workbench/SourcesRail'
import { ChatPane } from '../components/workbench/ChatPane'
import { PlanRail } from '../components/workbench/PlanRail'
import { ApprovalModal } from '../components/workbench/ApprovalModal'

/**
 * WorkbenchPage — the "/" route.
 * Three-pane workbench layout with interactive Approval Modal.
 */
export function WorkbenchPage() {
  const [modalOpen, setModalOpen] = useState(false)

  return (
    <div
      className="flex h-full overflow-hidden relative"
      style={{ minWidth: 1200 }}
    >
      <SourcesRail />
      <ChatPane />
      <PlanRail />

      {/* ── Human Approval Gate Modal (Ready for Day 6 trigger) ─────── */}
      <ApprovalModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onConfirm={() => setModalOpen(false)}
      />
    </div>
  )
}
