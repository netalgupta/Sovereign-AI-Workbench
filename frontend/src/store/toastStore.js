import { create } from 'zustand'

export const useToastStore = create((set, get) => ({
  toasts: [],

  addToast: (message, type = 'info', duration = 3000) => {
    const id = Date.now().toString() + Math.random().toString(36).slice(2, 6)
    const toast = { id, message, type }
    set((state) => ({ toasts: [...state.toasts, toast] }))

    if (duration > 0) {
      setTimeout(() => {
        get().removeToast(id)
      }, duration)
    }
  },

  removeToast: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
  },
}))

export const showToast = (message, type = 'info', duration = 3000) => {
  useToastStore.getState().addToast(message, type, duration)
}
