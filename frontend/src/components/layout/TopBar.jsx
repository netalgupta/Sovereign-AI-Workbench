import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { chatPath } from '../../lib/nav'
import { useWorkspaceStore } from '../../store/workspaceStore'
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
  const currentSessionId = useChatStore((s) => s.sessionId)
  const plan = useChatStore((s) => s.plan) || []
  const planDone = plan.filter((s) => s.status === 'done').length
  const planRunning = plan.some((s) => s.status === 'running')
  // Both buttons open ONE floating panel (Plan & Agents) on their tab; the
  // same button again closes it.
  const orchestration = useWorkspaceStore((s) => s.panels.orchestration)
  const orchestrationOpen = Boolean(orchestration?.isOpen)
  const orchestrationTab = orchestration?.tab || 'plan'
  const showOrchestration = (tab) => {
    const ws = useWorkspaceStore.getState()
    if (orchestrationOpen && orchestrationTab === tab) {
      ws.closePanel('orchestration')
      return
    }
    ws.setPanelTab('orchestration', tab)
    if (!orchestrationOpen) ws.openPanel('orchestration')
    ws.bringToFront?.('orchestration')
  }
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
          {/* Sovereign Workstation Emblem -- the refinery mark (it was the
              sidebar's before the revamp, and a text "SV" badge after it) */}
          <img
            src="/assets/logo-mark-transparent.png"
            alt="Sovereign Workbench"
            className="h-8 w-auto object-contain flex-shrink-0 select-none transition-transform duration-200 group-hover:scale-105"
            draggable={false}
          />

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
            // A chat tab is active only on the chat page: on Home, Sources or
            // Settings, "Chat" was lit while no chat was on screen.
            const onChatPage = location.pathname.startsWith('/chat/')
            const isActive = onChatPage && activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  // A tab is a place (lib/nav.js): back returns to the tab you
                  // were on. The same tab again adds no history entry.
                  if (isActive) return
                  navigate(chatPath(currentSessionId, tab.id))
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

        {/* The Plan DAG and the agent map, for the chat on screen. They sat in
            the chat header, which the revamp moved into this bar -- and they
            did not come with it. */}
        {location.pathname.startsWith('/chat/') && (
          <>
            <button
              type="button"
              onClick={() => showOrchestration('plan')}
              aria-pressed={orchestrationOpen && orchestrationTab === 'plan'}
              className="group flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
              style={{
                border: '1px solid var(--color-border)',
                background: orchestrationOpen && orchestrationTab === 'plan' ? 'var(--color-accent-tint)' : 'transparent',
              }}
              title={plan.length ? `Plan DAG: step ${planDone + (planRunning ? 1 : 0)} of ${plan.length}` : 'Plan DAG: the plan of the latest turn, as a graph'}
            >
              <GitBranch size={13} strokeWidth={2.2} style={{ color: 'var(--color-accent)' }} className="group-hover:scale-110 transition-transform" />
              <span className="text-[11px] font-semibold" style={{ color: 'var(--color-text)' }}>Plan DAG</span>
              {plan.length > 0 && (
                <>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                    {planDone + (planRunning ? 1 : 0)}/{plan.length}
                  </span>
                  <span className="flex items-center gap-0.5 w-10">
                    {plan.map((step, idx) => (
                      <span
                        key={step.id || idx}
                        className={`h-1 flex-1 rounded-sm ${step.status === 'running' ? 'animate-pulse' : ''}`}
                        style={{
                          background:
                            step.status === 'done' ? 'var(--color-success)'
                              : step.status === 'running' ? 'var(--color-accent)'
                                : step.status === 'failed' ? 'var(--color-danger, #ef4444)'
                                  : 'var(--color-border)',
                        }}
                      />
                    ))}
                  </span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => showOrchestration('agents')}
              aria-pressed={orchestrationOpen && orchestrationTab === 'agents'}
              title="Agent map: every model call, tool call and background job of this chat"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer transition-fast hover:bg-[var(--color-surface-hover)]"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-accent)',
                background: orchestrationOpen && orchestrationTab === 'agents' ? 'var(--color-accent-tint)' : 'transparent',
              }}
            >
              <Bot size={13} />
              <span>Agent map</span>
            </button>
          </>
        )}

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
