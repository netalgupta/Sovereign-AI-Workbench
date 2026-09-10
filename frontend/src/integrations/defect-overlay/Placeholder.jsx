import React, { useState } from 'react'
import { Scan, AlertTriangle, ShieldAlert } from 'lucide-react'
import { CANONICAL_DEFECT_SAMPLE } from './contract'

const SEVERITY_COLORS = {
  low: '#10b981',
  medium: '#f59e0b',
  high: '#ef4444',
  critical: '#dc2626',
}

/**
 * Placeholder for DefectOverlay component.
 * Owner: Sahil (FRONTEND.md §3.14)
 *
 * @param {import('./contract').DefectOverlayProps} props
 */
export default function Placeholder({
  imageUrl = CANONICAL_DEFECT_SAMPLE.imageUrl,
  detections = CANONICAL_DEFECT_SAMPLE.detections,
  selectedDetectionId = null,
  onSelectBox,
  findings = CANONICAL_DEFECT_SAMPLE.findings,
  showLabels = true,
}) {
  const [activeId, setActiveId] = useState(selectedDetectionId || detections[0]?.id)

  const handleBoxClick = (id) => {
    setActiveId(id)
    if (onSelectBox) onSelectBox(id)
  }

  return (
    <div
      className="my-3 rounded-xl border shadow-xs overflow-hidden text-xs"
      style={{
        background: 'var(--color-card-bg)',
        borderColor: 'var(--color-card-border)',
      }}
    >
      {/* Top Header & Integration Handoff Banner */}
      <div
        className="px-4 py-2.5 border-b flex flex-wrap items-center justify-between gap-2"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-2">
          <Scan size={15} style={{ color: 'var(--color-accent)' }} />
          <span className="font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
            YOLOv8 Defect &amp; Anomaly Overlay
          </span>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
            style={{
              background: 'var(--color-overlay)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
          >
            Integration pending — owned by Sahil
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
          <AlertTriangle size={12} className="text-amber-500" />
          <span>{detections.length} bounding boxes identified</span>
        </div>
      </div>

      {/* Main Image Overlay Area */}
      <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Canvas / SVG Overlay Container */}
        <div className="md:col-span-2 relative rounded-lg overflow-hidden border bg-zinc-950 flex items-center justify-center min-h-[260px]">
          <img
            src={imageUrl}
            alt="Refinery inspection target"
            className="w-full h-auto max-h-[380px] object-cover opacity-90"
          />

          {/* SVG Bounding Boxes Overlay */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none">
            {detections.map((det) => {
              const isSelected = det.id === activeId
              const color = SEVERITY_COLORS[det.severity || 'medium']
              // If normalized coordinates 0-1
              const x = `${det.box.xmin * 100}%`
              const y = `${det.box.ymin * 100}%`
              const width = `${(det.box.xmax - det.box.xmin) * 100}%`
              const height = `${(det.box.ymax - det.box.ymin) * 100}%`

              return (
                <g key={det.id}>
                  <rect
                    x={x}
                    y={y}
                    width={width}
                    height={height}
                    fill={isSelected ? `${color}25` : 'transparent'}
                    stroke={color}
                    strokeWidth={isSelected ? 3 : 1.8}
                    strokeDasharray={isSelected ? 'none' : '4 2'}
                  />
                </g>
              )
            })}
          </svg>

          {/* Interactive Click Targets & Pills */}
          {detections.map((det) => {
            const isSelected = det.id === activeId
            const color = SEVERITY_COLORS[det.severity || 'medium']
            return (
              <div
                key={det.id}
                onClick={() => handleBoxClick(det.id)}
                style={{
                  left: `${det.box.xmin * 100}%`,
                  top: `${det.box.ymin * 100}%`,
                  width: `${(det.box.xmax - det.box.xmin) * 100}%`,
                  height: `${(det.box.ymax - det.box.ymin) * 100}%`,
                }}
                className={`absolute cursor-pointer transition-all hover:bg-white/10 ${
                  isSelected ? 'ring-2 ring-white/80' : ''
                }`}
              >
                {showLabels && (
                  <div
                    className="absolute -top-6 left-0 px-2 py-0.5 rounded text-[10px] font-mono font-bold whitespace-nowrap shadow-sm"
                    style={{
                      background: color,
                      color: '#fff',
                    }}
                  >
                    {det.label} ({Math.round(det.confidence * 100)}%)
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Findings Side Panel */}
        <div
          className="rounded-lg border p-3 flex flex-col gap-2.5 overflow-y-auto"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
          }}
        >
          <div className="flex items-center gap-1.5 font-bold text-xs" style={{ color: 'var(--color-text)' }}>
            <ShieldAlert size={14} style={{ color: 'var(--color-accent)' }} />
            <span>Inspection Findings</span>
          </div>

          <div className="space-y-2">
            {findings.map((finding) => {
              const det = detections.find((d) => d.id === finding.detectionId)
              const isSelected = finding.detectionId === activeId
              const color = SEVERITY_COLORS[det?.severity || 'medium']

              return (
                <div
                  key={finding.id}
                  onClick={() => det && handleBoxClick(det.id)}
                  className="p-2.5 rounded-lg border cursor-pointer transition-colors text-xs"
                  style={{
                    background: isSelected ? 'var(--color-card-bg)' : 'transparent',
                    borderColor: isSelected ? color : 'var(--color-border)',
                    boxShadow: isSelected ? `0 0 0 1px ${color}` : 'none',
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-[11px]" style={{ color: color }}>
                      {det?.label || 'Defect'}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                      {Math.round((det?.confidence || 0.9) * 100)}% conf
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-text)' }}>
                    {finding.description}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
