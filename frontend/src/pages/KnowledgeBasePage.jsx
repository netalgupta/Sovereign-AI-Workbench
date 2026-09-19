import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, FileText, Image as ImageIcon, X } from 'lucide-react'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'

// ---------------------------------------------------------------------------
// SourcePreview — renders the exact PDF page via GET /api/preview
// Claude-app style: the user's own document at the exact cited location.
// ---------------------------------------------------------------------------
function SourcePreview({ doc, page, onClose }) {
  const [state, setState] = useState('loading')  // 'loading' | 'iframe' | 'error'

  // Build preview URL — /api/preview returns an inline PDF page render
  const previewUrl = `/api/preview?doc=${encodeURIComponent(doc)}&page=${page ?? 1}`

  return (
    <div
      className="flex flex-col border-l h-full min-h-0"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 border-b text-xs flex-shrink-0"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <FileText size={13} style={{ color: 'var(--color-accent)', flexShrink: 0 }} />
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate" style={{ color: 'var(--color-text)' }}>
            {doc}
          </div>
          <div style={{ color: 'var(--color-text-muted)' }}>
            Page {page ?? 1}
          </div>
        </div>
        <a
          href={previewUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="p-1 rounded"
          style={{ color: 'var(--color-text-muted)' }}
          title="Open in new tab"
        >
          <ExternalLink size={12} />
        </a>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded"
          style={{ color: 'var(--color-text-muted)' }}
        >
          <X size={13} />
        </button>
      </div>

      {/* Preview frame */}
      <div className="flex-1 relative min-h-0">
        {state === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Spinner />
          </div>
        )}
        {state === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center p-4">
            <EmptyState
              icon={FileText}
              title="Preview unavailable"
              description={`Backend /api/preview endpoint not reachable. Start the backend to see the source PDF at page ${page ?? 1}.`}
            />
          </div>
        )}
        <iframe
          src={previewUrl}
          title={`${doc} page ${page}`}
          className="w-full h-full border-0"
          style={{ display: state === 'iframe' ? 'block' : 'none' }}
          onLoad={() => setState('iframe')}
          onError={() => setState('error')}
        />
      </div>
    </div>
  )
}

/**
 * KnowledgeBasePage — what the retriever actually holds (FRONTEND.md §2, /sources).
 *
 * Three panels:
 *   Chunks — exact post-chunking text + nearest neighbours in embedding space.
 *   Images — every image the pipeline touched + OCR/chart understanding.
 *   [Source preview sidebar] — PDF page at the exact cited location, Claude-app style.
 *     Opens automatically when you click a chunk that has a source_document + page_number.
 */
