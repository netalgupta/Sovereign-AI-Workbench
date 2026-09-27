/**
 * workspaceStore.js — Spatial Workspace State Engine
 *
 * Manages panels as spatial objects within the workspace canvas:
 * - Fluid drag & floating coordinates or adaptive docking
 * - Dynamic resizing
 * - Collapse into compact pill controls
 * - Focus mode (full workspace expansion with spatial continuity)
 * - Pinned states (persist layout vs floating)
 * - Layering (z-index stacking on interaction)
 * - Layout presets: 'trio' (Sources, Chat, Plan), 'focus', 'freeform'
 * - LocalStorage persistence (client-side only per spec)
 */

import { create } from 'zustand'

const STORAGE_KEY = 'sovereign_workspace_layout_v6'

export const DEFAULT_PANELS = {
  sources: {
    id: 'sources',
    title: 'Sources',
    category: 'evidence',
    isOpen: true,
    isCollapsed: false,
    isPinned: true,
    isFocused: false,
    width: 320,
    minWidth: 240,
    maxWidth: 480,
    height: null,
    zIndex: 10,
    dockPosition: 'left',
    floatingPos: { x: 40, y: 72 },
  },
  chat: {
    id: 'chat',
    title: 'Intelligence Stream',
    category: 'primary',
    isOpen: true,
    isCollapsed: false,
    isPinned: true,
    isFocused: false,
    width: null, // flex-1 full width
    minWidth: 420,
    height: null,
    zIndex: 5,
    dockPosition: 'center',
    floatingPos: { x: 340, y: 72 },
  },
  plan: {
    id: 'plan',
    title: 'Plan DAG',
    category: 'orchestration',
    isOpen: false, // Closed by default when idle so Chat breathes! Auto-opens when plan runs.
    isCollapsed: false,
    isPinned: true,
    isFocused: false,
    width: 340,
    minWidth: 260,
    maxWidth: 560,
    height: null,
    zIndex: 10,
    dockPosition: 'right',
    floatingPos: { x: 920, y: 72 },
  },
  // Plan DAG + agent map in one floating, draggable panel beside the chat.
  // A new id (not 'plan'): a saved layout overrides a panel's defaults, and
  // the old 'plan' entry was pinned and docked.
  orchestration: {
    id: 'orchestration',
    title: 'Plan & Agents',
    category: 'orchestration',
    isOpen: false,
    isCollapsed: false,
    isPinned: false,
    isFocused: false,
    width: 560,
    minWidth: 380,
    height: 560,
    zIndex: 12,
    dockPosition: 'floating',
    floatingPos: { x: typeof window !== 'undefined' ? Math.max(380, window.innerWidth - 600) : 860, y: 76 },
    tab: 'plan',
  },
  graph: {
    id: 'graph',
    title: 'Knowledge Graph',
    category: 'exploration',
    isOpen: false,
    isCollapsed: false,
    isPinned: false,
    isFocused: false,
    width: 580,
    minWidth: 380,
    height: 480,
    zIndex: 20,
    dockPosition: 'floating',
    floatingPos: { x: 420, y: 100 },
  },
  evidence: {
    id: 'evidence',
    title: 'Evidence Reader',
    category: 'evidence',
    isOpen: false,
    isCollapsed: false,
    isPinned: false,
    isFocused: false,
    width: 520,
    minWidth: 360,
    height: 520,
    zIndex: 25,
    dockPosition: 'floating',
    floatingPos: { x: 460, y: 120 },
  },
  monitor: {
    id: 'monitor',
    title: 'Air-Gap & Socket Monitor',
    category: 'system',
    isOpen: false,
    isCollapsed: false,
    isPinned: false,
    isFocused: false,
    width: 480,
    minWidth: 360,
    height: 420,
    zIndex: 30,
    dockPosition: 'floating',
    floatingPos: { x: 500, y: 140 },
  },
}

function loadSavedLayout() {
  if (typeof window === 'undefined') return DEFAULT_PANELS
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_PANELS
    const parsed = JSON.parse(raw)
    // Merge with defaults in case new panels were added
    return { ...DEFAULT_PANELS, ...parsed }
  } catch (e) {
    console.warn('Failed to parse saved workspace layout:', e)
    return DEFAULT_PANELS
  }
}

