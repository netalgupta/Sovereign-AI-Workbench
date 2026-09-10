/**
 * EmptyState — consistent empty state for every list/panel that can be empty.
 * FRONTEND.md §6 rule 3: "Every list that can be empty has a designed empty
 * state (not just blank space)."
 *
 * @param {React.ReactNode} icon  - A Lucide icon component
 * @param {string}          title
 * @param {string}          [description]
 * @param {React.ReactNode} [action] - Optional CTA element
 */
export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-10 px-6 text-center"
      style={{ color: 'var(--color-text-muted)' }}
    >
      {Icon && (
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{
            background: 'var(--color-surface-hover)',
            color: 'var(--color-text-faint)',
          }}
        >
          <Icon size={20} strokeWidth={1.5} />
        </div>
      )}
      <div className="flex flex-col gap-1">
        <p
          className="text-sm font-medium"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {title}
        </p>
        {description && (
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-faint)' }}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
