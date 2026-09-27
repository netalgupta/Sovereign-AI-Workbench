import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Home,
  MessageSquare,
  FolderSearch,
  Network,
  Image as ImageIcon,
  Compass,
  FileCheck2,
  ScrollText,
  ShieldCheck,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react'
import { springs } from '../../lib/motion'

const NAV_ITEMS = [
  { path: '/', label: 'Home', icon: Home, exact: true },
  { path: '/workbench', label: 'Chat', icon: MessageSquare },
  { path: '/sources', label: 'Sources', icon: FolderSearch },
  { path: '/graph', label: 'Knowledge Graph', icon: Network },
  { path: '/vision', label: 'Images & Vision', icon: ImageIcon },
  { path: '/retrieval', label: 'Retrieval', icon: Compass },
  { path: '/outputs', label: 'Outputs', icon: FileCheck2 },
  { path: '/audit', label: 'Audit Log', icon: ScrollText },
  { path: '/monitor', label: 'Network Monitor', icon: ShieldCheck },
  { path: '/settings', label: 'System & Models', icon: Settings },
]

export function NavigationRail({ isExpanded, onToggleExpand }) {
  const location = useLocation()

  return (
    <motion.aside
      layout
      initial={false}
      animate={{
        width: isExpanded ? 200 : 54,
      }}
      transition={springs.spatial}
      className="h-full flex flex-col border-r flex-shrink-0 z-30 select-none relative"
      style={{
        background: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* ── Navigation Links ────────────────────────────────────────── */}
      <div className="flex-1 py-3 px-2 flex flex-col gap-1 overflow-y-auto overflow-x-hidden">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const isActive = item.exact
            ? location.pathname === item.path
            : location.pathname.startsWith(item.path)

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-2.5 py-2 rounded-lg text-xs font-medium transition-all group relative cursor-pointer ${
                isActive
                  ? 'bg-[var(--color-overlay)] text-[var(--color-accent)] font-semibold shadow-xs'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]'
              }`}
              title={!isExpanded ? item.label : undefined}
            >
              {/* Active accent vertical pill indicator */}
              {isActive && (
                <motion.div
                  layoutId="activeNavIndicator"
                  className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r-full bg-[var(--color-accent)]"
                  transition={springs.micro}
                />
              )}

              <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
                <Icon
                  size={16}
                  strokeWidth={isActive ? 2.4 : 1.9}
                  className={isActive ? 'text-[var(--color-accent)]' : 'group-hover:scale-105 transition-transform'}
                />
              </div>

              <AnimatePresence>
                {isExpanded && (
                  <motion.span
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -6 }}
                    transition={{ duration: 0.15 }}
                    className="truncate whitespace-nowrap text-[12.5px] tracking-tight"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </NavLink>
          )
        })}
      </div>

      {/* ── Bottom Collapse / Expand Toggle Button ───────────────────── */}
      <div
        className="p-2 border-t flex items-center justify-between"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <button
          type="button"
          onClick={onToggleExpand}
          className="w-full flex items-center justify-center gap-2 p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
          title={isExpanded ? 'Collapse navigation rail' : 'Expand navigation rail'}
        >
          {isExpanded ? (
            <>
              <ChevronLeft size={15} strokeWidth={2} />
              <span className="text-[11px] font-medium">Collapse</span>
            </>
          ) : (
            <ChevronRight size={15} strokeWidth={2} />
          )}
        </button>
      </div>
    </motion.aside>
  )
}
