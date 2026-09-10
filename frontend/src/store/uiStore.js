import { create } from 'zustand'

/**
 * uiStore.js — Zustand store for UI-only state.
 *
 * Stubbed now so import paths are stable for future features:
 *   - Rail collapse toggles (Day 8+ integration pass)
 *   - Active session panel tabs
 *   - Theme overrides (future)
 */
export const useUIStore = create((set) => ({
  // Rail visibility — placeholders for Day 8 collapse toggles
  isSourcesRailOpen: true,
  isPlanRailOpen: true,

  setSourcesRailOpen: (open) => set({ isSourcesRailOpen: open }),
  setPlanRailOpen: (open) => set({ isPlanRailOpen: open }),
}))
