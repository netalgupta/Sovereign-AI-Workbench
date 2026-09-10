import { AlertTriangle, X } from 'lucide-react'

/**
 * ApprovalModal — Human approval gate modal matching the reference design.
 * Fully theme-tokenized for Light and Dark modes.
 */
export function ApprovalModal({ isOpen, onClose, onConfirm }) {
  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 top-14 z-50 flex items-center justify-center p-4 animate-fade-in"
      style={{
        background: 'rgba(10, 8, 6, 0.45)',
        backdropFilter: 'blur(3px)',
        WebkitBackdropFilter: 'blur(3px)',
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="approval-modal-title"
    >
      {/* Modal Card */}
      <div
        className="w-full max-w-[430px] rounded-2xl p-6 relative flex flex-col items-center text-center animate-fade-in shadow-2xl"
        style={{
          background: 'var(--color-card-bg)',
          border: '1px solid var(--color-card-border)',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-7 h-7 rounded-lg flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
          style={{ color: 'var(--color-text-muted)' }}
          title="Close dialog"
          aria-label="Close dialog"
        >
          <X size={15} strokeWidth={2} />
        </button>

        {/* Warning Icon in soft circular tint */}
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center mb-3.5"
          style={{
            background: 'var(--color-accent-tint)',
            color: 'var(--color-accent)',
          }}
        >
          <AlertTriangle size={22} strokeWidth={2.2} />
        </div>

        {/* Heading */}
        <h2
          id="approval-modal-title"
          className="text-base font-bold tracking-tight"
          style={{ color: 'var(--color-text)' }}
        >
          Confirm Critical Action
        </h2>

        {/* Description with specific values */}
        <p
          className="text-xs leading-relaxed mt-1.5 px-2"
          style={{ color: 'var(--color-text-muted)' }}
        >
          This action will modify the operating setpoint for HCU feed rate from 100% to 115%.
        </p>

        {/* Inline Warning Callout Box */}
        <div
          className="w-full mt-4 p-3 rounded-xl flex items-center gap-2.5 text-left border"
          style={{
            background: 'var(--color-error-tint)',
            borderColor: 'var(--color-accent-border)',
          }}
        >
          <AlertTriangle
            size={16}
            strokeWidth={2}
            className="flex-shrink-0"
            style={{ color: 'var(--color-accent)' }}
          />
          <p
            className="text-xs font-medium leading-snug"
            style={{ color: 'var(--color-text)' }}
          >
            This may impact unit stability and safety systems. Please confirm before proceeding.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="w-full mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-xs font-semibold transition-fast cursor-pointer border"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border-strong)',
              color: 'var(--color-text)',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="flex-1 py-2.5 rounded-xl text-xs font-semibold text-white transition-fast shadow-sm cursor-pointer"
            style={{
              background: 'var(--color-accent)',
            }}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
