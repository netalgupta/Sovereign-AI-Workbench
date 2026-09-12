/**
 * graphApi.js — All graph-related backend calls in one place.
 *
 * Two endpoints:
 *   GET /api/graph                              — full graph dump (nodes + relationships)
 *   GET /api/graph/neighbourhood?node=X&hops=N — ego-subgraph starting at node X,
 *                                                 N hops out, with per-hop histogram
 *
 * Both fall back gracefully:
 *  - If /api/graph fails → try the static /pipeline/graph.json snapshot
 *  - If /api/graph/neighbourhood fails → derive the neighbourhood client-side
 *    from whichever graph data we already have (static or live)
 *
 * The neighbourhood endpoint is specifically designed for hop-by-hop reveal:
 * every node in the response carries a `distance` integer, and the response
 * includes a `by_distance` histogram so the UI can reveal nodes at distance 0
 * first, then 1, then 2, etc. — not a hairball dump all at once.
 *
 * GRAPH_SPEC.md §6 signature demo: 'Mangalore-Hassan', hops=2
 * Verified result: 8 nodes, 18 edges, {'0':1,'1':2,'2':5}
 */

const GRAPH_API   = '/api/graph'
const NEIGHBOURHOOD_API = '/api/graph/neighbourhood'
const STATIC_SNAPSHOT   = '/pipeline/graph.json'

const FETCH_TIMEOUT_MS = 4000

async function fetchWithTimeout(url, opts = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetch(url, { ...opts, signal: ctrl.signal })
    clearTimeout(timer)
    return res
  } catch (err) {
    clearTimeout(timer)
    throw err
  }
}

// ---------------------------------------------------------------------------
// Full graph
// ---------------------------------------------------------------------------

/**
 * Fetch the full knowledge graph.
 * Returns { nodes, relationships, source: 'live' | 'snapshot' }
 * Throws if both the live endpoint and the static snapshot fail.
 */
export async function fetchFullGraph() {
  // 1. Try live API
  try {
    const res = await fetchWithTimeout(GRAPH_API)
    if (res.ok) {
      const data = await res.json()
      if (data?.nodes?.length > 0) {
        return { ...data, source: 'live' }
      }
      // 0-node response — graph container probably lost its data
      console.warn(
        '[graphApi] /api/graph returned 0 nodes. ' +
        'Run: py -3 -m backend.evaluation.build_graph'
      )
      // Fall through to snapshot so the UI still renders something
    }
  } catch (err) {
    if (err?.name !== 'AbortError') {
      console.warn('[graphApi] /api/graph unreachable:', err?.message)
    }
  }

  // 2. Fall back to static snapshot
  const snap = await fetchWithTimeout(STATIC_SNAPSHOT)
  if (snap.ok) {
    const data = await snap.json()
    return { ...data, source: 'snapshot' }
  }

  throw new Error(
    'Graph unavailable: /api/graph returned no nodes and /pipeline/graph.json is missing. ' +
    'Rebuild with: py -3 -m backend.evaluation.build_graph'
  )
}

// ---------------------------------------------------------------------------
// Neighbourhood / ego-subgraph
// ---------------------------------------------------------------------------

/**
 * Fetch the N-hop neighbourhood of `nodeId`.
 *
 * Live response shape (from the backend):
 *   {
 *     nodes:        [{ id, labels, properties, distance }],
 *     edges:        [{ source, target, type }],
 *     by_distance:  { '0': 1, '1': 2, '2': 5 },
 *   }
 *
 * Falls back to client-side BFS over `fallbackGraph` when the endpoint is
 * unreachable (e.g. backend down, frontend-only dev session).
 *
 * @param {string} nodeId
 * @param {number} hops
 * @param {{ nodes: any[], relationships: any[] } | null} fallbackGraph
 * @returns {{ nodes, edges, by_distance, source: 'live'|'client' }}
 */
export async function fetchNeighbourhood(nodeId, hops = 2, fallbackGraph = null) {
  // 1. Try live endpoint
  try {
    const url = `${NEIGHBOURHOOD_API}?node=${encodeURIComponent(nodeId)}&hops=${hops}`
    const res = await fetchWithTimeout(url)
    if (res.ok) {
      const data = await res.json()
      if (data?.nodes?.length > 0) {
        return { ...data, source: 'live' }
      }
    }
  } catch (err) {
    if (err?.name !== 'AbortError') {
      console.warn('[graphApi] /api/graph/neighbourhood unreachable:', err?.message)
    }
  }

  // 2. Client-side BFS fallback
  if (fallbackGraph) {
    return clientSideNeighbourhood(nodeId, hops, fallbackGraph)
  }

  return { nodes: [], edges: [], by_distance: {}, source: 'client' }
}

// ---------------------------------------------------------------------------
// Client-side BFS (used when the neighbourhood endpoint is unreachable)
// ---------------------------------------------------------------------------

/**
 * BFS over the full graph to produce the same shape as the live endpoint.
 * Runs in O(V + E) which is fine at hackathon corpus scale.
 */
function clientSideNeighbourhood(startId, maxHops, graph) {
  const { nodes: allNodes, relationships: allEdges } = graph

  // Build adjacency list (undirected for traversal)
  const adj = {}
  for (const n of allNodes) adj[n.id] = []
  for (const e of allEdges) {
    adj[e.source]?.push({ neighbour: e.target, edge: e })
    adj[e.target]?.push({ neighbour: e.source, edge: e })
  }

  // BFS
  const distance = {}
  const queue = [[startId, 0]]
  distance[startId] = 0
  const visitedEdges = new Set()

  while (queue.length) {
    const [cur, d] = queue.shift()
    if (d >= maxHops) continue
    for (const { neighbour, edge } of (adj[cur] || [])) {
      if (distance[neighbour] === undefined) {
        distance[neighbour] = d + 1
        queue.push([neighbour, d + 1])
      }
      const eKey = [edge.source, edge.target, edge.type].join('|')
      visitedEdges.add(eKey)
    }
  }

  const nodeIds = new Set(Object.keys(distance))
  const resultNodes = allNodes
    .filter((n) => nodeIds.has(n.id))
    .map((n) => ({ ...n, distance: distance[n.id] }))

  const resultEdges = allEdges.filter((e) => {
    const key = [e.source, e.target, e.type].join('|')
    return visitedEdges.has(key) && nodeIds.has(e.source) && nodeIds.has(e.target)
  })

  // Build by_distance histogram
  const by_distance = {}
  for (const d of Object.values(distance)) {
    by_distance[String(d)] = (by_distance[String(d)] || 0) + 1
  }

  return { nodes: resultNodes, edges: resultEdges, by_distance, source: 'client' }
}

// ---------------------------------------------------------------------------
// NetworkX centrality (TOOLS.md row 32 — natural partner to hop traversal)
// ---------------------------------------------------------------------------

/**
 * Fetch NetworkX centrality scores for a set of node IDs.
 * Used to surface which nodes in a neighbourhood subgraph matter most.
 *
 * GET /api/graph/centrality?nodes=id1,id2,...
 * Returns { [nodeId]: { degree, betweenness, pagerank } }
 */
export async function fetchCentrality(nodeIds) {
  if (!nodeIds?.length) return {}
  try {
    const url = `/api/graph/centrality?nodes=${nodeIds.map(encodeURIComponent).join(',')}`
    const res = await fetchWithTimeout(url)
    if (res.ok) return await res.json()
  } catch (err) {
    console.warn('[graphApi] /api/graph/centrality unreachable:', err?.message)
  }
  return {}
}
