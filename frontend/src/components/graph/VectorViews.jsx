import { useEffect, useRef, useState } from 'react'

/**
 * Canvas views over the embedding space.
 *
 * Canvas rather than SVG for both: the similarity heatmap is N² cells
 * (441 today, and quadratic in corpus size), which as SVG rects becomes
 * a DOM the browser struggles with well before the corpus becomes
 * interesting. The scatter is canvas for consistency with the graph and
 * because hit-testing points is simpler than managing hover handlers on
 * hundreds of nodes.
 *
 * Colours are read from CSS custom properties on every draw rather than
 * captured once, so both views follow a theme switch without a re-render.
 */

const cssVar = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

/** Stable colour per source document.
 *  Hue is derived from the document name rather than assignment order,
 *  so a document keeps its colour between the scatter and any other view
 *  and across reloads — a legend that reshuffles on every load is worse
 *  than no legend. */
function docColor(name, isDark) {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) % 360
  return `hsl(${hash} 58% ${isDark ? '62%' : '42%'})`
}

const prefersDark = () =>
  document.documentElement.getAttribute('data-theme') === 'dark' ||
  (!document.documentElement.getAttribute('data-theme') &&
    window.matchMedia('(prefers-color-scheme: dark)').matches)

export function VectorScatter({ chunks, pcaExplained = [], height = 380 }) {
  const canvasRef = useRef(null)
  const [hover, setHover] = useState(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !chunks?.length) return
    const ctx = canvas.getContext('2d')

    const draw = () => {
      const width = canvas.parentElement.clientWidth
      if (!width) return
      canvas.width = width * devicePixelRatio
      canvas.height = height * devicePixelRatio
      canvas.style.height = `${height}px`
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
      ctx.clearRect(0, 0, width, height)

      const isDark = prefersDark()
      const pad = 34
      const xs = chunks.map((c) => c.x)
      const ys = chunks.map((c) => c.y)
      const x0 = Math.min(...xs), x1 = Math.max(...xs)
      const y0 = Math.min(...ys), y1 = Math.max(...ys)
      const sx = (v) => pad + ((v - x0) / (x1 - x0 || 1)) * (width - pad * 2)
      const sy = (v) => height - pad - ((v - y0) / (y1 - y0 || 1)) * (height - pad * 2)

      ctx.strokeStyle = cssVar('--color-border', '#ddd')
      ctx.lineWidth = 1
      for (let i = 0; i <= 4; i++) {
        const gy = pad + ((height - pad * 2) * i) / 4
        const gx = pad + ((width - pad * 2) * i) / 4
        ctx.beginPath(); ctx.moveTo(pad, gy); ctx.lineTo(width - pad, gy); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(gx, pad); ctx.lineTo(gx, height - pad); ctx.stroke()
      }

      chunks.forEach((c) => {
        ctx.beginPath()
        ctx.arc(sx(c.x), sy(c.y), 6, 0, Math.PI * 2)
        ctx.fillStyle = docColor(c.source_document, isDark)
        ctx.fill()
        ctx.strokeStyle = cssVar('--color-bg', '#fff')
        ctx.lineWidth = 1.5
        ctx.stroke()
      })

      // Axes name the variance they carry. A projection that explains
      // 27% of variance is showing you a quarter of the story, and a
      // reader drawing conclusions from cluster distances deserves to
      // know that rather than infer it.
      ctx.font = '500 10px "IBM Plex Mono", ui-monospace, monospace'
      ctx.fillStyle = cssVar('--color-text-muted', '#888')
      ctx.textAlign = 'left'
      ctx.fillText(`PC1 · ${((pcaExplained[0] ?? 0) * 100).toFixed(1)}% of variance`, pad, height - 10)
      ctx.save()
      ctx.translate(12, height - pad)
      ctx.rotate(-Math.PI / 2)
      ctx.fillText(`PC2 · ${((pcaExplained[1] ?? 0) * 100).toFixed(1)}%`, 0, 0)
      ctx.restore()

      canvas.onmousemove = (e) => {
        const rect = canvas.getBoundingClientRect()
        const mx = e.clientX - rect.left
        const my = e.clientY - rect.top
        const hit = chunks.find((c) => (sx(c.x) - mx) ** 2 + (sy(c.y) - my) ** 2 < 64)
        setHover(hit ? { chunk: hit, x: mx, y: my } : null)
      }
      canvas.onmouseleave = () => setHover(null)
    }

    draw()
    window.addEventListener('resize', draw)
    return () => window.removeEventListener('resize', draw)
  }, [chunks, pcaExplained, height])

  return (
    <div className="relative">
      <canvas ref={canvasRef} className="block w-full" style={{ height }} />
      {hover && (
        <div className="absolute pointer-events-none rounded border px-2 py-1 text-[11px] leading-snug shadow"
             style={{ left: hover.x + 10, top: hover.y + 10, maxWidth: 240,
                      background: 'var(--color-bg)', borderColor: 'var(--color-border)',
                      color: 'var(--color-text)' }}>
          <b>{hover.chunk.source_document}</b><br />
          chunk {hover.chunk.chunk_index} · {hover.chunk.chars} chars
        </div>
      )}
    </div>
  )
}

