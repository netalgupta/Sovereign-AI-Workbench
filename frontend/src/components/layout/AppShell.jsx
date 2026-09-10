import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Flame,
  ChevronDown,
  Search,
  Bell,
  Check,
  FileText,
  Network,
  Shield,
  Settings,
  Activity,
} from 'lucide-react'

/**
 * AppShell — Top bar chrome + full-height content area.
 * Matches the reference design layout: full-width top bar with
 * product branding, context switcher, search, notification, and user avatar.
 */
export function AppShell({ children }) {
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false)
  const location = useLocation()

  const SESSIONS = [
    { id: '1', title: 'Refinery Turnaround Analysis', active: true },
    { id: '2', title: 'CDU-II Column Maintenance Review', active: false },
    { id: '3', title: 'Hydrocracker Catalyst Life Estimation', active: false },
  ]

  const NAV_LINKS = [
    { to: '/', label: 'Workbench', icon: Flame },
    { to: '/sources', label: 'Sources Library', icon: FileText },
    { to: '/graph', label: 'Knowledge Graph', icon: Network },
    { to: '/outputs', label: 'Outputs & Reports', icon: FileText },
    { to: '/audit', label: 'Audit Trail', icon: Shield },
    { to: '/settings', label: 'Settings', icon: Settings },
    { to: '/monitor', label: 'System Monitor', icon: Activity },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--color-bg)' }}>
      {/* ── Top Bar (matches reference) ─────────────────────────────────── */}
      <header
        className="flex items-center justify-between px-5 h-14 flex-shrink-0 select-none z-50 relative"
        style={{
          background: 'var(--color-bg)',
          borderBottom: '1px solid rgba(42, 39, 36, 0.06)',
        }}
      >
        {/* Left: Brand mark + Product Title + Tagline */}
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 transition-fast"
              style={{
                background: 'var(--color-accent)',
                boxShadow: '0 2px 6px rgba(181, 101, 74, 0.25)',
              }}
              title="Agentic AI Workbench"
            >
              <Flame size={16} strokeWidth={2.2} style={{ color: '#FFFFFF' }} />
            </div>
            <div className="flex flex-col">
              <span
                className="text-sm font-bold tracking-tight leading-none"
                style={{ color: 'var(--color-text)' }}
              >
                Agentic AI Workbench
              </span>
              <span
                className="text-[10px] mt-0.5 leading-none"
                style={{ color: 'var(--color-text-muted)' }}
              >
                For safer, smarter plant operations
              </span>
            </div>
          </Link>
        </div>

        {/* Center: Session / Context Switcher Pill */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setSessionMenuOpen(!sessionMenuOpen)}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-fast"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
              boxShadow: 'var(--shadow-xs)',
            }}
            aria-expanded={sessionMenuOpen}
            aria-haspopup="true"
          >
            {/* Small icon representing technical session */}
            <span
              className="w-4 h-4 rounded flex items-center justify-center font-mono text-[9px]"
              style={{ background: 'var(--color-overlay)', color: 'var(--color-text-muted)' }}
            >
              ☷
            </span>
            <span>Refinery Turnaround Analysis</span>
            <ChevronDown size={13} strokeWidth={2} style={{ color: 'var(--color-text-muted)' }} />
          </button>

          {/* Session Switcher Dropdown */}
          {sessionMenuOpen && (
            <div
              className="absolute left-1/2 -translate-x-1/2 mt-1.5 w-64 rounded-xl py-1.5 z-50 animate-fade-in"
              style={{
                background: '#FFFFFF',
                border: '1px solid var(--color-border)',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              <div
                className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: 'var(--color-text-faint)' }}
              >
                Active Sessions
              </div>
              {SESSIONS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSessionMenuOpen(false)}
                  className="w-full px-3 py-2 text-left text-xs flex items-center justify-between transition-fast hover:bg-[#F5EFEB]"
                  style={{ color: s.active ? 'var(--color-text)' : 'var(--color-text-muted)' }}
                >
                  <span className="truncate">{s.title}</span>
                  {s.active && <Check size={13} style={{ color: 'var(--color-accent)' }} />}
                </button>
              ))}
              <div className="my-1 border-t" style={{ borderColor: 'var(--color-border)' }} />
              <div
                className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: 'var(--color-text-faint)' }}
              >
                Views & Subsystems
              </div>
              {NAV_LINKS.map((nav) => (
                <Link
                  key={nav.to}
                  to={nav.to}
                  onClick={() => setSessionMenuOpen(false)}
                  className="px-3 py-1.5 text-xs flex items-center gap-2 transition-fast hover:bg-[#F5EFEB]"
                  style={{
                    color: location.pathname === nav.to ? 'var(--color-accent)' : 'var(--color-text-muted)',
                  }}
                >
                  <nav.icon size={13} />
                  <span>{nav.label}</span>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Right: Search + Notification Bell + Avatar */}
        <div className="flex items-center gap-2.5">
          {/* Search Input Box */}
          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl transition-fast"
            style={{
              background: 'white',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-xs)',
              width: 190,
            }}
          >
            <Search size={13} strokeWidth={2} style={{ color: 'var(--color-text-muted)' }} />
            <input
              type="text"
              placeholder="Search anything..."
              className="bg-transparent text-xs outline-none w-full placeholder:text-[#9E9790]"
              style={{ color: 'var(--color-text)' }}
            />
            <kbd
              className="px-1.5 py-0.5 rounded text-[10px] font-mono leading-none flex-shrink-0"
              style={{
                background: 'var(--color-overlay)',
                color: 'var(--color-text-muted)',
                border: '1px solid rgba(42, 39, 36, 0.08)',
              }}
            >
              Ctrl K
            </kbd>
          </div>

          {/* Notification Bell */}
          <button
            type="button"
            className="w-8 h-8 rounded-xl flex items-center justify-center transition-fast hover:bg-[#EDE5DC]"
            style={{ color: 'var(--color-text-muted)' }}
            title="Notifications"
          >
            <Bell size={16} strokeWidth={1.8} />
          </button>

          {/* Circular User Avatar */}
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center font-semibold text-xs transition-fast cursor-pointer"
            style={{
              background: 'var(--color-overlay)',
              border: '1px solid var(--color-border-strong)',
              color: 'var(--color-text)',
            }}
            title="Engineer: Advay (Lead)"
          >
            AC
          </div>
        </div>
      </header>

      {/* ── Main Content Area (3 Panes) ───────────────────────────────── */}
      <main className="flex-1 overflow-hidden flex flex-col">
        {children}
      </main>
    </div>
  )
}
