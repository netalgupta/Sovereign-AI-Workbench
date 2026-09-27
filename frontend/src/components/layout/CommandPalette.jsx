import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search,
  MessageSquare,
  FolderSearch,
  Network,
  Image as ImageIcon,
  Compass,
  FileCheck2,
  ScrollText,
  ShieldCheck,
  Settings,
  ArrowRight,
  ExternalLink,
  Plus,
  FileText,
} from 'lucide-react'
import { springs, popoverVariants } from '../../lib/motion'
import { useChatStore } from '../../store/chatStore'

const QUICK_LINKS = [
  { id: 'nav-home', title: 'Command Center', subtitle: 'Overview, corpus stats & recent work', path: '/', icon: Search },
  { id: 'nav-chat', title: 'Chat & Spatial Workbench', subtitle: 'Primary intelligence conversation stream', path: '/workbench', icon: MessageSquare },
  { id: 'nav-sources', title: 'Grounded Sources', subtitle: 'Ingestion, active corpus files & previews', path: '/sources', icon: FolderSearch },
  { id: 'nav-graph', title: 'Knowledge Graph Explorer', subtitle: 'Neo4j entity canvas & signature queries', path: '/graph', icon: Network },
  { id: 'nav-vision', title: 'Images & Vision Studio', subtitle: 'OCR overlays, chart estimates & inspections', path: '/vision', icon: ImageIcon },
  { id: 'nav-retrieval', title: 'Retrieval Observatory', subtitle: 'Embeddings, PCA scatter & similarity heatmaps', path: '/retrieval', icon: Compass },
  { id: 'nav-outputs', title: 'Deliverables & Outputs', subtitle: 'DOCX reports, XLSX tables & PPTX decks', path: '/outputs', icon: FileCheck2 },
  { id: 'nav-audit', title: 'Operational Audit Log', subtitle: 'Tamper-evident tool invocation records', path: '/audit', icon: ScrollText },
  { id: 'nav-monitor', title: 'Air-Gap Security Monitor', subtitle: 'Hardware sockets & zero-egress verification', path: '/monitor', icon: ShieldCheck },
  { id: 'nav-settings', title: 'System & Model Registry', subtitle: 'Local LLMs, VRAM and storage diagnostics', path: '/settings', icon: Settings },
]

export function CommandPalette({ isOpen, onClose }) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [corpusSources, setCorpusSources] = useState([])
  const navigate = useNavigate()
  const inputRef = useRef(null)

  // Fetch real corpus files when open
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    fetch('/api/corpus')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data?.sources) {
          setCorpusSources(data.sources.slice(0, 8))
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [isOpen])

  // Focus input on open
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Filter items
  const filteredNav = QUICK_LINKS.filter((item) =>
    item.title.toLowerCase().includes(query.toLowerCase()) ||
    item.subtitle.toLowerCase().includes(query.toLowerCase())
  )

  const filteredSources = corpusSources.filter((s) =>
    (s.name || s.id || '').toLowerCase().includes(query.toLowerCase())
  )

  const allItems = [
    ...filteredNav.map((n) => ({ ...n, type: 'nav' })),
    ...filteredSources.map((s) => ({
      id: `source-${s.id}`,
      title: s.name || s.id,
      subtitle: `${s.category || 'Document'} · ${s.sizeDisplay || 'Ready'}`,
      path: `/sources?select=${encodeURIComponent(s.id)}`,
      icon: FileText,
      type: 'source',
    })),
  ]

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, allItems.length))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev - 1 + allItems.length) % Math.max(1, allItems.length))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const item = allItems[selectedIndex]
      if (item) {
        navigate(item.path)
        onClose()
      }
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/40 backdrop-blur-xs select-none">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: -10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: -10 }}
        transition={springs.micro}
        className="w-full max-w-xl rounded-2xl overflow-hidden border shadow-2xl flex flex-col"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        {/* Search Input Bar */}
        <div
          className="flex items-center gap-3 px-4 py-3 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <Search size={18} strokeWidth={2} className="text-[var(--color-accent)]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSelectedIndex(0)
            }}
            onKeyDown={handleKeyDown}
            placeholder="Type a command, navigate, or search sources..."
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--color-text-faint)]"
            style={{ color: 'var(--color-text)' }}
          />
          <kbd
            className="px-1.5 py-0.5 rounded text-[10px] font-mono border"
            style={{
              background: 'var(--color-overlay)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
          >
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div className="max-h-[380px] overflow-y-auto p-2 flex flex-col gap-1">
          {allItems.length === 0 ? (
            <div className="py-10 text-center text-xs text-[var(--color-text-muted)]">
              No matching commands or sources found.
            </div>
          ) : (
            allItems.map((item, idx) => {
              const Icon = item.icon
              const isSelected = idx === selectedIndex

              return (
                <div
                  key={item.id}
                  onClick={() => {
                    navigate(item.path)
                    onClose()
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs cursor-pointer transition-fast ${
                    isSelected
                      ? 'bg-[var(--color-overlay)] text-[var(--color-text)] shadow-xs'
                      : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                        isSelected
                          ? 'bg-[var(--color-accent-tint)] text-[var(--color-accent)] border-[var(--color-accent-border)]'
                          : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] border-[var(--color-border)]'
                      }`}
                    >
                      <Icon size={14} strokeWidth={2} />
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span
                        className={`font-semibold truncate ${
                          isSelected ? 'text-[var(--color-text)]' : ''
                        }`}
                      >
                        {item.title}
                      </span>
                      <span className="text-[11px] text-[var(--color-text-muted)] truncate">
                        {item.subtitle}
                      </span>
                    </div>
                  </div>

                  <ArrowRight
                    size={13}
                    className={`transition-transform flex-shrink-0 ${
                      isSelected
                        ? 'text-[var(--color-accent)] translate-x-0.5'
                        : 'text-transparent'
                    }`}
                  />
                </div>
              )
            })
          )}
        </div>

        {/* Footer shortcuts hint */}
        <div
          className="px-4 py-2 border-t flex items-center justify-between text-[11px] font-mono text-[var(--color-text-muted)]"
          style={{
            background: 'var(--color-overlay)',
            borderColor: 'var(--color-border)',
          }}
        >
          <span>Use ↑↓ to navigate</span>
          <span>↵ to select</span>
        </div>
      </motion.div>
    </div>
  )
}