export function KnowledgeBasePage() {
  const [tab, setTab] = useState('chunks')
  const [chunks, setChunks] = useState(null)
  const [images, setImages] = useState(null)
  const [error, setError] = useState(null)
  const [selectedChunk, setSelectedChunk] = useState(0)
  const [selectedImage, setSelectedImage] = useState(null)
  const [filter, setFilter] = useState('')
  // Source preview sidebar
  const [preview, setPreview] = useState(null)   // { doc, page } | null

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetch('/pipeline/chunks.json').then((r) => r.json()),
      fetch('/pipeline/images.json').then((r) => r.json()).catch(() => []),
    ])
      .then(([c, i]) => {
        if (cancelled) return
        setChunks(c)
        setImages(i)
        // Open on the image that demonstrates the failure mode, if there is
        // one — the page should surface what it found, not item zero.
        const worst = i.find((im) => im.scored?.fabricated_value_count > 0)
        setSelectedImage(worst?.filename ?? i[0]?.filename ?? null)
      })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [])

  const visibleChunks = useMemo(() => {
    if (!chunks) return []
    const f = filter.toLowerCase()
    return chunks.chunks.filter(
      (c) => !f || c.text.toLowerCase().includes(f) || c.source_document.toLowerCase().includes(f),
    )
  }, [chunks, filter])

  const neighbours = useMemo(() => {
    if (!chunks) return []
    const row = chunks.similarity[selectedChunk]
    if (!row) return []
    return row
      .map((v, i) => ({ v, i }))
      .filter((o) => o.i !== selectedChunk)
      .sort((a, b) => b.v - a.v)
      .slice(0, 5)
  }, [chunks, selectedChunk])

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <EmptyState
          icon={FileText}
          title="Corpus snapshot unavailable"
          description={`Could not load /pipeline/chunks.json (${error}). Export it with: python -m backend.evaluation.export_frontend_assets`}
        />
      </div>
    )
  }
  if (!chunks) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <Spinner />
      </div>
    )
  }

  const chunk = chunks.chunks[selectedChunk]
  const image = images?.find((i) => i.filename === selectedImage)
  const fabricated = image?.scored?.fabricated_value_count ?? null
  const labelsPrinted = image?.ground_truth?.has_printed_labels

  const tabBtn = (id, label, count) => (
    <button
      key={id}
      type="button"
      onClick={() => setTab(id)}
      className="px-3 py-1.5 text-xs font-medium rounded-md border"
      style={{
        background: tab === id ? 'var(--color-accent-soft, var(--color-bg-subtle))' : 'transparent',
        borderColor: tab === id ? 'var(--color-accent)' : 'var(--color-border)',
        color: tab === id ? 'var(--color-accent)' : 'var(--color-text-muted)',
      }}
    >
      {label} <span className="font-mono opacity-70">{count}</span>
    </button>
  )

  return (
    <div className="flex-1 flex flex-col min-h-0" style={{ background: 'var(--color-bg)' }}>
      <header className="flex items-center gap-3 flex-wrap px-5 py-3 border-b"
              style={{ borderColor: 'var(--color-border)' }}>
        <div className="mr-auto">
          <h1 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            Knowledge base
          </h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {chunks.chunks.length} chunks at {chunks.chunking.chunk_size_tokens}/
            {chunks.chunking.chunk_overlap_tokens} tokens · {chunks.embedding_dim}-dim embeddings
          </p>
        </div>
        {tabBtn('chunks', 'Chunks', chunks.chunks.length)}
        {tabBtn('images', 'Images', images?.length ?? 0)}
      </header>

      {tab === 'chunks' ? (
        <div
          className="flex-1 grid min-h-0"
          style={{
            gridTemplateColumns: preview
              ? '320px 1fr 380px'
              : '320px 1fr',
          }}
        >
          <div className="border-r overflow-y-auto" style={{ borderColor: 'var(--color-border)' }}>
            <div className="p-2 sticky top-0" style={{ background: 'var(--color-bg)' }}>
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter chunks…"
                aria-label="Filter chunks"
                className="w-full px-2.5 py-1.5 text-xs rounded-md border outline-none"
                style={{
                  background: 'var(--color-bg-subtle)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
            </div>
            <ul className="p-2 pt-0 space-y-1">
              {visibleChunks.map((c) => (
                <li key={c.index}>
                   <button
                    type="button"
                    onClick={() => {
                      setSelectedChunk(c.index)
                      // Open the source preview at the cited page if available
                      if (c.source_document) {
                        setPreview({ doc: c.source_document, page: c.page_number ?? 1 })
                      }
                    }}
                    className="w-full text-left px-2.5 py-2 rounded-md border"
                    style={{
                      background: c.index === selectedChunk
                        ? 'var(--color-accent-soft, var(--color-bg-subtle))' : 'transparent',
                      borderColor: c.index === selectedChunk
                        ? 'var(--color-accent)' : 'transparent',
                    }}
                  >
                    <div className="flex justify-between gap-2 items-baseline">
                      <span className="text-xs font-semibold truncate"
                            style={{ color: 'var(--color-text)' }}>
                        {c.source_document}
                      </span>
                      <span className="font-mono text-[10px] shrink-0"
                            style={{ color: 'var(--color-text-muted)' }}>
                        #{c.chunk_index}
                      </span>
                    </div>
                    <p className="text-[11px] mt-1 line-clamp-2"
                       style={{ color: 'var(--color-text-muted)' }}>
                      {c.text.slice(0, 120)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="overflow-y-auto p-5">
            <div className="flex flex-wrap gap-2 mb-3">
              {[
                ['type', chunk.document_type],
                ['chunk', chunk.chunk_index],
                ['page', chunk.page_number ?? '—'],
                ['chars', chunk.chars],
              ].map(([k, v]) => (
                <span key={k} className="font-mono text-[11px] px-2 py-0.5 rounded border"
                      style={{
                        background: 'var(--color-bg-subtle)',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text-muted)',
                      }}>
                  {k} <b style={{ color: 'var(--color-text)' }}>{v}</b>
                </span>
              ))}
            </div>
            <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words p-3.5 rounded-md"
                 style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
              {chunk.text}
            </pre>

            <h3 className="mt-5 mb-2 text-[10px] uppercase tracking-wider"
                style={{ color: 'var(--color-text-muted)' }}>
              Nearest neighbours in embedding space
            </h3>
            {neighbours.map((o) => (
              <div key={o.i} className="font-mono text-[11px] py-1 border-b"
                   style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
                <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
                  {o.v.toFixed(3)}
                </span>{' '}
                {chunks.chunks[o.i].source_document} · #{chunks.chunks[o.i].chunk_index}
              </div>
            ))}
          </div>

          {/* Source preview panel — 3rd column when open */}
          {preview && (
            <SourcePreview
              doc={preview.doc}
              page={preview.page}
              onClose={() => setPreview(null)}
            />
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-5">
          {!images?.length ? (
            <EmptyState
              icon={ImageIcon}
              title="No image snapshot"
              description="Run: python -m backend.evaluation.export_image_data"
            />
          ) : (
            <>
              <div className="grid gap-3 mb-5"
                   style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))' }}>
                {images.map((im) => (
                  <button
                    key={im.filename}
                    type="button"
                    onClick={() => setSelectedImage(im.filename)}
                    className="text-left rounded-lg border overflow-hidden"
                    style={{
                      borderColor: im.filename === selectedImage
                        ? 'var(--color-accent)' : 'var(--color-border)',
                      background: 'var(--color-bg-subtle)',
                    }}
                  >
                    <img src={im.data_uri} alt={im.filename}
                         className="w-full h-28 object-cover object-top bg-white" loading="lazy" />
                    <div className="p-2">
                      <p className="text-[11px] font-semibold truncate"
                         style={{ color: 'var(--color-text)' }}>{im.filename}</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {im.ocr_text && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold"
                                style={{ background: 'var(--color-bg)', color: 'var(--color-text-muted)' }}>
                            OCR
                          </span>
                        )}
                        {im.scored?.fabricated_value_count > 0 && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold text-white"
                                style={{ background: 'var(--color-danger, #a63927)' }}>
                            {im.scored.fabricated_value_count} INVENTED
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {image && (
                <div className="rounded-lg border p-4 grid gap-5 lg:grid-cols-2"
                     style={{ borderColor: 'var(--color-border)' }}>
                  <img src={image.data_uri} alt={image.filename}
                       className="w-full rounded-md border bg-white"
                       style={{ borderColor: 'var(--color-border)' }} />
                  <div className="min-w-0">
                    {fabricated > 0 ? (
                      <p className="flex gap-2 text-xs leading-relaxed p-2.5 rounded-r-md mb-3"
                         style={{
                           borderLeft: '3px solid var(--color-danger, #a63927)',
                           background: 'var(--color-bg-subtle)',
                           color: 'var(--color-text)',
                         }}>
                        <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                        <span>
                          <b>{fabricated} value(s) invented.</b> This chart carries no printed
                          numbers, yet the model stated specific figures — read off bar heights.
                          Treat everything below as an estimate, never a measurement.
                        </span>
                      </p>
                    ) : labelsPrinted === false ? (
                      <p className="flex gap-2 text-xs leading-relaxed p-2.5 rounded-r-md mb-3"
                         style={{
                           borderLeft: '3px solid var(--color-success, #2f7a52)',
                           background: 'var(--color-bg-subtle)',
                           color: 'var(--color-text)',
                         }}>
                        <CheckCircle2 size={15} className="shrink-0 mt-0.5" />
                        <span><b>Clean.</b> No printed numbers, and none invented.</span>
                      </p>
                    ) : null}

                    {image.vision_description && (
                      <>
                        <h3 className="text-[10px] uppercase tracking-wider mb-1.5 flex items-center gap-2"
                            style={{ color: 'var(--color-text-muted)' }}>
                          Chart reading
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold"
                                style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-accent)' }}>
                            ESTIMATE
                          </span>
                        </h3>
                        <pre className="font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words p-3 rounded-md max-h-64 overflow-y-auto mb-4"
                             style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                          {image.vision_description.trim()}
                        </pre>
                      </>
                    )}

                    {image.ocr_text && (
                      <>
                        <h3 className="text-[10px] uppercase tracking-wider mb-1.5"
                            style={{ color: 'var(--color-text-muted)' }}>
                          OCR text — indexed into the corpus
                        </h3>
                        <pre className="font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words p-3 rounded-md max-h-64 overflow-y-auto"
                             style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                          {image.ocr_text.trim()}
                        </pre>
                      </>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
