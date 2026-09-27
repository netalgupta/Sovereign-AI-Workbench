import { useEffect, useState } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import { SafeHtmlFrame } from '../../common/SafeHtmlFrame'
import { TextViewerRenderer } from './TextViewerRenderer'

/**
 * An .html file, rendered (no network, no access to the app -- see
 * SafeHtmlFrame), with its source one click away. It used to open as
 * plain text only.
 */
export function HtmlPreviewRenderer({ filePath, zoomLevel = 100 }) {
  const [view, setView] = useState('rendered')
  const [html, setHtml] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!filePath) return
    let alive = true
    setHtml(null)
    setError(null)
    fetch(`/api/sources/content?path=${encodeURIComponent(filePath)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: the file could not be read`)
        return res.text()
      })
      .then((text) => alive && setHtml(text))
      .catch((err) => alive && setError(err.message))
    return () => {
      alive = false
    }
  }, [filePath])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center gap-1 px-3 py-2 border-b" style={{ borderColor: 'var(--color-border)' }}>
        {[['rendered', 'Rendered'], ['source', 'Source']].map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setView(id)}
            aria-pressed={view === id}
            className="px-2.5 py-1 rounded-md text-[11px] font-semibold cursor-pointer"
            style={{
              background: view === id ? 'var(--color-accent-tint)' : 'transparent',
              color: view === id ? 'var(--color-accent)' : 'var(--color-text-muted)',
            }}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
          Sandboxed: no network, no access to the app
        </span>
      </div>
      {view === 'source' ? (
        <TextViewerRenderer filePath={filePath} zoomLevel={zoomLevel} />
      ) : error ? (
        <div className="flex items-center gap-2 p-6 text-sm text-red-500"><AlertCircle size={16} /> {error}</div>
      ) : html == null ? (
        <div className="flex items-center justify-center gap-2 p-12 text-sm" style={{ color: 'var(--color-text-muted)' }}>
          <Loader2 size={18} className="animate-spin" /> Loading the page…
        </div>
      ) : (
        <div className="flex-1 min-h-0" style={{ zoom: zoomLevel / 100 }}>
          <SafeHtmlFrame html={html} title={`Rendered ${filePath}`} height="100%" />
        </div>
      )}
    </div>
  )
}
