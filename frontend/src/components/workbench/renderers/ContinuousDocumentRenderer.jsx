import { useState, useEffect, useRef } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'

// Simple in-memory cache for render jobs to prevent re-fetching on toggle
const renderCache = new Map()

export function ContinuousDocumentRenderer({
  filePath,
  ext = 'pdf',
  zoomLevel = 100,
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

    let cancelled = false

    const cacheKey = filePath
    if (renderCache.has(cacheKey)) {
      const cached = renderCache.get(cacheKey)
      setPreviewBaseUrl(cached.preview_url)
      setPageCount(cached.page_count || 1)
      setLoading(false)
      if (onPageChange) onPageChange(1, cached.page_count || 1)
      return
    }

    // Submit document for sandbox conversion
    fetch('/api/sandbox/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((d) => Promise.reject(new Error(d.detail || 'Render job submission failed')))
        }
        return res.json()
      })
      .then((data) => {
        if (cancelled) return
        const jobId = data.job_id

        const pollInterval = setInterval(() => {
          if (cancelled) {
            clearInterval(pollInterval)
            return
          }
          fetch(`/api/sandbox/render/${jobId}`)
            .then((r) => r.json())
            .then((job) => {
              if (cancelled) return
              if (job.status === 'ready') {
                clearInterval(pollInterval)
                const count = Math.max(1, job.page_count || 1)
                setPreviewBaseUrl(job.preview_url)
                setPageCount(count)
                setLoading(false)
                renderCache.set(cacheKey, job)

                if (onPageChange) onPageChange(1, count)
              } else if (job.status === 'failed') {
                clearInterval(pollInterval)
                setError(job.error || 'Sandboxed document conversion failed')
                setLoading(false)
              }
            })
            .catch((err) => {
              clearInterval(pollInterval)
              if (!cancelled) {
                setError(err.message || 'Error checking rendering job status')
                setLoading(false)
              }
            })
        }, 400)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message || 'Failed to submit document for rendering')
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [filePath])

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
          {/* Page Image */}
          <div className="relative w-full rounded-lg shadow-md border overflow-hidden bg-white">
            <img
              src={`${previewBaseUrl}?page=${pageNum}`}
              alt={`${labelWord} ${pageNum}`}
              className="w-full h-auto object-contain block bg-white"
              loading={pageNum <= 3 ? 'eager' : 'lazy'}
            />
          </div>

          {/* Bottom Page Label */}
          <span className="text-[10px] font-mono text-muted px-2 py-0.5 rounded bg-[var(--color-surface)] border border-[var(--color-border)] opacity-70 group-hover:opacity-100 transition-opacity">
            {labelWord} {pageNum} of {pageCount}
          </span>
        </div>
      ))}
    </div>
  )
}
