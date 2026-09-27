/**
 * PreviewUrlSync — the file viewer's place in the URL (?view=<file>&page=<n>).
 *
 * The viewer was in-memory state only, so the back button LEFT THE PAGE
 * instead of closing it, and a refresh closed it. Now:
 *
 *   open a file        -> a history entry is pushed (back closes it)
 *   another file/page  -> that entry is replaced (back still closes it)
 *   close (X / Esc)    -> the entry is popped, as if back had been pressed
 *   back / forward     -> the viewer follows the URL
 *   refresh            -> the file reopens, at its page
 *   leave the page     -> the viewer closes (the new page's URL has no view)
 *
 * Renders nothing. Mounted once, in App.
 */

import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { usePreviewStore } from '../../store/previewStore'

const keyOf = (file) =>
  file ? (typeof file === 'string' ? file : file.fullPath || file.relativePath || file.path || file.id || file.name || '') : ''

export function PreviewUrlSync() {
  const location = useLocation()
  const navigate = useNavigate()
  const file = usePreviewStore((s) => s.file)
  const isOpen = usePreviewStore((s) => s.isOpen)

  const params = new URLSearchParams(location.search)
  const urlView = params.get('view') || null
  const urlPage = Number(params.get('page')) || null
  const storeView = isOpen && file ? keyOf(file) || null : null
  const storePage = isOpen && file && typeof file === 'object' ? Number(file.page) || null : null

  // What each side said last time, so a change can be attributed to the
  // side that made it (and never echoed back into a loop).
  const last = useRef({ urlView: null, urlPage: null, storeView: null, storePage: null })

  useEffect(() => {
    const prev = last.current
    last.current = { urlView, urlPage, storeView, storePage }
    const urlMoved = urlView !== prev.urlView || urlPage !== prev.urlPage
    const storeMoved = storeView !== prev.storeView || storePage !== prev.storePage
    const inSync = urlView === storeView && (urlPage || null) === (storePage || null)
    if (inSync) return

    if (urlMoved && !storeMoved) {
      // back / forward / refresh / a link: the viewer follows the URL
      const store = usePreviewStore.getState()
      if (!urlView) {
        store.closePreview()
      } else {
        const name = urlView.split(/[/\\]/).pop()
        store.openPreview({ id: urlView, name, filename: name, relativePath: urlView, page: urlPage })
      }
      return
    }

    if (storeMoved) {
      const next = new URLSearchParams(location.search)
      if (storeView) {
        next.set('view', storeView)
        if (storePage) next.set('page', String(storePage))
        else next.delete('page')
        // a first open is a new place (back closes it); switching file or
        // page inside the open viewer is the same place
        navigate({ search: `?${next}` }, { replace: Boolean(prev.storeView), state: { viewer: true } })
      } else if (urlView) {
        // closed with X / Esc: undo the entry the open pushed, when there is one
        if (location.state?.viewer) {
          navigate(-1)
        } else {
          next.delete('view')
          next.delete('page')
          const q = next.toString()
          navigate({ search: q ? `?${q}` : '' }, { replace: true })
        }
      }
    }
  }, [urlView, urlPage, storeView, storePage]) // eslint-disable-line react-hooks/exhaustive-deps

  return null
}
