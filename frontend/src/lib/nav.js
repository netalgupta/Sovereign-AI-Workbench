/**
 * nav.js — where the operator is, as a URL.
 *
 * The URL is the one record of place: back, forward and refresh (and, in
 * the Electron shell, Alt+Left and the mouse's back button) all read it.
 *
 *   /                                   Home
 *   /chat/<sessionId>                   a chat
 *   /chat/<sessionId>?tab=notebooks     ... its Notebooks tab (or artifacts)
 *   ...&view=<file>&page=<n>            ... with a file open in the viewer
 *
 * Before this, every chat was "/workbench", the tab and the viewer were
 * in-memory state, and back skipped over all of them.
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

export const CHAT_TABS = ['chat', 'notebooks', 'artifacts']

export function chatPath(sessionId, tab = 'chat') {
  const base = `/chat/${encodeURIComponent(sessionId)}`
  return tab && tab !== 'chat' ? `${base}?tab=${tab}` : base
}

/**
 * "Back" means where the operator came from, inside this app. Opened
 * directly (a first page, nothing to go back to), it goes to `fallback`.
 * The Sources and Settings back links always went Home.
 */
export function useGoBack(fallback = '/') {
  const navigate = useNavigate()
  return useCallback(() => {
    const idx = window.history.state?.idx
    if (typeof idx === 'number' && idx > 0) navigate(-1)
    else navigate(fallback, { replace: true })
  }, [navigate, fallback])
}