function saveLayout(panels) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(panels))
  } catch (e) {
    console.warn('Failed to save workspace layout:', e)
  }
}

export const useWorkspaceStore = create((set, get) => ({
  panels: loadSavedLayout(),
  focusedPanelId: null,
  layoutMode: 'fluid', // 'fluid' | 'focus' | 'freeform'
  highestZIndex: 35,

  // ── Actions ───────────────────────────────────────────────────────────────

  openPanel: (id) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const nextZ = state.highestZIndex + 1
      const updated = {
        ...state.panels,
        [id]: { ...p, isOpen: true, isCollapsed: false, zIndex: nextZ },
      }
      saveLayout(updated)
      return { panels: updated, highestZIndex: nextZ }
    })
  },

  closePanel: (id) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = {
        ...state.panels,
        [id]: { ...p, isOpen: false, isFocused: false },
      }
      const nextFocused = state.focusedPanelId === id ? null : state.focusedPanelId
      saveLayout(updated)
      return {
        panels: updated,
        focusedPanelId: nextFocused,
        layoutMode: nextFocused ? 'focus' : state.layoutMode === 'focus' ? 'fluid' : state.layoutMode,
      }
    })
  },

  togglePanel: (id) => {
    const p = get().panels[id]
    if (!p) return
    if (p.isOpen && !p.isCollapsed) {
      get().closePanel(id)
    } else {
      get().openPanel(id)
    }
  },

  collapsePanel: (id) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = {
        ...state.panels,
        [id]: { ...p, isCollapsed: true, isFocused: false },
      }
      saveLayout(updated)
      return { panels: updated }
    })
  },

  expandPanel: (id) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = {
        ...state.panels,
        [id]: { ...p, isCollapsed: false, isOpen: true },
      }
      saveLayout(updated)
      return { panels: updated }
    })
  },

  toggleCollapse: (id) => {
    const p = get().panels[id]
    if (!p) return
    if (p.isCollapsed) {
      get().expandPanel(id)
    } else {
      get().collapsePanel(id)
    }
  },

  focusPanel: (id) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const nextZ = state.highestZIndex + 1
      const updated = {
        ...state.panels,
        [id]: { ...p, isOpen: true, isCollapsed: false, isFocused: true, zIndex: nextZ },
      }
      return {
        panels: updated,
        focusedPanelId: id,
        layoutMode: 'focus',
        highestZIndex: nextZ,
      }
    })
  },

  exitFocus: () => {
    set((state) => {
      const updated = { ...state.panels }
      Object.keys(updated).forEach((k) => {
        updated[k] = { ...updated[k], isFocused: false }
      })
      return {
        panels: updated,
        focusedPanelId: null,
        layoutMode: 'fluid',
      }
    })
  },

  toggleFocus: (id) => {
    if (get().focusedPanelId === id) {
      get().exitFocus()
    } else {
      get().focusPanel(id)
    }
  },

  pinPanel: (id, isPinned = true) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = {
        ...state.panels,
        [id]: { ...p, isPinned },
      }
      saveLayout(updated)
      return { panels: updated }
    })
  },

  setPanelTab: (id, tab) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = { ...state.panels, [id]: { ...p, tab } }
      saveLayout(updated)
      return { panels: updated }
    })
  },

  updatePanelPosition: (id, pos) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = {
        ...state.panels,
        [id]: { ...p, floatingPos: pos, dockPosition: 'floating' },
      }
      saveLayout(updated)
      return { panels: updated }
    })
  },

  updatePanelSize: (id, size) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const updated = {
        ...state.panels,
        [id]: { ...p, ...size },
      }
      saveLayout(updated)
      return { panels: updated }
    })
  },

  bringToFront: (id) => {
    set((state) => {
      const p = state.panels[id]
      if (!p) return state
      const nextZ = state.highestZIndex + 1
      const updated = {
        ...state.panels,
        [id]: { ...p, zIndex: nextZ },
      }
      return { panels: updated, highestZIndex: nextZ }
    })
  },

  setLayoutMode: (mode) => {
    set({ layoutMode: mode })
  },

  resetLayout: () => {
    saveLayout(DEFAULT_PANELS)
    set({
      panels: DEFAULT_PANELS,
      focusedPanelId: null,
      layoutMode: 'fluid',
      highestZIndex: 35,
    })
  },
}))
