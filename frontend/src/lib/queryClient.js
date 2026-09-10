import { QueryClient } from '@tanstack/react-query'

/**
 * queryClient.js — Single shared QueryClient instance.
 *
 * Configuration rationale:
 * - refetchOnWindowFocus: false — this is a local desktop app, not a SaaS
 *   dashboard. Window focus should never trigger unexpected re-fetches.
 * - retry: 0 for mutations — a failed send should surface immediately,
 *   not silently retry and confuse the user about whether it was sent.
 * - retry: 1 for queries — a single retry is acceptable for idempotent reads.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000 * 60 * 5, // 5 minutes — fine for local data
    },
    mutations: {
      retry: 0,
    },
  },
})
