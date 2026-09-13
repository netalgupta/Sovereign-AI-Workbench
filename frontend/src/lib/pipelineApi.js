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
    // If backend on API_BASE is down, try same-origin relative API path (e.g. Vite dev middleware)
    if (API_BASE && API_BASE !== '') {
      try {
        const response = await fetch(apiPath)
        if (response.ok) {
          const data = await response.json()
          return { ...shape(data), source: data.source ?? 'api', live: true }
        }
      } catch {}
    }

    // EXPORTED SNAPSHOTS ARE OFF BY DEFAULT.
    //
    // /pipeline/*.json are exports of a corpus as it stood when someone
    // last ran export_frontend_assets.py. They are real data, and they
    // are dated -- graph.json and chunks.json are committed, so every
    // clone carries one machine's corpus from one moment.
    //
    // The old behaviour fell back to them silently whenever the backend
    // was unreachable, labelling the result `source: 'snapshot'`. The
    // label is correct and it is not enough: /sources and /graph then
    // render a full, plausible knowledge base, and the only thing
    // separating that from the live system is one small badge. A judge
    // looking at a populated graph while the backend is down is being
    // shown a different machine's data.
    //
    // So the default is now an honest empty state that says the backend
    // is unreachable. Set VITE_ALLOW_SNAPSHOTS=true to get the old
    // behaviour deliberately -- useful for frontend work with no
    // backend running, which is the only case it was ever good for.
    const allowSnapshots =
      import.meta.env?.VITE_ALLOW_SNAPSHOTS === 'true' ||
      (typeof window !== 'undefined' && window.__ALLOW_PIPELINE_SNAPSHOTS === true)

    if (!snapshotPath || !allowSnapshots) {
      return {
        ...shape({}),
        source: 'unavailable',
        live: false,
        unavailableReason:
          'The backend is not reachable. Nothing is shown from an exported ' +
          'snapshot, because a snapshot is another machine\'s corpus at ' +
          'another moment and would be indistinguishable from live data here.',
      }
    }
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
      // NORMALISED, because the live API and the exported snapshot do
      // not agree on field names and the UI was written against the
      // snapshot.
      //
      //   snapshot: filename, data_uri, size_kb, vision_description
      //   live API: image_id, url,      byte_size, description
      //
      // The Images tab rendered a blank page on every click for that
      // reason -- currentImage.filename.endsWith('.png') on a payload
      // with no `filename` throws a TypeError, React unmounts the tree,
      // and the user sees nothing at all with no error on screen.
      //
      // Normalising here rather than at each of the ~15 render sites
      // means a future field rename breaks one function instead of
      // silently blanking a page again.
      images: ((Array.isArray(d) ? d : d.images) ?? []).map((im) => ({
        ...im,
        filename: im.filename ?? im.image_id ?? 'image',
        size_kb:
          im.size_kb ??
          (typeof im.byte_size === 'number'
            ? Math.round(im.byte_size / 1024)
            : undefined),
        vision_description: im.vision_description ?? im.description,
        // The live API flags an estimate on its own field; the UI reads
        // ground_truth. An estimate labelled as measured is the one
        // thing this must not lose (CHART_STRESS_REPORT.md).
        description_is_estimate:
          im.description_is_estimate ?? im.scored?.is_estimate ?? false,
      })),
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
