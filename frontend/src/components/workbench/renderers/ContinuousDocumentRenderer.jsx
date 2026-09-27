import { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { Loader2, AlertCircle, RotateCcw } from 'lucide-react'

// No client-side cache of render jobs: the backend answers an unchanged file
// from its disk cache in milliseconds, and knows when a file was edited --
// a Map here kept showing the old pages of an edited file until reload.
const POLL_MS = 350
const GIVE_UP_MS = 120000

// One page image. Until it loads it holds its space (so lazy loading loads
// only what is near the viewport, and the scrollbar does not jump); a page
// the backend cannot render says so, with a retry, instead of a broken icon.
function PageImage({ src, label, aspect, eager }) {
  const [state, setState] = useState('loading') // loading | ready | failed
  const [attempt, setAttempt] = useState(0)
  return (
    <div
      className="relative w-full rounded-lg shadow-md border overflow-hidden transition-colors duration-300"
      // White only once the page is there. White placeholders were the
      // "flash" on Open: a column of blank white slabs, then the pages.
      style={state === 'ready'
        ? { background: '#FFFFFF', borderColor: 'var(--color-border)' }
        : { aspectRatio: aspect, background: 'var(--color-overlay)', borderColor: 'var(--color-border)' }}
    >
      {state !== 'failed' && (
        <img
          key={attempt}
          src={attempt ? `${src}&retry=${attempt}` : src}
          alt={label}
          className="w-full h-auto object-contain block transition-opacity duration-300"
          style={{ opacity: state === 'ready' ? 1 : 0 }}
          loading={eager ? 'eager' : 'lazy'}
          decoding="async"
          onLoad={() => setState('ready')}
          onError={() => setState('failed')}
        />
      )}
      {state === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 animate-pulse" style={{ background: 'var(--color-overlay)' }}>
          <Loader2 size={18} className="animate-spin text-muted" />
          <span className="text-[10px] font-mono text-muted">Rendering {label}</span>
        </div>
      )}
      {state === 'failed' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center p-4" style={{ background: 'var(--color-overlay)' }}>
          <AlertCircle size={18} className="text-red-500" />
          <span className="text-xs text-muted">{label} could not be rendered.</span>
          <button
            type="button"
            onClick={() => { setState('loading'); setAttempt((a) => a + 1) }}
            className="flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded border cursor-pointer hover:bg-[var(--color-surface)]"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
          >
            <RotateCcw size={11} /> Try again
          </button>
        </div>
      )}
    </div>
  )
}

