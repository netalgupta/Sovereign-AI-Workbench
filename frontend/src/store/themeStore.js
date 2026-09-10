import { create } from 'zustand'

const STORAGE_KEY = 'sovereign_workbench_theme'

function getInitialTheme() {
  if (typeof window === 'undefined') return 'light'
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'dark' || saved === 'light') return saved
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark'
    }
  } catch (e) {
    console.warn('Unable to access localStorage for theme:', e)
  }
  return 'light'
}

function applyThemeToDocument(theme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.setAttribute('data-theme', theme)
  if (theme === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

// Initialize theme on script load
const initialTheme = getInitialTheme()
applyThemeToDocument(initialTheme)

export const useThemeStore = create((set, get) => ({
  theme: initialTheme,

  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark'
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch (e) {
      console.warn('Unable to save theme to localStorage:', e)
    }
    applyThemeToDocument(next)
    set({ theme: next })
  },

  setTheme: (theme) => {
    if (theme !== 'dark' && theme !== 'light') return
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch (e) {
      console.warn('Unable to save theme to localStorage:', e)
    }
    applyThemeToDocument(theme)
    set({ theme })
  },
}))

if (typeof window !== 'undefined') {
  window.__workbenchSetTheme = (theme) => {
    useThemeStore.getState().setTheme(theme)
  }
}
