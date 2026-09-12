import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import {
  Brain,
  Code2,
  Eye,
  Calculator,
  Search,
  CheckCircle2,
  Loader2,
  Clock,
  AlertCircle,
  ArrowUpRight,
} from 'lucide-react'

// Agent icon & color mappings
const AGENT_CONFIG = {
  reasoning: {
    label: 'REASONING',
    icon: Brain,
    color: 'var(--color-accent)',
  },
  code: {
    label: 'CODE',
    icon: Code2,
    color: 'var(--color-accent)',
  },
  vision: {
    label: 'VISION',
    icon: Eye,
    color: 'var(--color-accent)',
  },
  math: {
    label: 'MATH',
    icon: Calculator,
    color: 'var(--color-accent)',
  },
  retrieval: {
    label: 'RETRIEVAL',
    icon: Search,
    color: 'var(--color-accent)',
  },
}

const STATUS_CONFIG = {
  done: {
    label: 'Done',
    icon: CheckCircle2,
    borderColor: 'var(--color-success)',
    badgeBg: 'rgba(34, 197, 94, 0.12)',
    badgeText: 'var(--color-success)',
    pulse: false,
  },
  running: {
    label: 'Running',
    icon: Loader2,
    borderColor: 'var(--color-accent)',
    badgeBg: 'rgba(234, 88, 12, 0.14)',
    badgeText: 'var(--color-accent)',
    pulse: true,
  },
  pending: {
    label: 'Pending',
    icon: Clock,
    borderColor: 'var(--color-border)',
    badgeBg: 'var(--color-surface)',
    badgeText: 'var(--color-text-faint)',
    pulse: false,
  },
  failed: {
    label: 'Failed',
    icon: AlertCircle,
    borderColor: 'var(--color-danger, #ef4444)',
    badgeBg: 'rgba(239, 68, 68, 0.12)',
    badgeText: 'var(--color-danger, #ef4444)',
    pulse: false,
  },
}

function PlanNodeComponent({ data, selected }) {
  const agentKey = data.assigned_agent || 'reasoning'
  const agent = AGENT_CONFIG[agentKey] || AGENT_CONFIG.reasoning
  const AgentIcon = agent.icon

  const statusKey = data.status || 'pending'
  const status = STATUS_CONFIG[statusKey] || STATUS_CONFIG.pending
  const StatusIcon = status.icon

  const isRunning = statusKey === 'running'
  const isDone = statusKey === 'done'

  return (
    <div
      className={`group relative rounded-lg transition-all duration-200 cursor-pointer select-none ${
        isRunning ? 'ring-2 ring-offset-2 ring-offset-[var(--color-bg)] ring-[var(--color-accent)]' : ''
      }`}
      style={{
        width: 280,
        background: 'var(--color-surface)',
        border: `1.5px solid ${selected ? 'var(--color-accent)' : status.borderColor}`,
        boxShadow: isRunning
          ? '0 0 16px rgba(234, 88, 12, 0.22), var(--shadow-sm)'
          : isDone
          ? '0 0 12px rgba(34, 197, 94, 0.12), var(--shadow-xs)'
          : 'var(--shadow-xs)',
      }}
      title="Click to jump to this step in chat trace"
    >
      {/* Top Handle for dependency incoming edges */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !border-2 transition-transform hover:!scale-125"
        style={{
          background: status.borderColor,
          borderColor: 'var(--color-bg)',
          top: -6,
        }}
      />

      {/* Pulsing indicator aura for running status */}
      {isRunning && (
        <div
          className="absolute -inset-0.5 rounded-lg opacity-40 animate-pulse pointer-events-none"
          style={{ background: 'var(--color-accent)', filter: 'blur(4px)' }}
        />
      )}

      {/* Main Node Content Card */}
      <div className="relative p-3 flex flex-col gap-2">
        {/* Top Meta Row: Agent pill + Status Badge */}
        <div className="flex items-center justify-between gap-2">
          {/* Sub-agent Badge */}
          <div
            className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-semibold tracking-wider"
            style={{
              background: 'var(--color-overlay)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
            }}
          >
            <AgentIcon size={12} strokeWidth={2.2} style={{ color: agent.color }} />
            <span>{agent.label}</span>
          </div>

          {/* Status Badge */}
          <div
            className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium"
            style={{
              background: status.badgeBg,
              color: status.badgeText,
              border: `1px solid ${statusKey === 'pending' ? 'var(--color-border)' : 'transparent'}`,
            }}
          >
            <StatusIcon
              size={11}
              strokeWidth={2.4}
              className={isRunning ? 'animate-spin' : ''}
            />
            <span className="capitalize">{status.label}</span>
          </div>
        </div>

        {/* Step Description */}
        <div
          className="text-xs font-medium leading-snug line-clamp-2"
          style={{
            color: statusKey === 'pending' ? 'var(--color-text-muted)' : 'var(--color-text)',
          }}
        >
          {data.description}
        </div>

        {/* Node Footer / Interaction Hint */}
        <div
          className="pt-1 mt-0.5 border-t flex items-center justify-between text-[10px] font-mono transition-opacity"
          style={{
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-faint)',
          }}
        >
          <span className="truncate">{data.step_id || data.id}</span>
          <div className="flex items-center gap-0.5 group-hover:text-[var(--color-accent)] transition-colors">
            <span>Trace</span>
            <ArrowUpRight size={10} strokeWidth={2.2} />
          </div>
        </div>
      </div>

      {/* Bottom Handle for downstream dependencies */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !border-2 transition-transform hover:!scale-125"
        style={{
          background: status.borderColor,
          borderColor: 'var(--color-bg)',
          bottom: -6,
        }}
      />
    </div>
  )
}

export const PlanNode = memo(PlanNodeComponent)
