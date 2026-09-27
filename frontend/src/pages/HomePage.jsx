import { useState, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowRight, MessageSquare, Search, Plus, Trash2, Clock } from "lucide-react"
import { useChatStore } from "../store/chatStore"
import { springs, buttonTapMotion } from "../lib/motion"

function relativeTime(iso) {
  if (!iso) return ""
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m ago`
  if (h < 24) return `${h}h ago`
  if (d < 7) return `${d}d ago`
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" })
}

export function HomePage() {
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState("")
  const [search, setSearch] = useState("")

  const sessions = useChatStore((s) => s.sessions)
  const newSession = useChatStore((s) => s.newSession)
  const loadSession = useChatStore((s) => s.loadSession)
  const deleteSession = useChatStore((s) => s.deleteSession)
  const currentSessionId = useChatStore((s) => s.sessionId)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    newSession()
    navigate(`/workbench?prompt=${encodeURIComponent(prompt.trim())}`)
  }

  const handleOpenSession = (id) => {
    loadSession(id)
    navigate("/workbench")
  }

  const handleNewChat = () => {
    newSession()
    navigate("/workbench")
  }

  const handleDelete = (e, id) => {
    e.stopPropagation()
    deleteSession(id)
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return sessions
    return sessions.filter((s) => s.title?.toLowerCase().includes(q))
  }, [sessions, search])

  const hour = new Date().getHours()
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"

  return (
    <div className="flex-1 overflow-y-auto px-6 md:px-12 py-10 flex flex-col items-center" style={{ background: "var(--color-bg)" }}>
      <div className="w-full max-w-3xl flex flex-col gap-10">

        {/* Header */}
        <div className="flex flex-col items-center text-center gap-3">
          <span className="text-[11px] font-mono uppercase tracking-widest font-semibold px-2 py-0.5 rounded border" style={{ background: "var(--color-overlay)", borderColor: "var(--color-border)", color: "var(--color-accent)" }}>
            SOVEREIGN WORKBENCH · PS26117
          </span>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight" style={{ color: "var(--color-text)" }}>
            {greeting}, Engineer.
          </h1>
          <p className="text-sm md:text-base max-w-lg leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
            Continue an investigation or start a new one.
          </p>
        </div>

        {/* Compose */}
        <motion.form onSubmit={handleSubmit} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={springs.spatial} className="w-full rounded-2xl border p-2 shadow-md focus-within:shadow-xl focus-within:border-[var(--color-accent-border)] transition-all" style={{ background: "var(--color-surface)", borderColor: "var(--color-border)" }}>
          <div className="flex flex-col gap-2 p-2">
            <textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e) } }} placeholder="Ask a technical question, command a setpoint evaluation, or explore pipeline correlations..." className="w-full bg-transparent resize-none outline-none text-sm md:text-base leading-relaxed placeholder:text-[var(--color-text-faint)]" style={{ color: "var(--color-text)" }} />
            <div className="flex items-center justify-between pt-2 border-t" style={{ borderColor: "var(--color-border)" }}>
              <div className="flex items-center gap-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
                <span className="flex items-center gap-1 font-mono text-[11px]"><kbd className="px-1 py-0.5 rounded bg-[var(--color-overlay)] border border-[var(--color-border)]">?</kbd> send</span>
                <span>·</span>
                <span className="hidden sm:inline">Grounded exclusively in verified local sources</span>
              </div>
              <motion.button {...buttonTapMotion} type="submit" disabled={!prompt.trim()} className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white transition-all shadow-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" style={{ background: "var(--color-accent)" }}>
                <span>Ask Sovereign</span><ArrowRight size={14} strokeWidth={2.2} />
              </motion.button>
            </div>
          </div>
        </motion.form>

        {/* Sessions */}
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock size={14} style={{ color: "var(--color-accent)" }} />
              <span className="text-[11px] font-mono uppercase tracking-wider font-semibold" style={{ color: "var(--color-text-muted)" }}>Chat Sessions</span>
              {sessions.length > 0 && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded font-semibold border" style={{ background: "var(--color-overlay)", borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>{sessions.length}</span>
              )}
            </div>
            <button type="button" onClick={handleNewChat} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-fast cursor-pointer" style={{ background: "var(--color-accent-tint)", color: "var(--color-accent)", border: "1px solid var(--color-accent-border)" }}>
              <Plus size={12} strokeWidth={2.5} />New Chat
            </button>
          </div>

          {sessions.length > 2 && (
            <div className="relative flex items-center">
              <Search size={13} className="absolute left-3 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
              <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search sessions..." className="w-full pl-9 pr-4 py-2 text-sm rounded-xl outline-none transition-all placeholder:text-[var(--color-text-faint)]" style={{ background: "var(--color-surface)", border: "1px solid transparent", color: "var(--color-text)" }} onFocus={(e) => (e.target.style.borderColor = "var(--color-accent-border)")} onBlur={(e) => (e.target.style.borderColor = "transparent")} />
            </div>
          )}

          <AnimatePresence mode="popLayout">
            {sessions.length === 0 ? (
              <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-16 flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed" style={{ borderColor: "var(--color-border)" }}>
                <MessageSquare size={24} style={{ color: "var(--color-text-faint)" }} />
                <p className="text-sm font-medium" style={{ color: "var(--color-text-muted)" }}>No sessions yet</p>
                <p className="text-xs" style={{ color: "var(--color-text-faint)" }}>Start a conversation above — it will appear here automatically.</p>
              </motion.div>
            ) : filtered.length === 0 ? (
              <motion.div key="no-match" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-10 text-center text-sm" style={{ color: "var(--color-text-muted)" }}>
                No sessions match "{search}"
              </motion.div>
            ) : (
              <motion.div key="list" className="flex flex-col gap-1.5">
                {filtered.map((s, idx) => {
                  const isActive = s.id === currentSessionId
                  return (
                    <motion.div key={s.id} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97 }} transition={{ delay: idx * 0.02 }} onClick={() => handleOpenSession(s.id)} className="group flex items-center justify-between px-4 py-3 rounded-xl border cursor-pointer transition-all" style={{ background: isActive ? "var(--color-accent-tint)" : "var(--color-surface)", borderColor: isActive ? "var(--color-accent-border)" : "var(--color-border)" }} onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "var(--color-surface-hover)" }} onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "var(--color-surface)" }}>
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <MessageSquare size={14} style={{ color: isActive ? "var(--color-accent)" : "var(--color-text-muted)", flexShrink: 0 }} />
                        <span className="text-sm font-medium truncate" style={{ color: isActive ? "var(--color-accent)" : "var(--color-text)" }}>{s.title || `Session ${s.id.slice(0, 8)}`}</span>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                        {s.messageCount > 0 && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded font-semibold border" style={{ background: "var(--color-overlay)", borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>{s.messageCount} msg{s.messageCount !== 1 ? "s" : ""}</span>
                        )}
                        <span className="text-[11px] font-mono hidden sm:inline" style={{ color: "var(--color-text-faint)" }}>{relativeTime(s.updatedAt)}</span>
                        <button type="button" onClick={(e) => handleDelete(e, s.id)} className="p-1 rounded opacity-0 group-hover:opacity-100 transition-all cursor-pointer hover:text-red-400 hover:bg-red-500/10" style={{ color: "var(--color-text-faint)" }} title="Delete session"><Trash2 size={13} /></button>
                        <ArrowRight size={13} className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "var(--color-text-muted)" }} />
                      </div>
                    </motion.div>
                  )
                })}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
