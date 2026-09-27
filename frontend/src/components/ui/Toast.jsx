import { Check, Info, AlertTriangle, X } from 'lucide-react'
import { useToastStore } from '../../store/toastStore'

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const removeToast = useToastStore((s) => s.removeToast)

  if (!toasts.length) return null

  return (
    <div
      className="fixed bottom-5 right-5 z-[10200] flex flex-col gap-2 pointer-events-none max-w-sm w-full"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto flex items-center justify-between gap-3 px-4 py-3 rounded-xl shadow-lg border animate-fade-in text-xs font-medium"
          style={{
            background: 'var(--color-surface)',
            color: 'var(--color-text)',
            borderColor: 'var(--color-border-strong)',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          <div className="flex items-center gap-2.5">
            {t.type === 'success' ? (
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--color-success)', color: '#FFFFFF' }}
              >
                <Check size={12} strokeWidth={2.5} />
              </div>
            ) : t.type === 'warning' ? (
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--color-warning)', color: '#FFFFFF' }}
              >
                <AlertTriangle size={12} strokeWidth={2.5} />
              </div>
            ) : (
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--color-accent)', color: '#FFFFFF' }}
              >
                <Info size={12} strokeWidth={2.5} />
              </div>
            )}
            <span className="leading-snug">{t.message}</span>
          </div>

          <button
            onClick={() => removeToast(t.id)}
            className="p-1 rounded-md opacity-60 hover:opacity-100 transition-fast"
            style={{ color: 'var(--color-text-muted)' }}
            aria-label="Dismiss toast"
          >
            <X size={13} strokeWidth={2} />
          </button>
        </div>
      ))}
    </div>
  )
}
