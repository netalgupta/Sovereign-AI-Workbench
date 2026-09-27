import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  ShieldCheck,
  ShieldAlert,
  Search,
  Sun,
  Moon,
  Cpu,
  User,
  Radio,
  SlidersHorizontal,
  Settings,
  FolderSearch,
  MessageSquare,
  ChevronDown,
  GitBranch,
  Bot,
  BookOpen,
  FileCode,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useThemeStore } from '../../store/themeStore'
import { useChatStore } from '../../store/chatStore'
import { springs } from '../../lib/motion'

export function TopBar({ onOpenSearch }) {
  // Who and where, from the backend. Empty until it answers.
  const [station, setStation] = useState({ user: '', host: '' })
  useEffect(() => {
    let alive = true
    fetch('/api/system-info')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && d && setStation({ user: d.user || '', host: d.host || '' }))
      .catch(() => {})
    return () => { alive = false }
  }, [])
  const { theme, toggleTheme } = useThemeStore()
  const location = useLocation()
  const navigate = useNavigate()
  const activeTab = useChatStore((s) => s.activeTab)
  const setActiveTab = useChatStore((s) => s.setActiveTab)
  const plan = useChatStore((s) => s.plan) || []
  const doneCount = plan.filter((s) => s.status === 'done').length
  const runningStep = plan.find((s) => s.status === 'running')

  return (
    <header
      className="h-12 w-full px-5 flex items-center justify-between flex-shrink-0 z-40 select-none relative"
      style={{
        background: 'transparent',
      }}
    >
      {/* ── Left: Sovereign Emblem & Identity ────────────────────────── */}
      <div className="flex items-center gap-3">
        <Link
          to="/"
          className="flex items-center gap-2.5 group cursor-pointer"
          title="Sovereign Workbench Home"
        >
          {/* Sovereign Workstation Emblem */}
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs tracking-tight transition-transform duration-200 group-hover:scale-105 shadow-xs"
            style={{
              background: 'var(--color-accent)',
              color: '#FFFFFF',
            }}
          >
            <span className="font-mono text-sm leading-none font-bold">SV</span>
          </div>

          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span
                className="font-bold tracking-tight text-xs uppercase"
                style={{ color: 'var(--color-text)', letterSpacing: '0.06em' }}
              >
                Sovereign
              </span>
              <span
                className="text-[10px] font-mono px-1.5 py-0.5 rounded font-medium"
                style={{
                  background: 'var(--color-overlay)',
                  color: 'var(--color-text-muted)',
                }}
              >
                ON-PREMISE
              </span>
            </div>
            <span
              className="text-[10px] font-medium leading-none"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Industrial Intelligence Workstation
            </span>
          </div>
        </Link>
      </div>

      {/* ── Center: Segmented Navigation Options (Chat / Notebooks / Artifacts) ── */}
      <div className="flex-1 flex justify-center mx-4 select-none">
        <div
          className="flex items-center p-0.5 rounded-xl text-xs font-medium gap-1 relative shadow-xs"
          style={{ background: 'var(--color-overlay)' }}
        >
          {[
            { id: 'chat', label: 'Chat', icon: Bot },
            { id: 'notebooks', label: 'Notebooks', icon: BookOpen },
            { id: 'artifacts', label: 'Artifacts', icon: FileCode },
          ].map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id)
                  if (location.pathname !== '/workbench' && location.pathname !== '/chat') {
                    navigate('/workbench')
                  }
                }}
                className="relative flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs transition-fast cursor-pointer"
                style={{
                  color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                  fontWeight: isActive ? 600 : 500,
                }}
              >
                {isActive && (
                  <motion.div
                    layoutId="topbar-active-tab-pill"
                    className="absolute inset-0 rounded-lg shadow-xs"
                    style={{
                      background: 'var(--color-surface)',
                    }}
                    transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <tab.icon size={13} strokeWidth={2} />
                  <span>{tab.label}</span>
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Right: Navigation Links, Theme Toggle, Air-Gap, Operator ── */}
      <div className="flex items-center gap-1.5 sm:gap-2">

        {/* Sources Button — Takes to Sources page */}
        <Link
          to="/sources"
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-fast cursor-pointer ${
            location.pathname === '/sources'
              ? 'bg-[var(--color-accent-tint)] text-[var(--color-accent)] font-semibold'
              : 'hover:bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
          }`}
          title="Manage Corpus Sources & Documents"
        >
          <FolderSearch
            size={13}
            strokeWidth={2}
            className={location.pathname === '/sources' ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'}
          />
          <span className="hidden sm:inline">Sources</span>
        </Link>

        {/* Settings Button — Takes to Settings page */}
        <Link
          to="/settings"
          className={`p-2 rounded-lg text-xs font-medium transition-fast cursor-pointer ${
            location.pathname === '/settings' || location.pathname === '/system'
              ? 'bg-[var(--color-accent-tint)] text-[var(--color-accent)]'
              : 'hover:bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
          }`}
          title="System Settings & Model Registry"
        >
          <Settings size={14} strokeWidth={2} />
        </Link>

        {/* Theme Toggle (Warm Day / Carbon Night) */}
        <button
          type="button"
          onClick={toggleTheme}
          className="p-2 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
          title={`Switch to ${theme === 'dark' ? 'Warm Day' : 'Carbon Night'} Mode`}
        >
          {theme === 'dark' ? (
            <Sun size={15} strokeWidth={2} />
          ) : (
            <Moon size={15} strokeWidth={2} />
          )}
        </button>

        {/* Operator Profile Control (Seamless hover, no border-l) */}
        <div className="flex items-center gap-2 pl-1">
          <div
            className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium"
            style={{
              background: 'var(--color-overlay)',
              color: 'var(--color-text)',
            }}
            title={station.host ? `Signed in as ${station.user || 'local account'} on ${station.host}` : 'Local workstation'}
          >
            <User size={12} strokeWidth={2.2} />
          </div>
          <div className="hidden xl:flex flex-col">
            {/* The real OS account and machine (/api/system-info), not a fixed
                "Operator / Station #1". Blank until known, never invented. */}
            <span className="text-[11px] font-semibold leading-none" style={{ color: 'var(--color-text)' }}>
              {station.user || ' '}
            </span>
            <span className="text-[9px] font-mono leading-none mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
              {station.host || ' '}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}
