import { AlertTriangle, X } from 'lucide-react'

/**
 * ApprovalModal — Human approval gate modal matching the reference design.
 *
 * Positioned centered over the workbench, elevated with a deep soft shadow,
 * subtle backdrop blur, specific setpoint parameter values, and clear button hierarchy.
 */
export function ApprovalModal({ isOpen, onClose, onConfirm }) {
  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 top-14 z-40 flex items-center justify-center p-4 animate-fade-in"
      style={{
        background: 'rgba(38, 35, 32, 0.10)',
        backdropFilter: 'blur(1.5px)',
        WebkitBackdropFilter: 'blur(1.5px)',
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="approval-modal-title"
    >
      {/* Modal Card */}
      <div
        className="w-full max-w-[430px] rounded-2xl p-6 relative flex flex-col items-center text-center animate-fade-in"
        style={{
          background: '#FFFFFF',
          border: '1px solid #ECE4DB',
          boxShadow: '0 24px 48px -12px rgba(42, 39, 36, 0.28), 0 10px 24px -4px rgba(42, 39, 36, 0.14)',
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-7 h-7 rounded-lg flex items-center justify-center transition-fast hover:bg-[#F3EDE3]"
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
            background: '#FDF0EE',
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
          className="w-full mt-4 p-3 rounded-xl flex items-center gap-2.5 text-left"
          style={{
            background: '#FDF2F0',
            border: '1px solid #F6D8D2',
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
            style={{ color: '#9E3E28' }}
          >
            This may impact unit stability and safety systems. Please confirm before proceeding.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="w-full mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-xs font-semibold transition-fast cursor-pointer"
            style={{
              background: 'transparent',
              border: '1px solid var(--color-border-strong)',
              color: 'var(--color-text)',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-surface)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
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
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-accent-hover)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-accent)' }}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
