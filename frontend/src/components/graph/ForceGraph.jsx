import { useEffect, useRef, useCallback } from 'react'

/**
 * ForceGraph — canvas force-directed graph for the Neo4j knowledge graph.
 *
 * Canvas rather than SVG deliberately: the graph is ~100 nodes and ~115
 * edges today and will grow with the corpus, and an SVG node-per-element
 * approach re-lays-out the DOM on every simulation tick. Canvas draws the
 * whole frame in one pass and stays smooth as the graph grows.
 *
 * No graph library. d3-force / cytoscape would each add a dependency that
 * has to be vendored onto an air-gapped venue machine (CLAUDE.md hard
 * constraint #1 — nothing may be fetched at runtime), for a spring/repulsion
 * simulation that is about forty lines. The tradeoff would be different for
 * a graph with thousands of nodes; it is not for this one.
 *
 * The simulation "cools": `heat` decays each tick so the layout settles
 * instead of jittering forever, and is re-heated on drag or when the caller
 * asks for a re-layout. A permanently animating canvas is both distracting
 * and a battery drain on a laptop running local models.
 */

import { getNodeColor, nodeName } from './graphTheme'

export function ForceGraph({
  nodes: rawNodes,
  relationships,
  height = 560,
  labelFilter = '',
  selectedId = null,
  onSelect,
  reheatToken = 0,
  focusId = null,
  // Hop-by-hop reveal: a Set<number> of distances that are currently visible.
  // Nodes whose `distance` property is NOT in this set are drawn at low opacity.
  // Pass `null` (default) to disable — all nodes fully visible (backward-compatible).
  revealByDistance = null,
  // Nodes to render with a bright highlight pulse (neighbourhood result set).
  // A Set<string> of node ids.
  highlightIds = null,
}) {
  const canvasRef = useRef(null)
  const stateRef = useRef({
    nodes: [], links: [], byId: {},
    zoom: 1, panX: 0, panY: 0, heat: 1,
    dragging: null, panning: null, hover: null,
  })

  const cssVar = useCallback((name) => {
    if (typeof window === 'undefined') return ''
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  }, [])

  // Build simulation bodies once per dataset. Positions start on a circle
  // rather than at random: a random cloud takes far longer to untangle, and
  // the first frame the user sees is the messiest one.
  useEffect(() => {
    const byId = {}
    const nodes = rawNodes.map((n, i) => {
      const angle = (i / rawNodes.length) * Math.PI * 2
      const body = {
        id: n.id,
        labels: n.labels,
        properties: n.properties,
        name: nodeName(n),
        x: Math.cos(angle) * 170 + (Math.random() - 0.5) * 40,
        y: Math.sin(angle) * 170 + (Math.random() - 0.5) * 40,
        vx: 0, vy: 0, degree: 0,
      }
      byId[n.id] = body
      return body
    })
    const links = relationships
      .map((r) => {
        const s = byId[r.source]
        const t = byId[r.target]
        if (!s || !t) return null
        s.degree += 1
        t.degree += 1
        return { s, t, type: r.type }
      })
      .filter(Boolean)

    stateRef.current = { ...stateRef.current, nodes, links, byId, heat: 1 }
  }, [rawNodes, relationships])

  useEffect(() => {
    stateRef.current.heat = 1
  }, [reheatToken])

  // Centre the viewport on a node the caller wants shown (search result).
  useEffect(() => {
    const st = stateRef.current
    const canvas = canvasRef.current
    if (!focusId || !canvas) return
    const target = st.byId[focusId]
    if (!target) return
    const w = canvas.width / devicePixelRatio
    const h = canvas.height / devicePixelRatio
    st.panX = w / 2 - target.x * st.zoom
    st.panY = h / 2 - target.y * st.zoom
  }, [focusId])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let raf = 0

    const resize = () => {
      const w = canvas.parentElement.clientWidth
      const h = canvas.parentElement.clientHeight || height
      if (!w || !h) return
      canvas.width = w * devicePixelRatio
      canvas.height = h * devicePixelRatio
      canvas.style.height = `${h}px`
    }
    resize()
    window.addEventListener('resize', resize)

    const visible = (n) => !labelFilter || n.labels.includes(labelFilter)
    const radius = (n) =>
      5 + Math.min(n.degree, 8) * 1.4 + (n.id === selectedId ? 2 : 0)

    // Hop-reveal: if revealByDistance is active, a node is "revealed" only when
    // its .distance is in the set. Unrevealed nodes render at low opacity so the
    // sequential unfold reads as an explanation rather than a simultaneous dump.
    const isRevealed = (n) => {
      if (!revealByDistance) return true
      return revealByDistance.has(n.distance ?? 0)
    }
    // Neighbourhood highlight: these nodes get a pulsing outer glow.
    const isHighlighted = (n) => !!(highlightIds?.has(n.id))

    const step = () => {
      const st = stateRef.current
      const w = canvas.width / devicePixelRatio
      const h = canvas.height / devicePixelRatio

      if (st.heat > 0 || st.dragging) {
        st.heat = Math.max(0, st.heat - 0.0016)
        const cx = w / 2
        const cy = h / 2
        for (const n of st.nodes) {
          if (n === st.dragging) continue
          n.vx += (cx - n.x) * 0.0016
          n.vy += (cy - n.y) * 0.0016
        }
        // O(n^2) repulsion is fine at this size and avoids a quadtree; the
        // 90000 cutoff skips pairs far enough apart to contribute nothing.
        for (let i = 0; i < st.nodes.length; i++) {
          for (let j = i + 1; j < st.nodes.length; j++) {
            const a = st.nodes[i]
            const b = st.nodes[j]
            let dx = b.x - a.x
            let dy = b.y - a.y
            let d2 = dx * dx + dy * dy
            if (d2 < 0.01) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 0.01 }
            if (d2 > 90000) continue
            const d = Math.sqrt(d2)
            const f = 900 / d2
            const ux = (dx / d) * f
            const uy = (dy / d) * f
            a.vx -= ux; a.vy -= uy; b.vx += ux; b.vy += uy
          }
        }
        for (const l of st.links) {
          const dx = l.t.x - l.s.x
          const dy = l.t.y - l.s.y
          const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
          const f = (d - 74) * 0.012
          const ux = (dx / d) * f
          const uy = (dy / d) * f
          l.s.vx += ux; l.s.vy += uy; l.t.vx -= ux; l.t.vy -= uy
        }
        for (const n of st.nodes) {
          if (n === st.dragging) { n.vx = 0; n.vy = 0; continue }
          n.vx *= 0.82; n.vy *= 0.82
          n.x += Math.max(-8, Math.min(8, n.vx))
          n.y += Math.max(-8, Math.min(8, n.vy))
          n.x = Math.max(16, Math.min(w - 16, n.x))
          n.y = Math.max(16, Math.min(h - 16, n.y))
        }
      }

      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
      ctx.clearRect(0, 0, w, h)
      ctx.translate(st.panX, st.panY)
      ctx.scale(st.zoom, st.zoom)

      const isDark =
        typeof document !== 'undefined' &&
        (document.documentElement.getAttribute('data-theme') === 'dark' ||
         document.documentElement.classList.contains('dark') ||
         (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches))

      const lineColor = cssVar('--color-border') || (isDark ? '#2B2520' : '#E5DFD7')
      const accent = cssVar('--color-accent') || (isDark ? '#D97757' : '#B5654A')

      // 1. Draw Links
      for (const l of st.links) {
        if (!visible(l.s) && !visible(l.t)) continue
        const isSelectedLink = selectedId && (l.s.id === selectedId || l.t.id === selectedId)
        const isHoveredLink = st.hover && (l.s.id === st.hover.id || l.t.id === st.hover.id)

        ctx.beginPath()
        ctx.moveTo(l.s.x, l.s.y)
        ctx.lineTo(l.t.x, l.t.y)

        if (isSelectedLink) {
          ctx.strokeStyle = accent
          ctx.lineWidth = 2.2
          ctx.globalAlpha = 0.95
        } else if (isHoveredLink) {
          ctx.strokeStyle = isDark ? '#F0EDE7' : '#2A2724'
          ctx.lineWidth = 1.6
          ctx.globalAlpha = 0.75
        } else if (selectedId || st.hover) {
          // Softly dim other links when an active node is selected or hovered
          ctx.strokeStyle = lineColor
          ctx.lineWidth = 0.8
          ctx.globalAlpha = 0.15
        } else {
          ctx.strokeStyle = lineColor
          ctx.lineWidth = 1
          ctx.globalAlpha = 0.45
        }
        ctx.stroke()
      }
      ctx.globalAlpha = 1

      // 2. Draw Nodes with vibrant category colors, subtle halos and crisp borders
      for (const n of st.nodes) {
        if (!visible(n)) continue
        const r = radius(n, st)
        const isSelected = n.id === selectedId
        const isHovered = n === st.hover
        const nodeCol = getNodeColor(n, cssVar)

        const isConnectedToActive =
          (selectedId &&
            st.links.some(
              (l) =>
                (l.s.id === selectedId && l.t.id === n.id) ||
                (l.t.id === selectedId && l.s.id === n.id)
            )) ||
          (st.hover &&
            st.links.some(
              (l) =>
                (l.s.id === st.hover.id && l.t.id === n.id) ||
                (l.t.id === st.hover.id && l.s.id === n.id)
            ))

        const shouldDim =
          (selectedId || st.hover) && !isSelected && !isHovered && !isConnectedToActive

        // Hop-reveal opacity: unrevealed nodes are ghost-dim so the reveal reads as sequential
        const revealed = isRevealed(n)
        const highlighted = isHighlighted(n)

        // Neighbourhood highlight glow ring (drawn before the node so it sits under it)
        if (highlighted && revealed) {
          ctx.beginPath()
          ctx.arc(n.x, n.y, r + 7, 0, Math.PI * 2)
          ctx.fillStyle = accent
          ctx.globalAlpha = 0.28
          ctx.fill()
        }

        // Outer glow/aura for selected or hovered nodes
        if (isSelected || isHovered) {
          ctx.beginPath()
          ctx.arc(n.x, n.y, r + (isSelected ? 5 : 3.5), 0, Math.PI * 2)
          ctx.fillStyle = nodeCol
          ctx.globalAlpha = shouldDim ? 0.08 : isSelected ? 0.35 : 0.22
          ctx.fill()
        }

        // Unrevealed nodes are rendered at very low opacity (ghost) so the hop
        // unfold animation reads as nodes "appearing" one hop at a time
        const baseAlpha = revealed ? (shouldDim ? 0.35 : 1) : 0.12
        ctx.globalAlpha = baseAlpha

        // Main node circle
        ctx.beginPath()
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx.fillStyle = nodeCol
        ctx.fill()

        // Crisp border for contrast and definition
        ctx.beginPath()
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        if (isSelected) {
          ctx.strokeStyle = '#FFFFFF'
          ctx.lineWidth = 2.4
          ctx.stroke()
        } else if (isHovered) {
          ctx.strokeStyle = '#FFFFFF'
          ctx.lineWidth = 1.8
          ctx.stroke()
        } else if (highlighted && revealed) {
          ctx.strokeStyle = accent
          ctx.lineWidth = 2
          ctx.stroke()
        } else {
          ctx.strokeStyle = isDark ? 'rgba(0, 0, 0, 0.45)' : 'rgba(255, 255, 255, 0.65)'
          ctx.lineWidth = 1.2
          ctx.stroke()
        }
      }
      ctx.globalAlpha = 1

      // 3. Draw Node Labels with modern typography and outline halos
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      for (const n of st.nodes) {
        if (!visible(n)) continue
        const isSelected = n.id === selectedId
        const isHovered = n === st.hover

        // Label hubs, selected, hovered, or when zoomed in
        if (n.degree >= 2 || isSelected || isHovered || st.zoom > 1.45) {
          const t = n.name.length > 20 ? `${n.name.slice(0, 19)}…` : n.name
          const r = radius(n, st)
          const textY = n.y - r - 4

          ctx.font =
            isSelected || isHovered
              ? '600 11px Inter, system-ui, -apple-system, sans-serif'
              : '500 10.5px Inter, system-ui, -apple-system, sans-serif'

          // Text halo for high readability against canvas lines and dark/light background
          ctx.strokeStyle = isDark ? 'rgba(20, 18, 15, 0.92)' : 'rgba(250, 247, 242, 0.92)'
          ctx.lineWidth = 3
          ctx.lineJoin = 'round'
          ctx.strokeText(t, n.x, textY)

          // Foreground text
          ctx.fillStyle =
            isSelected || isHovered
              ? isDark
                ? '#FFFFFF'
                : '#14120F'
              : isDark
              ? '#E2DFD8'
              : '#2A2724'
          ctx.fillText(t, n.x, textY)
        }
      }

      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)

    const toWorld = (sx, sy) => {
      const st = stateRef.current
      return [(sx - st.panX) / st.zoom, (sy - st.panY) / st.zoom]
    }
    const pick = (ev) => {
      const st = stateRef.current
      const r = canvas.getBoundingClientRect()
      const [x, y] = toWorld(ev.clientX - r.left, ev.clientY - r.top)
      let best = null
      let bd = Infinity
      for (const n of st.nodes) {
        if (!visible(n)) continue
        const d = (n.x - x) ** 2 + (n.y - y) ** 2
        if (d < bd && d < (radius(n, st) + 6) ** 2) { bd = d; best = n }
      }
      return best
    }

    const onDown = (e) => {
      const st = stateRef.current
      const hit = pick(e)
      canvas.setPointerCapture(e.pointerId)
      if (hit) {
        st.dragging = hit
        st.heat = Math.max(st.heat, 0.3)
        onSelect?.(hit)
      } else {
        st.panning = { x: e.clientX - st.panX, y: e.clientY - st.panY }
        canvas.style.cursor = 'grabbing'
      }
    }
    const onMove = (e) => {
      const st = stateRef.current
      const r = canvas.getBoundingClientRect()
      if (st.panning) {
        st.panX = e.clientX - st.panning.x
        st.panY = e.clientY - st.panning.y
        return
      }
      if (st.dragging) {
        const [x, y] = toWorld(e.clientX - r.left, e.clientY - r.top)
        st.dragging.x = x
        st.dragging.y = y
        return
      }
      st.hover = pick(e)
      canvas.style.cursor = st.hover ? 'pointer' : 'default'
    }
    const onUp = () => {
      const st = stateRef.current
      st.dragging = null
      st.panning = null
      canvas.style.cursor = 'default'
    }
    // Zoom anchored at the cursor: the world point under the pointer stays
    // under the pointer, which is what makes zooming feel like a map rather
    // than a slider.
    const onWheel = (e) => {
      e.preventDefault()
      const st = stateRef.current
      const r = canvas.getBoundingClientRect()
      const mx = e.clientX - r.left
      const my = e.clientY - r.top
      const [wx, wy] = toWorld(mx, my)
      st.zoom = Math.max(0.25, Math.min(5, st.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)))
      st.panX = mx - wx * st.zoom
      st.panY = my - wy * st.zoom
    }

    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerup', onUp)
    canvas.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', onUp)
      canvas.removeEventListener('wheel', onWheel)
    }
  }, [labelFilter, selectedId, onSelect, height, cssVar, revealByDistance, highlightIds])

  return <canvas ref={canvasRef} className="block w-full touch-none" style={{ height }} />
}
