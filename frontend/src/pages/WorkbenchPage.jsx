import { useState } from 'react'
import { Sidebar } from '../components/workbench/Sidebar'
import { ChatPane } from '../components/workbench/ChatPane'
import { ApprovalModal } from '../components/workbench/ApprovalModal'

/**
 * WorkbenchPage — Clean two-pane layout:
 * Left: Unified Collapsible Sidebar (Header, Sources/Chats accordion, User footer)
 * Center: Full-height Chat Pane (Inline live-thinking trace + persistent bottom System Monitor)
 */
export function WorkbenchPage() {
  const [modalOpen, setModalOpen] = useState(false)

  return (
    <div className="flex h-full w-full overflow-hidden relative">
      <Sidebar />
      <ChatPane />

      {/* ── Human Approval Gate Modal (Ready for Day 6 trigger) ─────── */}
      <ApprovalModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onConfirm={() => setModalOpen(false)}
      />
    </div>
  )
}
