import { AlertTriangle, ArrowRight, ShieldAlert, Check } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useChatStore } from '../../store/chatStore'

/**
 * ApprovalModal — Safety-critical human approval gate modal per FRONTEND.md §3.12.
 *
 * Requirements:
 * - Centered, backdrop-blurred (blur-md), impossible to miss.
 * - CANNOT be dismissed by clicking outside — only explicit Confirm or Cancel closes it.
 * - NO top-right "X" close button — safety-critical actions require deliberate decision.
 * - Plain-language description + parameter diff card (100% -> 115%).
 * - Inline amber/red warning callout with engineering risk statement.
 * - Cancel (ghost/outline) and Confirm (solid accent, font-bold) buttons.
 * - Fully theme-tokenized for Light and Dark modes.
 */
export function ApprovalModal({
  isOpen: propIsOpen,
  action: propAction,
  onClose: propOnClose,
  onConfirm: propOnConfirm,
}) {
  const storeIsOpen = useChatStore((s) => s.isApprovalModalOpen)
  const storeAction = useChatStore((s) => s.pendingApprovalAction)
  const storeApprovalError = useChatStore((s) => s.approvalError)
  const isResolving = useChatStore((s) => s.isResolvingApproval)
  const resolveApproval = useChatStore((s) => s.resolveApproval)

  const isOpen = propIsOpen !== undefined ? propIsOpen : storeIsOpen
  const action = propAction || storeAction

  const handleCancel = async () => {
    if (propOnClose) {
      propOnClose()
    } else {
      await resolveApproval(false)
    }
  }

  const handleConfirm = async () => {
    if (propOnConfirm) {
      await propOnConfirm()
    } else {
      await resolveApproval(true)
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="approval-gate-modal-backdrop"
          id="approval-gate-modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 select-none"
          style={{
            background: 'rgba(5, 5, 8, 0.72)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="approval-modal-title"
        >
          {!action ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 6 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 6 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-[490px] rounded-2xl p-6 flex flex-col items-center gap-4 shadow-2xl"
              style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-card-border)' }}
            >
              <ShieldAlert size={28} style={{ color: 'var(--color-accent)' }} />
              <p className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
                No action data available
              </p>
              <p className="text-xs text-center" style={{ color: 'var(--color-text-muted)' }}>
                The approval gate was triggered but no action payload arrived from the backend.
                Close this modal and retry the operation.
              </p>
              <button
                type="button"
                onClick={handleCancel}
                className="px-4 py-2 rounded-lg text-xs font-semibold border cursor-pointer hover:bg-[var(--color-surface-hover)]"
                style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
              >
                Close
              </button>
            </motion.div>
          ) : (
            /* Modal Card — Deliberately weightier than regular cards */
            <motion.div
              key="approval-gate-modal-card"
              id="approval-gate-modal-card"
              onClick={(e) => e.stopPropagation()}
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-[490px] rounded-2xl p-6 relative flex flex-col shadow-2xl"
              style={{
                background: 'var(--color-card-bg)',
                border: '1px solid var(--color-card-border)',
                boxShadow: 'var(--shadow-lg)',
              }}
            >
        {/* Top Badges: Safety Level + System Tag */}
        <div className="flex items-center justify-between gap-2 mb-3.5">
          <div
            className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase"
            style={{
              background: 'var(--color-error-tint)',
              border: '1px solid var(--color-accent-border)',
              color: 'var(--color-accent)',
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ background: 'var(--color-accent)' }}
            />
            Safety-Critical Gate · FR-15 / §3.12
          </div>

          <span
            className="font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded"
            style={{
              background: 'var(--color-overlay)',
              color: 'var(--color-text-muted)',
            }}
          >
            {/* The pending action's own type. This defaulted to
                DCS_SETPOINT_WRITE, labelling a document write as a
                setpoint change on the screen where consent is recorded. */}
            {action.action_type || 'operator action'}
          </span>
        </div>

        {/* Header Icon + Title */}
        <div className="flex items-start gap-3 text-left">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{
              background: 'var(--color-accent-tint)',
              color: 'var(--color-accent)',
            }}
          >
            <ShieldAlert size={22} strokeWidth={2.2} />
          </div>

          <div className="flex-1 min-w-0">
            <h2
              id="approval-modal-title"
              className="text-sm font-bold tracking-tight leading-snug"
              style={{ color: 'var(--color-text)' }}
            >
              {action.title || 'Confirm operator action'}
            </h2>
            {/* THE FALLBACKS IN THIS FILE WERE FABRICATIONS.
                `action.target || 'HCU-2 / FFC-201'` meant the backend
                could correctly send target: null and the modal would
                still display a specific controller tag. Observed live:
                a request to "Draft a DOCX report on the Hassan incident
                and save it" rendered as a DCS setpoint change on
                HCU-2 / FFC-201, 1,450 -> 1,667 m3/h, with a catalyst
                residence-time warning.
                An unresolved field must read as unresolved. A plausible
                default reads as measured, and this is the one screen
                where a human signs off -- consent recorded against
                invented figures is a signed audit entry for something
                nobody approved. */}
            {action.target ? (
              <div
                className="text-[11px] font-mono mt-0.5"
                style={{ color: 'var(--color-text-muted)' }}
              >
                Target: <span className="font-semibold" style={{ color: 'var(--color-text)' }}>{action.target}</span>
              </div>
            ) : (
              <div
                className="text-[11px] mt-0.5"
                style={{ color: 'var(--color-text-muted)' }}
              >
                Target not resolved by the system
              </div>
            )}
          </div>
        </div>

        {/* Exact Plain-Language Description */}
        <div className="mt-3.5 text-left">
          <p
            className="text-xs font-semibold leading-relaxed"
            style={{ color: 'var(--color-text)' }}
          >
            {action.description ||
              'This action requires your authorisation before it can run.'}
          </p>
          {action.detail && (
            <p
              className="text-[11px] leading-relaxed mt-1 font-mono"
              style={{ color: 'var(--color-text-muted)' }}
            >
              {/* The operator's own words, quoted. Not a paraphrase and
                  not a substitute: this is what they are authorising. */}
              Requested: &ldquo;{action.detail}&rdquo;
            </p>
          )}
        </div>

        {/* Before/after values, ONLY when the system actually resolved
            them. This card previously rendered
            "100% (1,450 m3/h) -> 115% (1,667 m3/h)  +15.0% Excursion"
            as hardcoded fallbacks, for every gated action regardless of
            what was asked -- including file writes and audit-log
            deletions. A diff with invented endpoints is worse than no
            diff: it is the most convincing part of the screen. */}
        {/* WHAT THIS WILL WRITE. The backend resolves every gated action to
            a concrete call and describes it line by line — the file, its
            slides or sections, the sources they rest on, and what was
            checked. The modal never rendered any of it, so the operator
            approved a one-line effect with the detail sitting unused in
            the payload. */}
        {Array.isArray(action.preview) && action.preview.length > 0 && (
          <div
            className="mt-3 rounded-lg border px-3 py-2 text-left"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1"
                 style={{ color: 'var(--color-text-muted)' }}>
              What this writes
            </div>
            <ul className="space-y-0.5 text-[11px]" style={{ color: 'var(--color-text)' }}>
              {action.preview.map((line, i) => (
                <li key={i} className="leading-snug">{line}</li>
              ))}
            </ul>
          </div>
        )}

        {/* What the repair loop tried on this deck, and what it kept: a
            change is only kept when the page scores higher after it. */}
        {Array.isArray(action.rounds) && action.rounds.length > 0 && (
          <div className="mt-2 text-[11px] text-left" style={{ color: 'var(--color-text-muted)' }}>
            {action.rounds.map((r) => (
              <div key={r.round}>
                Repair pass {r.round}: {Object.keys(r.tried || {}).length} slide(s) re-paginated,{' '}
                {(r.kept || []).length} kept, {(r.reverted || []).length} reverted
                {r.score_after != null && ` · deck ${r.score_before ?? '?'} → ${r.score_after}`}
              </div>
            ))}
          </div>
        )}

        {/* The pages the reviewer scored below the pass mark, or measured a
            defect on: the evidence behind the grade on the line above. */}
        {action.quality?.pages?.some((p) => (p.defects || []).length || (p.issues || []).length) && (
          <div
            className="mt-2 rounded-lg border px-3 py-2 text-left"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1"
                 style={{ color: 'var(--color-text-muted)' }}>
              Pages worth a look
            </div>
            <ul className="space-y-0.5 text-[11px]" style={{ color: 'var(--color-text)' }}>
              {action.quality.pages
                .filter((p) => (p.defects || []).length || (p.issues || []).length)
                .slice(0, 6)
                .map((p) => (
                  <li key={p.page} className="leading-snug">
                    <span className="font-semibold">p.{p.page}</span>
                    {p.score !== null && p.score !== undefined && <span> · {p.score}/10</span>}
                    {(p.defects || []).length > 0 && <span> · measured: {p.defects.join(', ')}</span>}
                    {(p.issues || []).length > 0 && <span> · {p.issues[0]}</span>}
                  </li>
                ))}
            </ul>
          </div>
        )}

        {action.current_value && action.proposed_value ? (
          <div
            className="mt-3.5 p-3 rounded-xl flex items-center justify-between gap-3 border"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border)',
            }}
          >
            <div className="flex-1 text-left">
              <div className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--color-text-faint)' }}>
                Current
              </div>
              <div className="font-mono text-xs font-bold mt-0.5" style={{ color: 'var(--color-text)' }}>
                {action.current_value}
              </div>
            </div>

            <div
              className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: 'var(--color-accent-tint)',
                color: 'var(--color-accent)',
              }}
            >
              <ArrowRight size={14} strokeWidth={2.4} />
            </div>

            <div className="flex-1 text-right">
              <div className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--color-text-faint)' }}>
                Proposed
              </div>
              <div className="font-mono text-xs font-bold mt-0.5" style={{ color: 'var(--color-accent)' }}>
                {action.proposed_value}
              </div>
            </div>
          </div>
        ) : (
          <div
            className="mt-3.5 p-3 rounded-xl text-left border text-[11px] leading-relaxed"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
          >
            The workbench has <span style={{ color: 'var(--color-text)' }}>not resolved</span> a
            specific device, file path or value for this instruction. There is
            nothing to show a before/after for. Confirm the specifics yourself
            before authorising.
          </div>
        )}

        {/* Inline Warning Callout Box with Risk Statement */}
        <div
          className="w-full mt-3.5 p-3 rounded-xl flex items-start gap-2.5 text-left border"
          style={{
            background: 'var(--color-error-tint)',
            borderColor: 'var(--color-accent-border)',
          }}
        >
          <AlertTriangle
            size={16}
            strokeWidth={2.2}
            className="flex-shrink-0 mt-0.5"
            style={{ color: 'var(--color-accent)' }}
          />
          <div className="flex-1 min-w-0">
            <p
              className="text-xs font-semibold leading-snug"
              style={{ color: 'var(--color-text)' }}
            >
              {/* No invented risk assessment. The previous fallback
                  asserted a catalyst residence-time hazard and a "34%
                  fractionation flooding probability" for every gated
                  action, including deleting an audit log. A fabricated
                  risk number on an approval screen is a safety claim
                  nobody computed. */}
              {action.warning ||
                'Review this action before authorising it. Once authorised it will be executed and recorded in the audit log against your approval.'}
            </p>
            {action.mitigation_required && (
              <p
                className="text-[11px] font-medium mt-1 leading-snug"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {action.mitigation_required}
              </p>
            )}
          </div>
        </div>

        {/* Authorization Failure Banner if backend rejection or network error */}
        {storeApprovalError && (
          <div
            id="approval-gate-error-banner"
            className="w-full mt-3 p-3 rounded-xl flex items-center gap-2.5 text-left border animate-shake"
            style={{
              background: 'rgba(239, 68, 68, 0.12)',
              borderColor: 'rgba(239, 68, 68, 0.35)',
              color: '#ef4444',
            }}
          >
            <ShieldAlert size={16} className="flex-shrink-0" />
            <span className="text-xs font-semibold leading-tight">
              {storeApprovalError}
            </span>
          </div>
        )}

        {/* Explicit Action Buttons ONLY — No click-outside or top-right X dismiss */}
        <div className="w-full mt-5 flex items-center gap-3">
          <button
            type="button"
            id="approval-gate-cancel-btn"
            disabled={isResolving}
            onClick={handleCancel}
            className="flex-1 py-2.5 rounded-xl text-xs font-semibold transition-fast cursor-pointer border hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border-strong)',
              color: 'var(--color-text)',
            }}
          >
            Cancel Action
          </button>
          <button
            type="button"
            id="approval-gate-confirm-btn"
            disabled={isResolving}
            onClick={handleConfirm}
            className="flex-1 py-2.5 rounded-xl text-xs font-bold text-white transition-fast shadow-sm cursor-pointer hover:brightness-110 flex items-center justify-center gap-1.5 disabled:opacity-60"
            style={{
              background: 'var(--color-accent)',
            }}
          >
            <Check size={14} strokeWidth={2.6} />
            <span>{isResolving ? 'Authorizing…' : 'Authorize & Dispatch'}</span>
          </button>
        </div>
            </motion.div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
