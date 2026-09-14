import { create } from 'zustand'

let pollTimer = null

export const useIngestionStore = create((set, get) => ({
  activeJob: null,
  // fileStatuses: { [filename]: { stage: 'extracting'|'chunking'|'embedding'|'indexing'|'indexed'|'failed', chunks: number, seconds: number, completedAt: number | null } }
  fileStatuses: {},

  startTracking: (jobId) => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }

    set({
      activeJob: {
        job_id: jobId,
        state: 'running',
        total_documents: 0,
        completed: 0,
        documents: [],
        current_document: null,
      },
    })

    let notFoundStreak = 0
    const MAX_NOT_FOUND = 5 // allow a few misses before giving up

    const poll = async () => {
      try {
        const res = await fetch(`/api/ingestion/${jobId}`)
        if (!res.ok) {
          if (res.status === 404) {
            notFoundStreak++
            // After MAX_NOT_FOUND consecutive 404s, the job is truly gone
            if (notFoundStreak >= MAX_NOT_FOUND) {
              if (pollTimer) {
                clearInterval(pollTimer)
                pollTimer = null
              }
              setTimeout(() => {
                set((state) => ({
                  activeJob: state.activeJob?.job_id === jobId ? null : state.activeJob,
                  fileStatuses: {},
                }))
              }, 1000)
            }
          }
          return
        }
        // Got a real response — reset the streak
        notFoundStreak = 0
        const data = await res.json()
        const now = Date.now()

        const currentStatuses = { ...get().fileStatuses }
        if (Array.isArray(data.documents)) {
          data.documents.forEach((doc) => {
            const existing = currentStatuses[doc.name]
            const isDone = doc.stage === 'indexed' || doc.stage === 'failed' || doc.stage === 'skipped'
            currentStatuses[doc.name] = {
              stage: doc.stage,
              chunks: doc.chunks,
              seconds: doc.seconds,
              detail: doc.detail,
              completedAt: isDone ? (existing?.completedAt || now) : null,
            }
          })
        }

        // Prune completed items after 3.5s
        Object.keys(currentStatuses).forEach((name) => {
          const item = currentStatuses[name]
          if (item.completedAt && now - item.completedAt > 3500) {
            delete currentStatuses[name]
          }
        })

        set({
          activeJob: data,
          fileStatuses: currentStatuses,
        })

        if (data.state === 'complete' || data.state === 'failed') {
          if (pollTimer) {
            clearInterval(pollTimer)
            pollTimer = null
          }
          // After 3.5s, clear the active job indicator
          setTimeout(() => {
            set((state) => ({
              activeJob: state.activeJob?.job_id === jobId ? null : state.activeJob,
              fileStatuses: {},
            }))
          }, 3500)
        }
      } catch (err) {
        console.warn('Failed to poll ingestion status:', err)
      }
    }

    poll()
    pollTimer = setInterval(poll, 450)
  },

  stopTracking: () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  },

  clearJob: () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    set({ activeJob: null, fileStatuses: {} })
  },
}))

if (typeof window !== 'undefined') {
  window.__ingestionStore = useIngestionStore
}

