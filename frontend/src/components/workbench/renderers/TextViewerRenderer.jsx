import { useState, useEffect } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'

export function TextViewerRenderer({ filePath, zoomLevel = 100 }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [textContent, setTextContent] = useState('')

  useEffect(() => {
    if (!filePath) return
    setLoading(true)
    setError(null)

    fetch(`/api/sources/content?path=${encodeURIComponent(filePath)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to read text document`)
        return res.text()
      })
      .then((text) => {
        setTextContent(text)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message || 'Could not load file text')
        setLoading(false)
      })
  }, [filePath])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-center min-h-[300px]">
        <Loader2 size={32} className="animate-spin text-[var(--color-accent)]" />
        <span className="text-sm font-semibold">Loading Text Content...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 gap-3 max-w-md mx-auto text-center rounded-xl border border-red-500/30 bg-red-500/5 my-8">
        <AlertCircle size={32} className="text-red-500" />
        <span className="text-sm font-bold text-red-500">Read Error</span>
        <p className="text-xs text-muted font-mono">{error}</p>
      </div>
    )
  }

  const fontSize = Math.max(9, Math.round(12 * (zoomLevel / 100)))

  return (
    <div className="flex-1 w-full h-full overflow-auto p-4 custom-scrollbar bg-[var(--color-bg)]">
      <pre
        className="w-full min-h-full p-4 rounded-lg font-mono leading-relaxed overflow-auto whitespace-pre-wrap border border-[var(--color-border)] select-text"
        style={{
          background: 'var(--color-surface)',
          color: 'var(--color-text)',
          fontSize: `${fontSize}px`,
        }}
      >
        {textContent}
      </pre>
    </div>
  )
}
