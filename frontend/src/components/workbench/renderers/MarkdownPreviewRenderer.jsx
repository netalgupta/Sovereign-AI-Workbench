import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, AlertCircle } from 'lucide-react'

export function MarkdownPreviewRenderer({ filePath, zoomLevel = 100 }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [content, setContent] = useState('')

  useEffect(() => {
    if (!filePath) return
    setLoading(true)
    setError(null)

    fetch(`/api/sources/content?path=${encodeURIComponent(filePath)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Could not read markdown file`)
        return res.text()
      })
      .then((text) => {
        setContent(text)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message || 'Failed to load markdown content')
        setLoading(false)
      })
  }, [filePath])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-center min-h-[300px]">
        <Loader2 size={32} className="animate-spin text-[var(--color-accent)]" />
        <span className="text-sm font-semibold">Loading Markdown Document...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 gap-3 max-w-md mx-auto text-center rounded-xl border border-red-500/30 bg-red-500/5 my-8">
        <AlertCircle size={32} className="text-red-500" />
        <span className="text-sm font-bold text-red-500">Markdown Load Error</span>
        <p className="text-xs text-muted font-mono">{error}</p>
      </div>
    )
  }

  const fontScale = zoomLevel / 100

  return (
    <div className="flex-1 w-full h-full overflow-auto p-6 custom-scrollbar bg-[var(--color-bg)] select-text">
      <div
        className="max-w-3xl mx-auto space-y-4 text-[var(--color-text)] font-sans leading-relaxed"
        style={{ fontSize: `${14 * fontScale}px` }}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="text-2xl font-bold border-b border-[var(--color-border)] pb-2 pt-4 mt-2" style={{ color: 'var(--color-text)' }}>
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xl font-bold border-b border-[var(--color-border)] pb-1 pt-3 mt-4" style={{ color: 'var(--color-text)' }}>
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-lg font-semibold pt-2 mt-3" style={{ color: 'var(--color-text)' }}>
                {children}
              </h3>
            ),
            p: ({ children }) => <p className="leading-relaxed my-2">{children}</p>,
            ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-2 pl-2">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-2 pl-2">{children}</ol>,
            li: ({ children }) => <li className="my-0.5">{children}</li>,
            blockquote: ({ children }) => (
              <blockquote className="border-l-4 border-[var(--color-accent)] pl-4 py-1 italic my-3 text-muted bg-[var(--color-overlay)] rounded-r">
                {children}
              </blockquote>
            ),
            code: ({ inline, className, children }) => {
              if (inline) {
                return (
                  <code className="px-1.5 py-0.5 rounded font-mono text-xs bg-[var(--color-surface)] border border-[var(--color-border)] text-amber-500">
                    {children}
                  </code>
                )
              }
              return (
                <pre className="p-4 rounded-lg font-mono text-xs overflow-x-auto bg-[var(--color-surface)] border border-[var(--color-border)] my-3 text-[var(--color-text)]">
                  <code>{children}</code>
                </pre>
              )
            },
            table: ({ children }) => (
              <div className="overflow-x-auto my-4 border rounded-lg border-[var(--color-border)]">
                <table className="min-w-full border-collapse text-xs font-sans">{children}</table>
              </div>
            ),
            th: ({ children }) => (
              <th className="border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-left font-bold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border border-[var(--color-border)] px-3 py-2">{children}</td>
            ),
            hr: () => <hr className="my-6 border-[var(--color-border)]" />,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
