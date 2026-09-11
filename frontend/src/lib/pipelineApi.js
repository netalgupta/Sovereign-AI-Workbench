/**
 * Client for the workbench backend.
 *
 * Every call goes to the local API first and falls back to the static
 * snapshots under /pipeline/ if the backend is not running. That
 * fallback is not politeness — the frontend and backend are separate
 * processes a developer starts separately, and a UI that shows nothing
 * but a connection error when one of them is down is useless exactly
 * when you are trying to work out which one is down.
 *
 * Every result carries `source` ('api' | 'snapshot') so the UI can say
 * which it is showing. A dashboard presenting a stale export as live
 * data is the same class of mistake as a citation pointing at a
 * document that has since been edited.
 */

const API_BASE = import.meta.env?.VITE_API_BASE ?? 'http://127.0.0.1:8000'

async function tryApi(path, options) {
  const controller = new AbortController()
  // Short timeout: this is localhost. If it has not answered in two
  // seconds the backend is not running, and waiting longer just delays
  // the fallback that is going to happen anyway.
  const timer = setTimeout(() => controller.abort(), 2000)
  try {
    const response = await fetch(`${API_BASE}${path}`, { ...options, signal: controller.signal })
    if (!response.ok) throw new Error(`${path} -> ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timer)
  }
}

async function withFallback(apiPath, snapshotPath, shape = (d) => d) {
  try {
    const data = await tryApi(apiPath)
    return { ...shape(data), source: data.source ?? 'api', live: true }
  } catch {
    if (!snapshotPath) return { ...shape({}), source: 'unavailable', live: false }
    try {
      const response = await fetch(snapshotPath)
      if (!response.ok) throw new Error('no snapshot')
      const data = await response.json()
      return { ...shape(data), source: 'snapshot', live: false }
    } catch {
      return { ...shape({}), source: 'unavailable', live: false }
    }
  }
}

export const api = {
  base: API_BASE,

  health: () => tryApi('/api/health').catch(() => null),

  graph: () =>
    withFallback('/api/graph', '/pipeline/graph.json', (d) => ({
      nodes: d.nodes ?? [],
      relationships: d.relationships ?? [],
      warning: d.warning ?? null,
    })),

  chunks: () =>
    withFallback('/api/chunks', '/pipeline/chunks.json', (d) => ({
      chunks: d.chunks ?? [],
      similarity: d.similarity ?? [],
      chunking: d.chunking ?? null,
      embeddingDim: d.embedding_dim ?? null,
      pcaExplained: d.pca_explained_variance ?? [],
    })),

  images: () =>
    withFallback('/api/images', '/pipeline/images.json', (d) => ({
      images: (Array.isArray(d) ? d : d.images) ?? [],
    })),

  metrics: () => tryApi('/api/metrics').catch(() => null),

  sources: () => tryApi('/api/sources').catch(() => null),

  addSource: (path, recursive = true) =>
    tryApi('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, recursive }),
    }),

  scanSources: () => tryApi('/api/sources/scan', { method: 'POST' }),

  search: (query, topK = 5) =>
    tryApi('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: topK }),
    }),

  selectImage: (request, imageIds = [], topK = 1) =>
    tryApi('/api/images/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request, image_ids: imageIds, top_k: topK }),
    }),

  /** Resolve an image to something an <img src> can use.
   *  Live images stream from the API; snapshot images already carry a
   *  base64 data URI, so both shapes work without the caller caring. */
  imageSrc: (image) => image.data_uri ?? `${API_BASE}${image.url ?? ''}`,

  previewUrl: (document, page, highlight) => {
    const params = new URLSearchParams({ document, page: String(page) })
    if (highlight) params.set('highlight', highlight.slice(0, 400))
    return `${API_BASE}/api/preview?${params}`
  },
}
