import { useMemo, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'
import { PlanNode } from './PlanNode'
import { showToast } from '../../store/toastStore'

const nodeTypes = {
  planStep: PlanNode,
}

const NODE_WIDTH = 280
const NODE_HEIGHT = 110

/**
 * Automatically layout nodes and edges Top-to-Bottom using dagre
 */
function getLayoutedElements(nodes, edges, direction = 'TB') {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 60,
    ranksep: 80,
    marginx: 32,
    marginy: 32,
  })

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    return {
      ...node,
      targetPosition: 'top',
      sourcePosition: 'bottom',
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}

export function PlanGraphView({ plan = [], onNodeClick }) {
  const navigate = useNavigate()

  // Build raw React Flow nodes & edges from the PlanStep array
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(() => {
    const rawNodes = plan.map((step) => ({
      id: step.id || step.step_id,
      type: 'planStep',
      data: {
        ...step,
      },
      position: { x: 0, y: 0 },
    }))

    const rawEdges = []
    plan.forEach((step) => {
      const targetId = step.id || step.step_id
      const isRunning = step.status === 'running'
      const isDone = step.status === 'done'

      if (Array.isArray(step.depends_on)) {
        step.depends_on.forEach((sourceId) => {
          rawEdges.push({
            id: `e-${sourceId}->${targetId}`,
            source: sourceId,
            target: targetId,
            type: 'smoothstep',
            animated: isRunning,
            style: {
              stroke: isRunning
                ? 'var(--color-accent)'
                : isDone
                ? 'var(--color-success)'
                : 'var(--color-border)',
              strokeWidth: 2,
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: isRunning
                ? 'var(--color-accent)'
                : isDone
                ? 'var(--color-success)'
                : 'var(--color-border)',
              width: 16,
              height: 16,
            },
          })
        })
      }
    })

    return getLayoutedElements(rawNodes, rawEdges, 'TB')
  }, [plan])

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges)

  useEffect(() => {
    setNodes(layoutedNodes)
    setEdges(layoutedEdges)
  }, [layoutedNodes, layoutedEdges, setNodes, setEdges])

  const handleNodeClick = useCallback(
    (event, node) => {
      const step = node.data
      const targetAnchorId = step.tool_call_event_id || step.step_id || step.id
      if (onNodeClick) {
        onNodeClick(step)
      } else {
        showToast(`Navigating to trace for: ${step.description.slice(0, 32)}...`, 'info')
        navigate(`/?scrollTo=${targetAnchorId}`)
      }
    },
    [navigate, onNodeClick]
  )

  const isDark = typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark'

  return (
    <div className="w-full h-full relative" style={{ background: 'var(--color-bg)' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.2}
        maxZoom={1.8}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color={isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)'}
          gap={20}
          size={1}
        />
        <Controls
          showInteractive={false}
          className="!border !shadow-sm !rounded-md"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
            fill: 'var(--color-text)',
          }}
        />
        <MiniMap
          nodeColor={(n) => {
            const status = n.data?.status
            if (status === 'done') return 'var(--color-success)'
            if (status === 'running') return 'var(--color-accent)'
            if (status === 'failed') return 'var(--color-danger, #ef4444)'
            return 'var(--color-border)'
          }}
          maskColor={isDark ? 'rgba(0, 0, 0, 0.6)' : 'rgba(255, 255, 255, 0.6)'}
          className="!border !shadow-sm !rounded-md !overflow-hidden"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
          }}
        />
      </ReactFlow>
    </div>
  )
}
