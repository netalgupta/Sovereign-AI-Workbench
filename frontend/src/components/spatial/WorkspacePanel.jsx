import { useRef, useState } from 'react'
import { motion, useDragControls } from 'framer-motion'
import {
  GripVertical,
  Maximize2,
  Minimize2,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Pin,
  PinOff,
  X,
  Sparkles,
} from 'lucide-react'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { springs, transitions } from '../../lib/motion'
import { ErrorBoundary } from '../common/ErrorBoundary'

/**
 * WorkspacePanel — The core spatial unit.
 *
 * Implements:
 * 1. DRAG — Lift slightly, subtle depth increase, follows pointer, settles softly.
 * 2. RESIZE — Width & height adjustment where appropriate.
 * 3. COLLAPSE / EXPAND — Dedicated 44px vertical ribbon with 1-click restore.
 * 4. PIN / UNPIN — Lock in place or freeform float.
 * 5. FOCUS — Expands to occupy primary canvas with smooth spatial continuity.
 * 6. CLOSE / REOPEN — Restorable from canvas edge tabs, toolbar, and dock.
 */
export function WorkspacePanel({
  id,
  title,
  icon: Icon,
  badge,
  badgeTone = 'neutral',
  headerActions,
  children,
  collapsedContent,
  isFloating = false,
  className = '',
  style = {},
  showHeader = true,
  allowClose = true,
  allowCollapse = true,
  allowFocus = true,
  allowPin = true,
  minWidth = 260,
  maxWidth = 720,
}) {
  const panel = useWorkspaceStore((s) => s.panels[id])
  const focusedPanelId = useWorkspaceStore((s) => s.focusedPanelId)
  const isFocused = focusedPanelId === id
  const hasAnyFocus = focusedPanelId !== null && !isFocused

  const {
    toggleCollapse,
    toggleFocus,
    pinPanel,
    closePanel,
    bringToFront,
    updatePanelPosition,
  } = useWorkspaceStore()

  const dragControls = useDragControls()
  const [isDragging, setIsDragging] = useState(false)
  const [isHeaderHovered, setIsHeaderHovered] = useState(false)

  if (!panel || !panel.isOpen) return null

  const isCollapsed = panel.isCollapsed
  const isPinned = panel.isPinned

  // 1. Dedicated Collapsed State for FLOATING Panels (e.g. Graph, Monitor)
  if (isCollapsed && isFloating) {
    return (
      <motion.div
        layout
        onClick={() => toggleCollapse(id)}
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.94 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className="h-10 px-3 rounded-xl border flex items-center justify-between gap-3 shadow-md select-none cursor-pointer group hover:border-[var(--color-accent-border)] transition-all absolute"
        style={{
          left: panel.floatingPos?.x || 420,
          top: panel.floatingPos?.y || 100,
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
          zIndex: panel.zIndex || 20,
        }}
        title={`Click to expand ${title}`}
      >
        <div className="flex items-center gap-2">
          {Icon && (
            <div
              className="w-5 h-5 rounded-md flex items-center justify-center transition-colors group-hover:bg-[var(--color-accent)] group-hover:text-white"
              style={{ background: 'var(--color-overlay)', color: 'var(--color-accent)' }}
            >
              <Icon size={12} strokeWidth={2.2} />
            </div>
          )}
          <span className="text-xs font-semibold tracking-tight text-[var(--color-text)]">
            {title}
          </span>
          {badge && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border text-[var(--color-text-muted)] bg-[var(--color-overlay)] border-[var(--color-border)]">
              {badge}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              toggleCollapse(id)
            }}
            className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-colors cursor-pointer"
            title="Expand panel"
          >
            <ChevronDown size={14} strokeWidth={2.2} />
          </button>
          {allowClose && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                closePanel(id)
              }}
              className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors cursor-pointer"
              title="Close panel"
            >
              <X size={13} strokeWidth={2.2} />
            </button>
          )}
        </div>
      </motion.div>
    )
  }

  // 2. Dedicated Collapsed Vertical Ribbon for DOCKED Panels (e.g. Sources, Plan)
  if (isCollapsed && !isFloating) {
    if (collapsedContent) {
      return (
        <div className={`h-full w-11 flex flex-col relative ${className}`}>
          {collapsedContent}
        </div>
      )
    }

    const isPlan = id === 'plan' || panel.dockPosition === 'right'
    return (
      <div
        onClick={() => toggleCollapse(id)}
        className={`h-full w-11 flex flex-col items-center justify-between py-3 rounded-xl border select-none cursor-pointer group transition-all shadow-xs ${className}`}
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
        title={`Click anywhere to expand ${title}`}
      >
        {/* Top: Icon + Prominent Expand Button */}
        <div className="flex flex-col items-center gap-2">
          {Icon && (
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors group-hover:bg-[var(--color-accent)] group-hover:text-white"
              style={{
                background: 'var(--color-overlay)',
                color: 'var(--color-accent)',
              }}
            >
              <Icon size={14} strokeWidth={2.2} />
            </div>
          )}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              toggleCollapse(id)
            }}
            className="p-1 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
            title={`Expand ${title}`}
          >
            {isPlan ? (
              <ChevronLeft size={16} strokeWidth={2.5} className="group-hover:translate-x-[-2px] transition-transform" />
            ) : (
              <ChevronRight size={16} strokeWidth={2.5} className="group-hover:translate-x-[2px] transition-transform" />
            )}
          </button>
        </div>

        {/* Center: Vertical Rotated Label */}
        <div className="flex-1 flex items-center justify-center my-4 overflow-hidden">
          <span
            className="text-[11px] font-mono font-semibold uppercase tracking-wider text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-colors whitespace-nowrap"
            style={{
              writingMode: 'vertical-rl',
              transform: 'rotate(180deg)',
            }}
          >
            {title}
          </span>
        </div>

        {/* Bottom: Badge / Status Dot */}
        <div className="flex flex-col items-center gap-1.5">
          {badge && (
            <span
              className="text-[9px] font-mono font-bold px-1 py-0.5 rounded border text-[var(--color-text-muted)]"
              style={{
                background: 'var(--color-overlay)',
                borderColor: 'var(--color-border)',
              }}
            >
              {String(badge).split(' ')[0]}
            </span>
          )}
          <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] group-hover:scale-125 transition-transform" />
        </div>
      </div>
    )
  }

  // Badge styling
  const badgeStyles = {
    neutral: {
      bg: 'var(--color-overlay)',
      text: 'var(--color-text-muted)',
      border: 'var(--color-border)',
    },
    accent: {
      bg: 'var(--color-accent-tint)',
      text: 'var(--color-accent)',
      border: 'var(--color-accent-border)',
    },
    success: {
      bg: 'var(--color-success-tint)',
      text: 'var(--color-success)',
      border: 'var(--color-border)',
    },
    warning: {
      bg: 'var(--color-warning-tint)',
      text: 'var(--color-warning)',
      border: 'var(--color-border)',
    },
  }[badgeTone] || {}

  // Explicit Fullscreen / Focus Mode styles
  const computedStyle = isFocused
    ? {
        position: 'fixed',
        top: '52px',
        left: '58px',
        right: '12px',
        bottom: '44px',
        width: 'calc(100vw - 70px)',
        height: 'calc(100vh - 96px)',
        maxWidth: 'none',
        maxHeight: 'none',
        zIndex: 9999,
        margin: 0,
        background: 'var(--color-surface)',
        borderColor: 'var(--color-accent-border)',
        boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.7), 0 0 0 100vmax rgba(0, 0, 0, 0.5)',
      }
    : isFloating
    ? {
        ...style,
        zIndex: panel.zIndex || 10,
        background: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }
    : {
        ...style,
        zIndex: panel.zIndex || 10,
        background: id === 'chat' || (id === 'sources' && !isFloating) ? 'transparent' : 'var(--color-surface)',
        borderColor: id === 'chat' || (id === 'sources' && !isFloating) ? 'transparent' : 'var(--color-border)',
      }

  return (
    <motion.div
      layout={!isFocused}
      onMouseDown={() => bringToFront(id)}
      drag={isFloating && !isPinned && !isFocused}
      dragControls={dragControls}
      dragListener={false}
      dragMomentum={false}
      onDragStart={() => setIsDragging(true)}
      onDragEnd={(_, info) => {
        setIsDragging(false)
        if (panel.floatingPos) {
          updatePanelPosition(id, {
            x: Math.max(10, panel.floatingPos.x + info.offset.x),
            y: Math.max(60, panel.floatingPos.y + info.offset.y),
          })
        }
      }}
      initial={false}
      animate={{
        opacity: hasAnyFocus ? 0.28 : 1,
        scale: hasAnyFocus ? 0.98 : 1,
      }}
      transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
      style={{
        pointerEvents: hasAnyFocus ? 'none' : 'auto',
        ...computedStyle,
      }}
      className={`flex flex-col select-none ${
        id === 'chat' || (id === 'sources' && !isFloating)
          ? 'h-full w-full'
          : 'rounded-xl overflow-hidden border'
      } ${
        isFocused
          ? 'fixed shadow-2xl backdrop-blur-md'
          : isFloating
          ? 'absolute shadow-md'
          : 'h-full relative'
      } ${className}`}
    >
      {/* ── Panel Header & Spatial Controls ───────────────────────────── */}
      {showHeader && (
        <div
          onMouseEnter={() => setIsHeaderHovered(true)}
          onMouseLeave={() => setIsHeaderHovered(false)}
          className={`flex items-center justify-between px-3 py-2 flex-shrink-0 relative group ${
            id === 'sources' && !isFloating ? '' : 'border-b'
          }`}
          style={{
            background: id === 'sources' && !isFloating ? 'transparent' : 'var(--color-surface)',
            borderColor: id === 'sources' && !isFloating ? 'transparent' : 'var(--color-border)',
            cursor: isFloating && !isPinned ? 'grab' : 'default',
          }}
        >
          {/* Left: Drag grip, Icon & Title */}
          <div className="flex items-center gap-2 min-w-0">
            {isFloating && !isPinned && (
              <div
                onPointerDown={(e) => dragControls.start(e)}
                className="p-1 -ml-1 text-[var(--color-text-faint)] hover:text-[var(--color-text)] cursor-grab active:cursor-grabbing rounded transition-colors"
                title="Drag panel"
              >
                <GripVertical size={13} strokeWidth={2} />
              </div>
            )}

            {Icon && (
              <div
                className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'var(--color-overlay)',
                  color: 'var(--color-accent)',
                }}
              >
                <Icon size={12} strokeWidth={2.2} />
              </div>
            )}

            <span
              className="text-[12px] font-semibold tracking-tight truncate"
              style={{ color: 'var(--color-text)' }}
            >
              {title}
            </span>

            {badge && (
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium flex-shrink-0 border"
                style={{
                  background: badgeStyles.bg,
                  color: badgeStyles.text,
                  borderColor: badgeStyles.border,
                }}
              >
                {badge}
              </span>
            )}
          </div>

          {/* Right: Custom actions + Spatial Controls */}
          <div className="flex items-center gap-1">
            {headerActions}

            {/* Revealable Controls on Hover */}
            <div
              className={`flex items-center gap-0.5 transition-opacity duration-150 ${
                isHeaderHovered || isFocused ? 'opacity-100' : 'opacity-60 md:opacity-40'
              }`}
            >
              {allowPin && isFloating && (
                <button
                  type="button"
                  onClick={() => pinPanel(id, !isPinned)}
                  className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
                  title={isPinned ? 'Unpin (allow moving)' : 'Pin in place'}
                >
                  {isPinned ? <Pin size={12} strokeWidth={2.2} /> : <PinOff size={12} strokeWidth={2} />}
                </button>
              )}

              {allowCollapse && !isFocused && (
                <button
                  type="button"
                  onClick={() => toggleCollapse(id)}
                  className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
                  title={isCollapsed ? 'Expand panel' : 'Collapse panel'}
                >
                  {isCollapsed ? <ChevronDown size={13} strokeWidth={2.2} /> : <ChevronUp size={13} strokeWidth={2.2} />}
                </button>
              )}

              {allowFocus && !isCollapsed && (
                <button
                  type="button"
                  onClick={() => toggleFocus(id)}
                  className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
                  title={isFocused ? 'Exit focus mode (Esc)' : 'Focus mode'}
                >
                  {isFocused ? <Minimize2 size={12} strokeWidth={2.2} /> : <Maximize2 size={12} strokeWidth={2.2} />}
                </button>
              )}

              {allowClose && (
                <button
                  type="button"
                  onClick={() => closePanel(id)}
                  className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
                  title="Close panel"
                >
                  <X size={12} strokeWidth={2.2} />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Panel Body ────────────────────────────────────────────────── */}
      {!isCollapsed && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fast}
          className="flex-1 min-h-0 overflow-y-auto flex flex-col relative"
          style={{ background: id === 'sources' && !isFloating ? 'transparent' : 'var(--color-bg)' }}
        >
          <ErrorBoundary>
            {children}
          </ErrorBoundary>
        </motion.div>
      )}
    </motion.div>
  )
}