export function SimilarityHeatmap({ similarity, chunks, height = 380 }) {
  const canvasRef = useRef(null)
  const [readout, setReadout] = useState(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !similarity?.length) return
    const ctx = canvas.getContext('2d')

    const draw = () => {
      const width = canvas.parentElement.clientWidth
      if (!width) return
      const n = similarity.length
      const size = Math.min(width - 8, height - 20)
      canvas.width = width * devicePixelRatio
      canvas.height = height * devicePixelRatio
      canvas.style.height = `${height}px`
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
      ctx.clearRect(0, 0, width, height)

      const cell = size / n
      const ox = (width - size) / 2
      const oy = 8
      const accent = cssVar('--color-accent', '#12798c')

      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          const v = similarity[i][j]
          // Stretch 0.3-1.0 across the ramp: cosine similarity between
          // any two chunks of one corpus rarely drops below ~0.3, so a
          // 0-1 ramp wastes most of its range and renders every cell the
          // same shade. Squaring sharpens the near-duplicates, which are
          // the cells worth finding.
          const t = Math.max(0, Math.min(1, (v - 0.3) / 0.7))
          ctx.globalAlpha = i === j ? 0.16 : t * t
          ctx.fillStyle = accent
          ctx.fillRect(ox + j * cell, oy + i * cell, Math.ceil(cell), Math.ceil(cell))
        }
      }
      ctx.globalAlpha = 1

      canvas.onmousemove = (e) => {
        const rect = canvas.getBoundingClientRect()
        const j = Math.floor((e.clientX - rect.left - ox) / cell)
        const i = Math.floor((e.clientY - rect.top - oy) / cell)
        if (i >= 0 && j >= 0 && i < n && j < n && i !== j) {
          setReadout({ value: similarity[i][j], a: chunks?.[i], b: chunks?.[j] })
        }
      }
      canvas.onmouseleave = () => setReadout(null)
    }

    draw()
    window.addEventListener('resize', draw)
    return () => window.removeEventListener('resize', draw)
  }, [similarity, chunks, height])

  return (
    <>
      <canvas ref={canvasRef} className="block w-full" style={{ height }} />
      <div className="text-[11px] mt-1 min-h-[2.5rem]" style={{ color: 'var(--color-text-muted)' }}>
        {readout ? (
          <>
            <b className="font-mono" style={{ color: 'var(--color-text)' }}>
              {readout.value.toFixed(3)}
            </b>{' '}cosine<br />
            {readout.a?.source_document} · {readout.a?.chunk_index} ↔{' '}
            {readout.b?.source_document} · {readout.b?.chunk_index}
          </>
        ) : (
          'Every chunk against every other. Bright off-diagonal cells are near-duplicates competing for the same queries.'
        )}
      </div>
    </>
  )
}