export function ContinuousDocumentRenderer({
  filePath,
  ext = 'pdf',
  zoomLevel = 100,
  initialPage = null,
  jumpToken = null,
  onPageChange,
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pageCount, setPageCount] = useState(1)
  const [previewBaseUrl, setPreviewBaseUrl] = useState(null)
  const [activePage, setActivePage] = useState(1)

  const containerRef = useRef(null)
  const pageRefs = useRef([])

  useEffect(() => {
    if (!filePath) return

    setLoading(true)
    setError(null)
    setActivePage(1)
    pageRefs.current = []

    let cancelled = false
    let timer = null
    const started = Date.now()

    const fail = (message) => {
      if (cancelled) return
      setError(message)
      setLoading(false)
    }

    // One request at a time: the next poll is scheduled only after the
    // previous answer, so a slow backend is never stacked with requests.
    const poll = (jobId) => {
      fetch(`/api/sandbox/render/${jobId}`)
        .then((r) => (r.ok ? r.json() : r.json().catch(() => ({})).then((d) => Promise.reject(new Error(d.detail || `HTTP ${r.status}`)))))
        .then((job) => {
          if (cancelled) return
          if (job.status === 'ready') {
            const count = Math.max(1, job.page_count || 1)
            setPreviewBaseUrl(`${job.preview_url}?v=${started}`)
            setPageCount(count)
            setLoading(false)
            if (onPageChange) onPageChange(1, count)
          } else if (job.status === 'failed') {
            fail(job.error || 'Sandboxed document conversion failed')
          } else if (Date.now() - started > GIVE_UP_MS) {
            fail('The document is still converting after two minutes. Close and reopen it to try again.')
          } else {
            timer = setTimeout(() => poll(jobId), POLL_MS)
          }
        })
        .catch((err) => fail(err.message || 'Error checking rendering job status'))
    }

    fetch('/api/sandbox/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().catch(() => ({})).then((d) => Promise.reject(new Error(d.detail || 'Render job submission failed')))
        }
        return res.json()
      })
      .then((data) => {
        if (!cancelled) poll(data.job_id)
      })
      .catch((err) => fail(err.message || 'Failed to submit document for rendering'))

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [filePath])

  // A citation opens the viewer AT its page: scroll there once the pages
  // exist, and again when another citation points into the same file
  // (jumpToken is the preview request, new on every click).
  useEffect(() => {
    if (loading || error || !initialPage || initialPage < 2) return
    const page = Math.min(initialPage, pageCount)
    const frame = requestAnimationFrame(() => {
      const el = pageRefs.current[page - 1]
      const container = containerRef.current
      if (el && container) {
        container.scrollTo({ top: el.offsetTop - container.offsetTop - 16, behavior: 'smooth' })
        setActivePage(page)
        if (onPageChange) onPageChange(page, pageCount)
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [loading, error, initialPage, pageCount, jumpToken]) // eslint-disable-line react-hooks/exhaustive-deps

  // Zoom keeps the page you are reading in view (it used to stay at the same
  // scroll offset, which is a different page once every page changes size).
  const lastZoom = useRef(zoomLevel)
  useLayoutEffect(() => {
    const container = containerRef.current
    const el = pageRefs.current[activePage - 1]
    if (lastZoom.current !== zoomLevel && container && el) {
      container.scrollTop = el.offsetTop - container.offsetTop - 16
    }
    lastZoom.current = zoomLevel
  }, [zoomLevel]) // eslint-disable-line react-hooks/exhaustive-deps

  // Continuous Scroll Intersection Observer for active page calculation
  useEffect(() => {
    if (loading || error || pageCount <= 1 || !previewBaseUrl) return

    const container = containerRef.current
    if (!container) return

    const handleScroll = () => {
      const pageElements = pageRefs.current.filter(Boolean)
      if (!pageElements.length) return

      const containerRect = container.getBoundingClientRect()
      const containerMid = containerRect.top + containerRect.height / 2

      let closestPage = 1
      let minDistance = Infinity

      pageElements.forEach((el, idx) => {
        const rect = el.getBoundingClientRect()
        const pageMid = rect.top + rect.height / 2
        const dist = Math.abs(pageMid - containerMid)
        if (dist < minDistance) {
          minDistance = dist
          closestPage = idx + 1
        }
      })

      if (closestPage !== activePage) {
        setActivePage(closestPage)
        if (onPageChange) {
          onPageChange(closestPage, pageCount)
        }
      }
    }

    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => container.removeEventListener('scroll', handleScroll)
  }, [loading, error, pageCount, previewBaseUrl, activePage, onPageChange])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-center min-h-[350px]">
        <Loader2 size={32} className="animate-spin text-[var(--color-accent)]" />
        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold">Generating Continuous Document View...</span>
          <span className="text-xs text-muted">
            Converting {ext.toUpperCase()} pages in isolated sandbox container
          </span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 gap-3 max-w-md mx-auto text-center rounded-xl border border-red-500/30 bg-red-500/5 my-8">
        <AlertCircle size={32} className="text-red-500" />
        <div className="flex flex-col gap-1">
          <span className="text-sm font-bold text-red-500">Document Conversion Failed</span>
          <p className="text-xs text-muted font-mono leading-relaxed">{error}</p>
        </div>
      </div>
    )
  }

  const pages = Array.from({ length: pageCount }, (_, i) => i + 1)
  const isPptx = ['pptx', 'ppt'].includes(ext.toLowerCase())
  const labelWord = isPptx ? 'Slide' : 'Page'

  const targetWidthPx = Math.max(350, Math.min(1400, Math.round(750 * (zoomLevel / 100))))

  return (
    <div
      ref={containerRef}
      className="flex-1 w-full h-full overflow-auto p-4 flex flex-col items-center gap-6 custom-scrollbar bg-[var(--color-bg)]"
    >
      {pages.map((pageNum) => (
        <div
          key={pageNum}
          ref={(el) => (pageRefs.current[pageNum - 1] = el)}
          className="flex flex-col items-center gap-2 group transition-all duration-150"
          style={{ width: `${targetWidthPx}px`, maxWidth: '100%' }}
        >
          <PageImage
            src={`${previewBaseUrl}&page=${pageNum}`}
            label={`${labelWord} ${pageNum}`}
            aspect={isPptx ? '16 / 9' : '1 / 1.414'}
            eager={pageNum <= 2}
          />

          {/* Bottom Page Label */}
          <span className="text-[10px] font-mono text-muted px-2 py-0.5 rounded bg-[var(--color-surface)] border border-[var(--color-border)] opacity-70 group-hover:opacity-100 transition-opacity">
            {labelWord} {pageNum} of {pageCount}
          </span>
        </div>
      ))}
    </div>
  )
}
