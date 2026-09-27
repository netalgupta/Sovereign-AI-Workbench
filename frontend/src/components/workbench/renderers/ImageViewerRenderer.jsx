import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'

/**
 * An image, zoomed by SIZE. It was zoomed with transform: scale(), which
 * does not change layout: a zoomed image spilled past the pane and its
 * edges could not be scrolled to. Now 100% fits the pane (never enlarging
 * a small image past its own size), larger zoom widens it and the pane
 * scrolls, and Ctrl + wheel / pinch zooms.
 */
export function ImageViewerRenderer({ filePath, name, zoomLevel = 100, onZoomDelta }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [natural, setNatural] = useState(null)
  const [pane, setPane] = useState({ w: 0, h: 0 })
  const paneRef = useRef(null)

  const directUrl = `/api/sources/content?path=${encodeURIComponent(filePath)}`

  useEffect(() => {
    setLoading(true)
    setError(false)
    setNatural(null)
  }, [filePath])

  useEffect(() => {
    const el = paneRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setPane({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setPane({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const el = paneRef.current
    if (!el || !onZoomDelta) return
    let acc = 0
    const onWheel = (e) => {
      if (!e.ctrlKey) return
      e.preventDefault()
      acc += e.deltaY
      if (Math.abs(acc) >= 40) {
        onZoomDelta(acc < 0 ? 25 : -25)
        acc = 0
      }
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [onZoomDelta])

  // Fit: the largest size that shows the whole image in the pane, never
  // bigger than the image itself.
  let width = null
  if (natural && pane.w) {
    const availW = Math.max(120, pane.w - 48)
    const availH = Math.max(120, pane.h - 48)
    const fit = Math.min(1, availW / natural.w, availH / natural.h)
    width = Math.round(natural.w * fit * (zoomLevel / 100))
  }

  return (
    <div ref={paneRef} className="flex-1 w-full h-full overflow-auto p-6 relative bg-[var(--color-bg)] custom-scrollbar">
      {loading && !error && (
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <Loader2 size={32} className="animate-spin text-[var(--color-accent)]" />
        </div>
      )}
      {error ? (
        <div className="text-center text-red-500 font-mono text-xs p-4">This image could not be loaded.</div>
      ) : (
        // A block with auto margins: centred when it fits, scrollable to
        // every edge when it does not (flex centring cut the left edge off).
        <img
          src={directUrl}
          alt={name || 'Image preview'}
          draggable={false}
          className="block rounded-lg shadow-lg border border-[var(--color-border)] transition-opacity duration-200"
          style={{
            width: width ?? undefined,
            maxWidth: width ? 'none' : '100%',
            height: 'auto',
            margin: '0 auto',
            opacity: loading ? 0 : 1,
            background: loading ? 'transparent' : '#FFFFFF',
          }}
          onLoad={(e) => {
            setNatural({ w: e.currentTarget.naturalWidth || 1, h: e.currentTarget.naturalHeight || 1 })
            setLoading(false)
          }}
          onError={() => {
            setLoading(false)
            setError(true)
          }}
        />
      )}
    </div>
  )
}
