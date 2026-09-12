/**
 * Spinner — animated loading ring used wherever an async action is in progress.
 * Color defaults to accent; size defaults to 'md'.
 */
export function Spinner({ size = 'md', className = '' }) {
  const sizes = {
    sm: 'w-3.5 h-3.5 border-[1.5px]',
    md: 'w-4 h-4 border-2',
    lg: 'w-5 h-5 border-2',
  }

  return (
    <span
      className={`inline-block rounded-full border-transparent animate-spin-smooth ${sizes[size]} ${className}`}
      style={{
        borderTopColor: 'var(--color-accent)',
        borderRightColor: 'var(--color-accent)',
        borderBottomColor: 'transparent',
        borderLeftColor: 'transparent',
      }}
      role="status"
      aria-label="Loading"
    />
  )
}
