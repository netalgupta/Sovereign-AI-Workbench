import { useState, useEffect } from 'react'
import { TopBar } from './TopBar'
import { CommandPalette } from './CommandPalette'
import { ToastContainer } from '../ui/Toast'

/**
 * AppShell — Sovereign Workstation Unified Chrome.
 *
 * Provides:
 * 1. Minimal TopBar: Workstation emblem (links to home), global search (Ctrl+K), Sources, Settings, real air-gap status, theme toggle, operator badge.
 * 2. Clean, full-viewport canvas with zero distraction sidebars.
 * 3. CommandPalette modal overlay: Fast keyboard-driven command & search interface.
 * 4. ToastContainer: Non-intrusive notifications.
 */
export function AppShell({ children }) {
  const [isSearchOpen, setIsSearchOpen] = useState(false)

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setIsSearchOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div
      className="flex flex-col h-screen w-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}
    >
      {/* ── Top Bar ─────────────────────────────────────────────────── */}
      <TopBar onOpenSearch={() => setIsSearchOpen(true)} />

      {/* ── Body: Full-width Main Viewport Stage ─────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 min-h-0 h-full w-full overflow-hidden relative">
        {children}
      </main>

      {/* ── Global Command Search Palette ──────────────────────────── */}
      <CommandPalette
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
      />

      {/* ── Global Toast Container ──────────────────────────────────── */}
      <ToastContainer />
    </div>
  )
}
